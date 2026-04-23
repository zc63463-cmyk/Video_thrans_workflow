"""YouTube 收藏夹/播放列表抓取器"""
from pathlib import Path
from fetch_base import BaseFetcher, VideoEntry


class YoutubeFetcher(BaseFetcher):
    """YouTube 收藏夹/播放列表抓取"""

    def __init__(self, config: dict):
        super().__init__(
            config=config,
            cookies_file=config.get("youtube", {}).get("cookies_file"),
        )
        self.playlist_id = config.get("youtube", {}).get("playlist_id", "")

    def fetch_favorites(self) -> list[VideoEntry]:
        """抓取 YouTube 播放列表"""
        if not self.playlist_id:
            print("[YouTube] 未配置 playlist_id，跳过")
            return []

        if not self.cookies_file or not Path(self.cookies_file).exists():
            print(f"[YouTube] Cookie 文件不存在: {self.cookies_file}，跳过")
            return []

        url = f"https://www.youtube.com/playlist?list={self.playlist_id}"
        print(f"[YouTube] 正在抓取播放列表: {url}")
        raw_data = self._run_yt_dlp(url)

        entries = []
        for item in raw_data:
            entry = self._video_to_entry(item)
            entry.platform = "youtube"
            # YouTube 上传日期格式是 YYYYMMDD，VideoEntry 需要确认字段
            entries.append(entry)

        print(f"[YouTube] 获取到 {len(entries)} 条视频")
        return entries
