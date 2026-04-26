"""B站收藏夹抓取器"""
import json
import re
import sys
from pathlib import Path
from fetch_base import BaseFetcher, VideoEntry

# 确保 scripts 目录在 Python 路径中
scripts_dir = Path(__file__).parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from logger_config import get_logger

logger = get_logger(__name__)


class BilibiliFetcher(BaseFetcher):
    """B站收藏夹抓取"""

    def __init__(self, config):
        # config 可能是 VideoCollectorConfig (Pydantic) 或 dict
        if hasattr(config, "bilibili") and config.bilibili:
            cookies_file = config.bilibili.cookies_file
            favorite_url = config.bilibili.favorite_url or ""
        elif isinstance(config, dict):
            cookies_file = config.get("bilibili", {}).get("cookies_file")
            favorite_url = config.get("bilibili", {}).get("favorite_url", "")
        else:
            cookies_file = None
            favorite_url = ""
        super().__init__(
            config=config,
            cookies_file=cookies_file,
        )
        self.favorite_url = favorite_url

    def fetch_favorites(self, use_cache: bool = False) -> list[VideoEntry]:
        """抓取B站收藏夹"""
        if not self.favorite_url:
            logger.warning("未配置 favorite_url，跳过")
            return []
        if "<" in self.favorite_url or ">" in self.favorite_url:
            logger.warning("favorite_url 仍包含占位符，请先填写真实收藏夹 URL，跳过")
            return []
        
        if not self.cookies_file or not Path(self.cookies_file).exists():
            logger.error(f"Cookie 文件不存在: {self.cookies_file}，跳过")
            return []
        
        logger.info(f"正在抓取收藏夹: {self.favorite_url}")
        raw_data = self._run_yt_dlp(self.favorite_url, use_cache=use_cache)
        
        entries = []
        for item in raw_data:
            entry = self._video_to_entry(item)
            entry.platform = "bilibili"
            entries.append(entry)
        
        logger.info(f"获取到 {len(entries)} 条视频")
        return entries
