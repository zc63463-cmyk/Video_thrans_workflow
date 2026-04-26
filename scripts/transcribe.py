"""
语音转文字模块：音频提取 + Whisper 转录
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from logger_config import get_logger

logger = get_logger(__name__)

# 导入模型池
try:
    from whisper_pool import get_whisper_model
    WHISPER_POOL_AVAILABLE = True
except ImportError:
    WHISPER_POOL_AVAILABLE = False
    logger.warning("whisper_pool 模块未找到，将使用传统方式加载模型")

# 国内访问 HuggingFace Hub 默认走镜像加速
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# 复用 fetch_base 的路径解析逻辑
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 检查 rich 是否可用（用于美化进度条）
try:
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
    RICH_PROGRESS_AVAILABLE = True
except ImportError:
    RICH_PROGRESS_AVAILABLE = False


# ---------------------------------------------------------------------------
# 音频提取
# ---------------------------------------------------------------------------

def _get_python_executable() -> str:
    """获取 Python 路径（Windows 完整路径）"""
    return sys.executable


def _build_audio_download_cmd(
    url: str,
    output_path: str,
    cookies_file: str | None = None,
) -> list[str]:
    """
    构建 yt-dlp 音频下载命令。
    
    优先下载纯音频流（不转码），避免依赖 ffmpeg。
    B站音频通常是 m4a 容器，直接下载即可。
    """
    cmd = [
        _get_python_executable(), "-m", "yt_dlp",
        # 直接下载最佳音频流，不转码（不需要 ffmpeg）
        "-f", "bestaudio[ext=m4a]/bestaudio/best",
        "--no-playlist",
        "--no-check-certificates",
        "--output", output_path,
    ]
    if cookies_file and Path(cookies_file).exists():
        cmd.extend(["--cookies", cookies_file])
    cmd.append(url)
    return cmd


def download_audio(
    url: str,
    cookies_file: str | None = None,
    temp_dir: str | None = None,
) -> tuple[str, str] | None:
    """
    用 yt-dlp 从视频 URL 提取音频流。
    
    Returns:
        (audio_path, temp_dir) - 音频文件路径和临时目录（调用方负责清理）
        None - 提取失败
    """
    if temp_dir:
        temp_path = Path(temp_dir)
    else:
        temp_path = Path(tempfile.mkdtemp(prefix="video_transcribe_"))

    output_template = str(temp_path / "audio.%(ext)s")

    cmd = _build_audio_download_cmd(url, output_template, cookies_file)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        if result.returncode != 0:
            logger.error(f"音频下载失败: {result.stderr[-300:]}")
            return None

        # 找生成的音频文件
        audio_files = list(temp_path.glob("audio.*"))
        if not audio_files:
            logger.error(f"音频文件未生成，yt-dlp 输出: {result.stdout[-200:]}")
            return None

        return str(audio_files[0]), str(temp_path)

    except subprocess.TimeoutExpired:
        logger.error("音频下载超时（10分钟）")
        return None
    except Exception as e:
        logger.error(f"音频下载异常: {e}")
        return None


# ---------------------------------------------------------------------------
# Whisper 转录
# ---------------------------------------------------------------------------

def _load_faster_whisper():
    """延迟导入 faster-whisper"""
    try:
        from faster_whisper import WhisperModel
        return WhisperModel
    except ImportError:
        return None


def _load_whisper():
    """延迟导入 openai-whisper"""
    try:
        import whisper
        return whisper
    except ImportError:
        return None


def transcribe_audio(
    audio_path: str,
    model: str = "base",
    language: str | None = None,
    device: str = "cpu",
    provider: str = "auto",
) -> tuple[str, list[dict], dict] | None:
    """
    用 Whisper 将音频转录为文字。
    
    Args:
        audio_path:  音频文件路径（支持 m4a/mp3/wav 等）
        model:       模型大小，tiny/base/small/medium/large-v3
        language:    目标语言，None=自动检测
        device:      cpu/cuda
        provider:    auto/faster-whisper/native
    
    Returns:
        (transcript_text, segments, info_dict) - 纯文本转录 + 分段 + 元信息
        None - 转录失败
    """
    provider = (provider or "auto").lower()

    transcript_module = None
    whisper_type = ""

    if provider in ("auto", "faster-whisper", "faster"):
        transcript_module = _load_faster_whisper()
        if transcript_module is not None:
            whisper_type = "faster-whisper"

    if transcript_module is None and provider in ("auto", "native", "openai-whisper", "whisper"):
        whisper_module = _load_whisper()
        if whisper_module is not None:
            transcript_module = whisper_module
            whisper_type = "openai-whisper"

    if transcript_module is None:
        logger.error("未安装可用的 Whisper 实现，请运行：")
        logger.info("  pip install faster-whisper")
        return None

    try:
        logger.info(f"加载模型: {model} ({whisper_type})...")

        # 使用模型池获取模型
        if WHISPER_POOL_AVAILABLE:
            whisper_model = get_whisper_model(
                model_name=model,
                device=device,
                model_type=whisper_type,
            )
        else:
            # 传统方式加载模型
            if whisper_type == "faster-whisper":
                compute_type = "int8" if device == "cpu" else "float16"
                whisper_model = transcript_module(
                    model,
                    device=device,
                    compute_type=compute_type,
                )
            else:
                whisper_model = transcript_module.load_model(model, device=device)

        # 转录并显示进度
        if whisper_type == "faster-whisper":
            # faster-whisper 支持进度回调
            import time
            
            # 获取音频时长（用于计算进度）
            try:
                import ffmpeg
                probe = ffmpeg.probe(audio_path)
                duration = float(probe['format']['duration'])
            except:
                duration = 0
            
            # 创建 rich 进度条或降级到 tqdm
            if RICH_PROGRESS_AVAILABLE:
                from rich.progress import Progress as RichProgress
                progress = RichProgress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    TimeRemainingColumn(),
                )
                pbar = progress
                task = progress.add_task("转录中...", total=100 if duration > 0 else None)
                last_progress = 0
                
                def progress_callback(current: int, total: int):
                    """faster-whisper 进度回调"""
                    if duration > 0:
                        progress_value = int((current / total) * 100)
                        progress.update(task, completed=progress_value)
            elif duration > 0:
                # 降级到 tqdm
                from tqdm import tqdm
                pbar = tqdm(total=100, desc="转录进度", unit="%")
                last_progress = 0
                
                def progress_callback(current: int, total: int):
                    """faster-whisper 进度回调"""
                    progress = int((current / total) * 100)
                    pbar.update(progress - last_progress)
                    return progress
            else:
                pbar = None
                progress_callback = None
            
            segments, info = whisper_model.transcribe(
                audio_path,
                language=language if language else None,
                beam_size=5,
                vad_filter=True,
                progress_callback=progress_callback if duration > 0 else None,
            )
            
            if RICH_PROGRESS_AVAILABLE and duration > 0:
                progress.stop()
            elif pbar is not None:
                pbar.close()
            
            transcript_parts = []
            segment_items = []
            for seg in segments:
                text = seg.text.strip()
                if not text:
                    continue
                transcript_parts.append(text)
                segment_items.append({
                    "start": float(seg.start),
                    "end": float(seg.end),
                    "text": text,
                })
            full_text = " ".join(transcript_parts)
            info_dict = {
                "language": info.language,
                "language_probability": info.language_probability,
                "model": model,
                "provider": "faster-whisper",
                "duration": info.duration,
            }
        else:
            # openai-whisper (native) - 不支持进度回调
            import time
            
            if RICH_PROGRESS_AVAILABLE:
                from rich.progress import Progress as RichProgress
                from rich.progress import SpinnerColumn, TextColumn
                
                logger.info("开始转录（openai-whisper 不支持详细进度显示）...")
                with RichProgress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                ) as progress:
                    task = progress.add_task("转录中（openai-whisper）...", total=None)
                    result = whisper_model.transcribe(
                        audio_path,
                        language=language if language else None,
                        fp16=(device == "cuda"),
                    )
                    progress.update(task, completed=100)
            else:
                # 降级到 tqdm
                from tqdm import tqdm
                
                logger.info("开始转录（openai-whisper 不支持进度显示）...")
                pbar = tqdm(total=None, desc="转录中", unit="seg")  # 未知总量进度条
                
                result = whisper_model.transcribe(
                    audio_path,
                    language=language if language else None,
                    fp16=(device == "cuda"),
                )
                
                pbar.close()
            
            full_text = result["text"].strip()
            segment_items = [
                {
                    "start": float(seg.get("start", 0)),
                    "end": float(seg.get("end", 0)),
                    "text": seg.get("text", "").strip(),
                }
                for seg in result.get("segments", [])
                if seg.get("text", "").strip()
            ]
            info_dict = {
                "language": result.get("language", "unknown"),
                "language_probability": 1.0,
                "model": model,
                "provider": "openai-whisper",
                "duration": result.get("duration", 0),
            }

        return full_text, segment_items, info_dict

    except Exception as e:
        logger.error(f"转录异常: {e}")
        return None


# ---------------------------------------------------------------------------
# 端到端：从 URL 到转录文本
# ---------------------------------------------------------------------------

def transcribe_from_url(
    url: str,
    cookies_file: str | None = None,
    config: dict | None = None,
    force: bool = False,
) -> tuple[str, list[dict], dict] | None:
    """
    完整流程：从视频 URL 下载音频 → Whisper 转录 → 返回文本
    
    Args:
        url:         视频 URL
        cookies_file: cookies 文件路径（用于 B站等需要登录的平台）
        config:      whisper 配置字典
        force:       强制转录（即使有字幕也转录）
    
    Returns:
        (transcript_text, segments, info_dict) - 纯文本转录 + 分段 + 元信息
        None - 转录失败
    """
    config = config or {}
    # config 可能是 VideoCollectorConfig (Pydantic) 或 dict
    if hasattr(config, "whisper") and config.whisper:
        whisper_cfg = config.whisper.model_dump(exclude_none=True)
    elif isinstance(config, dict) and "whisper" in config:
        whisper_cfg = config.get("whisper", {}) or {}
    else:
        whisper_cfg = config if isinstance(config, dict) else {}

    model = whisper_cfg.get("model", "small")
    language = whisper_cfg.get("language", "zh")   # None=自动检测
    device = whisper_cfg.get("device", "cpu")
    provider = whisper_cfg.get("provider", "auto")

    logger.info(f"开始语音转文字...")
    logger.info(f"  URL: {url}")
    logger.info(f"  模型: {model} | 语言: {language or '自动检测'} | 设备: {device}")

    result = download_audio(url, cookies_file)
    if result is None:
        return None

    audio_path, temp_dir = result

    try:
        transcript, segments, info = transcribe_audio(
            audio_path=audio_path,
            model=model,
            language=language if language and language.lower() not in ("null", "auto", "") else None,
            device=device,
            provider=provider,
        )
        return transcript, segments, info
    finally:
        # 清理临时音频文件
        try:
            Path(audio_path).unlink(missing_ok=True)
            Path(temp_dir).rmdir(missing_ok=True)
        except Exception as e:
            logger.debug(f"清理临时文件失败: {e}")


def transcribe_from_file(
    media_file: str,
    config: dict | None = None,
) -> tuple[str, list[dict], dict] | None:
    """从本地音频/视频文件转录。"""
    config = config or {}
    # config 可能是 VideoCollectorConfig (Pydantic) 或 dict
    if hasattr(config, "whisper") and config.whisper:
        whisper_cfg = config.whisper.model_dump(exclude_none=True)
    elif isinstance(config, dict) and "whisper" in config:
        whisper_cfg = config.get("whisper", {}) or {}
    else:
        whisper_cfg = config if isinstance(config, dict) else {}

    model = whisper_cfg.get("model", "small")
    language = whisper_cfg.get("language", "zh")
    device = whisper_cfg.get("device", "cpu")
    provider = whisper_cfg.get("provider", "auto")

    path = Path(media_file)
    if not path.exists():
        logger.error(f"本地媒体文件不存在: {path}")
        return None

    logger.info("开始本地文件语音转文字...")
    logger.info(f"  文件: {path}")
    logger.info(f"  模型: {model} | 语言: {language or '自动检测'} | 设备: {device}")

    return transcribe_audio(
        audio_path=str(path),
        model=model,
        language=language if language and language.lower() not in ("null", "auto", "") else None,
        device=device,
        provider=provider,
    )


# ---------------------------------------------------------------------------
# CLI 调试入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="语音转文字")
    parser.add_argument("url", help="视频链接")
    parser.add_argument("--cookies", help="cookies 文件路径")
    parser.add_argument("--model", default="base", help="模型大小 (tiny/base/small/medium/large-v3)")
    parser.add_argument("--language", default=None, help="语言代码，如 zh/en，None=自动检测")
    parser.add_argument("--device", default="cpu", help="cpu 或 cuda")
    args = parser.parse_args()

    result = transcribe_from_url(
        url=args.url,
        cookies_file=args.cookies,
        config={"whisper": {"model": args.model, "language": args.language, "device": args.device}},
    )

    if result:
        transcript, segments, info = result
        logger.info(f"\n=== 转录结果 ({info}) ===")
        logger.info(transcript)
    else:
        logger.error("转录失败")
