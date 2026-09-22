import asyncio
import json
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import httpx
from openai import APIError, AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import WebSocketException

from classfox.asr_wire import MAX_RESPONSE, Recognition, dashscope_result, protocol_error, seed_packet, seed_response, seed_results, text_value
from classfox.audio import AudioError, OfflineSpeech, pcm_to_wav, validate_pcm
from classfox.settings import ASRSettings

EmitRecognition = Callable[[Recognition], None]


class SpeechConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    settings: ASRSettings
    model_dir: Path | None = None
    keys: dict[str, SecretStr] = Field(default_factory=dict, repr=False)

    def key(self, name: str) -> str:
        value = self.keys.get(name)
        if value is None or not value.get_secret_value():
            raise AudioError("尚未配置此语音服务的凭据，请打开语音设置", code="missing_credentials")
        return value.get_secret_value()


class DirectConnect(connect):
    def process_redirect(self, exc: Exception) -> Exception:
        # Seed uses custom credential headers that generic redirect filters do not strip.
        return exc


def provider_error(error: Exception) -> AudioError:
    if isinstance(error, AudioError):
        return error
    if isinstance(error, TimeoutError):
        return AudioError("语音服务响应超时，已停止录音；请检查网络后重试", code="provider_timeout")
    return AudioError("语音服务连接失败，已停止录音；请检查网络、凭据和额度", code="provider_unavailable")


class StreamingSpeech:
    def __init__(self, config: SpeechConfig, emit: EmitRecognition) -> None:
        self.config, self.emit = config, emit
        self.task_id = uuid4().hex
        self._socket: ClientConnection | None = None
        self._receiver: asyncio.Task[None] | None = None
        self._finishing = False

    def _connection(self) -> tuple[str, dict[str, str]]:
        if self.config.settings.mode == "dashscope":
            host = "dashscope-intl.aliyuncs.com" if self.config.settings.dashscope_region == "singapore" else "dashscope.aliyuncs.com"
            return f"wss://{host}/api-ws/v1/inference", {"Authorization": f"Bearer {self.config.key('dashscope')}"}
        headers = {"X-Api-Resource-Id": self.config.settings.seed_resource_id, "X-Api-Connect-Id": self.task_id}
        if self.config.keys.get("seed_api"):
            headers["X-Api-Key"] = self.config.key("seed_api")
        else:
            headers.update({"X-Api-App-Key": self.config.key("seed_app"), "X-Api-Access-Key": self.config.key("seed_access")})
        return "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async", headers

    def _dash_command(self, action: str) -> str:
        payload: dict[str, object] = {"input": {}}
        if action == "run-task":
            payload.update(
                {
                    "task_group": "audio",
                    "task": "asr",
                    "function": "recognition",
                    "model": self.config.settings.dashscope_model,
                    "parameters": {
                        "format": "pcm",
                        "sample_rate": 16000,
                        "semantic_punctuation_enabled": False,
                        "max_sentence_silence": 800,
                        "heartbeat": True,
                    },
                }
            )
        return json.dumps({"header": {"action": action, "task_id": self.task_id, "streaming": "duplex"}, "payload": payload})

    async def start(self) -> None:
        url, headers = self._connection()
        try:
            self._socket = await DirectConnect(
                url, additional_headers=headers, proxy=None, open_timeout=10, close_timeout=2, max_size=MAX_RESPONSE, max_queue=16
            )
            if self.config.settings.mode == "dashscope":
                await self._socket.send(self._dash_command("run-task"))
                async with asyncio.timeout(10):
                    event = self._dash_event(await self._socket.recv())
                    if event[0] != "task-started":
                        raise protocol_error()
            else:
                parameters = {
                    "user": {"uid": "classfox"},
                    "audio": {"format": "pcm", "rate": 16000, "bits": 16, "channel": 1},
                    "request": {
                        "model_name": "bigmodel",
                        "enable_itn": True,
                        "enable_punc": True,
                        "show_utterances": True,
                        "end_window_size": 800,
                        "result_type": "single",
                    },
                }
                await self._socket.send(seed_packet(json.dumps(parameters).encode()))
            self._receiver = asyncio.create_task(self._receive())
        except (WebSocketException, OSError, TimeoutError, AudioError) as exc:
            await self.close()
            raise provider_error(exc) from exc

    def _dash_event(self, message: str | bytes) -> tuple[str, dict[str, object]]:
        try:
            parsed = json.loads(message)
            header = parsed["header"]
            event = header["event"]
            if header.get("task_id") != self.task_id:
                raise protocol_error()
            if event == "task-failed":
                raise AudioError("语音服务拒绝请求，请检查凭据、模型名称和额度", code="provider_rejected")
            payload = parsed.get("payload", {})
            if not isinstance(event, str) or not isinstance(payload, dict):
                raise protocol_error()
            return event, payload
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise protocol_error() from exc

    async def _receive(self) -> None:
        assert self._socket is not None
        try:
            async for message in self._socket:
                if self.config.settings.mode == "dashscope":
                    event, payload = self._dash_event(message)
                    final = event == "task-finished"
                    row = dashscope_result(payload) if event == "result-generated" else None
                    rows = [row] if row is not None else []
                else:
                    if not isinstance(message, bytes):
                        raise protocol_error()
                    payload, final = seed_response(message)
                    rows = seed_results(payload)
                for row in rows:
                    self.emit(Recognition(row.text, f"{self.task_id}:{row.source_id}", row.final))
                if final:
                    if not self._finishing:
                        raise AudioError("语音连接提前结束，请重新开始识别", code="provider_disconnected")
                    return
            raise AudioError("语音连接已断开，请检查网络后恢复识别", code="provider_disconnected")
        except (WebSocketException, OSError) as exc:
            raise provider_error(exc) from exc

    def check(self) -> None:
        if self._receiver is not None and self._receiver.done():
            self._receiver.result()

    async def feed(self, pcm: bytes) -> None:
        validate_pcm(pcm)
        self.check()
        assert self._socket is not None
        data = pcm if self.config.settings.mode == "dashscope" else seed_packet(pcm, audio=True)
        try:
            async with asyncio.timeout(5):
                await self._socket.send(data)
        except (WebSocketException, OSError, TimeoutError) as exc:
            raise provider_error(exc) from exc

    async def finish(self) -> None:
        assert self._socket is not None and self._receiver is not None
        self._finishing = True
        message = self._dash_command("finish-task") if self.config.settings.mode == "dashscope" else seed_packet(b"", audio=True, final=True)
        try:
            async with asyncio.timeout(12):
                await self._socket.send(message)
                await self._receiver
        except (WebSocketException, OSError, TimeoutError) as exc:
            raise provider_error(exc) from exc

    async def close(self) -> None:
        if self._receiver is not None:
            self._receiver.cancel()
            with suppress(asyncio.CancelledError, AudioError):
                await self._receiver
        if self._socket is not None:
            await self._socket.close()


class ChunkSpeech:
    def __init__(self, config: SpeechConfig) -> None:
        self.config = config
        self._offline: OfflineSpeech | None = None

    async def start(self) -> None:
        if self.config.settings.mode == "offline":
            if self.config.model_dir is None:
                raise AudioError("请先下载离线语音模型", code="model_unavailable")
            language = self.config.settings.language.split("-")[0]
            if language not in {"zh", "en", "ja", "ko", "yue", "auto"}:
                raise AudioError("此离线模型支持中、英、日、韩、粤语或自动检测，请调整语种", code="unsupported_language")
            self._offline = await asyncio.to_thread(OfflineSpeech, self.config.model_dir, language=language)
        elif self.config.settings.mode == "openai":
            self.config.key("asr")
        elif self.config.settings.mode != "google":
            raise AudioError("请选择离线或在线语音识别；浏览器识别由桌面界面采集", code="unsupported_provider")

    async def transcribe(self, pcm: bytes) -> str:
        validate_pcm(pcm)
        if self._offline is not None:
            return await asyncio.to_thread(self._offline.transcribe, pcm)
        try:
            async with asyncio.timeout(30):
                if self.config.settings.mode == "google":
                    return await asyncio.to_thread(self._google, pcm)
                settings = self.config.settings
                async with AsyncOpenAI(
                    api_key=self.config.key("asr"),
                    base_url=settings.base_url,
                    max_retries=0,
                    http_client=httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=httpx.Timeout(30, connect=10)),
                ) as client:
                    options = {"language": settings.language.split("-")[0]} if settings.language != "auto" else {}
                    result = await client.audio.transcriptions.create(
                        model=settings.model,
                        file=("speech.wav", pcm_to_wav(pcm), "audio/wav"),
                        response_format="json",
                        **options,
                    )
                    return text_value(result.text)
        except (APIError, httpx.HTTPError, TimeoutError) as exc:
            raise provider_error(exc) from exc

    def _google(self, pcm: bytes) -> str:
        import speech_recognition as sr
        from speech_recognition.recognizers.google import recognize_legacy

        recognizer = sr.Recognizer()
        recognizer.operation_timeout = 15
        try:
            return text_value(
                recognize_legacy(
                    recognizer,
                    sr.AudioData(pcm, 16000, 2),
                    language=self.config.settings.language,
                    key=self.config.keys["asr"].get_secret_value() if "asr" in self.config.keys else None,
                    endpoint="https://www.google.com/speech-api/v2/recognize",
                )
            )
        except sr.UnknownValueError:
            return ""
        except (sr.RequestError, OSError) as exc:
            raise AudioError("Google 兼容识别不可用，请检查网络或选择其他语音服务", code="provider_unavailable") from exc
