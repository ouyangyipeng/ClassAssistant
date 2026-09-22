import os
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import uuid4

from classfox.models import Material, Session, SessionStatus, Summary, TranscriptEntry

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    course_name TEXT NOT NULL,
    material_id TEXT REFERENCES materials(id),
    status TEXT NOT NULL CHECK(status IN ('starting','recording','paused','stopped','interrupted','error')),
    created_at REAL NOT NULL,
    ended_at REAL
);
CREATE INDEX IF NOT EXISTS sessions_owner ON sessions(owner_id, created_at DESC);
CREATE TABLE IF NOT EXISTS transcript_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    text TEXT NOT NULL CHECK(length(trim(text)) > 0),
    created_at REAL NOT NULL,
    source_id TEXT,
    UNIQUE(session_id, source_id)
);
CREATE INDEX IF NOT EXISTS transcript_session ON transcript_entries(session_id, created_at, id);
CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS summaries (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    title TEXT NOT NULL,
    markdown TEXT NOT NULL CHECK(length(trim(markdown)) > 0),
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS summaries_session ON summaries(session_id, created_at DESC);
CREATE TABLE IF NOT EXISTS imports (
    source TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id)
);
CREATE TABLE IF NOT EXISTS material_imports (
    source TEXT PRIMARY KEY,
    material_id TEXT NOT NULL REFERENCES materials(id)
);
CREATE TABLE IF NOT EXISTS audio_receipts (
    session_id TEXT NOT NULL REFERENCES sessions(id),
    source_id TEXT NOT NULL,
    digest TEXT NOT NULL,
    entry_id INTEGER REFERENCES transcript_entries(id),
    PRIMARY KEY(session_id, source_id)
);
PRAGMA user_version = 1;
"""


def timestamp(at: datetime | None = None) -> float:
    value = at or datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("时间戳必须包含时区")
    return value.timestamp()


class Store:
    """Own one serialized SQLite connection for an application lifetime."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(descriptor)
        if os.name != "nt":
            path.chmod(0o600)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA journal_mode = WAL")
        self._db.execute("PRAGMA synchronous = FULL")
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            self._db.close()
            raise ValueError("此数据库由更新的 ClassFox 版本创建，请先升级应用")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def create_session(self, course_name: str, *, owner_id: str = "desktop", material_id: str | None = None, at: datetime | None = None) -> Session:
        name = course_name.strip()
        if not name or len(name) > 120:
            raise ValueError("课程名称需为 1 至 120 个字符")
        session_id = uuid4().hex
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, 'recording', ?, NULL)",
                (session_id, owner_id, name, material_id, timestamp(at)),
            )
            return self.get_session(session_id)

    def get_session(self, session_id: str, *, owner_id: str | None = None) -> Session:
        with self._lock:
            row = self._db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None or (owner_id is not None and row["owner_id"] != owner_id):
            raise KeyError("未找到课堂")
        return Session.model_validate(dict(row))

    def list_sessions(self, *, owner_id: str = "desktop", limit: int = 100, offset: int = 0) -> list[Session]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM sessions WHERE owner_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (owner_id, min(max(limit, 1), 500), max(offset, 0)),
            ).fetchall()
        return [Session.model_validate(dict(row)) for row in rows]

    def set_status(self, session_id: str, status: SessionStatus) -> Session:
        with self._lock, self._db:
            current = self.get_session(session_id)
            if current.status in {"stopped", "interrupted"} and status != current.status:
                raise ValueError("课堂已结束，请开始新课堂")
            ended_at = timestamp() if status in {"stopped", "interrupted"} else None
            self._db.execute("UPDATE sessions SET status = ?, ended_at = ? WHERE id = ?", (status, ended_at, session_id))
            return self.get_session(session_id)

    def finish_session(self, session_id: str) -> Session:
        return self.set_status(session_id, "stopped")

    def recover_interrupted_sessions(self) -> int:
        with self._lock, self._db:
            cursor = self._db.execute(
                "UPDATE sessions SET status = 'interrupted', ended_at = ? WHERE status IN ('starting', 'recording', 'paused', 'error')",
                (timestamp(),),
            )
            return cursor.rowcount

    def append_entry(
        self, session_id: str, text: str, *, at: datetime | None = None, source_id: str | None = None, allow_paused: bool = False
    ) -> TranscriptEntry:
        cleaned = text.strip()
        if not cleaned or len(cleaned) > 8000:
            raise ValueError("转录需为 1 至 8000 个字符")
        with self._lock, self._db:
            session = self.get_session(session_id)
            if session.status not in {"recording", "starting"} and not (allow_paused and session.status == "paused"):
                raise ValueError("课堂已结束或暂停，无法追加转录")
            if source_id is not None:
                existing = self._db.execute("SELECT * FROM transcript_entries WHERE session_id = ? AND source_id = ?", (session_id, source_id)).fetchone()
                if existing is not None:
                    if existing["text"] != cleaned:
                        raise ValueError("相同片段标识不能提交不同内容")
                    return TranscriptEntry.model_validate(dict(existing))
            cursor = self._db.execute(
                "INSERT INTO transcript_entries(session_id, text, created_at, source_id) VALUES (?, ?, ?, ?)",
                (session_id, cleaned, timestamp(at), source_id),
            )
            row = self._db.execute("SELECT * FROM transcript_entries WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return TranscriptEntry.model_validate(dict(row))

    def entry_extent(self, session_id: str) -> tuple[int, int]:
        with self._lock:
            row = self._db.execute("SELECT coalesce(max(id), 0), count(*) FROM transcript_entries WHERE session_id = ?", (session_id,)).fetchone()
        return int(row[0]), int(row[1])

    def list_entries(self, session_id: str, *, after_id: int = 0, through_id: int | None = None, limit: int = 1000) -> list[TranscriptEntry]:
        with self._lock:
            self.get_session(session_id)
            rows = self._db.execute(
                "SELECT * FROM transcript_entries WHERE session_id = ? AND id > ? AND (? IS NULL OR id <= ?) ORDER BY id LIMIT ?",
                (session_id, after_id, through_id, through_id, min(max(limit, 1), 10000)),
            ).fetchall()
        return [TranscriptEntry.model_validate(dict(row)) for row in rows]

    def find_entry(self, session_id: str, source_id: str) -> TranscriptEntry | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM transcript_entries WHERE session_id = ? AND source_id = ?", (session_id, source_id)).fetchone()
        return TranscriptEntry.model_validate(dict(row)) if row else None

    def audio_receipt(self, session_id: str, source_id: str, digest: str) -> tuple[bool, TranscriptEntry | None]:
        with self._lock:
            receipt = self._db.execute("SELECT * FROM audio_receipts WHERE session_id = ? AND source_id = ?", (session_id, source_id)).fetchone()
            if receipt is None:
                return False, None
            if receipt["digest"] != digest:
                raise ValueError("相同音频片段标识不能提交不同内容")
            row = self._db.execute("SELECT * FROM transcript_entries WHERE id = ?", (receipt["entry_id"],)).fetchone()
            return True, TranscriptEntry.model_validate(dict(row)) if row else None

    def accept_audio(self, session_id: str, source_id: str, digest: str, text: str) -> tuple[TranscriptEntry | None, bool]:
        cleaned = text.strip()
        if len(cleaned) > 8000:
            raise ValueError("识别文字过长，请缩短音频")
        with self._lock, self._db:
            found, previous = self.audio_receipt(session_id, source_id, digest)
            if found:
                return previous, False
            if self.get_session(session_id).status != "recording":
                raise ValueError("课堂已结束或暂停，无法追加识别结果")
            entry_id = None
            if cleaned:
                cursor = self._db.execute(
                    "INSERT INTO transcript_entries(session_id, text, created_at, source_id) VALUES (?, ?, ?, ?)",
                    (session_id, cleaned, timestamp(), f"audio:{uuid4().hex}"),
                )
                entry_id = cursor.lastrowid
            self._db.execute("INSERT INTO audio_receipts VALUES (?, ?, ?, ?)", (session_id, source_id, digest, entry_id))
            return self.audio_receipt(session_id, source_id, digest)[1], True

    def recent_entries(self, session_id: str, *, minutes: float = 2, now: datetime | None = None, limit: int = 500) -> list[TranscriptEntry]:
        current = now or datetime.now(UTC)
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM transcript_entries WHERE session_id = ? AND created_at BETWEEN ? AND ? ORDER BY created_at DESC, id DESC LIMIT ?",
                (session_id, timestamp(current - timedelta(minutes=minutes)), timestamp(current), min(max(limit, 1), 10000)),
            ).fetchall()
        return [TranscriptEntry.model_validate(dict(row)) for row in reversed(rows)]

    def add_material(self, filename: str, text: str) -> Material:
        if not text.strip() or len(text) > 2_000_000:
            raise ValueError("资料没有可提取文字或超过 200 万字符限制")
        material_id = uuid4().hex
        with self._lock, self._db:
            self._db.execute("INSERT INTO materials VALUES (?, ?, ?, ?)", (material_id, filename, text, timestamp()))
            return self.get_material(material_id)

    def get_material(self, material_id: str) -> Material:
        with self._lock:
            row = self._db.execute("SELECT * FROM materials WHERE id = ?", (material_id,)).fetchone()
        if row is None:
            raise KeyError("未找到课程资料")
        return Material.model_validate(dict(row))

    def list_materials(self, *, limit: int = 100, offset: int = 0) -> list[Material]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM materials ORDER BY created_at DESC LIMIT ? OFFSET ?", (min(max(limit, 1), 500), max(offset, 0))).fetchall()
        return [Material.model_validate(dict(row)) for row in rows]

    def save_summary(self, session_id: str, title: str, markdown: str) -> Summary:
        if not markdown.strip():
            raise ValueError("模型未返回有效笔记")
        summary_id = uuid4().hex
        with self._lock, self._db:
            self.get_session(session_id)
            self._db.execute("INSERT INTO summaries VALUES (?, ?, ?, ?, ?)", (summary_id, session_id, title, markdown, timestamp()))
            return self.get_summary(summary_id)

    def get_summary(self, summary_id: str) -> Summary:
        with self._lock:
            row = self._db.execute("SELECT * FROM summaries WHERE id = ?", (summary_id,)).fetchone()
        if row is None:
            raise KeyError("未找到课堂笔记")
        return Summary.model_validate(dict(row))

    def list_summaries(self, session_id: str, *, limit: int | None = None, offset: int = 0) -> list[Summary]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM summaries WHERE session_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (session_id, -1 if limit is None else min(max(limit, 1), 500), max(0, offset)),
            ).fetchall()
        return [Summary.model_validate(dict(row)) for row in rows]

    def export_session(self, session_id: str, *, format: Literal["text", "markdown"] = "text") -> str:
        session = self.get_session(session_id)
        with self._lock:
            rows = self._db.execute("SELECT * FROM transcript_entries WHERE session_id = ? ORDER BY id", (session_id,)).fetchall()
        heading = f"# {session.course_name}\n" if format == "markdown" else session.course_name
        lines = [heading, f"{session.created_at.isoformat()}\n"]
        for row in rows:
            at = datetime.fromtimestamp(row["created_at"], UTC).astimezone().isoformat(timespec="seconds")
            lines.append(f"[{at}] {row['text']}")
        return "\n".join(lines) + "\n"

    def import_session(self, source: str, course_name: str, entries: list[tuple[datetime, str]], *, summary: str = "", at: datetime) -> Session:
        records = [(timestamp(time), text.strip()) for time, text in entries if text.strip()]
        if any(len(text) > 8000 for _, text in records):
            raise ValueError("旧转录单条内容超过 8000 字符，请拆分后导入")
        with self._lock, self._db:
            imported = self._db.execute("SELECT session_id FROM imports WHERE source = ?", (source,)).fetchone()
            if imported:
                return self.get_session(imported["session_id"])
            session_id = uuid4().hex
            self._db.execute(
                "INSERT INTO sessions VALUES (?, 'desktop', ?, NULL, 'stopped', ?, ?)",
                (session_id, course_name.strip()[:120] or "导入课堂", timestamp(at), records[-1][0] if records else timestamp(at)),
            )
            self._db.executemany(
                "INSERT INTO transcript_entries(session_id, text, created_at) VALUES (?, ?, ?)",
                [(session_id, text, time) for time, text in records],
            )
            if summary.strip():
                self._db.execute("INSERT INTO summaries VALUES (?, ?, ?, ?, ?)", (uuid4().hex, session_id, "导入的历史笔记", summary.strip(), timestamp(at)))
            self._db.execute("INSERT INTO imports VALUES (?, ?)", (source, session_id))
            return self.get_session(session_id)

    def import_material(self, source: str, filename: str, text: str) -> Material:
        if not text.strip() or len(text) > 2_000_000:
            raise ValueError("资料没有可提取文字或超过 200 万字符限制")
        with self._lock, self._db:
            imported = self._db.execute("SELECT material_id FROM material_imports WHERE source = ?", (source,)).fetchone()
            if imported:
                return self.get_material(imported["material_id"])
            material_id = uuid4().hex
            self._db.execute("INSERT INTO materials VALUES (?, ?, ?, ?)", (material_id, filename, text, timestamp()))
            self._db.execute("INSERT INTO material_imports VALUES (?, ?)", (source, material_id))
            return self.get_material(material_id)
