"""Single video fetcher."""
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen

from fetch_base import BaseFetcher, VideoEntry

# 确保 scripts 目录在 Python 路径中
scripts_dir = Path(__file__).parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from logger_config import get_logger

logger = get_logger(__name__)


class SingleVideoFetcher(BaseFetcher):
    """Fetch metadata for a single video URL."""

    def __init__(self, config: dict, cookies_file: Optional[str] = None):
        super().__init__(config=config, cookies_file=cookies_file)
        self.platform = "unknown"

    def fetch_favorites(self) -> list[VideoEntry]:
        raise NotImplementedError("Use fetch_url() for single video metadata.")

    def detect_platform(self, url: str) -> str:
        url_lower = url.lower()
        if "bilibili.com" in url_lower or "b23.tv" in url_lower:
            return "bilibili"
        if "youtube.com" in url_lower or "youtu.be" in url_lower:
            return "youtube"
        return "unknown"

    def resolve_cookies_file(self, platform: str) -> Optional[str]:
        if self.cookies_file:
            return self.cookies_file
        # self.config 是 VideoCollectorConfig (Pydantic 模型)，不能用 .get()
        platform_config = getattr(self.config, platform, None)
        if platform_config and hasattr(platform_config, 'cookies_file'):
            cookies_file = platform_config.cookies_file
            if cookies_file and Path(cookies_file).exists():
                return cookies_file
        return None

    def fetch_url(self, url: str, use_cache: bool = False) -> list[VideoEntry]:
        entry, _ = self.fetch_url_with_raw(url, use_cache=use_cache)
        if entry:
            return [entry]
        return []

    def fetch_url_with_raw(self, url: str, use_cache: bool = False) -> tuple[Optional[VideoEntry], Optional[dict]]:
        """Fetch one video URL and keep raw metadata for bundle export."""
        self.platform = self.detect_platform(url)
        if self.platform == "unknown":
            logger.error(f"无法识别视频平台，不支持的 URL: {url}")
            logger.error("支持的平台: Bilibili (bilibili.com / b23.tv), YouTube (youtube.com / youtu.be)")
            return None, None
        self.cookies_file = self.resolve_cookies_file(self.platform)

        if self.cookies_file:
            logger.info(f"使用 {self.platform} cookies: {self.cookies_file}")
        else:
            logger.info("未提供 cookies，将按公开视频方式抓取")

        raw_data = self._run_yt_dlp(url, flat_playlist=False, single_json=True, use_cache=use_cache)

        for item in raw_data:
            if item.get("_type") == "playlist":
                continue
            entry = self._video_to_entry(item)
            if self.platform != "unknown":
                entry.platform = self.platform
            return entry, item

        if self.platform == "bilibili":
            return self.fetch_bilibili_with_api(url, use_cache=use_cache)

        return None, None

    def fetch_bilibili_with_api(self, url: str, use_cache: bool = False) -> tuple[Optional[VideoEntry], Optional[dict]]:
        bvid = self.extract_bvid(url)
        if not bvid:
            return None, None

        # 尝试从缓存获取
        if use_cache and self.cache is not None:
            cache_key = f"bilibili_api_{bvid}"
            cached_result = self.cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Bilibili API 缓存命中: {url[:50]}...")
                return cached_result

        logger.warning("yt-dlp 失败，尝试 Bilibili 公开 API fallback")
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.bilibili.com/",
        }
        try:
            request = Request(api_url, headers=headers)
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            logger.error(f"Bilibili API fallback 失败: {exc}")
            return None, None

        if payload.get("code") != 0:
            logger.error(f"Bilibili API fallback 返回错误: {payload.get('message')}")
            return None, None

        data = payload.get("data") or {}
        owner = data.get("owner") or {}
        stat = data.get("stat") or {}
        pages = data.get("pages") or []
        raw_data = {
            "id": data.get("bvid") or bvid,
            "webpage_url": f"https://www.bilibili.com/video/{data.get('bvid') or bvid}/",
            "title": data.get("title") or "",
            "uploader": owner.get("name") or "",
            "uploader_id": owner.get("mid"),
            "upload_date": self.format_pubdate(data.get("pubdate")),
            "duration": data.get("duration"),
            "description": data.get("desc") or "",
            "thumbnail": data.get("pic"),
            "view_count": stat.get("view"),
            "like_count": stat.get("like"),
            "comment_count": stat.get("reply"),
            "tags": [],
            "subtitles": {},
            "automatic_captions": {},
            "chapters": [],
            "cid": data.get("cid") or (pages[0].get("cid") if pages else None),
            "api_fallback": "bilibili_web_interface_view",
        }
        entry = self._video_to_entry(raw_data)
        entry.platform = "bilibili"
        
        # 保存结果到缓存
        if use_cache and self.cache is not None:
            cache_key = f"bilibili_api_{bvid}"
            self.cache.set(cache_key, (entry, raw_data))
        
        return entry, raw_data

    @staticmethod
    def extract_bvid(url: str) -> Optional[str]:
        match = re.search(r"(BV[0-9A-Za-z]+)", url)
        return match.group(1) if match else None

    @staticmethod
    def format_pubdate(value) -> Optional[str]:
        if not value:
            return None
        try:
            return datetime.fromtimestamp(int(value)).strftime("%Y%m%d")
        except (TypeError, ValueError, OSError):
            return None
