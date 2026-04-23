"""
语音转文字模块：音频提取 + Whisper 转录
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# 国内访问 HuggingFace Hub 默认走镜像加速
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# 复用 fetch_base 的路径解析逻辑
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))


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
        "--no-check-certificate",
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
            print(f"[Transcribe] 音频下载失败: {result.stderr[-300:]}")
            return None

        # 找生成的音频文件
        audio_files = list(temp_path.glob("audio.*"))
        if not audio_files:
            print(f"[Transcribe] 音频文件未生成，yt-dlp 输出: {result.stdout[-200:]}")
            return None

        return str(audio_files[0]), str(temp_path)

    except subprocess.TimeoutExpired:
        print("[Transcribe] 音频下载超时（10分钟）")
        return None
    except Exception as e:
        print(f"[Transcribe] 音频下载异常: {e}")
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
        print("[Transcribe] 未安装可用的 Whisper 实现，请运行：")
        print("  pip install faster-whisper")
        return None

    try:
        print(f"[Transcribe] 加载模型: {model} ({whisper_type})...")

        if whisper_type == "faster-whisper":
            # faster-whisper
            compute_type = "int8" if device == "cpu" else "float16"
            whisper_model = transcript_module(
                model,
                device=device,
                compute_type=compute_type,
            )
            segments, info = whisper_model.transcribe(
                audio_path,
                language=language if language else None,
                beam_size=5,
                vad_filter=True,
            )
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
            # openai-whisper (native)
            whisper_model = transcript_module.load_model(model, device=device)
            result = whisper_model.transcribe(
                audio_path,
                language=language if language else None,
                fp16=(device == "cuda"),
            )
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
        print(f"[Transcribe] 转录异常: {e}")
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
    if isinstance(config, dict) and "whisper" in config:
        whisper_cfg = config.get("whisper", {}) or {}
    else:
        whisper_cfg = config if isinstance(config, dict) else {}

    model = whisper_cfg.get("model", "small")
    language = whisper_cfg.get("language", "zh")   # None=自动检测
    device = whisper_cfg.get("device", "cpu")
    provider = whisper_cfg.get("provider", "auto")

    print(f"[Transcribe] 开始语音转文字...")
    print(f"[Transcribe]   URL: {url}")
    print(f"[Transcribe]   模型: {model} | 语言: {language or '自动检测'} | 设备: {device}")

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
        except Exception:
            pass


def transcribe_from_file(
    media_file: str,
    config: dict | None = None,
) -> tuple[str, list[dict], dict] | None:
    """从本地音频/视频文件转录。"""
    config = config or {}
    if isinstance(config, dict) and "whisper" in config:
        whisper_cfg = config.get("whisper", {}) or {}
    else:
        whisper_cfg = config if isinstance(config, dict) else {}

    model = whisper_cfg.get("model", "small")
    language = whisper_cfg.get("language", "zh")
    device = whisper_cfg.get("device", "cpu")
    provider = whisper_cfg.get("provider", "auto")

    path = Path(media_file)
    if not path.exists():
        print(f"[Transcribe] 本地媒体文件不存在: {path}")
        return None

    print("[Transcribe] 开始本地文件语音转文字...")
    print(f"[Transcribe]   文件: {path}")
    print(f"[Transcribe]   模型: {model} | 语言: {language or '自动检测'} | 设备: {device}")

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
        print(f"\n=== 转录结果 ({info}) ===")
        print(transcript)
    else:
        print("[ERROR] 转录失败")
