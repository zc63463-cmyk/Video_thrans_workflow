"""Export LLM-ready bundles: metadata/source/transcript/prompt."""
import json
import re
import shutil
from collections import Counter
from html import unescape
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from logger_config import get_logger
from fetch_base import VideoEntry
from transcribe import transcribe_from_file, transcribe_from_url

logger = get_logger(__name__)


LANGUAGE_PRIORITY = [
    "zh-Hans", "zh-CN", "zh", "zh-Hant", "zh-TW",
    "en", "en-US", "en-GB",
]

SUBTITLE_EXT_PRIORITY = ["json3", "json", "srv3", "srv2", "srv1", "vtt", "srt", "ttml"]
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPT_TEMPLATE_PATH = PROJECT_ROOT / "templates" / "prompt.md"
ASCII_STOPWORDS = {
    "about", "after", "before", "bilibili", "channel", "episode", "from", "have",
    "into", "just", "more", "part", "that", "their", "there", "these", "they",
    "this", "video", "what", "when", "where", "which", "with", "would", "youtube",
}
CJK_STOPWORDS = {
    "大家", "今天", "我们", "你们", "视频", "内容", "分享", "系列", "教程", "讲解",
    "解析", "精选", "速递", "同传", "频道", "合集", "完整", "一起", "一下", "什么",
    "为什么", "如何", "真的", "就是", "一个", "这个", "那个", "这里", "那里",
}


def slugify(text: str, max_len: int = 80) -> str:
    safe = re.sub(r'[<>:"/\\|?*]', "", text).strip()
    safe = re.sub(r"\s+", " ", safe)
    return safe[:max_len].strip() or "untitled"


def format_duration(seconds) -> str:
    if seconds is None:
        return "未知"
    total = int(float(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_timestamp(seconds) -> str:
    if seconds is None:
        return "00:00"
    total = int(float(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_date(date_str) -> str:
    if date_str and len(str(date_str)) == 8:
        text = str(date_str)
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return date_str or "未知"


def _is_transcript_usable(transcript: str, duration: float | int | None) -> bool:
    if not transcript or len(transcript.strip()) < 200:
        return False
    try:
        duration_value = float(duration or 0)
    except (TypeError, ValueError):
        duration_value = 0
    if duration_value > 0 and len(transcript) < duration_value * 2:
        return False
    return True


def _extract_reference_terms(text: str) -> list[str]:
    terms = []
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text or ""):
        token = word.lower()
        if token not in ASCII_STOPWORDS:
            terms.append(token)
    for word in re.findall(r"[\u4e00-\u9fff]{2,12}", text or ""):
        if word not in CJK_STOPWORDS:
            terms.append(word)
    return terms


def _build_reference_terms(entry: VideoEntry, raw_data: dict) -> list[str]:
    counts = Counter()
    sources = []
    sources.extend([entry.title] * 3)
    sources.extend((entry.tags or []) * 2)
    sources.extend(raw_data.get("categories") or [])
    for chapter in raw_data.get("chapters") or []:
        if chapter.get("title"):
            sources.append(chapter["title"])
    description = clean_text(entry.description or "")[:400]
    if description:
        sources.append(description)

    for source in sources:
        counts.update(_extract_reference_terms(source))

    return [term for term, _ in counts.most_common(24)]


def _transcript_matches_context(entry: VideoEntry, raw_data: dict, transcript: str) -> tuple[bool, list[str]]:
    reference_terms = _build_reference_terms(entry, raw_data)
    if len(reference_terms) < 3:
        return True, []
    
    transcript_text = clean_text(transcript)
    transcript_lower = transcript_text.lower()
    hits = []
    for term in reference_terms:
        if term.isascii():
            if re.search(rf"\b{re.escape(term)}\b", transcript_lower):
                hits.append(term)
        elif term in transcript_text:
            hits.append(term)

    return bool(hits), hits[:8]


def clean_text(text: str) -> str:
    cleaned = unescape(text or "")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def extract_links(text: str) -> list[str]:
    return re.findall(r"https?://[^\s)>\]]+", text or "")


def fetch_url_text(url: str, encoding: str | None = None) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        raw_data = response.read()
        if encoding:
            return raw_data.decode(encoding, errors="replace")
        if raw_data.startswith(b"\xff\xfe"):
            return raw_data.decode("utf-16-le", errors="replace")
        if raw_data.startswith(b"\xfe\xff"):
            return raw_data.decode("utf-16-be", errors="replace")
        if raw_data.startswith(b"\xef\xbb\xbf"):
            return raw_data.decode("utf-8-sig", errors="replace")
        try:
            return raw_data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            try:
                return raw_data.decode("gbk", errors="replace")
            except Exception:
                return raw_data.decode("utf-8", errors="replace")


def build_cookie_header(cookies_file: str | None) -> str:
    if not cookies_file:
        return ""

    path = Path(cookies_file)
    if not path.exists():
        return ""

    cookies = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line and not line.startswith("#"):
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def fetch_json(url: str, headers: dict | None = None) -> dict:
    request_headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}
    if headers:
        request_headers.update(headers)
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def parse_json_transcript(payload: dict) -> str:
    if isinstance(payload.get("events"), list):
        lines = []
        for event in payload["events"]:
            if "segs" not in event:
                continue
            text = "".join(segment.get("utf8", "") for segment in event["segs"])
            text = clean_text(text)
            if text:
                lines.append(text)
        return "\n".join(lines).strip()

    if isinstance(payload.get("body"), list):
        lines = []
        for item in payload["body"]:
            text = clean_text(item.get("content", ""))
            if text:
                lines.append(text)
        return "\n".join(lines).strip()

    return ""


def parse_json_segments(payload: dict) -> list[dict]:
    segments = []

    if isinstance(payload.get("events"), list):
        for event in payload["events"]:
            if "segs" not in event:
                continue
            text = "".join(segment.get("utf8", "") for segment in event["segs"])
            text = clean_text(text)
            if text:
                start = (event.get("tStartMs") or 0) / 1000
                duration = (event.get("dDurationMs") or 0) / 1000
                segments.append({"start": start, "end": start + duration, "text": text})

    if isinstance(payload.get("body"), list):
        for item in payload["body"]:
            text = clean_text(item.get("content", ""))
            if text:
                start = float(item.get("from", 0))
                end = float(item.get("to", start))
                segments.append({"start": start, "end": end, "text": text})

    return segments


def parse_vtt_transcript(content: str) -> str:
    lines = []
    seen = set()
    for raw_line in content.splitlines():
        line = raw_line.strip().replace("\ufeff", "")
        if not line or line == "WEBVTT" or "-->" in line:
            continue
        if re.fullmatch(r"\d+", line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = clean_text(line)
        if line and line not in seen:
            seen.add(line)
            lines.append(line)
    return "\n".join(lines).strip()


def parse_srt_transcript(content: str) -> str:
    return parse_vtt_transcript(content)


def parse_transcript_content(content: str, ext: str) -> str:
    ext = (ext or "").lower()
    if ext in {"json3", "json", "srv3", "srv2", "srv1"}:
        try:
            return parse_json_transcript(json.loads(content))
        except json.JSONDecodeError:
            return ""
    if ext == "vtt":
        return parse_vtt_transcript(content)
    if ext == "srt":
        return parse_srt_transcript(content)
    if ext == "ttml":
        return clean_text(re.sub(r"<[^>]+>", "", content))
    return clean_text(content)


def parse_transcript_segments(content: str, ext: str) -> list[dict]:
    ext = (ext or "").lower()
    if ext in {"json3", "json", "srv3", "srv2", "srv1"}:
        try:
            return parse_json_segments(json.loads(content))
        except json.JSONDecodeError:
            return []
    return []


def subtitle_candidates(raw_data: dict) -> list[tuple[str, dict, str]]:
    candidates = []

    for source_name, subtitles in (
        ("manual", raw_data.get("subtitles") or {}),
        ("automatic", raw_data.get("automatic_captions") or {}),
    ):
        for language, items in subtitles.items():
            if not isinstance(items, list):
                continue
            for item in items:
                ext = (item.get("ext") or "").lower()
                if item.get("url"):
                    candidates.append((source_name, item, language))

    def language_rank(language: str) -> int:
        if language in LANGUAGE_PRIORITY:
            return LANGUAGE_PRIORITY.index(language)
        base = language.split("-")[0]
        if base in LANGUAGE_PRIORITY:
            return LANGUAGE_PRIORITY.index(base)
        return len(LANGUAGE_PRIORITY) + 10

    def ext_rank(ext: str) -> int:
        if ext in SUBTITLE_EXT_PRIORITY:
            return SUBTITLE_EXT_PRIORITY.index(ext)
        return len(SUBTITLE_EXT_PRIORITY) + 10

    return sorted(
        candidates,
        key=lambda item: (
            0 if item[0] == "manual" else 1,
            language_rank(item[2]),
            ext_rank((item[1].get("ext") or "").lower()),
        ),
    )


def bilibili_subtitle_candidates(entry: VideoEntry, cookies_file: str | None) -> list[tuple[str, dict, str]]:
    if entry.platform != "bilibili":
        return []

    cookie_header = build_cookie_header(cookies_file)
    headers = {"Cookie": cookie_header} if cookie_header else {}

    try:
        params = urlencode({"bvid": entry.video_id})
        pagelist = fetch_json(f"https://api.bilibili.com/x/player/pagelist?{params}", headers=headers)
        pages = pagelist.get("data") or []
        if not pages:
            return []
        cid = pages[0].get("cid")
        if not cid:
            return []

        params = urlencode({"bvid": entry.video_id, "cid": cid})
        player_data = fetch_json(f"https://api.bilibili.com/x/player/v2?{params}", headers=headers)
        subtitle_data = (player_data.get("data") or {}).get("subtitle") or {}
        candidates = []
        for item in subtitle_data.get("subtitles") or []:
            subtitle_url = item.get("subtitle_url") or item.get("url")
            if not subtitle_url:
                continue
            if subtitle_url.startswith("//"):
                subtitle_url = "https:" + subtitle_url
            candidates.append((
                "manual",
                {"url": subtitle_url, "ext": "json"},
                item.get("lan") or item.get("lan_doc") or "",
            ))
        return candidates
    except Exception as e:
        logger.debug(f"Bilibili 字幕获取失败: {e}")
        return []


def extract_transcript(
    entry: VideoEntry,
    raw_data: dict,
    cookies_file: str | None = None,
    force_whisper: bool = False,
    whisper_config: dict | None = None,
) -> tuple[str, list[dict], dict]:
    if not force_whisper:
        for source_name, item, language in subtitle_candidates(raw_data):
            try:
                content = fetch_url_text(item["url"])
                transcript = parse_transcript_content(content, item.get("ext", ""))
                segments = parse_transcript_segments(content, item.get("ext", ""))
            except Exception as e:
                logger.debug(f"字幕获取失败: {e}")
                continue

            if transcript and _is_transcript_usable(transcript, entry.duration):
                matches_context, matched_terms = _transcript_matches_context(entry, raw_data, transcript)
                if not matches_context:
                    logger.warning("Skip subtitle candidate: low relevance to video context, fallback to other sources")
                    continue
                return transcript, segments, {
                    "language": language,
                    "source": source_name,
                    "ext": item.get("ext", ""),
                    "url": item.get("url", ""),
                    "matched_terms": matched_terms,
                }

        for source_name, item, language in bilibili_subtitle_candidates(entry, cookies_file):
            try:
                content = fetch_url_text(item["url"])
                transcript = parse_transcript_content(content, item.get("ext", ""))
                segments = parse_transcript_segments(content, item.get("ext", ""))
            except Exception as e:
                logger.debug(f"Bilibili 字幕获取失败: {e}")
                continue

            if transcript and _is_transcript_usable(transcript, entry.duration):
                matches_context, matched_terms = _transcript_matches_context(entry, raw_data, transcript)
                if not matches_context:
                    logger.warning("Skip subtitle candidate: low relevance to video context")
                    continue
                return transcript, segments, {
                    "language": language,
                    "source": f"bilibili_{source_name}",
                    "ext": item.get("ext", ""),
                    "url": item.get("url", ""),
                    "matched_terms": matched_terms,
                }

    if force_whisper:
        logger.info("启用 Whisper 语音转文字...")
        result = transcribe_from_url(
            url=entry.url,
            cookies_file=cookies_file,
            config=whisper_config,
            force=force_whisper,
        )
        if result:
            transcript, segments, info = result
            return transcript, segments, {
                "language": info.get("language", "unknown"),
                "source": f"whisper_{info.get('provider', 'unknown')}",
                "model": info.get("model", ""),
                "device": whisper_config.get("device", "cpu") if whisper_config else "cpu",
                "language_probability": info.get("language_probability"),
            }

    return "", [], {}


def normalize_metadata(entry: VideoEntry, raw_data: dict, transcript_info: dict) -> dict:
    description = clean_text(entry.description or "")
    return {
        "platform": entry.platform,
        "video_id": entry.video_id,
        "title": entry.title,
        "url": entry.url,
        "uploader": entry.uploader,
        "published_date": format_date(entry.published_date),
        "duration_seconds": entry.duration,
        "duration_text": format_duration(entry.duration),
        "tags": entry.tags,
        "description": description,
        "thumbnail": entry.thumbnail,
        "view_count": raw_data.get("view_count"),
        "like_count": raw_data.get("like_count"),
        "comment_count": raw_data.get("comment_count"),
        "channel": raw_data.get("channel"),
        "uploader_id": raw_data.get("uploader_id"),
        "language": raw_data.get("language"),
        "categories": raw_data.get("categories") or [],
        "links_in_description": extract_links(description),
        "chapters": raw_data.get("chapters") or [],
        "transcript_info": transcript_info,
    }


def render_source_markdown(metadata: dict, transcript: str) -> str:
    tags = " ".join(f"#{tag}" for tag in metadata.get("tags") or []) or "无"
    links = metadata.get("links_in_description") or []
    chapters = metadata.get("chapters") or []

    lines = [
        f"# 原始资料 - {metadata['title']}",
        "",
        "## 基本信息",
        "",
        f"- 平台: {metadata['platform']}",
        f"- 视频 ID: {metadata['video_id']}",
        f"- 作者/频道: {metadata['uploader']}",
        f"- 发布时间: {metadata['published_date']}",
        f"- 时长: {metadata['duration_text']}",
        f"- 链接: {metadata['url']}",
        f"- 标签: {tags}",
    ]

    if metadata.get("view_count") is not None:
        lines.append(f"- 播放量: {metadata['view_count']}")
    if metadata.get("like_count") is not None:
        lines.append(f"- 点赞数: {metadata['like_count']}")
    if metadata.get("comment_count") is not None:
        lines.append(f"- 评论数: {metadata['comment_count']}")

    lines.extend([
        "",
        "## 视频简介",
        "",
        metadata.get("description") or "无",
    ])

    if links:
        lines.extend(["", "## 简介中的链接", ""])
        lines.extend(f"- {link}" for link in links)

    if chapters:
        lines.extend(["", "## 章节", ""])
        for chapter in chapters:
            lines.append(f"- {format_duration(chapter.get('start_time'))} {chapter.get('title', '').strip()}")

    transcript_info = metadata.get("transcript_info") or {}
    lines.extend(["", "## 字幕/转录", ""])
    if transcript_info:
        lines.append(
            f"- 字幕来源: {transcript_info.get('source', 'unknown')} / {transcript_info.get('language', 'unknown')}"
        )
        lines.append("")
    lines.append(transcript or "未获取到字幕或转录。")

    return "\n".join(lines).strip() + "\n"


def load_prompt_template() -> str:
    if PROMPT_TEMPLATE_PATH.exists():
        return PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    return """请根据下面的视频资料，为 Obsidian 生成一篇高质量中文学习笔记。

视频元数据：
```json
{metadata_json}
```

原始资料：
```markdown
{source_markdown}
```

字幕 / 转录：
```text
{transcript_text}
```

分段字幕：
```json
{transcript_segments_json}
```
"""


def render_timestamped_transcript(segments: list[dict], transcript: str) -> str:
    if segments:
        lines = []
        for segment in segments:
            start = format_timestamp(segment.get("start"))
            end = format_timestamp(segment.get("end"))
            text = clean_text(segment.get("text", ""))
            if text:
                lines.append(f"[{start} - {end}] {text}")
        return "\n".join(lines).strip() + "\n"

    if transcript:
        return transcript.strip() + "\n"

    return ""


def render_prompt_markdown(
    metadata: dict,
    transcript: str,
    timestamped_transcript: str = "",
    source_markdown: str = "",
    transcript_segments: list[dict] | None = None,
) -> str:
    if transcript:
        transcript_text = timestamped_transcript or transcript
    elif metadata["platform"] == "bilibili":
        transcript_text = "当前未获取到字幕。对 Bilibili 视频，这通常表示视频本身没有公开字幕。请基于元数据和简介谨慎整理，并明确标注资料不足。"
    else:
        transcript_text = "未获取到字幕。请基于元数据和简介谨慎整理，并明确标注资料不足。"

    metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2)
    transcript_segments_json = json.dumps(transcript_segments or [], ensure_ascii=False, indent=2)
    extra_context = "\n".join(
        f"- {link}" for link in (metadata.get("links_in_description") or [])
    ) or "无"

    return load_prompt_template().format(
        metadata_json=metadata_json,
        source_markdown=source_markdown or "无",
        transcript_text=transcript_text,
        transcript_segments_json=transcript_segments_json,
        extra_context=extra_context,
    )


def write_bundle_files(
    bundle_dir: Path,
    metadata: dict,
    raw_data: dict,
    transcript: str,
    transcript_segments: list[dict],
    timestamped_transcript: str,
    source_markdown: str,
) -> None:
    (bundle_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (bundle_dir / "raw.json").write_text(
        json.dumps(raw_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (bundle_dir / "transcript.txt").write_text(transcript or "", encoding="utf-8")
    (bundle_dir / "transcript_segments.json").write_text(
        json.dumps(transcript_segments, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (bundle_dir / "transcript_timestamps.md").write_text(timestamped_transcript, encoding="utf-8")
    (bundle_dir / "source.md").write_text(source_markdown, encoding="utf-8")
    (bundle_dir / "prompt.md").write_text(
        render_prompt_markdown(
            metadata,
            transcript,
            timestamped_transcript,
            source_markdown,
            transcript_segments,
        ),
        encoding="utf-8",
    )


def replace_bundle_dir(staging_dir: Path, bundle_dir: Path) -> None:
    """Atomically replace the target bundle directory with a fully written staging dir."""
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    staging_dir.replace(bundle_dir)


def export_bundle(
    entry: VideoEntry,
    raw_data: dict,
    output_dir: str,
    cookies_file: str | None = None,
    whisper_config: dict | None = None,
    force_whisper: bool = False,
) -> Path:
    bundle_root = Path(output_dir)
    bundle_root.mkdir(parents=True, exist_ok=True)

    bundle_name = f"{entry.platform}-{entry.video_id}-{slugify(entry.title, max_len=50)}"
    bundle_dir = bundle_root / bundle_name
    staging_dir = bundle_root / f".{bundle_name}.tmp"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    transcript, transcript_segments, transcript_info = extract_transcript(
        entry,
        raw_data,
        cookies_file,
        force_whisper=force_whisper,
        whisper_config=whisper_config,
    )
    timestamped_transcript = render_timestamped_transcript(transcript_segments, transcript)
    metadata = normalize_metadata(entry, raw_data, transcript_info)
    source_markdown = render_source_markdown(metadata, transcript)

    write_bundle_files(
        staging_dir,
        metadata,
        raw_data,
        transcript,
        transcript_segments,
        timestamped_transcript,
        source_markdown,
    )

    replace_bundle_dir(staging_dir, bundle_dir)
    logger.info(f"Bundle 导出成功: {bundle_dir}")
    return bundle_dir


def export_media_bundle(
    media_file: str,
    output_dir: str,
    whisper_config: dict | None = None,
) -> Path | None:
    """Export an LLM-ready bundle for a local audio/video file."""
    media_path = Path(media_file)
    if not media_path.exists():
        logger.error(f"文件不存在: {media_path}")
        return None

    result = transcribe_from_file(str(media_path), config=whisper_config)
    if not result:
        logger.error("转录失败")
        return None

    transcript, transcript_segments, transcript_info = result
    timestamped_transcript = render_timestamped_transcript(transcript_segments, transcript)

    title = media_path.stem
    metadata = {
        "platform": "local",
        "video_id": media_path.stem,
        "title": title,
        "url": "",
        "uploader": "",
        "published_date": "",
        "duration_seconds": transcript_info.get("duration"),
        "duration_text": format_duration(transcript_info.get("duration")),
        "tags": [],
        "description": "",
        "thumbnail": "",
        "view_count": None,
        "like_count": None,
        "comment_count": None,
        "channel": "",
        "uploader_id": "",
        "language": transcript_info.get("language"),
        "categories": [],
        "links_in_description": [],
        "chapters": [],
        "media_file": str(media_path),
        "transcript_info": {
            "language": transcript_info.get("language", "unknown"),
            "source": f"whisper_{transcript_info.get('provider', 'unknown')}",
            "model": transcript_info.get("model", ""),
            "device": (whisper_config or {}).get("device", "cpu"),
            "language_probability": transcript_info.get("language_probability"),
        },
    }

    source_markdown = render_source_markdown(metadata, transcript)

    bundle_root = Path(output_dir)
    bundle_root.mkdir(parents=True, exist_ok=True)
    bundle_dir = bundle_root / f"local-{slugify(title, max_len=70)}"
    staging_dir = bundle_root / f".{bundle_dir.name}.tmp"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    write_bundle_files(
        staging_dir,
        metadata,
        {"media_file": str(media_path)},
        transcript,
        transcript_segments,
        timestamped_transcript,
        source_markdown,
    )

    replace_bundle_dir(staging_dir, bundle_dir)
    logger.info(f"本地媒体 Bundle 导出成功: {bundle_dir}")
    return bundle_dir
