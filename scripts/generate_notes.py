"""Generate Obsidian notes from VideoEntry objects."""
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fetch_base import VideoEntry


FRONTMATTER_TEMPLATE = """---
platform: {platform}
video_id: "{video_id}"
title: "{title}"
url: {url}
uploader: "{uploader}"
published_date: "{published_date}"
duration: "{duration}"
tags: {tags}
created: {created}
modified: {modified}
---

"""

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "notes"
TEMPLATE_PATH = PROJECT_ROOT / "templates" / "video_note.md"

DEFAULT_VIDEO_NOTE_TEMPLATE = """## 视频信息

- **平台**: [[{platform}]]
- **UP 主/频道**: {uploader}
- **发布时间**: {published_date_str}
- **时长**: {duration_str}
- **标签**: {tags_str}

## 简介

{description}

## 时间戳

<!-- 时间戳待补充 -->

## 相关笔记

<!-- 关联笔记链接 -->

---

> [!VIDEO]+ 视频播放
> {embed_link}
"""

PLATFORM_DISPLAY = {
    "bilibili": "Bilibili",
    "youtube": "YouTube",
}

PLATFORM_EMBED = {
    "bilibili": "https://player.bilibili.com/player.html?bvid={video_id}",
    "youtube": "https://www.youtube.com/embed/{video_id}",
}


def format_duration(seconds: Optional[int]) -> str:
    if seconds is None:
        return "未知"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_date(date_str: Optional[str]) -> str:
    if date_str and len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return date_str or "未知"


def slugify(title: str, platform: str, video_id: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*]', "", title)
    safe = safe[:80].strip() or "untitled"
    return f"{platform}-{video_id}-{safe}.md"


def load_note_template() -> str:
    if TEMPLATE_PATH.exists():
        return TEMPLATE_PATH.read_text(encoding="utf-8")
    return DEFAULT_VIDEO_NOTE_TEMPLATE


def generate_note(entry: VideoEntry, output_dir: str = str(DEFAULT_OUTPUT_DIR)) -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d")
    platform_display = PLATFORM_DISPLAY.get(entry.platform, entry.platform)

    tags_str = "[" + ", ".join(f'"{t}"' for t in entry.tags) + "]"
    frontmatter = FRONTMATTER_TEMPLATE.format(
        platform=entry.platform,
        video_id=entry.video_id,
        title=entry.title.replace('"', '\\"'),
        url=entry.url,
        uploader=entry.uploader.replace('"', '\\"'),
        published_date=format_date(entry.published_date),
        duration=format_duration(entry.duration),
        tags=tags_str,
        created=now,
        modified=now,
    )

    embed_url = PLATFORM_EMBED.get(entry.platform, entry.url)
    embed_link = embed_url.format(video_id=entry.video_id)

    duration_str = format_duration(entry.duration)
    published_str = format_date(entry.published_date)
    note_tags = " ".join(f"#{t}" for t in entry.tags) if entry.tags else "无"
    if entry.description and len(entry.description) > 500:
        description = entry.description[:500] + "..."
    else:
        description = entry.description or "无"

    body = load_note_template().format(
        platform=platform_display,
        uploader=entry.uploader,
        published_date_str=published_str,
        duration_str=duration_str,
        tags_str=note_tags,
        description=description,
        embed_link=embed_link,
    )

    filename = slugify(entry.title, entry.platform, entry.video_id)
    filepath = Path(output_dir) / filename
    filepath.write_text(frontmatter + body, encoding="utf-8")

    print(f"  生成: {filename}")
    return str(filepath)


def batch_generate(entries: list[VideoEntry], output_dir: str = str(DEFAULT_OUTPUT_DIR)) -> list[str]:
    paths = []
    for entry in entries:
        try:
            path = generate_note(entry, output_dir)
            paths.append(path)
        except Exception as e:
            print(f"  生成失败 {entry.title}: {e}")
    return paths
