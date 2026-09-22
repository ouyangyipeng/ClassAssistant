import asyncio
from contextlib import suppress

from classfox.audio import AudioError
from classfox.events import Event, EventBus
from classfox.models import Session, SessionCreate, TranscriptEntry
from classfox.settings import SettingsStore
from classfox.speech import SpeechService
from classfox.speech_process import SpeechProcess
from classfox.storage import Store


class Classroom:
    def __init__(self, store: Store, settings: SettingsStore, events: EventBus, speech: SpeechService | None = None) -> None:
        self.store = store
        self.settings = settings
        self.events = events
        self.active_id: str | None = None
        self.source = "text"
        self._lock = asyncio.Lock()
        self.audio_upload_lock = asyncio.Lock()
        self.speech = speech
        self._capture: SpeechProcess | None = None
        self._starting: asyncio.Task[SpeechProcess] | None = None
        self._startup_cancelled = False

    def current(self) -> Session | None:
        return self.store.get_session(self.active_id) if self.active_id else None

    async def start(self, request: SessionCreate) -> Session:
        async with self._lock:
            if self.active_id is not None:
                raise ValueError("已有课堂正在进行，请先停止当前课堂")
            if request.material_id:
                self.store.get_material(request.material_id)
            if request.source == "microphone" and self.speech is None:
                raise ValueError("音频采集尚未就绪，请先配置识别模型和麦克风")
            session = self.store.create_session(request.course_name, material_id=request.material_id)
            self.active_id = session.id
            self.source = request.source
            if self.source == "microphone":
                await self._start_audio(session.id)
                session = self.store.get_session(session.id)
            self._state_event(session)
            return session

    async def _start_audio(self, session_id: str) -> None:
        assert self.speech is not None
        self._state_event(self.store.set_status(session_id, "starting"))
        self._startup_cancelled = False
        self._starting = asyncio.create_task(self.speech.microphone(lambda event: self._audio_event(session_id, event)), name=f"microphone-{session_id}")
        try:
            self._capture = await self._starting
            self._capture.check()
            self.store.set_status(session_id, "recording")
        except asyncio.CancelledError:
            self._state_event(self.store.set_status(session_id, "paused" if self._startup_cancelled else "error"))
            if self._startup_cancelled:
                raise AudioError("录音启动已取消，课堂原文仍已保留", code="startup_cancelled") from None
            raise
        except BaseException:
            self._state_event(self.store.set_status(session_id, "error"))
            raise
        finally:
            self._starting = None
            self._startup_cancelled = False

    def _cancel_startup(self, session_id: str) -> None:
        # Stop must interrupt the owned startup before waiting for its transition lock.
        if self.active_id == session_id and self._starting is not None and not self._starting.done() and not self._starting.cancelling():
            self._startup_cancelled = True
            self._starting.cancel()

    def _audio_event(self, session_id: str, event: dict[str, object]) -> None:
        if self.active_id != session_id:
            return
        kind = event["type"]
        if kind == "transcript":
            self.ingest(session_id, str(event["text"]), str(event["source_id"]))
        elif kind == "error":
            try:
                self._state_event(self.store.set_status(session_id, "error"))
            finally:
                self.events.publish("desktop", Event(type="audio.error", session_id=session_id, data=event))
        elif kind in {"partial", "level"}:
            self.events.publish("desktop", Event(type=f"audio.{kind}", session_id=session_id, data=event))

    async def _stop_audio(self, session_id: str) -> None:
        capture, self._capture = self._capture, None
        if capture is None:
            return
        assert self.speech is not None
        self.events.publish("desktop", Event(type="audio.stopping", session_id=session_id, data={}))
        try:
            await capture.stop()
        finally:
            await self.speech.release(capture)

    def _state_event(self, session: Session) -> None:
        self.events.publish(session.owner_id, Event(type="session", session_id=session.id, data=session.model_dump(mode="json")))

    def _require_active(self, session_id: str) -> Session:
        session = self.store.get_session(session_id, owner_id="desktop")
        if self.active_id != session_id:
            raise ValueError("此课堂不在录音，请开始或选择当前课堂")
        return session

    async def pause(self, session_id: str) -> Session:
        self._cancel_startup(session_id)
        async with self._lock:
            self._require_active(session_id)
            if self.store.get_session(session_id).status == "paused":
                return self.store.get_session(session_id)
            try:
                await self._stop_audio(session_id)
            except AudioError as error:
                self._audio_event(session_id, {"type": "error", "code": error.code, "message": str(error)})
                raise
            session = self.store.set_status(session_id, "paused")
            self._state_event(session)
            return session

    async def resume(self, session_id: str) -> Session:
        async with self._lock:
            self._require_active(session_id)
            if self.store.get_session(session_id).status == "recording":
                return self.store.get_session(session_id)
            if self.source == "microphone":
                with suppress(AudioError):
                    await self._stop_audio(session_id)
                await self._start_audio(session_id)
            session = self.store.set_status(session_id, "recording")
            self._state_event(session)
            return session

    async def stop(self, session_id: str) -> Session:
        self._cancel_startup(session_id)
        async with self._lock:
            session = self.store.get_session(session_id, owner_id="desktop")
            if session.status == "stopped":
                return session
            self._require_active(session_id)
            try:
                await self._stop_audio(session_id)
            except AudioError as error:
                self.events.publish("desktop", Event(type="audio.error", session_id=session_id, data={"code": error.code, "message": str(error)}))
            session = self.store.finish_session(session_id)
            self.active_id = None
            self._state_event(session)
            return session

    def ingest(self, session_id: str, text: str, source_id: str) -> TranscriptEntry:
        session = self._require_active(session_id)
        previous = self.store.find_entry(session_id, source_id)
        entry = self.store.append_entry(session_id, text, source_id=source_id)
        if previous is not None:
            return entry
        self.publish_entry(session, entry)
        return entry

    def publish_entry(self, session: Session, entry: TranscriptEntry) -> None:
        session_id, text = session.id, entry.text
        self.events.publish(session.owner_id, Event(type="transcript", session_id=session_id, data=entry.model_dump(mode="json")))
        preferences = self.settings.load()
        for level, keywords in [("danger", preferences.keywords), ("warning", preferences.warning_keywords)]:
            hits = [keyword for keyword in keywords if keyword.casefold() in text.casefold()]
            if hits:
                self.events.publish(
                    session.owner_id, Event(type="alert", session_id=session_id, data={"entry_id": entry.id, "level": level, "keywords": hits, "text": text})
                )
                break

    async def close(self) -> None:
        if self.active_id:
            await self.stop(self.active_id)
