import sqlite3
from pathlib import Path

import pytest

from classfox.migration import import_legacy_data
from classfox.storage import Store


def test_legacy_import_is_repeatable_preserves_files_and_handles_midnight(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    (legacy / "cite").mkdir(parents=True)
    (legacy / "summaries").mkdir()
    text = "\n".join(
        [
            "=== 课堂记录 开始于 2026-09-21 23:50:00 ===",
            "课程：数据库",
            "=== 历史摘要 开始 ===",
            "之前学习了事务。",
            "=== 历史摘要 结束 ===",
            "[23:59:30] 这是昨天的内容。",
            "[00:00:30] 这是今天的内容。",
        ]
    )
    (legacy / "class_transcript.txt").write_text(text, encoding="utf-8")
    (legacy / "cite/course.txt").write_text("课程资料", encoding="utf-8")
    (legacy / "summaries/note.md").write_text("# 上一次笔记\n保留我的笔记。", encoding="utf-8")
    store = Store(tmp_path / "new.sqlite3")
    first = import_legacy_data(legacy, store)
    second = import_legacy_data(legacy, store)
    assert first.session_id == second.session_id
    assert len(store.list_sessions()) == 2
    assert len(store.list_materials()) == 1
    assert first.session_id is not None
    entries = store.list_entries(first.session_id)
    assert [entry.text for entry in entries] == ["这是昨天的内容。", "这是今天的内容。"]
    assert (entries[1].created_at - entries[0].created_at).total_seconds() == 60
    assert store.list_summaries(first.session_id)[0].markdown == "之前学习了事务。"
    assert (legacy / "class_transcript.txt").read_text(encoding="utf-8") == text
    assert len(store.list_entries(first.session_id)) == 2
    store.close()


def test_missing_legacy_folder_reports_error_without_creating_a_session(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite3")
    with pytest.raises(ValueError, match="目录"):
        import_legacy_data(tmp_path / "missing", store)
    assert store.list_sessions() == []
    store.close()


def test_legacy_import_does_not_follow_symlinks_outside_selected_folder(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    (legacy / "cite").mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("synthetic private fixture", encoding="utf-8")
    (legacy / "cite/linked.txt").symlink_to(outside)
    store = Store(tmp_path / "db.sqlite3")
    result = import_legacy_data(legacy, store)
    assert store.list_materials() == []
    assert result.skipped_files == ["cite/linked.txt"]
    store.close()


def test_database_failure_rolls_back_entire_import_and_allows_retry(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "class_transcript.txt").write_text("[12:00:00] 第一条\n[12:00:01] 第二条", encoding="utf-8")
    path = tmp_path / "db.sqlite3"
    store = Store(path)
    with sqlite3.connect(path) as fault:
        fault.execute(
            "CREATE TRIGGER fail_import BEFORE INSERT ON transcript_entries WHEN NEW.text = '第二条' BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        import_legacy_data(legacy, store)
    assert store.list_sessions() == []
    with sqlite3.connect(path) as fault:
        fault.execute("DROP TRIGGER fail_import")
    result = import_legacy_data(legacy, store)
    assert result.session_id is not None
    assert len(store.list_entries(result.session_id)) == 2
    store.close()
