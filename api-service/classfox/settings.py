import ipaddress
import os
import tempfile
import threading
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


def validate_endpoint(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("无效端口")
    except ValueError as exc:
        raise ValueError("无效服务地址") from exc
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("服务地址不能包含凭据、查询参数或片段")
    try:
        loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = parsed.hostname == "localhost"
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise ValueError("远程模型须使用 HTTPS，本机模型可使用 HTTP")
    return value.rstrip("/")


class LLMSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    mode: Literal["local", "byok"] = "local"
    managed: bool = True
    local_model_id: str = Field(default="qwen35-4b", pattern=r"^[a-z][a-z0-9-]*$")
    base_url: str = "http://127.0.0.1:8080/v1"
    model: str = Field(default="local", min_length=1, max_length=200)
    timeout_seconds: int = Field(default=45, ge=5, le=180)
    context_characters: int = Field(default=16000, ge=1000, le=64000)
    _endpoint = field_validator("base_url")(validate_endpoint)


class ASRSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    mode: Literal["offline", "webspeech", "google", "seed-asr", "dashscope", "openai", "mock"] = "offline"
    language: str = Field(default="zh-CN", min_length=2, max_length=20)
    input_device: int | None = None
    model_id: str = "sensevoice-small"
    base_url: str = "https://api.openai.com/v1"
    model: str = "whisper-1"
    seed_resource_id: Literal["volc.seedasr.sauc.duration", "volc.seedasr.sauc.concurrent", "volc.bigasr.sauc.duration", "volc.bigasr.sauc.concurrent"] = (
        "volc.seedasr.sauc.duration"
    )
    dashscope_model: str = Field(default="fun-asr-realtime", min_length=1, max_length=200)
    dashscope_region: Literal["beijing", "singapore"] = "beijing"
    _endpoint = field_validator("base_url")(validate_endpoint)


class Appearance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme: Literal["system", "light", "dark"] = "system"
    accent: Literal["amber", "blue", "green", "slate"] = "amber"
    font_scale: float = Field(default=1, ge=0.85, le=1.5)
    opacity: float = Field(default=0.96, ge=0.6, le=1)
    window_radius: int = Field(default=12, ge=0, le=30)
    always_on_top: bool = True


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[2] = 2
    llm: LLMSettings = Field(default_factory=LLMSettings)
    asr: ASRSettings = Field(default_factory=ASRSettings)
    appearance: Appearance = Field(default_factory=Appearance)
    keywords: list[str] = Field(default_factory=list, max_length=100)
    warning_keywords: list[str] = Field(default_factory=lambda: ["考试", "重点", "作业", "截止", "下周交"], max_length=100)
    auto_summary: bool = True

    @field_validator("keywords", "warning_keywords")
    @classmethod
    def normalize_keywords(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(len(value) > 80 for value in cleaned):
            raise ValueError("单个关键词不能超过 80 个字符")
        return cleaned


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def load(self) -> Preferences:
        with self._lock:
            if not self.path.exists():
                return Preferences()
            try:
                return Preferences.model_validate_json(self.path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                raise ValueError("配置文件无法读取或格式无效；请保留原文件并从设置中恢复") from exc

    def save(self, preferences: Preferences) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(prefix="preferences-", suffix=".tmp", dir=self.path.parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                    output.write(preferences.model_dump_json(indent=2) + "\n")
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(name, self.path)
            finally:
                Path(name).unlink(missing_ok=True)
