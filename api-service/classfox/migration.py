import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from classfox.storage import Store


@dataclass
class LegacyImportResult:
    session_id: str | None = None
    materials: int = 0
    notes: int = 0
    skipped_files: list[str] = field(default_factory=list)


def parse_legacy_transcript(text: str, fallback: datetime) -> tuple[str, datetime, list[tuple[datetime, str]], str]:
    header = re.search(r"开始于 (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", text)
    started = datetime.strptime(header[1], "%Y-%m-%d %H:%M:%S").astimezone() if header else fallback.astimezone()
    date = started.date()
    course = "导入课堂"
    in_summary = False
    summary: list[str] = []
    entries: list[tuple[datetime, str]] = []
    previous: datetime | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line == "=== 历史摘要 开始 ===":
            in_summary = True
        elif line == "=== 历史摘要 结束 ===":
            in_summary = False
        elif in_summary:
            summary.append(line)
        elif line.startswith("课程："):
            course = line.split("：", 1)[1].strip() or course
        elif match := re.match(r"^\[(\d{2}:\d{2}:\d{2})\]\s*(.+)$", line):
            time = datetime.strptime(match[1], "%H:%M:%S").time()
            instant = datetime.combine(date, time).astimezone()
            if previous and instant < previous:
                date += timedelta(days=1)
                instant = datetime.combine(date, time).astimezone()
            entries.append((instant, match[2]))
            previous = instant
        elif line and not line.startswith(("===", "参考资料：")):
            entries.append((previous or started, line))
    return course, started, entries, "\n".join(summary).strip()


def import_legacy_data(root: Path, store: Store) -> LegacyImportResult:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError("旧数据目录不存在")
    result = LegacyImportResult()
    files = [root / "class_transcript.txt", *sorted((root / "cite").glob("*.txt")), *sorted((root / "summaries").glob("*.md"))]
    for path in files:
        try:
            if not path.exists():
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root) or path.stat().st_size > 20 * 1024 * 1024:
                result.skipped_files.append(path.relative_to(root).as_posix())
                continue
            text = path.read_text(encoding="utf-8-sig")
            if not text.strip():
                continue
            fingerprint = hashlib.sha256((str(path) + "\0" + text).encode()).hexdigest()
            at = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
            if path.name == "class_transcript.txt" and path.parent == root:
                course, started, entries, summary = parse_legacy_transcript(text, at)
                result.session_id = store.import_session(fingerprint, course, entries, summary=summary, at=started).id
            elif path.parent.name == "cite":
                store.import_material(fingerprint, path.name, text)
                result.materials += 1
            else:
                store.import_session(fingerprint, path.stem, [], summary=text, at=at)
                result.notes += 1
        except (OSError, UnicodeError, ValueError):
            result.skipped_files.append(path.relative_to(root).as_posix())
    return result
