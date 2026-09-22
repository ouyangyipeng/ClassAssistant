import asyncio
import base64
import json
import os
import sys
import threading
import time
from collections.abc import Callable
from typing import Literal, TextIO
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from classfox.asr_providers import ChunkSpeech, SpeechConfig, StreamingSpeech
from classfox.asr_wire import Recognition
from classfox.audio import AudioError, SpeechSegmenter, validate_pcm
from classfox.microphone import EnergySegmenter, Microphone, input_devices

Emit = Callable[[dict[str, object]], None]


class WorkerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["microphone", "transcribe", "devices"]
    config: SpeechConfig | None = None
    pcm: str | None = Field(default=None, max_length=1280000, repr=False)


class SpeechEngine:
    def __init__(self, config: SpeechConfig, emit: Emit) -> None:
        self.config, self.emit = config, emit
        self._streaming = StreamingSpeech(config, self.recognized) if config.settings.mode in {"seed-asr", "dashscope"} else None
        self._chunks = ChunkSpeech(config) if self._streaming is None else None
        self._segmenter: SpeechSegmenter | EnergySegmenter | None = None
        self._prefix, self._index = uuid4().hex, 0
        self._seen: set[str] = set()

    def recognized(self, result: Recognition) -> None:
        if not result.text:
            return
        if result.final:
            if result.source_id in self._seen:
                return
            self._seen.add(result.source_id)
        self.emit({"type": "transcript" if result.final else "partial", "text": result.text, "source_id": result.source_id})

    async def start(self, *, segmented: bool) -> None:
        if self._streaming is not None:
            await self._streaming.start()
            return
        assert self._chunks is not None
        await self._chunks.start()
        if segmented:
            if self.config.settings.mode == "offline" and self.config.model_dir is not None:
                self._segmenter = await asyncio.to_thread(SpeechSegmenter, self.config.model_dir)
            else:
                self._segmenter = EnergySegmenter()

    async def _transcribe(self, chunks: list[bytes]) -> None:
        assert self._chunks is not None
        for pcm in chunks:
            self._index += 1
            text = await self._chunks.transcribe(pcm)
            self.recognized(Recognition(text, f"{self._prefix}:{self._index}"))

    async def feed(self, pcm: bytes) -> None:
        if self._streaming is not None:
            await self._streaming.feed(pcm)
        elif self._segmenter is not None:
            await self._transcribe(self._segmenter.feed(pcm))
        else:
            await self._transcribe([pcm])

    async def finish(self) -> None:
        if self._streaming is not None:
            await self._streaming.finish()
        elif self._segmenter is not None:
            await self._transcribe(self._segmenter.flush())

    async def close(self) -> None:
        if self._streaming is not None:
            await self._streaming.close()


async def record(engine: SpeechEngine, stop: threading.Event, emit: Emit) -> None:
    import numpy as np

    await engine.start(segmented=True)
    with Microphone(engine.config.settings.input_device) as microphone:
        emit({"type": "ready"})
        last_meter = 0.0
        while not stop.is_set():
            pcm = await microphone.next_frame()
            if pcm is None:
                continue
            if time.monotonic() - last_meter >= 0.5:
                values = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
                emit({"type": "level", "peak": round(float(np.max(np.abs(values))) / 32768, 4)})
                last_meter = time.monotonic()
            await engine.feed(pcm)
        microphone.stop()
        for pcm in microphone.remaining():
            await engine.feed(pcm)
    await engine.finish()


async def transcribe(engine: SpeechEngine, encoded: str, emit: Emit) -> None:
    pcm = base64.b64decode(encoded, validate=True)
    validate_pcm(pcm)
    # File/phone uploads can contain silence too; use the installed VAD before ASR.
    await engine.start(segmented=engine.config.settings.mode == "offline")
    emit({"type": "ready"})
    if engine.config.settings.mode in {"seed-asr", "dashscope"}:
        for start in range(0, len(pcm), 6400):
            await engine.feed(pcm[start : start + 6400])
            await asyncio.sleep(0.2)
    else:
        await engine.feed(pcm)
    await engine.finish()


async def run(request: WorkerRequest, stop: threading.Event, emit: Emit) -> None:
    if request.action == "devices":
        emit({"type": "ready"})
        emit({"type": "devices", "devices": input_devices()})
        return
    if request.config is None:
        raise AudioError("缺少语音设置", code="invalid_configuration")
    engine = SpeechEngine(request.config, emit)
    try:
        if request.action == "microphone":
            await record(engine, stop, emit)
        else:
            await transcribe(engine, request.pcm or "", emit)
    finally:
        await engine.close()


def watch_commands(source: TextIO, stop: threading.Event) -> None:
    while not stop.is_set():
        message = source.readline(1024)
        if not message or message.strip() == '{"action":"stop"}':
            stop.set()


def main() -> None:
    # Keep library/native stdout and stderr away from the private JSON protocol and credentials.
    output = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
    with open(os.devnull, "w") as sink:
        os.dup2(sink.fileno(), sys.stdout.fileno())
        os.dup2(sink.fileno(), sys.stderr.fileno())

    def emit(event: dict[str, object]) -> None:
        output.write(json.dumps(event, ensure_ascii=True) + "\n")
        output.flush()

    try:
        request = WorkerRequest.model_validate_json(sys.stdin.readline(1500000))
        stop = threading.Event()
        if request.action == "microphone":
            threading.Thread(target=watch_commands, args=(sys.stdin, stop), daemon=True).start()
        asyncio.run(run(request, stop, emit))
        emit({"type": "done"})
    except AudioError as exc:
        emit({"type": "error", "code": exc.code, "message": str(exc)})
    except Exception:
        emit({"type": "error", "code": "audio_unavailable", "message": "无法启动或继续语音识别，请检查麦克风权限、设备、运行库和模型设置"})
    finally:
        output.close()


if __name__ == "__main__":
    main()
