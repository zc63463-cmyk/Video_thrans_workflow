"""增量同步引擎：对比本地数据库，新视频才写入"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from fetch_base import VideoEntry


class SyncEngine:
    """增量同步：对比数据库，只同步新条目"""

    DB_PATH = str(Path(__file__).resolve().parent.parent / "output" / "videos.db")

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or self.DB_PATH
        self._init_db()

    def _init_db(self):
        """初始化 SQLite 数据库"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                platform TEXT,
                video_id TEXT,
                title TEXT,
                url TEXT,
                uploader TEXT,
                published_date TEXT,
                duration INTEGER,
                description TEXT,
                thumbnail TEXT,
                tags TEXT,
                collected_at TEXT,
                fetched_at TEXT,
                synced_at TEXT,
                PRIMARY KEY (platform, video_id)
            )
        """)
        conn.commit()
        conn.close()

    def _video_to_tuple(self, v: VideoEntry) -> tuple:
        return (
            v.platform, v.video_id, v.title, v.url, v.uploader,
            v.published_date, v.duration, v.description, v.thumbnail,
            json.dumps(v.tags, ensure_ascii=False),
            v.collected_at, v.fetched_at,
            datetime.now().isoformat(),
        )

    def upsert(self, entries: list[VideoEntry]) -> tuple[list[VideoEntry], list[VideoEntry]]:
        """
        增量插入：返回 (new_entries, existing_entries)
        - new_entries: 新视频（写入数据库）
        - existing_entries: 已存在的视频
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        new_entries = []
        existing_entries = []

        for entry in entries:
            cursor.execute(
                "SELECT 1 FROM videos WHERE platform=? AND video_id=?",
                (entry.platform, entry.video_id)
            )
            if cursor.fetchone() is None:
                # 新视频：插入
                cursor.execute(
                    """INSERT OR REPLACE INTO videos
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    self._video_to_tuple(entry)
                )
                new_entries.append(entry)
            else:
                existing_entries.append(entry)

        conn.commit()
        conn.close()

        print(f"[Sync] 新视频: {len(new_entries)}, 已存在: {len(existing_entries)}")
        return new_entries, existing_entries

    def get_all(self) -> list[VideoEntry]:
        """读取数据库中所有视频"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM videos ORDER BY synced_at DESC")
        rows = cursor.fetchall()
        conn.close()

        entries = []
        for row in rows:
            entries.append(VideoEntry(
                platform=row["platform"],
                video_id=row["video_id"],
                title=row["title"],
                url=row["url"],
                uploader=row["uploader"],
                published_date=row["published_date"],
                duration=row["duration"],
                description=row["description"],
                thumbnail=row["thumbnail"],
                tags=json.loads(row["tags"]),
                collected_at=row["collected_at"],
                fetched_at=row["fetched_at"],
            ))
        return entries
