import base64
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import httpx
import pytest
from openai.types.chat import ChatCompletionMessageParam
from pydantic import JsonValue, ValidationError

from classfox.app import create_app
from classfox.assistant import Assistant, AssistantJob
from classfox.assistant_context import TaskRequest
from classfox.audio import AudioError
from classfox.config import RuntimeConfig
from classfox.model_process import ModelEndpoint
from classfox.phone_commands import COMMAND, Audio, CreateSession, PhoneClassrooms, StartAssistant
from classfox.phone_pairing import PairingDenied
from classfox.settings import ASRSettings, LLMSettings, Preferences
from tests.test_audio_runtime import NoCredentials
from tests.test_llm import delta


@pytest.fixture
async def rooms(tmp_path: Path) -> AsyncIterator[PhoneClassrooms]:
    def provider(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Phone must not use an online provider")

    app = create_app(RuntimeConfig(data_dir=tmp_path, api_token="synthetic"), credentials=NoCredentials(), provider_transport=httpx.MockTransport(provider))
    async with app.router.lifespan_context(app):
        yield app.state.phone_gateway.classrooms


def guard() -> None:
    pass


async def test_manual_text_remains_available_while_phone_audio_is_paused(rooms: PhoneClassrooms) -> None:
    await rooms.dispatch("phone:a", CreateSession(operation="create", course_name="暂停后文字记录"), guard)
    session = rooms.store.list_sessions(owner_id="phone:a")[0]
    await rooms.dispatch("phone:a", COMMAND.validate_python({"operation": "pause", "session_id": session.id}), guard)
    payload = {"operation": "append", "session_id": session.id, "text": "手动补充", "source_id": "manual:1"}
    await rooms.dispatch("phone:a", COMMAND.validate_python(payload), guard)
    assert rooms.store.get_session(session.id).status == "paused"
    assert rooms.store.list_entries(session.id)[0].text == "手动补充"
    with pytest.raises(ValueError, match="结束或暂停"):
        rooms.store.accept_audio(session.id, "late:1", "synthetic-digest", "迟到语音")
    await rooms.dispatch("phone:a", COMMAND.validate_python({"operation": "stop", "session_id": session.id}), guard)
    with pytest.raises(ValueError, match="结束或暂停"):
        await rooms.dispatch("phone:a", COMMAND.validate_python({**payload, "source_id": "manual:2"}), guard)


async def test_every_session_operation_is_owner_scoped(rooms: PhoneClassrooms) -> None:
    desktop = rooms.store.create_session("桌面资料课堂")
    phone_b = rooms.store.create_session("另一台手机", owner_id="phone:b")
    for session in (desktop, phone_b):
        rooms.store.append_entry(session.id, "其他用户的原文")
        rooms.store.save_summary(session.id, "笔记", "其他用户笔记")
        for operation in ["pause", "resume", "stop", "notes", "export", "entries", "append", "audio", "assistant.start"]:
            payload: dict[str, JsonValue] = {"operation": operation, "session_id": session.id}
            if operation == "append":
                payload.update(text="不该写入", source_id="malicious")
            if operation == "audio":
                payload.update(pcm=base64.b64encode(bytes(320)).decode(), source_id="malicious")
            if operation == "assistant.start":
                payload["task"] = {"kind": "summary"}
            with pytest.raises(KeyError):
                await rooms.dispatch("phone:a", COMMAND.validate_python(payload), guard)
        assert rooms.store.get_session(session.id).status == "recording"
        assert len(rooms.store.list_entries(session.id)) == 1
        job = rooms.assistant.start(session.id, TaskRequest(kind="summary"), owner_id=session.owner_id)
        for operation in ["assistant.get", "assistant.cancel"]:
            with pytest.raises(KeyError):
                await rooms.dispatch("phone:a", COMMAND.validate_python({"operation": operation, "job_id": job.id}), guard)


@pytest.mark.parametrize("extra", [{"owner_id": "desktop"}, {"material_id": "a" * 32}, {"source": "microphone"}, {"settings": {"owner_id": "desktop"}}])
def test_phone_creation_rejects_desktop_privileges(extra: dict[str, JsonValue]) -> None:
    with pytest.raises(ValidationError):
        COMMAND.validate_python({"operation": "create", "course_name": "课堂", **extra})


@pytest.mark.parametrize("llm", [LLMSettings(mode="byok"), LLMSettings(managed=False)])
async def test_phone_never_uses_desktop_byok_or_unmanaged_models(rooms: PhoneClassrooms, llm: LLMSettings) -> None:
    settings = rooms.classroom.settings
    settings.save(Preferences(llm=llm, asr=ASRSettings(mode="dashscope")))
    session = rooms.store.create_session("手机课堂", owner_id="phone:a")
    rooms.store.append_entry(session.id, "测试原文")
    with pytest.raises(ValueError, match="受管本地"):
        await rooms.dispatch("phone:a", StartAssistant(operation="assistant.start", session_id=session.id, task=TaskRequest(kind="summary")), guard)
    with pytest.raises(AudioError, match="离线"):
        await rooms.speech.transcribe(bytes(320), local_only=True)
    assert rooms.assistant.list_jobs(owner_id="phone:a") == []


async def test_model_settings_are_snapshotted_before_later_byok_change(rooms: PhoneClassrooms) -> None:
    async def local_model(_model_id: str) -> ModelEndpoint:
        rooms.classroom.settings.save(Preferences(llm=LLMSettings(mode="byok", base_url="https://provider.example/v1")))
        return ModelEndpoint(base_url="http://127.0.0.1:18888/v1", key="synthetic-local", model="offline")

    calls: list[str] = []

    def provider(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "127.0.0.1"
        assert request.headers["Authorization"] == "Bearer synthetic-local"
        calls.append(request.url.path)
        return httpx.Response(200, content=delta("合成离线结果") + delta(finish="stop") + b"data: [DONE]\n\n")

    from classfox.llm import LLMService

    rooms.assistant.llm = LLMService(NoCredentials(), local_model=local_model, transport=httpx.MockTransport(provider))
    session = rooms.store.create_session("手机课堂", owner_id="phone:a")
    rooms.store.append_entry(session.id, "测试原文")
    result = await rooms.dispatch("phone:a", StartAssistant(operation="assistant.start", session_id=session.id, task=TaskRequest(kind="summary")), guard)
    job_id = cast(dict[str, str], result["job"])["id"]
    await rooms.assistant.wait(job_id)
    assert rooms.assistant.get(job_id, owner_id="phone:a").status == "completed"
    assert len(calls) == 1


async def test_revocation_after_recognition_prevents_late_audio_write(rooms: PhoneClassrooms, monkeypatch: pytest.MonkeyPatch) -> None:
    result = await rooms.dispatch("phone:a", CreateSession(operation="create", course_name="手机课堂"), guard)
    session_id = cast(dict[str, str], result["session"])["id"]
    allowed = True

    async def recognize(_pcm: bytes, *, local_only: bool = False) -> str:
        nonlocal allowed
        assert local_only
        allowed = False
        return "不应在撤销后保存"

    def check() -> None:
        if not allowed:
            raise PairingDenied

    monkeypatch.setattr(rooms.speech, "transcribe", recognize)
    with pytest.raises(PairingDenied):
        await rooms.dispatch("phone:a", Audio(operation="audio", session_id=session_id, source_id="fragment", pcm=base64.b64encode(bytes(320)).decode()), check)
    assert rooms.store.list_entries(session_id) == []


async def test_expired_summary_cannot_save_after_model_returns(rooms: PhoneClassrooms, monkeypatch: pytest.MonkeyPatch) -> None:
    allowed = True

    async def finish(_self: Assistant, job: AssistantJob, _messages: list[ChatCompletionMessageParam], _settings: LLMSettings, _started: float) -> None:
        nonlocal allowed
        job.markdown = "不应写入的过期总结"
        allowed = False

    def check() -> None:
        if not allowed:
            raise PairingDenied

    monkeypatch.setattr(Assistant, "_stream_answer", finish)
    session = rooms.store.create_session("手机课堂", owner_id="phone:a")
    rooms.store.append_entry(session.id, "原文仍保存")
    job = rooms.assistant.start(session.id, TaskRequest(kind="summary"), owner_id="phone:a", local_only=True, guard=check)
    await rooms.assistant.wait(job.id)
    assert rooms.store.list_summaries(session.id) == []
    assert len(rooms.store.list_entries(session.id)) == 1
