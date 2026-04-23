"""Single video fetcher."""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen

from fetch_base import BaseFetcher, VideoEntry


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
        cookies_file = self.config.get(platform, {}).get("cookies_file")
        if cookies_file and Path(cookies_file).exists():
            return cookies_file
        return None

    def fetch_url(self, url: str) -> list[VideoEntry]:
        entry, _ = self.fetch_url_with_raw(url)
        if entry:
            return [entry]
        return []

    def fetch_url_with_raw(self, url: str) -> tuple[Optional[VideoEntry], Optional[dict]]:
        """Fetch one video URL and keep raw metadata for bundle export."""
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

        if self.platform == "bilibili":
            return self.fetch_bilibili_with_api(url)

        return None, None

    def fetch_bilibili_with_api(self, url: str) -> tuple[Optional[VideoEntry], Optional[dict]]:
        bvid = self.extract_bvid(url)
        if not bvid:
            return None, None

        print("[Single] yt-dlp 失败，尝试 Bilibili 公开 API fallback")
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
            print(f"[Single] Bilibili API fallback 失败: {exc}")
            return None, None

        if payload.get("code") != 0:
            print(f"[Single] Bilibili API fallback 返回错误: {payload.get('message')}")
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
