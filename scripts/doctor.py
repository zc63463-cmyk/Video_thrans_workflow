#!/usr/bin/env python3
"""Environment and media download diagnostics for Video Collector."""
import argparse
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config_models import load_and_validate_config
from transcribe import download_audio


def status(ok: bool) -> str:
    return "[OK]" if ok else "[FAIL]"


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def check_command(command: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except Exception as exc:
        return False, str(exc)
    output = (result.stdout or result.stderr).strip()
    return result.returncode == 0, output.splitlines()[0] if output else ""


def resolve_bilibili_cookies(config_path: Path, override: str | None) -> str | None:
    if override:
        return override
    if not config_path.exists():
        return None
    config = load_and_validate_config(str(config_path))
    if config.bilibili and config.bilibili.cookies_file:
        return config.bilibili.cookies_file
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Video Collector runtime and Bilibili audio download.")
    parser.add_argument("url", nargs="?", help="Optional video URL for an audio download smoke test.")
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "config" / "credentials.yaml"),
        help="Path to credentials.yaml.",
    )
    parser.add_argument("--cookies", help="Override cookies file for the audio test.")
    args = parser.parse_args()

    checks = [
        ("Python >= 3.10", sys.version_info >= (3, 10), sys.version.split()[0]),
        ("PyYAML", has_module("yaml"), ""),
        ("yt-dlp module", has_module("yt_dlp"), ""),
        ("pydantic", has_module("pydantic"), ""),
        ("rich", has_module("rich"), ""),
        ("faster-whisper", has_module("faster_whisper"), "optional; required for --transcribe"),
    ]

    yt_dlp_ok, yt_dlp_version = check_command([sys.executable, "-m", "yt_dlp", "--version"])
    checks.append(("yt-dlp executable", yt_dlp_ok, yt_dlp_version))

    for name, ok, detail in checks:
        print(f"{status(ok)} {name}" + (f" - {detail}" if detail else ""))

    config_path = Path(args.config)
    cookies_file = resolve_bilibili_cookies(config_path, args.cookies)
    if cookies_file:
        cookies_path = Path(cookies_file)
        print(f"{status(cookies_path.exists())} Bilibili cookies - {cookies_path}")
    else:
        print("[WARN] Bilibili cookies - not configured")

    if not args.url:
        return 0 if all(ok for _, ok, _ in checks[:5]) and yt_dlp_ok else 1

    print(f"[INFO] Audio smoke test: {args.url}")
    result = download_audio(args.url, cookies_file=cookies_file)
    if result is None:
        print("[FAIL] Audio download smoke test")
        return 2

    audio_path, temp_dir = result
    size = Path(audio_path).stat().st_size
    print(f"[OK] Audio download smoke test - {Path(audio_path).name}, {size} bytes")
    shutil.rmtree(temp_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
