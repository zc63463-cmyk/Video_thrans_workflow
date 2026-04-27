"""基础抓取类，所有平台抓取器继承此类"""
import json
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# 确保 scripts 目录在 Python 路径中
scripts_dir = Path(__file__).parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from logger_config import get_logger
from cache_manager import CacheManager

logger = get_logger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class VideoEntry:
    """统一视频条目格式"""
    platform: str          # bilibili / youtube
    video_id: str          # 平台原始ID
    title: str             # 标题
    url: str               # 视频链接
    uploader: str          # 上传者
    published_date: Optional[str] = None   # 发布日期
    duration: Optional[str] = None        # 时长
    description: Optional[str] = None     # 简介/描述
    thumbnail: Optional[str] = None       # 封面URL
    tags: list[str] = None                # 标签
    collected_at: str = None              # 收藏时间（本次抓取时间）
    fetched_at: str = None                # 抓取时间

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.collected_at is None:
            self.collected_at = datetime.now().isoformat()
        if self.fetched_at is None:
            self.fetched_at = datetime.now().isoformat()


class BaseFetcher(ABC):
    """平台抓取器基类"""

    def __init__(self, config: dict, cookies_file: Optional[str] = None):
        self.config = config
        self.cookies_file = cookies_file
        self.platform = self.__class__.__name__.replace("Fetcher", "").lower()
        self.cache = None  # 缓存管理器实例（默认：无缓存）
        
    def enable_cache(self, cache_dir: str = None, ttl: int = 7 * 24 * 3600):
        """
        启用缓存
        
        Args:
            cache_dir: 缓存目录（默认：project_root/cache）
            ttl: 缓存过期时间（秒，默认：7天）
        """
        self.cache = CacheManager(cache_dir=cache_dir, ttl=ttl)
        logger.info(f"已启用缓存: {self.cache.cache_dir}")
        
    def _get_cache_key_for_yt_dlp(self, url: str, extra_args: list[str] = None) -> str:
        """
        生成 yt-dlp 调用的缓存键
        
        Args:
            url: 视频 URL
            extra_args: 额外的命令行参数
            
        Returns:
            缓存键字符串
        """
        key_parts = [url]
        if extra_args:
            key_parts.extend(extra_args)
        return "|".join(key_parts)

    def _build_yt_dlp_cmd(
        self,
        url: str,
        output_path: str,
        extra_args: list[str] = None,
        flat_playlist: bool = True,
        single_json: bool = False,
    ) -> list[str]:
        """构建 yt-dlp 命令"""
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--no-check-certificates",
            "--extractor-retries", "3",
            "--socket-timeout", "30",
            "--add-headers", f"User-Agent:{BROWSER_USER_AGENT}",
            "--add-headers", "Referer:https://www.bilibili.com/",
        ]
        if self.cookies_file and Path(self.cookies_file).exists():
            cmd.extend(["--cookies", self.cookies_file])
        if flat_playlist:
            cmd.append("--flat-playlist")   # 只获取列表，不下载视频
        if single_json:
            cmd.extend(["--dump-single-json", "--skip-download"])
        else:
            cmd.extend([
                "--print", "json",
                "--skip-download",
                "-o", output_path,
            ])
        if extra_args:
            cmd.extend(extra_args)
        cmd.append(url)
        return cmd

    def _run_yt_dlp(
        self,
        url: str,
        output_path: str = "%(id)s.%(ext)s",
        extra_args: list[str] = None,
        flat_playlist: bool = True,
        single_json: bool = False,
        use_cache: bool = False,
    ) -> list[dict]:
        """运行 yt-dlp，返回 JSON 解析后的视频信息"""
        # 尝试从缓存获取
        if use_cache and self.cache is not None:
            cache_key = self._get_cache_key_for_yt_dlp(url, extra_args)
            cached_result = self.cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"yt-dlp 缓存命中: {url[:50]}...")
                return cached_result
        
        cmd = self._build_yt_dlp_cmd(
            url,
            output_path,
            extra_args=extra_args,
            flat_playlist=flat_playlist,
            single_json=single_json,
        )
        for attempt in range(3):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8"
                )
                if result.returncode != 0:
                    if attempt < 2:
                        time.sleep(1)
                        continue
                    logger.error(f"[{self.platform}] yt-dlp error: {result.stderr[:200]}")
                    return []

                if single_json:
                    try:
                        data = json.loads(result.stdout)
                    except json.JSONDecodeError:
                        logger.error(f"[{self.platform}] yt-dlp returned invalid JSON")
                        return []
                    
                    # 保存结果到缓存
                    if use_cache and self.cache is not None:
                        cache_key = self._get_cache_key_for_yt_dlp(url, extra_args)
                        self.cache.set(cache_key, data if isinstance(data, list) else [data])
                    
                    if isinstance(data, dict) and isinstance(data.get("entries"), list):
                        return data["entries"]
                    return [data]

                videos = []
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        try:
                            videos.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                
                # 保存结果到缓存
                if use_cache and self.cache is not None:
                    cache_key = self._get_cache_key_for_yt_dlp(url, extra_args)
                    self.cache.set(cache_key, videos)
                
                return videos
            except Exception as e:
                if attempt < 2:
                    time.sleep(1)
                    continue
                logger.error(f"[{self.platform}] Failed: {e}")
                return []

        return []

    @abstractmethod
    def fetch_favorites(self) -> list[VideoEntry]:
        """抓取收藏夹，必须被子类实现"""
        pass

    def _video_to_entry(self, data: dict) -> VideoEntry:
        """将 yt-dlp 的原始数据转为 VideoEntry"""
        return VideoEntry(
            platform=self.platform,
            video_id=data.get("id", ""),
            title=data.get("title", "无标题"),
            url=data.get("webpage_url", data.get("url", "")),
            uploader=data.get("uploader", "未知"),
            published_date=data.get("upload_date"),  # YYYYMMDD 格式
            duration=data.get("duration"),           # 秒数
            description=data.get("description", ""),
            thumbnail=data.get("thumbnail"),
            tags=data.get("tags", []),
        )
