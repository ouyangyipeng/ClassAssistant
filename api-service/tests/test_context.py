from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from classfox.assistant_context import ContextSnapshot, TaskRequest, answer_messages, summary_chunks
from classfox.settings import LLMSettings
from classfox.storage import Store


def test_rescue_uses_recent_context_within_budget_and_keeps_latest_question(tmp_path: Path) -> None:
    store = Store(tmp_path / "test.sqlite3")
    material = store.add_material("notes.txt", "无关章节\n" * 1000 + "\n二叉树的遍历\n前序：根左右\n" * 10)
    session = store.create_session("数据结构", material_id=material.id)
    now = datetime.now(UTC)
    store.append_entry(session.id, "过期内容", at=now - timedelta(minutes=10))
    for index in range(20):
        store.append_entry(session.id, f"二叉树遍历{index} " + "内容" * 100)
    request = TaskRequest(kind="rescue", question="二叉树的前序是什么？")
    snapshot = ContextSnapshot.capture(store, session.id, "desktop")
    messages = answer_messages(store, snapshot, request, LLMSettings(context_characters=1200))
    contents = [str(message["content"]) for message in messages]
    assert sum(map(len, contents)) <= 1200
    assert contents[-1] == request.question
    assert "过期内容" not in "".join(contents)
    assert "二叉树遍历19" in "".join(contents)
    assert "前序：根左右" in "".join(contents)
    store.close()


def test_summary_pages_every_entry_and_excludes_later_arrivals(tmp_path: Path) -> None:
    store = Store(tmp_path / "test.sqlite3")
    session = store.create_session("长课堂")
    for index in range(1101):
        store.append_entry(session.id, f"marker-{index:04d}")
    snapshot = ContextSnapshot.capture(store, session.id, "desktop")
    store.append_entry(session.id, "later-arrival")
    chunks = list(summary_chunks(store, snapshot, characters=800))
    assert all(len(chunk) <= 800 for chunk in chunks)
    whole = "\n".join(chunks)
    for index in range(1101):
        assert whole.count(f"marker-{index:04d}") == 1
    assert "later-arrival" not in whole
    assert len(store.list_entries(session.id, limit=2000)) == 1102
    store.close()


def test_snapshot_requires_owner_and_does_not_leak_other_class(tmp_path: Path) -> None:
    store = Store(tmp_path / "test.sqlite3")
    session = store.create_session("手机课堂", owner_id="phone-one")
    with pytest.raises(KeyError):
        ContextSnapshot.capture(store, session.id, "desktop")
    store.close()
