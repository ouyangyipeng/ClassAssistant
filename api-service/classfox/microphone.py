import asyncio
import math
import queue
import threading
from collections import deque
from collections.abc import Buffer
from types import TracebackType
from typing import Self

from classfox.audio import SAMPLE_RATE, AudioError, validate_pcm


class EnergySegmenter:
    """Bound utterance requests for file-only providers without requiring a local model."""

    def __init__(self) -> None:
        self._preroll: deque[bytes] = deque(maxlen=2)
        self._chunks: list[bytes] = []
        self._silence = 0
        self._size = 0

    def feed(self, pcm: bytes) -> list[bytes]:
        import numpy as np

        validate_pcm(pcm)
        values = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
        rms = math.sqrt(float(np.mean(values * values)))
        if not self._chunks:
            if rms < 200:
                self._preroll.append(pcm)
                return []
            self._chunks = list(self._preroll)
            self._preroll.clear()
            self._size = sum(map(len, self._chunks))
        self._chunks.append(pcm)
        self._size += len(pcm)
        self._silence = self._silence + len(pcm) if rms < 200 else 0
        if self._silence >= SAMPLE_RATE * 2 * 0.6 or self._size >= SAMPLE_RATE * 2 * 10:
            return self.flush()
        return []

    def flush(self) -> list[bytes]:
        result = [b"".join(self._chunks)] if self._chunks else []
        self._chunks, self._size, self._silence = [], 0, 0
        self._preroll.clear()
        return result


class Microphone:
    def __init__(self, device: int | None) -> None:
        import sounddevice as sd

        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=100)
        self._failed = threading.Event()
        self._closing = False
        self._stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=1600,
            device=device,
            channels=1,
            dtype="int16",
            callback=self._callback,
        )

    def _callback(self, data: Buffer, _frames: int, _time: object, status: object) -> None:
        if status:
            self._failed.set()
        if self._closing:
            return
        try:
            self._queue.put_nowait(bytes(data))
        except queue.Full:
            self._failed.set()

    def __enter__(self) -> Self:
        self._stream.start()
        return self

    def stop(self) -> None:
        self._closing = True
        self._stream.stop()

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None) -> None:
        self._closing = True
        self._stream.close()

    async def next_frame(self) -> bytes | None:
        if self._failed.is_set():
            raise AudioError("音频输入丢失或处理跟不上录音速度，已停止；请检查麦克风或选择更快的识别模式", code="audio_overflow")
        if not self._closing and not self._stream.active:
            raise AudioError("麦克风已断开，请重新连接设备后恢复录音", code="device_disconnected")
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.02)
            return None

    def remaining(self) -> list[bytes]:
        result = []
        while not self._queue.empty():
            result.append(self._queue.get_nowait())
        return result


def input_devices() -> list[dict[str, object]]:
    import sounddevice as sd

    default = sd.default.device[0]
    return [
        {"id": index, "name": device["name"], "channels": device["max_input_channels"], "default": index == default}
        for index, device in enumerate(sd.query_devices())
        if device["max_input_channels"] > 0
    ]
