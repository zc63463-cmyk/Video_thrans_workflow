"""单视频抓取器：直接从视频链接抓取元数据"""
from pathlib import Path
from typing import Optional

from fetch_base import BaseFetcher, VideoEntry


class SingleVideoFetcher(BaseFetcher):
    """单视频抓取：适合直接给公开视频链接"""

    def __init__(self, config: dict, cookies_file: Optional[str] = None):
        super().__init__(config=config, cookies_file=cookies_file)
        self.platform = "unknown"

    def fetch_favorites(self) -> list[VideoEntry]:
        raise NotImplementedError("请使用 fetch_url() 抓取单视频")

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
        cookies_file = self.config.get(platform, {}).get("cookies_file")
        if cookies_file and Path(cookies_file).exists():
            return cookies_file
        return None

    def fetch_url(self, url: str) -> list[VideoEntry]:
        """抓取单个视频链接"""
        entry, _ = self.fetch_url_with_raw(url)
        if entry:
            return [entry]
        return []

    def fetch_url_with_raw(self, url: str) -> tuple[Optional[VideoEntry], Optional[dict]]:
        """抓取单个视频链接，并保留原始数据用于后续处理。"""
        self.platform = self.detect_platform(url)
        self.cookies_file = self.resolve_cookies_file(self.platform)

        if self.cookies_file:
            print(f"[Single] 使用 {self.platform} cookies: {self.cookies_file}")
        else:
            print("[Single] 未提供 cookies，将按公开视频方式抓取")

        raw_data = self._run_yt_dlp(url, flat_playlist=False, single_json=True)

        for item in raw_data:
            if item.get("_type") == "playlist":
                continue
            entry = self._video_to_entry(item)
            if self.platform != "unknown":
                entry.platform = self.platform
            return entry, item

        return None, None
