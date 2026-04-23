#!/usr/bin/env python3
"""
视频收藏同步主入口

用法:
    python scripts/main.py --platform bilibili  # 只同步 B 站
    python scripts/main.py --platform youtube   # 只同步 YouTube
    python scripts/main.py --platform all       # 同步所有平台
    python scripts/main.py --regenerate         # 从数据库重新生成所有笔记
"""
import argparse
import re
import sys
import yaml
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent

# 添加 scripts 目录到路径
sys.path.insert(0, str(SCRIPTS_DIR))

from sync import SyncEngine
from generate_notes import batch_generate


def resolve_config_paths(config: dict) -> dict:
    """将配置中的相对路径转为项目根目录下的绝对路径。"""
    for platform in ("bilibili", "youtube"):
        platform_config = config.get(platform, {})
        cookies_file = platform_config.get("cookies_file")
        if cookies_file and not Path(cookies_file).is_absolute():
            platform_config["cookies_file"] = str(PROJECT_ROOT / cookies_file)
    return config


def load_config(config_path: Path) -> dict:
    """加载配置文件"""
    if not config_path.exists():
        print(f"[ERROR] 配置文件不存在: {config_path}")
        print("请复制 config/credentials.example.yaml 为 config/credentials.yaml 并填写配置")
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        return resolve_config_paths(yaml.safe_load(f) or {})


def load_optional_config(config_path: Path) -> dict:
    """尽量加载配置文件；单视频模式下允许没有配置。"""
    if not config_path.exists():
        return {}
    with open(config_path, encoding="utf-8") as f:
        return resolve_config_paths(yaml.safe_load(f) or {})


def read_clipboard_text() -> str:
    """读取剪贴板文本。"""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        text = root.clipboard_get()
        root.destroy()
        return text.strip()
    except Exception:
        return ""


def looks_like_url(text: str) -> bool:
    """简单判断一段文本是否像 URL。"""
    if not text:
        return False
    parsed = urlparse(text.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def extract_first_url(text: str) -> str | None:
    """从分享文案中提取第一个 URL。"""
    if not text:
        return None
    match = re.search(r"https?://[^\s\"'<>]+", text)
    if match:
        return match.group(0).rstrip("，。,.!！)")
    return None


def normalize_video_url(url: str) -> str:
    """去掉常见追踪参数，保留视频标识参数。"""
    parsed = urlparse(url.strip())
    hostname = (parsed.netloc or "").lower()
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)

    keep_keys = None
    if "youtube.com" in hostname:
        keep_keys = {"v", "list", "index", "t"}
    elif "youtu.be" in hostname:
        keep_keys = {"t"}
    elif "bilibili.com" in hostname or "b23.tv" in hostname:
        keep_keys = {"p"}

    if keep_keys is None:
        filtered = query_pairs
    else:
        filtered = [(k, v) for k, v in query_pairs if k in keep_keys]

    clean_query = urlencode(filtered, doseq=True)
    return urlunparse(parsed._replace(query=clean_query, fragment=""))


def resolve_url_input(args) -> str | None:
    """解析单视频链接来源：命令参数 > 剪贴板 > 交互输入。"""
    raw_url = args.url or args.input_url
    if raw_url:
        extracted = extract_first_url(raw_url) or raw_url
        return normalize_video_url(extracted)

    clipboard_text = read_clipboard_text()
    extracted_url = extract_first_url(clipboard_text)
    if extracted_url or looks_like_url(clipboard_text):
        clean_url = normalize_video_url(extracted_url or clipboard_text)
        print(f"[Input] 从剪贴板读取链接: {clean_url}")
        return clean_url

    return None


def sync_platform(platform: str, config: dict) -> list:
    """同步指定平台"""
    from fetch_bilibili import BilibiliFetcher
    from fetch_youtube import YoutubeFetcher

    fetchers = {
        "bilibili": BilibiliFetcher,
        "youtube": YoutubeFetcher,
    }

    fetcher_class = fetchers.get(platform)
    if not fetcher_class:
        print(f"[ERROR] 未知平台: {platform}")
        return []

    fetcher = fetcher_class(config)
    print(f"\n[=== 同步 {platform.upper()} ===]")
    entries = fetcher.fetch_favorites()
    return entries


def sync_url(url: str, config: dict, cookies_file: str | None = None) -> list:
    """同步单个视频链接"""
    from fetch_single import SingleVideoFetcher

    fetcher = SingleVideoFetcher(config=config, cookies_file=cookies_file)
    print(f"\n[=== 抓取单视频 ===]")
    entries = fetcher.fetch_url(url)
    return entries


def export_url_bundle(
    url: str,
    config: dict,
    cookies_file: str | None,
    output_dir: str,
    whisper_config: dict | None = None,
    force_whisper: bool = False,
) -> Path | None:
    """导出单视频的 AI 输入包。"""
    from fetch_single import SingleVideoFetcher
    from export_bundle import export_bundle

    fetcher = SingleVideoFetcher(config=config, cookies_file=cookies_file)
    print(f"\n[=== 导出 AI 输入包 ===]")
    entry, raw_data = fetcher.fetch_url_with_raw(url)
    if not entry or not raw_data:
        return None
    bundle_dir = export_bundle(
        entry, raw_data, output_dir,
        cookies_file=fetcher.cookies_file,
        whisper_config=whisper_config,
        force_whisper=force_whisper,
    )
    return bundle_dir


def export_local_media_bundle(
    media_file: str,
    output_dir: str,
    whisper_config: dict | None = None,
) -> Path | None:
    """导出本地媒体文件的 AI 输入包。"""
    from export_bundle import export_media_bundle

    print("\n[=== 导出本地媒体 AI 输入包 ===]")
    return export_media_bundle(media_file, output_dir, whisper_config=whisper_config)


def build_whisper_config(config: dict, args) -> dict:
    """构建 whisper 配置：命令行参数 > credentials.yaml。"""
    whisper_cfg = dict(config.get("whisper", {}))
    if args.whisper_model:
        whisper_cfg["model"] = args.whisper_model
    if args.whisper_language:
        whisper_cfg["language"] = args.whisper_language
    if args.whisper_device:
        whisper_cfg["device"] = args.whisper_device
    return whisper_cfg


def main():
    parser = argparse.ArgumentParser(description="视频收藏 → Obsidian 笔记同步")
    parser.add_argument(
        "input_url",
        nargs="?",
        help="单视频链接。也可以省略参数，直接从剪贴板读取"
    )
    parser.add_argument(
        "--platform", "-p",
        default="all",
        choices=["bilibili", "youtube", "all"],
        help="指定要同步的平台"
    )
    parser.add_argument(
        "--regenerate", "-r",
        action="store_true",
        help="从数据库重新生成所有笔记（不重新抓取）"
    )
    parser.add_argument(
        "--output", "-o",
        default=str(PROJECT_ROOT / "output" / "notes"),
        help="笔记输出目录"
    )
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "config" / "credentials.yaml"),
        help="配置文件路径"
    )
    parser.add_argument(
        "--url",
        help="单视频链接，适合 B 站/YouTube 的公开视频"
    )
    parser.add_argument(
        "--cookies",
        help="单视频模式下手动指定 cookies 文件路径"
    )
    parser.add_argument(
        "--bundle",
        action="store_true",
        help="为单视频导出 AI 输入包（metadata/source/transcript/prompt）"
    )
    parser.add_argument(
        "--media-file",
        help="本地音频/视频文件路径，用 Whisper 转录并导出 AI 输入包"
    )
    parser.add_argument(
        "--bundle-output",
        default=str(PROJECT_ROOT / "output" / "bundles"),
        help="AI 输入包输出目录"
    )
    parser.add_argument(
        "--transcribe",
        action="store_true",
        help="使用 Whisper 语音转文字（即使有字幕也强制转录）"
    )
    parser.add_argument(
        "--whisper-model",
        default=None,
        help="Whisper 模型大小：tiny/base/small/medium/large-v3"
    )
    parser.add_argument(
        "--whisper-language",
        default=None,
        help="Whisper 目标语言，如 zh/en/ja，None=自动检测"
    )
    parser.add_argument(
        "--whisper-device",
        default=None,
        choices=["cpu", "cuda"],
        help="Whisper 运行设备：cpu 或 cuda"
    )
    args = parser.parse_args()

    if args.regenerate:
        # 只从数据库重新生成笔记
        print("\n[=== 从数据库重新生成笔记 ===]")
        engine = SyncEngine()
        entries = engine.get_all()
        print(f"从数据库读取 {len(entries)} 条视频")
        paths = batch_generate(entries, args.output)
        print(f"\n[OK] 生成了 {len(paths)} 篇笔记到 {args.output}/")
        return

    if args.media_file:
        config_path = Path(args.config)
        config = load_optional_config(config_path)
        whisper_cfg = build_whisper_config(config, args)
        bundle_dir = export_local_media_bundle(
            args.media_file,
            args.bundle_output,
            whisper_config=whisper_cfg if whisper_cfg else None,
        )
        if bundle_dir is None:
            print("\n本地媒体文件处理失败，请检查路径或 Whisper 配置")
            return
        print(f"\n[OK] AI 输入包已导出到 {bundle_dir}")
        print("   你可以直接把 prompt.md 内容贴给 ChatGPT")
        return

    config_path = Path(args.config)
    resolved_url = resolve_url_input(args)

    if args.bundle:
        if not resolved_url:
            print("[ERROR] 导出 AI 输入包需要提供视频链接，或先把链接放到剪贴板")
            sys.exit(1)
        config = load_optional_config(config_path)
        whisper_cfg = build_whisper_config(config, args)

        bundle_dir = export_url_bundle(
            resolved_url, config, args.cookies, args.bundle_output,
            whisper_config=whisper_cfg if whisper_cfg else None,
            force_whisper=args.transcribe,
        )
        if bundle_dir is None:
            print("\n没有获取到任何视频，检查配置或Cookie是否有效")
            return
        print(f"\n[OK] AI 输入包已导出到 {bundle_dir}")
        print("   你可以直接把 prompt.md 内容贴给 ChatGPT")
        return

    if resolved_url:
        config = load_optional_config(config_path)
        all_entries = sync_url(resolved_url, config, args.cookies)
    else:
        config = load_config(config_path)

        # 正常同步流程
        if args.platform == "all":
            platforms = ["bilibili", "youtube"]
        else:
            platforms = [args.platform]

        all_entries = []
        for p in platforms:
            entries = sync_platform(p, config)
            all_entries.extend(entries)

    if not all_entries:
        print("\n没有获取到任何视频，检查配置或Cookie是否有效")
        return

    # 增量写入数据库
    engine = SyncEngine()
    new_entries, existing = engine.upsert(all_entries)

    if not new_entries:
        if resolved_url and existing:
            print("\n视频已存在，重新生成对应笔记")
            print(f"\n[=== 生成 {len(existing)} 篇笔记 ===]")
            paths = batch_generate(existing, args.output)
            print(f"\n[OK] 已重新生成 {len(paths)} 篇笔记到 {args.output}/")
            return
        print("\n没有新视频，上次同步后没有新的收藏")
        return

    # 生成 Obsidian 笔记
    print(f"\n[=== 生成 {len(new_entries)} 篇笔记 ===]")
    paths = batch_generate(new_entries, args.output)
    print(f"\n[OK] 完成！生成了 {len(paths)} 篇笔记到 {args.output}/")
    print("   将 output/notes/ 下的 md 文件复制到 Obsidian Content 目录即可")


if __name__ == "__main__":
    main()
