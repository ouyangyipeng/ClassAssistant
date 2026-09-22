import asyncio
import base64
from collections.abc import Callable

from pydantic import SecretStr

from classfox.asr_providers import SpeechConfig
from classfox.audio import AudioError, validate_pcm
from classfox.credentials import CredentialName, Credentials
from classfox.model_install import ModelInstaller
from classfox.settings import SettingsStore
from classfox.speech_process import SpeechEvent, SpeechProcess
from classfox.speech_worker import WorkerRequest


class SpeechService:
    def __init__(
        self,
        settings: SettingsStore,
        credentials: Credentials,
        models: ModelInstaller,
        *,
        process_factory: Callable[[SpeechEvent], SpeechProcess] = SpeechProcess,
    ) -> None:
        self.settings, self.credentials, self.models = settings, credentials, models
        self._factory = process_factory
        self._workers: set[SpeechProcess] = set()
        self._gate = asyncio.Semaphore(2)

    async def configuration(self, *, local_only: bool = False) -> SpeechConfig:
        settings = self.settings.load().asr
        if local_only and settings.mode != "offline":
            raise AudioError("手机连接仅使用电脑离线识别，请先在电脑选择并安装离线语音模型", code="local_only")
        names: tuple[CredentialName, ...] = ()
        directory = None
        if settings.mode == "offline":
            definition = self.models.catalog.get(settings.model_id)
            if definition is None or definition.kind != "asr":
                raise AudioError("请选择可用的离线语音模型", code="model_unavailable")
            directory = await self.models.verified_path(settings.model_id)
            if directory is None:
                raise AudioError("请先在模型管理中安装离线语音模型", code="model_unavailable")
        elif settings.mode == "dashscope":
            names = ("dashscope",)
        elif settings.mode == "seed-asr":
            names = ("seed_api", "seed_app", "seed_access")
        elif settings.mode in {"openai", "google"}:
            names = ("asr",)
        else:
            raise AudioError("请在界面选择浏览器识别或文本输入，或在设置中选择可用的音频识别服务", code="unsupported_provider")
        keys: dict[str, SecretStr] = {}
        for name in names:
            value = await asyncio.to_thread(self.credentials.get, name)
            if value:
                keys[name] = SecretStr(value)
        return SpeechConfig(settings=settings, model_dir=directory, keys=keys)

    async def microphone(self, emit: SpeechEvent) -> SpeechProcess:
        config = await self.configuration()
        process = self._factory(emit)
        self._workers.add(process)
        try:
            await process.start(WorkerRequest(action="microphone", config=config))
            return process
        except BaseException:
            await self.release(process)
            raise

    async def release(self, process: SpeechProcess) -> None:
        await process.close()
        self._workers.discard(process)

    async def _run(self, request: WorkerRequest, *, timeout: float) -> list[dict[str, object]]:
        events: list[dict[str, object]] = []
        async with self._gate:
            process = self._factory(events.append)
            self._workers.add(process)
            try:
                await process.start(request, timeout=min(timeout, 90))
                await process.wait(timeout=timeout)
                return events
            finally:
                await self.release(process)

    async def transcribe(self, pcm: bytes, *, local_only: bool = False) -> str:
        validate_pcm(pcm)
        config = await self.configuration(local_only=local_only)
        events = await self._run(WorkerRequest(action="transcribe", config=config, pcm=base64.b64encode(pcm).decode("ascii")), timeout=75)
        text = "\n".join(str(event["text"]) for event in events if event["type"] == "transcript")
        if len(text) > 8000:
            raise AudioError("单段识别文字过长，请缩短音频后重试", code="invalid_response")
        return text

    async def devices(self) -> list[dict[str, object]]:
        events = await self._run(WorkerRequest(action="devices"), timeout=15)
        for event in events:
            devices = event.get("devices")
            if event["type"] == "devices" and isinstance(devices, list) and all(isinstance(device, dict) for device in devices):
                return [dict(device) for device in devices]
        raise AudioError("无法读取麦克风列表，请检查系统音频设备", code="device_unavailable")

    async def close(self) -> None:
        for process in tuple(self._workers):
            await self.release(process)
