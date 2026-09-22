import asyncio
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from classfox.app import create_app
from classfox.asr_providers import SpeechConfig
from classfox.audio import AudioError, pcm_to_wav
from classfox.config import RuntimeConfig
from classfox.credentials import CredentialName
from classfox.events import EventBus
from classfox.models import Session, SessionCreate
from classfox.runtime import Classroom
from classfox.settings import ASRSettings, Preferences, SettingsStore
from classfox.speech import SpeechService
from classfox.speech_process import SpeechEvent, SpeechProcess
from classfox.storage import Store


class NoCredentials:
    def get(self, name: CredentialName) -> None:
        raise AssertionError("No test should read the system credential store")

    def set(self, name: CredentialName, value: str | None) -> None:
        raise AssertionError("No test should update credentials")


class SyntheticSpeech(SpeechService):
    def __init__(self, script: Path) -> None:
        self.script = script
        self.captures: list[SpeechProcess] = []
        self.callbacks: list[SpeechEvent] = []

    async def microphone(self, emit: SpeechEvent) -> SpeechProcess:
        from classfox.speech_worker import WorkerRequest

        process = SpeechProcess(emit, command=[sys.executable, "-u", str(self.script)])
        self.callbacks.append(emit)
        self.captures.append(process)
        await process.start(WorkerRequest(action="microphone", config=SpeechConfig(settings=ASRSettings())))
        return process

    async def release(self, process: SpeechProcess) -> None:
        await process.close()


async def test_pause_flush_resume_and_old_worker_cannot_cross_sessions(tmp_path: Path) -> None:
    script = tmp_path / "capture.py"
    script.write_text("""import json,sys,uuid
sys.stdin.readline()
print(json.dumps({'type':'ready'}),flush=True)
sys.stdin.readline()
print(json.dumps({'type':'transcript','text':'末尾课堂知识','source_id':uuid.uuid4().hex}),flush=True)
print(json.dumps({'type':'done'}),flush=True)
""")
    settings = SettingsStore(tmp_path / "settings.json")
    speech = SyntheticSpeech(script)
    store = Store(tmp_path / "test.sqlite3")
    room = Classroom(store, settings, EventBus(), speech)
    try:
        first = await room.start(SessionCreate())
        assert first.status == "recording"
        assert (await room.pause(first.id)).status == "paused"
        assert len(store.list_entries(first.id)) == 1
        assert speech.captures[0].pid is None
        await room.resume(first.id)
        await room.resume(first.id)
        assert len(speech.captures) == 2
        await room.stop(first.id)
        assert len(store.list_entries(first.id)) == 2
        second = await room.start(SessionCreate(source="text"))
        speech.callbacks[0]({"type": "transcript", "text": "旧识别结果", "source_id": "stale"})
        speech.callbacks[0]({"type": "error", "message": "旧连接断开", "code": "old"})
        assert store.list_entries(second.id) == []
        current = room.current()
        assert current is not None and current.status == "recording"
    finally:
        await room.close()
        store.close()


async def test_missing_speech_model_leaves_recoverable_error_and_no_capture(tmp_path: Path) -> None:
    app = create_app(RuntimeConfig(data_dir=tmp_path, api_token="synthetic"), credentials=NoCredentials())
    async with app.router.lifespan_context(app):
        room: Classroom = app.state.classroom
        with pytest.raises(AudioError, match="安装"):
            await room.start(SessionCreate())
        current = room.current()
        assert current is not None and current.status == "error"
        assert (await room.stop(current.id)).status == "stopped"
        assert (await room.start(SessionCreate(source="text"))).status == "recording"


async def test_audio_upload_deduplicates_after_stop_and_rejects_mutated_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def transcribe(_speech: SpeechService, _pcm: bytes) -> str:
        nonlocal calls
        calls += 1
        return "考试重点"

    monkeypatch.setattr(SpeechService, "transcribe", transcribe)
    app = create_app(RuntimeConfig(data_dir=tmp_path, api_token="synthetic"), credentials=NoCredentials())
    SettingsStore(tmp_path / "preferences.json").save(Preferences(auto_summary=False))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app), base_url="http://localhost", headers={"Authorization": "Bearer synthetic"}) as client,
    ):
        session = (await client.post("/api/v2/sessions", json={"source": "remote"})).json()
        path = f"/api/v2/sessions/{session['id']}"
        data = {"source_id": "audio-1"}
        files = {"file": ("recording.wav", pcm_to_wav(b"\0\0" * 1600), "audio/wav")}
        first = await client.post(f"{path}/audio", data=data, files=files)
        assert first.status_code == 200 and first.json()["entry"]["text"] == "考试重点"
        await client.post(f"{path}/stop")
        retry = await client.post(f"{path}/audio", data=data, files=files)
        assert retry.status_code == 200 and retry.json()["duplicate"]
        different = await client.post(f"{path}/audio", data=data, files={"file": ("audio.wav", pcm_to_wav(b"\1\0" * 1600), "audio/wav")})
        assert different.status_code == 409
        assert calls == 1 and len((await client.get(f"{path}/entries")).json()) == 1
        assert (await client.post(f"{path}/audio", data={"source_id": "bad"}, files={"file": ("bad.wav", b"wrong")})).status_code == 422


async def test_inflight_audio_cannot_enter_a_new_or_paused_class(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    entered, release = asyncio.Event(), asyncio.Event()

    async def transcribe(_speech: SpeechService, _pcm: bytes) -> str:
        entered.set()
        await release.wait()
        return "延迟识别的旧课"

    monkeypatch.setattr(SpeechService, "transcribe", transcribe)
    app = create_app(RuntimeConfig(data_dir=tmp_path, api_token="synthetic"), credentials=NoCredentials())
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app), base_url="http://localhost", headers={"Authorization": "Bearer synthetic"}) as client,
    ):
        first = (await client.post("/api/v2/sessions", json={"source": "remote"})).json()["id"]
        task = asyncio.create_task(
            client.post(
                f"/api/v2/sessions/{first}/audio",
                data={"source_id": "delayed"},
                files={"file": ("audio.wav", pcm_to_wav(b"\0\0" * 1600), "audio/wav")},
            )
        )
        await asyncio.wait_for(entered.wait(), 1)
        await client.post(f"/api/v2/sessions/{first}/stop")
        second = (await client.post("/api/v2/sessions", json={"source": "text"})).json()["id"]
        release.set()
        assert (await task).status_code == 409
        assert (await client.get(f"/api/v2/sessions/{second}/entries")).json() == []


def test_silent_audio_receipt_is_persistent_and_idempotent(tmp_path: Path) -> None:
    store = Store(tmp_path / "test.sqlite3")
    session = store.create_session("安静课堂")
    assert store.accept_audio(session.id, "silence", "same-digest", "") == (None, True)
    store.close()
    store = Store(tmp_path / "test.sqlite3")
    try:
        assert store.accept_audio(session.id, "silence", "same-digest", "") == (None, False)
        assert store.list_entries(session.id) == []
    finally:
        store.close()


@pytest.mark.parametrize("action", ["pause", "stop"])
async def test_stop_or_pause_cancels_owned_microphone_before_startup_timeout(tmp_path: Path, action: str) -> None:
    script = tmp_path / "slow_start.py"
    script.write_text("import sys,time\nsys.stdin.readline()\ntime.sleep(60)\n")
    speech = SyntheticSpeech(script)
    store = Store(tmp_path / "test.sqlite3")
    room = Classroom(store, SettingsStore(tmp_path / "settings.json"), EventBus(), speech)
    pending = asyncio.create_task(room.start(SessionCreate()))
    try:
        async with asyncio.timeout(3):
            while not speech.captures or speech.captures[0].pid is None:
                await asyncio.sleep(0.01)
        current = room.current()
        assert current is not None and current.status == "starting"
        result = await asyncio.wait_for(room.pause(current.id) if action == "pause" else room.stop(current.id), 3)
        assert result.status == ("paused" if action == "pause" else "stopped")
        with pytest.raises(AudioError, match="启动已取消"):
            await pending
        assert speech.captures[0].pid is None
        if action == "pause":
            await room.stop(current.id)
        assert (await room.start(SessionCreate(source="text"))).status == "recording"
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await room.close()
        store.close()


async def test_repeated_stop_does_not_interrupt_startup_cleanup(tmp_path: Path) -> None:
    entered, cleaning, release, cleaned = (asyncio.Event() for _ in range(4))

    class DelayedCleanup(SpeechService):
        def __init__(self) -> None:
            pass

        async def microphone(self, emit: SpeechEvent) -> SpeechProcess:
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()
                cleaned.set()
            raise AssertionError("Unreachable")

    store = Store(tmp_path / "test.sqlite3")
    room = Classroom(store, SettingsStore(tmp_path / "settings.json"), EventBus(), DelayedCleanup())
    pending = asyncio.create_task(room.start(SessionCreate()))
    stopping: list[asyncio.Task[Session]] = []
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert room.active_id is not None
        stopping.append(asyncio.create_task(room.stop(room.active_id)))
        await asyncio.wait_for(cleaning.wait(), 1)
        stopping.append(asyncio.create_task(room.stop(room.active_id)))
        await asyncio.sleep(0)
        release.set()
        assert all(session.status == "stopped" for session in await asyncio.wait_for(asyncio.gather(*stopping), 1))
        assert cleaned.is_set()
        with pytest.raises(AudioError, match="启动已取消"):
            await pending
    finally:
        release.set()
        await asyncio.gather(pending, *stopping, return_exceptions=True)
        await room.close()
        store.close()
