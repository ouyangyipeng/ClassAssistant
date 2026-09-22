from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SessionStatus = Literal["starting", "recording", "paused", "stopped", "interrupted", "error"]


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Session(Record):
    id: str
    owner_id: str
    course_name: str
    material_id: str | None = None
    status: SessionStatus
    created_at: datetime
    ended_at: datetime | None = None


class TranscriptEntry(Record):
    id: int
    session_id: str
    text: str
    created_at: datetime
    source_id: str | None = None


class Material(Record):
    id: str
    filename: str
    text: str
    created_at: datetime


class Summary(Record):
    id: str
    session_id: str
    title: str
    markdown: str
    created_at: datetime


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    course_name: str = Field(default="未命名课堂", min_length=1, max_length=120)
    material_id: str | None = None
    source: Literal["microphone", "browser", "text", "remote"] = "microphone"


class TextInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=8000)
    source_id: str = Field(min_length=1, max_length=128)
