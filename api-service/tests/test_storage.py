import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from classfox.storage import Store


def test_new_database_is_private_to_current_user(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("Windows permissions are enforced by user profile ACLs")
    path = tmp_path / "private-data" / "classfox.sqlite3"
    store = Store(path)
    try:
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    finally:
        store.close()


def test_sessions_preserve_raw_transcripts_after_summary_and_restart(tmp_path: Path) -> None:
    path = tmp_path / "classfox.sqlite3"
    store = Store(path)
    first = store.create_session("第一课")
    entry = store.append_entry(first.id, "老师刚才讲了事务的原子性。")
    store.save_summary(first.id, "课堂笔记", "# 事务\n原子性是核心属性。")
    store.finish_session(first.id)
    second = store.create_session("第二课")
    store.append_entry(second.id, "这是第二课。")
    store.close()

    reopened = Store(path)
    assert [item.id for item in reopened.list_entries(first.id)] == [entry.id]
    assert reopened.list_entries(first.id)[0].text == "老师刚才讲了事务的原子性。"
    assert reopened.get_session(first.id).status == "stopped"
    assert len(reopened.list_sessions()) == 2
    assert len(reopened.list_summaries(first.id)) == 1
    reopened.close()


def test_recent_entries_exclude_old_and_future_records_at_midnight(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite3")
    session = store.create_session("午夜课")
    now = datetime(2026, 9, 22, 0, 1, tzinfo=UTC)
    for text, age in [("旧内容", 31), ("刚才内容", 1.5), ("现在内容", 0.5), ("未来内容", -1)]:
        store.append_entry(session.id, text, at=now - timedelta(minutes=age))
    assert [item.text for item in store.recent_entries(session.id, minutes=2, now=now)] == ["刚才内容", "现在内容"]
    store.close()


def test_late_callback_cannot_append_to_finished_session(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite3")
    session = store.create_session("已下课")
    store.finish_session(session.id)
    with pytest.raises(ValueError, match="课堂已结束"):
        store.append_entry(session.id, "迟到的识别结果")
    assert store.list_entries(session.id) == []
    store.close()


def test_idempotency_key_deduplicates_retries_without_dropping_repeated_speech(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite3")
    session = store.create_session("测试")
    first = store.append_entry(session.id, "非常重要", source_id="frame-1")
    retry = store.append_entry(session.id, "非常重要", source_id="frame-1")
    second = store.append_entry(session.id, "非常重要", source_id="frame-2")
    assert retry.id == first.id
    assert second.id != first.id
    assert len(store.list_entries(session.id)) == 2
    store.close()


def test_material_lookup_is_an_id_not_a_path(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite3")
    material = store.add_material("课程.pdf", "课堂参考资料")
    assert store.get_material(material.id).text == "课堂参考资料"
    with pytest.raises(KeyError):
        store.get_material("../outside-fixture.txt")
    store.close()


def test_summary_failure_does_not_replace_existing_summary(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite3")
    session = store.create_session("测试")
    existing = store.save_summary(session.id, "有效笔记", "# 已生成")
    with pytest.raises(ValueError):
        store.save_summary(session.id, "空笔记", "   ")
    assert [item.id for item in store.list_summaries(session.id)] == [existing.id]
    store.close()


def test_restart_recovers_interrupted_recording_without_losing_transcript(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite3"
    store = Store(path)
    session = store.create_session("意外退出的课")
    store.append_entry(session.id, "退出前已保存的内容")
    store.close()
    recovered = Store(path)
    assert recovered.recover_interrupted_sessions() == 1
    assert recovered.get_session(session.id).status == "interrupted"
    assert recovered.list_entries(session.id)[0].text == "退出前已保存的内容"
    assert recovered.recover_interrupted_sessions() == 0
    recovered.close()
