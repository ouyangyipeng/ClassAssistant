import asyncio
import json
from pathlib import Path

import httpx
import pytest

from classfox.assistant import Assistant
from classfox.assistant_context import TaskRequest
from classfox.events import EventBus
from classfox.llm import LLMError, LLMService
from classfox.settings import LLMSettings, Preferences, SettingsStore
from classfox.storage import Store
from tests.test_llm import ControlledStream, TestCredentials, delta


def assistant(tmp_path: Path, transport: httpx.MockTransport, *, context_characters: int = 16000) -> Assistant:
    store = Store(tmp_path / "test.sqlite3")
    settings = SettingsStore(tmp_path / "preferences.json")
    settings.save(Preferences(llm=LLMSettings(mode="byok", base_url="https://provider.example/v1", model="test-model", context_characters=context_characters)))
    return Assistant(store, settings, EventBus(), LLMService(TestCredentials(), transport=transport))


async def test_connection_probe_uses_only_fixed_prompt_and_never_saves_a_classroom_note(tmp_path: Path) -> None:
    requests: list[dict[str, object]] = []

    def provider(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, content=delta("连接成功", finish="stop") + b"data: [DONE]\n\n")

    service = assistant(tmp_path, httpx.MockTransport(provider))
    try:
        session = service.store.create_session("Private synthetic class")
        service.store.append_entry(session.id, "Do not send this transcript in a connection test")
        result = await service.probe()
        assert result["ok"] and result["first_token_ms"]
        assert requests[0]["max_tokens"] == 48
        assert "Do not send" not in json.dumps(requests)
        assert not service.store.list_summaries(session.id)
        assert not service.list_jobs()
    finally:
        await service.close()
        service.store.close()


async def test_failed_probe_releases_gate_and_reports_sanitized_errors(tmp_path: Path) -> None:
    service = assistant(tmp_path, httpx.MockTransport(lambda request: httpx.Response(401, json={"error": {"message": "synthetic-key"}})))
    try:
        for _ in range(2):
            with pytest.raises(LLMError, match="凭据") as failure:
                await service.probe()
            assert "synthetic-key" not in str(failure.value)
    finally:
        await service.close()
        service.store.close()


async def test_job_streams_before_completion_and_is_owner_scoped(tmp_path: Path) -> None:
    body = ControlledStream()
    service = assistant(tmp_path, httpx.MockTransport(lambda request: httpx.Response(200, stream=body)))
    session = service.store.create_session("课堂")
    service.store.append_entry(session.id, "二叉树是什么")
    subscription = service.events.subscribe("desktop")
    job = service.start(session.id, TaskRequest(kind="rescue"))
    async with asyncio.timeout(20):
        while (event := await subscription.queue.get()).type != "assistant.delta":
            pass
    assert event.data["text"] == "先回答"
    assert service.get(job.id).status == "running"
    assert service.get(job.id).first_token_ms is not None
    with pytest.raises(KeyError):
        service.get(job.id, owner_id="phone-other")
    body.release.set()
    await service.wait(job.id)
    assert service.get(job.id).status == "completed"
    assert service.get(job.id).markdown == "先回答，再解释。"
    assert not service.store.list_summaries(session.id)
    await service.close()
    service.store.close()


async def test_failed_summary_keeps_original_and_creates_no_note(tmp_path: Path) -> None:
    service = assistant(tmp_path, httpx.MockTransport(lambda request: httpx.Response(401, json={"error": {"message": "private-key"}})))
    session = service.store.create_session("失败总结")
    service.store.append_entry(session.id, "完整原文")
    service.store.finish_session(session.id)
    job = service.start(session.id, TaskRequest(kind="summary"))
    await service.wait(job.id)
    result = service.get(job.id)
    assert result.status == "failed"
    assert result.error_code == "invalid_key"
    assert "private-key" not in result.model_dump_json()
    assert service.store.list_entries(session.id)[0].text == "完整原文"
    assert not service.store.list_summaries(session.id)
    assert service.store.get_session(session.id).status == "stopped"
    await service.close()
    service.store.close()


async def test_cancel_closes_stream_without_blocking_next_class(tmp_path: Path) -> None:
    body = ControlledStream()
    service = assistant(tmp_path, httpx.MockTransport(lambda request: httpx.Response(200, stream=body)))
    session = service.store.create_session("原课堂")
    service.store.append_entry(session.id, "第一堂原文")
    job = service.start(session.id, TaskRequest(kind="summary"))
    await service.cancel(job.id)
    assert service.get(job.id).status == "cancelled"
    next_class = service.store.create_session("下一堂")
    service.store.append_entry(next_class.id, "下一堂原文")
    assert not service.store.list_summaries(next_class.id)
    assert not service.store.list_summaries(session.id)
    await service.close()
    service.store.close()


async def test_long_summary_covers_all_entries_with_bounded_requests(tmp_path: Path) -> None:
    payloads: list[list[str]] = []

    def provider(request: httpx.Request) -> httpx.Response:
        payloads.append([message["content"] for message in json.loads(request.content)["messages"]])
        return httpx.Response(200, content=delta("课堂要点。") + delta(finish="stop") + b"data: [DONE]\n\n")

    service = assistant(tmp_path, httpx.MockTransport(provider), context_characters=1200)
    session = service.store.create_session("完整课堂")
    for index in range(1101):
        service.store.append_entry(session.id, f"marker-{index:04d}")
    job = service.start(session.id, TaskRequest(kind="summary"))
    service.store.append_entry(session.id, "later-arrival")
    await service.wait(job.id)
    assert service.get(job.id).status == "completed"
    assert len(payloads) > 1
    all_prompts = json.dumps(payloads, ensure_ascii=False)
    for index in range(1101):
        assert f"marker-{index:04d}" in all_prompts
    assert "later-arrival" not in all_prompts
    for payload in payloads:
        assert sum(map(len, payload)) <= 1200
    assert service.store.list_summaries(session.id)[0].markdown == "课堂要点。"
    assert service.get(job.id).through_entry_id == 1101
    await service.close()
    service.store.close()
