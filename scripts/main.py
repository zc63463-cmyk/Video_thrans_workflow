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

# 最低 Python 版本
_MIN_PYTHON = (3, 10)

# 添加 scripts 目录到路径
sys.path.insert(0, str(SCRIPTS_DIR))

from logger_config import get_logger, RICH_AVAILABLE
from config_models import load_and_validate_config, VideoCollectorConfig
from exceptions import ConfigurationError, FetchError, TranscriptionError, BundleExportError
from sync import SyncEngine
from generate_notes import batch_generate

# 如果 rich 可用，导入相关组件
if RICH_AVAILABLE:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.box import ROUNDED
    from rich import print as rprint
    
    console = Console()
else:
    console = None
    ROUNDED = None

logger = get_logger(__name__)

def show_banner():
    """显示启动横幅"""
    if not console:
        return
    
    from rich.align import Align
    from rich.box import ROUNDED
    
    banner_text = Text()
    banner_text.append("Video Collector\n", style="bold cyan")
    banner_text.append("视频收藏 -> AI 输入包生成工具\n", style="dim")
    banner_text.append("支持 Bilibili / YouTube / 本地文件", style="green")
    
    panel = Panel(
        Align.center(banner_text),
        box=ROUNDED,
        border_style="blue",
        padding=(1, 2),
    )
    console.print(panel)
    console.print()


def show_config_status(config_path: Path, config: dict):
    """显示配置状态表格"""
    if not console:
        return
    
    table = Table(title="配置状态", box=ROUNDED, show_lines=True)
    table.add_column("配置项", style="cyan")
    table.add_column("状态", style="green")
    table.add_column("说明", style="dim")
    
    # 检查配置文件
    if config_path.exists():
        table.add_row("配置文件", "✅ 已加载", str(config_path))
    else:
        table.add_row("配置文件", "❌ 未找到", "将使用空配置")
    
    # 检查 cookies
    cookies_file = None
    for platform in ["bilibili", "youtube"]:
        platform_config = getattr(config, platform, None)
        if platform_config and hasattr(platform_config, "cookies_file") and platform_config.cookies_file:
            cookies_file = platform_config.cookies_file
            break
    if not cookies_file and isinstance(config, dict):
        for platform in ["bilibili", "youtube"]:
            platform_config = config.get(platform, {})
            if platform_config.get("cookies_file"):
                cookies_file = platform_config["cookies_file"]
                break
    
    if cookies_file and Path(cookies_file).exists():
        table.add_row("Cookies", "✅ 已配置", cookies_file)
    else:
        table.add_row("Cookies", "⚠️ 未配置", "公开视频可正常抓取")
    
    console.print(table)
    console.print()


def show_results_table(results: list, title: str = "处理结果"):
    """用表格展示处理结果"""
    if not console or not results:
        return
    
    table = Table(title=title, box=ROUNDED, show_lines=True)
    table.add_column("序号", style="dim", width=6)
    table.add_column("视频标题", style="cyan")
    table.add_column("状态", style="green", width=10)
    table.add_column("输出路径", style="dim")
    
    for idx, result in enumerate(results, 1):
        if result is None:
            table.add_row(str(idx), "处理失败", "❌", "-")
        else:
            path = str(result) if result else "-"
            table.add_row(str(idx), Path(path).name, "✅", path)
    
    console.print(table)
    console.print()


def show_interactive_menu() -> str | None:
    """显示交互式菜单，返回用户选择的操作"""
    if not console:
        return None
    
    from rich.prompt import Prompt, Confirm
    from rich.table import Table as MenuTable
    
    console.print("\n[bold cyan]请选择操作：[/bold cyan]")
    
    menu_table = MenuTable(box=ROUNDED, show_header=False, show_lines=True)
    menu_table.add_column("选项", style="bold green", width=8)
    menu_table.add_column("说明", style="white")
    
    menu_options = {
        "1": "导出 AI 输入包（单视频）",
        "2": "导出 AI 输入包（批量 URL）",
        "3": "处理本地音视频文件",
        "4": "同步收藏夹",
        "5": "重新生成笔记",
        "h": "显示帮助",
        "q": "退出",
    }
    
    for key, value in menu_options.items():
        menu_table.add_row(f"  {key}  ", value)
    
    console.print(menu_table)
    
    # 获取用户输入
    choice = Prompt.ask("\n请输入选项", choices=list(menu_options.keys()), default="1")
    
    return choice


def handle_interactive_mode():
    """处理交互式模式"""
    if not console:
        return None
    
    from rich.prompt import Prompt, Confirm
    
    choice = show_interactive_menu()
    
    if choice == "q":
        console.print("[yellow]再见！[/yellow]")
        return "quit"
    
    if choice == "h":
        show_help()
        return "help"
    
    # 根据用户选择，引导输入参数
    args_dict = {}
    
    if choice == "1":
        # 导出单视频 AI 输入包
        console.print("\n[bold]导出单视频 AI 输入包[/bold]")
        console.print("提示：可以直接粘贴视频链接，或按回车从剪贴板读取")
        
        url = Prompt.ask("视频链接（可选，直接回车从剪贴板读取）", default="")
        if url:
            args_dict["url"] = url
        
        if Confirm.ask("是否强制使用 Whisper 转录？", default=False):
            args_dict["transcribe"] = True
            model = Prompt.ask("Whisper 模型大小", choices=["tiny", "base", "small", "medium", "large-v3"], default="small")
            args_dict["whisper_model"] = model
            language = Prompt.ask("语言（zh/en/auto）", default="zh")
            args_dict["whisper_language"] = language if language != "auto" else None
        
        if Confirm.ask("是否启用缓存？", default=True):
            args_dict["use_cache"] = True
        
        args_dict["bundle"] = True
        
    elif choice == "2":
        # 导出批量 URL AI 输入包
        console.print("\n[bold]导出批量 URL AI 输入包[/bold]")
        
        url_file = Prompt.ask("URL 文件路径（每行一个 URL）")
        if not Path(url_file).exists():
            console.print(f"[red]文件不存在：{url_file}[/red]")
            return None
        args_dict["url_file"] = url_file
        
        workers = Prompt.ask("并发线程数", default="3")
        args_dict["workers"] = int(workers)
        
        if Confirm.ask("是否强制使用 Whisper 转录？", default=False):
            args_dict["transcribe"] = True
            model = Prompt.ask("Whisper 模型大小", choices=["tiny", "base", "small", "medium", "large-v3"], default="small")
            args_dict["whisper_model"] = model
        
        if Confirm.ask("是否启用缓存？", default=True):
            args_dict["use_cache"] = True
        
        args_dict["bundle"] = True
        
    elif choice == "3":
        # 处理本地音视频文件
        console.print("\n[bold]处理本地音视频文件[/bold]")
        
        media_file = Prompt.ask("音视频文件路径")
        if not Path(media_file).exists():
            console.print(f"[red]文件不存在：{media_file}[/red]")
            return None
        args_dict["media_file"] = media_file
        
        model = Prompt.ask("Whisper 模型大小", choices=["tiny", "base", "small", "medium", "large-v3"], default="small")
        args_dict["whisper_model"] = model
        language = Prompt.ask("语言（zh/en/auto）", default="zh")
        args_dict["whisper_language"] = language if language != "auto" else None
        
    elif choice == "4":
        # 同步收藏夹
        console.print("\n[bold]同步收藏夹[/bold]")
        
        platform = Prompt.ask("平台", choices=["bilibili", "youtube", "all"], default="all")
        args_dict["platform"] = platform
        
        if Confirm.ask("是否启用缓存？", default=True):
            args_dict["use_cache"] = True
        
    elif choice == "5":
        # 重新生成笔记
        args_dict["regenerate"] = True
    
    return args_dict


def show_help():
    """显示帮助信息"""
    if not console:
        return
    
    from rich.markdown import Markdown
    
    help_text = """
# Video Collector 使用帮助

## 主要功能

### 1. 导出 AI 输入包
将视频（Bilibili/YouTube/本地文件）转换为 AI 可处理的输入包：
- `metadata.json` - 视频元数据
- `transcript.txt` - 转录文本
- `prompt.md` - 给大模型的输入包

### 2. 同步收藏夹
同步 Bilibili/YouTube 收藏夹到本地数据库，并生成 Obsidian 笔记。

### 3. 处理本地文件
将本地音视频文件用 Whisper 转录，并导出 AI 输入包。

## 优化功能

- **并发处理**：批量处理多个视频，提高速度
- **缓存机制**：避免重复下载和 API 调用
- **Whisper 转录**：将视频语音转换为文字

## 命令行参数

运行 `python scripts/main.py --help` 查看所有参数。
"""
    
    console.print(Markdown(help_text))
    console.print()


def resolve_config_paths(config) -> dict:
    """将配置中的相对路径转为项目根目录下的绝对路径。"""
    # config 可能是 VideoCollectorConfig (Pydantic) 或 dict
    if hasattr(config, "model_dump"):
        # Pydantic 模型：转为 dict 处理路径后再返回原对象
        for platform in ("bilibili", "youtube"):
            platform_config = getattr(config, platform, None)
            if platform_config and hasattr(platform_config, "cookies_file") and platform_config.cookies_file:
                if not Path(platform_config.cookies_file).is_absolute():
                    platform_config.cookies_file = str(PROJECT_ROOT / platform_config.cookies_file)
        return config
    # 普通 dict
    for platform in ("bilibili", "youtube"):
        platform_config = config.get(platform, {})
        cookies_file = platform_config.get("cookies_file")
        if cookies_file and not Path(cookies_file).is_absolute():
            platform_config["cookies_file"] = str(PROJECT_ROOT / cookies_file)
    return config


def load_config(config_path: Path) -> VideoCollectorConfig:
    """加载并验证配置文件"""
    try:
        config = load_and_validate_config(str(config_path))
        return config
    except ConfigurationError as e:
        logger.error(str(e))
        logger.info("请复制 config/credentials.example.yaml 为 config/credentials.yaml 并填写配置")
        sys.exit(1)
    except Exception as e:
        logger.error(f"配置加载失败: {e}")
        sys.exit(1)


def load_optional_config(config_path: Path) -> VideoCollectorConfig | dict:
    """尽量加载配置文件；单视频模式下允许没有配置。"""
    if not config_path.exists():
        logger.warning("配置文件不存在，使用空配置")
        return {}
    try:
        return load_and_validate_config(str(config_path))
    except Exception as e:
        logger.warning(f"配置验证失败，使用原始配置: {e}")
        # 降级：返回原始 dict
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
    except Exception as e:
        logger.debug(f"读取剪贴板失败: {e}")
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


_PLATFORM_PATTERNS = {
    "bilibili": lambda u: "bilibili.com" in u or "b23.tv" in u,
    "youtube": lambda u: "youtube.com" in u or "youtu.be" in u,
}

def _is_supported_video_url(url: str) -> bool:
    """判断 URL 是否属于支持的视频平台。"""
    url_lower = url.lower()
    return any(p(url_lower) for p in _PLATFORM_PATTERNS.values())


def resolve_url_input(args) -> str | None:
    """解析单视频链接来源：命令参数 > 剪贴板 > 交互输入。"""
    raw_url = args.url or args.input_url
    if raw_url:
        extracted = extract_first_url(raw_url) or raw_url
        return normalize_video_url(extracted)

    clipboard_text = read_clipboard_text()
    extracted_url = extract_first_url(clipboard_text)
    candidate = normalize_video_url(extracted_url or clipboard_text) if (extracted_url or looks_like_url(clipboard_text)) else None
    if candidate:
        if _is_supported_video_url(candidate):
            logger.info(f"从剪贴板读取链接: {candidate}")
            return candidate
        else:
            logger.warning(f"剪贴板内容不是支持的视频平台链接，已忽略: {candidate[:60]}")

    return None


def sync_platform(platform: str, config: dict, args) -> list:
    """同步指定平台"""
    from fetch_bilibili import BilibiliFetcher
    from fetch_youtube import YoutubeFetcher

    fetchers = {
        "bilibili": BilibiliFetcher,
        "youtube": YoutubeFetcher,
    }

    fetcher_class = fetchers.get(platform)
    if not fetcher_class:
        logger.error(f"未知平台: {platform}")
        return []

    fetcher = fetcher_class(config)

    # 启用缓存
    if args.use_cache:
        fetcher.enable_cache()

    logger.info(f"同步 {platform.upper()}")
    entries = fetcher.fetch_favorites(use_cache=args.use_cache)
    return entries


def sync_url(url: str, config: dict, cookies_file: str | None, args) -> list:
    """同步单个视频链接"""
    from fetch_single import SingleVideoFetcher

    fetcher = SingleVideoFetcher(config=config, cookies_file=cookies_file)

    # 启用缓存
    if args.use_cache:
        fetcher.enable_cache()

    logger.info(f"抓取单视频: {url}")
    entries = fetcher.fetch_url(url, use_cache=args.use_cache)
    return entries


def export_url_bundle(
    url: str,
    config: dict,
    cookies_file: str | None,
    output_dir: str,
    args,
    whisper_config: dict | None = None,
    force_whisper: bool = False,
) -> Path | None:
    """导出单视频的 AI 输入包。"""
    from fetch_single import SingleVideoFetcher
    from export_bundle import export_bundle

    fetcher = SingleVideoFetcher(config=config, cookies_file=cookies_file)

    # 启用缓存
    if args.use_cache:
        fetcher.enable_cache()

    logger.info("导出 AI 输入包")
    entry, raw_data = fetcher.fetch_url_with_raw(url, use_cache=args.use_cache)
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

    logger.info("导出本地媒体 AI 输入包")
    return export_media_bundle(media_file, output_dir, whisper_config=whisper_config)


def build_whisper_config(config, args) -> dict:
    """构建 whisper 配置：命令行参数 > credentials.yaml。"""
    # config 可能是 VideoCollectorConfig (Pydantic 模型) 或 dict
    if hasattr(config, "whisper") and config.whisper:
        whisper_cfg = config.whisper.model_dump(exclude_none=True)
    elif isinstance(config, dict):
        whisper_cfg = dict(config.get("whisper", {}))
    else:
        whisper_cfg = {}
    if args.whisper_model:
        whisper_cfg["model"] = args.whisper_model
    if args.whisper_language:
        whisper_cfg["language"] = args.whisper_language
    if args.whisper_device:
        whisper_cfg["device"] = args.whisper_device
    return whisper_cfg


def check_python_version():
    """检查 Python 版本是否满足最低要求。"""
    if sys.version_info < _MIN_PYTHON:
        print(f"[ERROR] Python {_MIN_PYTHON[0]}.{_MIN_PYTHON[1]}+ required, "
              f"got {sys.version_info.major}.{sys.version_info.minor}")
        sys.exit(1)


def ensure_directories():
    """确保必要的输出目录存在。"""
    dirs = [
        PROJECT_ROOT / "output",
        PROJECT_ROOT / "output" / "bundles",
        PROJECT_ROOT / "output" / "notes",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def check_dependencies():
    """检查关键依赖是否已安装，返回缺失列表。"""
    missing = []
    # 必需依赖
    for pkg, import_name in [
        ("PyYAML", "yaml"),
        ("yt-dlp", "yt_dlp"),
        ("pydantic", "pydantic"),
        ("rich", "rich"),
        ("tqdm", "tqdm"),
    ]:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)
    return missing


def first_run_setup(config_path: Path):
    """首次运行引导：如果配置文件不存在，从模板复制。"""
    example_path = config_path.parent / "credentials.example.yaml"
    if not config_path.exists() and example_path.exists():
        if console:
            from rich.prompt import Confirm
            console.print("\n[yellow]未找到配置文件 config/credentials.yaml[/yellow]")
            console.print("公开视频不需要配置即可使用。收藏夹同步和需要登录的视频需要配置 cookies。")
            if Confirm.ask("是否从模板创建配置文件？", default=True):
                import shutil
                shutil.copy2(example_path, config_path)
                console.print(f"[green]已创建 {config_path}[/green]")
                console.print("[dim]请编辑该文件填写 cookies 路径和收藏夹 URL[/dim]\n")
        else:
            logger.info(f"未找到配置文件，可复制 {example_path} 为 {config_path}")


def main():
    # 启动自检
    check_python_version()

    missing_deps = check_dependencies()
    if missing_deps:
        print(f"[ERROR] Missing required packages: {', '.join(missing_deps)}")
        print(f"        Run: pip install -r requirements.txt")
        sys.exit(1)

    ensure_directories()
    # 显示启动横幅
    show_banner()
    
    # 检查是否需要进入交互式模式（无参数运行）
    if len(sys.argv) == 1 and console is not None:
        # 进入交互式模式
        while True:
            result = handle_interactive_mode()
            
            if result == "quit":
                return
            elif result == "help":
                # 显示帮助后继续循环
                continue
            elif result is None:
                # 出错，继续循环
                continue
            else:
                # 有有效输入，转换为 args 对象
                console.print("\n[bold green]开始处理...[/bold green]\n")
                
                # 创建命名空间对象模拟 args
                import types
                args = types.SimpleNamespace()
                
                # 设置默认值
                args.input_url = None
                args.platform = "all"
                args.regenerate = False
                args.output = str(PROJECT_ROOT / "output" / "notes")
                args.config = str(PROJECT_ROOT / "config" / "credentials.yaml")
                
                # 首次运行引导
                first_run_setup(Path(args.config))
                
                args.url = None
                args.cookies = None
                args.bundle = False
                args.media_file = None
                args.bundle_output = str(PROJECT_ROOT / "output" / "bundles")
                args.transcribe = False
                args.whisper_model = None
                args.whisper_language = None
                args.whisper_device = None
                args.url_file = None
                args.workers = 3
                args.use_cache = False
                
                # 用交互式输入覆盖默认值
                for key, value in result.items():
                    setattr(args, key, value)
                
                # 跳出循环，继续正常处理流程
                break
    
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
    # 批量处理和并发控制
    parser.add_argument(
        "--url-file",
        help="从文件读取多个 URL（每行一个）"
    )
    parser.add_argument(
        "--workers", "-j",
        type=int,
        default=3,
        help="并发处理线程数（默认: 3）"
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="启用缓存（避免重复下载和 API 调用）"
    )
    args = parser.parse_args()

    # 尝试加载配置并显示状态
    config_path = Path(args.config)
    first_run_setup(config_path)
    config = load_optional_config(config_path) if config_path.exists() else {}
    show_config_status(config_path, config)

    if args.regenerate:
        # 只从数据库重新生成笔记
        logger.info("从数据库重新生成笔记")
        engine = SyncEngine()
        entries = engine.get_all()
        logger.info(f"从数据库读取 {len(entries)} 条视频")
        paths = batch_generate(entries, args.output)
        logger.info(f"生成了 {len(paths)} 篇笔记到 {args.output}/")
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
            logger.error("本地媒体文件处理失败，请检查路径或 Whisper 配置")
            return
        logger.info(f"AI 输入包已导出到 {bundle_dir}")
        logger.info("你可以直接把 prompt.md 内容贴给 ChatGPT")
        return

    config_path = Path(args.config)
    resolved_url = resolve_url_input(args)

    if args.bundle:
        # 支持从文件读取多个 URL
        urls = []
        if args.url_file:
            url_file = Path(args.url_file)
            if not url_file.exists():
                logger.error(f"URL 文件不存在: {args.url_file}")
                sys.exit(1)
            with open(url_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        urls.append(line)
            logger.info(f"从文件读取了 {len(urls)} 个 URL")
        
        if not urls and resolved_url:
            urls = [resolved_url]
        
        if not urls:
            logger.error("导出 AI 输入包需要提供视频链接，或先把链接放到剪贴板")
            sys.exit(1)
        
        config = load_optional_config(config_path)
        whisper_cfg = build_whisper_config(config, args)
        
        # 单个 URL，直接处理
        if len(urls) == 1:
            bundle_dir = export_url_bundle(
                urls[0], config, args.cookies, args.bundle_output, args,
                whisper_config=whisper_cfg if whisper_cfg else None,
                force_whisper=args.transcribe,
            )
            if bundle_dir is None:
                logger.error("没有获取到任何视频，检查配置或Cookie是否有效")
                return
            
            # 用表格展示结果
            if console:
                show_results_table([bundle_dir], title="Bundle 导出结果")
            else:
                logger.info(f"AI 输入包已导出到 {bundle_dir}")
            
            logger.info("你可以直接把 prompt.md 内容贴给 ChatGPT")
            return
        
        # 多个 URL，使用并发处理
        from concurrent_processor import process_urls_concurrently
        
        logger.info(f"开始并发处理 {len(urls)} 个 URL，并发数: {args.workers}")
        
        # 定义包装函数，固定配置参数
        def process_single_url(url: str) -> Path | None:
            """处理单个 URL（使用固定的配置）"""
            return export_url_bundle(
                url, config, args.cookies, args.bundle_output, args,
                whisper_config=whisper_cfg if whisper_cfg else None,
                force_whisper=args.transcribe,
            )
        
        # 并发处理
        results = process_urls_concurrently(
            urls,
            process_single_url,
            max_workers=args.workers,
            show_progress=True
        )
        
        success_count = sum(1 for r in results if r is not None)
        logger.info(f"并发处理完成！成功: {success_count}/{len(urls)}")
        
        # 用表格展示结果
        show_results_table(results, title="Bundle 导出结果")
        
        logger.info(f"AI 输入包已导出到 {args.bundle_output}")
        logger.info("你可以直接把 prompt.md 内容贴给 ChatGPT")
        return

    if resolved_url:
        config = load_optional_config(config_path)
        all_entries = sync_url(resolved_url, config, args.cookies, args)
        
        # 单视频链接：默认也导出 AI 输入包
        if all_entries:
            whisper_cfg = build_whisper_config(config, args)
            bundle_dir = export_url_bundle(
                resolved_url, config, args.cookies, args.bundle_output, args,
                whisper_config=whisper_cfg if whisper_cfg else None,
                force_whisper=args.transcribe,
            )
            if bundle_dir and console:
                show_results_table([bundle_dir], title="AI 输入包导出结果")
            elif bundle_dir:
                logger.info(f"AI 输入包已导出到 {bundle_dir}")
    else:
        config = load_config(config_path)

        # 正常同步流程
        if args.platform == "all":
            platforms = ["bilibili", "youtube"]
        else:
            platforms = [args.platform]

        all_entries = []
        for p in platforms:
            entries = sync_platform(p, config, args)
            all_entries.extend(entries)

    if not all_entries:
        logger.error("没有获取到任何视频，检查配置或Cookie是否有效")
        return

    # 增量写入数据库
    engine = SyncEngine()
    new_entries, existing = engine.upsert(all_entries)

    if not new_entries:
        if resolved_url and existing:
            logger.info("视频已存在，重新生成对应笔记")
            logger.info(f"生成 {len(existing)} 篇笔记")
            paths = batch_generate(existing, args.output)
            logger.info(f"已重新生成 {len(paths)} 篇笔记到 {args.output}/")
            return
        logger.info("没有新视频，上次同步后没有新的收藏")
        return

    # 生成 Obsidian 笔记
    logger.info(f"生成 {len(new_entries)} 篇笔记")
    paths = batch_generate(new_entries, args.output)
    logger.info(f"完成！生成了 {len(paths)} 篇笔记到 {args.output}/")
    
    # 用表格展示生成的笔记
    if console and paths:
        notes_table = Table(title="生成的笔记", box=ROUNDED, show_lines=True)
        notes_table.add_column("序号", style="dim", width=6)
        notes_table.add_column("笔记标题", style="cyan")
        notes_table.add_column("输出路径", style="dim")
        
        for idx, path in enumerate(paths, 1):
            path_obj = Path(path)
            notes_table.add_row(str(idx), path_obj.stem, str(path_obj.parent))
        
        console.print(notes_table)
        console.print()
    else:
        logger.info("将 output/notes/ 下的 md 文件复制到 Obsidian Content 目录即可")


if __name__ == "__main__":
    main()
