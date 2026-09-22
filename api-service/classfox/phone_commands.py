import base64
import hashlib
from collections.abc import Callable
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

from classfox.assistant import Assistant
from classfox.assistant_context import TaskRequest
from classfox.audio import AudioError, validate_pcm
from classfox.models import TextInput
from classfox.runtime import Classroom
from classfox.speech import SpeechService

Identifier = Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Hello(Command):
    operation: Literal["hello"]
    name: str = Field(min_length=1, max_length=40)


class Status(Command):
    operation: Literal["status"]


class ListSessions(Command):
    operation: Literal["sessions"]
    offset: int = Field(default=0, ge=0, le=100000)


class CreateSession(Command):
    operation: Literal["create"]
    course_name: str = Field(min_length=1, max_length=120)


class SessionCommand(Command):
    operation: Literal["pause", "resume", "stop", "export"]
    session_id: Identifier


class Notes(Command):
    operation: Literal["notes"]
    session_id: Identifier
    offset: int = Field(default=0, ge=0, le=100000)


class Entries(Command):
    operation: Literal["entries"]
    session_id: Identifier
    after_id: int = Field(default=0, ge=0)


class Append(TextInput):
    operation: Literal["append"]
    session_id: Identifier


class Audio(Command):
    operation: Literal["audio"]
    session_id: Identifier
    source_id: str = Field(min_length=1, max_length=128)
    pcm: str = Field(min_length=4, max_length=430000)


class StartAssistant(Command):
    operation: Literal["assistant.start"]
    session_id: Identifier
    task: TaskRequest


class JobCommand(Command):
    operation: Literal["assistant.get", "assistant.cancel"]
    job_id: Identifier


PhoneCommand = Hello | Status | ListSessions | CreateSession | SessionCommand | Notes | Entries | Append | Audio | StartAssistant | JobCommand
COMMAND = TypeAdapter(Annotated[PhoneCommand, Field(discriminator="operation")])


class PhoneClassrooms:
    def __init__(self, classroom: Classroom, assistant: Assistant, speech: SpeechService) -> None:
        self.classroom, self.assistant, self.speech = classroom, assistant, speech
        self.store = classroom.store
        self._active: dict[str, str] = {}

    async def dispatch(self, owner: str, command: PhoneCommand, guard: Callable[[], None]) -> dict[str, JsonValue]:
        guard()
        if isinstance(command, CreateSession):
            if owner in self._active:
                raise ValueError("请先结束手机当前课堂")
            if len(self.store.list_sessions(owner_id=owner, limit=100)) >= 100:
                raise ValueError("此连接已达到课堂数量上限，请导出历史后重新配对")
            session = self.store.create_session(command.course_name, owner_id=owner)
            self._active[owner] = session.id
            return {"session": session.model_dump(mode="json")}
        if isinstance(command, ListSessions):
            return {"sessions": [session.model_dump(mode="json") for session in self.store.list_sessions(owner_id=owner, limit=50, offset=command.offset)]}
        if isinstance(command, JobCommand):
            job = (
                await self.assistant.cancel(command.job_id, owner_id=owner)
                if command.operation == "assistant.cancel"
                else self.assistant.get(command.job_id, owner_id=owner)
            )
            return {"job": job.model_dump(mode="json")}
        if isinstance(command, (Hello, Status)):
            raise ValueError("此操作不属于课堂接口")
        self.store.get_session(command.session_id, owner_id=owner)
        if isinstance(command, Audio):
            return await self._audio(owner, command, guard)
        if isinstance(command, StartAssistant):
            job = self.assistant.start(command.session_id, command.task, owner_id=owner, local_only=True, guard=guard)
            return {"job": job.model_dump(mode="json")}
        return self._record(owner, command)

    def _record(self, owner: str, command: SessionCommand | Notes | Entries | Append) -> dict[str, JsonValue]:
        session = self.store.get_session(command.session_id, owner_id=owner)
        if isinstance(command, Entries):
            # 12 * (8,000 six-byte JSON escapes + bounded metadata) fits the 700 KiB envelope.
            return {"entries": [entry.model_dump(mode="json") for entry in self.store.list_entries(session.id, after_id=command.after_id, limit=12)]}
        if isinstance(command, Append):
            previous = self.store.find_entry(session.id, command.source_id)
            if previous:
                if previous.text != command.text:
                    raise ValueError("相同片段标识不能提交不同内容")
                return {"entry": previous.model_dump(mode="json")}
            entry = self.store.append_entry(session.id, command.text, source_id=command.source_id, allow_paused=True)
            self.classroom.publish_entry(session, entry)
            return {"entry": entry.model_dump(mode="json")}
        if isinstance(command, Notes):
            return {"notes": [note.model_dump(mode="json") for note in self.store.list_summaries(session_id=session.id, limit=1, offset=command.offset)]}
        if command.operation == "export":
            if self.store.entry_extent(session.id)[1] > 1000:
                raise ValueError("原文较长，请从手机已同步的课堂历史导出")
            text = self.store.export_session(session.id)
            if len(text.encode("utf-8")) > 300000:
                raise ValueError("原文较长，请从手机已同步的课堂历史导出")
            return {"text": text}
        if self._active.get(owner) != session.id:
            if command.operation == "stop" and session.status == "stopped":
                return {"session": session.model_dump(mode="json")}
            raise ValueError("请选择手机当前课堂")
        if command.operation == "stop":
            self._active.pop(owner, None)
            session = self.store.finish_session(session.id)
        else:
            session = self.store.set_status(session.id, "paused" if command.operation == "pause" else "recording")
        return {"session": session.model_dump(mode="json")}

    async def _audio(self, owner: str, command: Audio, guard: Callable[[], None]) -> dict[str, JsonValue]:
        pcm = base64.b64decode(command.pcm, validate=True)
        validate_pcm(pcm)
        if len(pcm) > 320000:
            raise AudioError("手机每段音频最多 10 秒")
        session = self.store.get_session(command.session_id, owner_id=owner)
        digest = hashlib.sha256(pcm).hexdigest()
        found, previous = self.store.audio_receipt(session.id, command.source_id, digest)
        if found:
            return {"entry": previous.model_dump(mode="json") if previous else None, "duplicate": True}
        if self._active.get(owner) != session.id or session.status != "recording":
            raise ValueError("请先开始或继续手机课堂")
        text = await self.speech.transcribe(pcm, local_only=True)
        guard()
        entry, created = self.store.accept_audio(session.id, command.source_id, digest, text)
        if created and entry:
            self.classroom.publish_entry(session, entry)
        return {"entry": entry.model_dump(mode="json") if entry else None, "duplicate": not created}

    async def close_owner(self, owner: str) -> None:
        for job in self.assistant.list_jobs(owner_id=owner):
            await self.assistant.cancel(job.id, owner_id=owner)
        if session_id := self._active.pop(owner, None):
            self.store.finish_session(session_id)
