import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from transcribe import _audio_download_strategies, _build_audio_download_cmd


class AudioDownloadCommandTests(unittest.TestCase):
    def test_bilibili_strategies_include_412_fallbacks(self):
        strategies = _audio_download_strategies("https://www.bilibili.com/video/BV17xo9BsEnx/")
        names = [strategy["name"] for strategy in strategies]

        self.assertIn("bilibili-best-m4a", names)
        self.assertIn("bilibili-best-m4a-ipv4", names)
        self.assertIn("bilibili-known-audio-ids", names)
        self.assertIn("bilibili-low-bitrate", names)

    def test_audio_download_command_sends_browser_headers(self):
        cmd = _build_audio_download_cmd(
            "https://www.bilibili.com/video/BV17xo9BsEnx/",
            "audio.%(ext)s",
            format_selector="bestaudio[ext=m4a]/bestaudio/best",
            extra_args=["--force-ipv4"],
        )

        self.assertIn("--add-headers", cmd)
        self.assertIn("Referer:https://www.bilibili.com/", cmd)
        self.assertIn("Origin:https://www.bilibili.com", cmd)
        self.assertIn("--force-ipv4", cmd)
        self.assertIn("--retries", cmd)
        self.assertIn("--extractor-retries", cmd)


if __name__ == "__main__":
    unittest.main()
