"""B站收藏夹抓取器"""
import json
import re
from pathlib import Path
from fetch_base import BaseFetcher, VideoEntry


class BilibiliFetcher(BaseFetcher):
    """B站收藏夹抓取"""

    def __init__(self, config: dict):
        super().__init__(
            config=config,
            cookies_file=config.get("bilibili", {}).get("cookies_file"),
        )
        self.favorite_url = config.get("bilibili", {}).get("favorite_url", "")

    def fetch_favorites(self) -> list[VideoEntry]:
        """抓取B站收藏夹"""
        if not self.favorite_url:
            print("[Bilibili] 未配置 favorite_url，跳过")
            return []
        if "<" in self.favorite_url or ">" in self.favorite_url:
            print("[Bilibili] favorite_url 仍包含占位符，请先填写真实收藏夹 URL，跳过")
            return []

        if not self.cookies_file or not Path(self.cookies_file).exists():
            print(f"[Bilibili] Cookie 文件不存在: {self.cookies_file}，跳过")
            return []

        print(f"[Bilibili] 正在抓取收藏夹: {self.favorite_url}")
        raw_data = self._run_yt_dlp(self.favorite_url)

        entries = []
        for item in raw_data:
            entry = self._video_to_entry(item)
            entry.platform = "bilibili"
            entries.append(entry)

        print(f"[Bilibili] 获取到 {len(entries)} 条视频")
        return entries
