"""YouTube 收藏夹/播放列表抓取器"""
import sys
from pathlib import Path
from fetch_base import BaseFetcher, VideoEntry

# 确保 scripts 目录在 Python 路径中
scripts_dir = Path(__file__).parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from logger_config import get_logger

logger = get_logger(__name__)


class YoutubeFetcher(BaseFetcher):
    """YouTube 收藏夹/播放列表抓取"""

    def __init__(self, config):
        # config 可能是 VideoCollectorConfig (Pydantic) 或 dict
        if hasattr(config, "youtube") and config.youtube:
            cookies_file = config.youtube.cookies_file
            playlist_id = config.youtube.playlist_id or ""
        elif isinstance(config, dict):
            cookies_file = config.get("youtube", {}).get("cookies_file")
            playlist_id = config.get("youtube", {}).get("playlist_id", "")
        else:
            cookies_file = None
            playlist_id = ""
        super().__init__(
            config=config,
            cookies_file=cookies_file,
        )
        self.playlist_id = playlist_id

    def fetch_favorites(self, use_cache: bool = False) -> list[VideoEntry]:
        """抓取 YouTube 播放列表"""
        if not self.playlist_id:
            logger.warning("未配置 playlist_id，跳过")
            return []
        
        if not self.cookies_file or not Path(self.cookies_file).exists():
            logger.error(f"Cookie 文件不存在: {self.cookies_file}，跳过")
            return []
        
        url = f"https://www.youtube.com/playlist?list={self.playlist_id}"
        logger.info(f"正在抓取播放列表: {url}")
        raw_data = self._run_yt_dlp(url, use_cache=use_cache)
        
        entries = []
        for item in raw_data:
            entry = self._video_to_entry(item)
            entry.platform = "youtube"
            # YouTube 上传日期格式是 YYYYMMDD，VideoEntry 需要确认字段
            entries.append(entry)
        
        logger.info(f"获取到 {len(entries)} 条视频")
        return entries
