import io
import threading
import wave
from pathlib import Path

SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2
MAX_AUDIO_SECONDS = 30


class AudioError(Exception):
    def __init__(self, message: str, *, code: str = "invalid_audio") -> None:
        super().__init__(message)
        self.code = code


def validate_pcm(pcm: bytes, *, max_seconds: int = MAX_AUDIO_SECONDS) -> None:
    if not pcm or len(pcm) % SAMPLE_WIDTH:
        raise AudioError("音频不能为空，且必须为 16 位 PCM 采样")
    if len(pcm) > SAMPLE_RATE * SAMPLE_WIDTH * max_seconds:
        raise AudioError(f"单段音频不能超过 {max_seconds} 秒，请分段上传")


def pcm_to_wav(pcm: bytes) -> bytes:
    validate_pcm(pcm, max_seconds=600)
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    return output.getvalue()


def decode_wav(data: bytes) -> bytes:
    if len(data) > SAMPLE_RATE * SAMPLE_WIDTH * MAX_AUDIO_SECONDS + 64 * 1024:
        raise AudioError("单段音频过大，请分段上传")
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != SAMPLE_WIDTH or wav.getframerate() != SAMPLE_RATE or wav.getcomptype() != "NONE":
                raise AudioError("请提供 16 kHz、单声道、16 位 PCM WAV 音频")
            pcm = wav.readframes(SAMPLE_RATE * MAX_AUDIO_SECONDS + 1)
            if len(pcm) != wav.getnframes() * SAMPLE_WIDTH:
                raise AudioError("音频内容不完整或超过 30 秒，请重新录制")
    except (wave.Error, EOFError, ValueError) as exc:
        raise AudioError("无法读取音频，请提供有效 WAV 文件") from exc
    validate_pcm(pcm)
    return pcm


class OfflineSpeech:
    def __init__(self, model_dir: Path, *, language: str = "auto") -> None:
        try:
            import sherpa_onnx
        except (ImportError, OSError) as exc:
            raise AudioError("离线语音运行库不可用，请修复或重新安装应用", code="runtime_unavailable") from exc
        self._lock = threading.Lock()
        try:
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(model_dir / "model.int8.onnx"),
                tokens=str(model_dir / "tokens.txt"),
                num_threads=2,
                language=language,
                use_itn=True,
            )
        except (RuntimeError, ValueError) as exc:
            raise AudioError("离线语音模型加载失败，请在模型管理中检查并重新下载", code="model_unavailable") from exc

    def transcribe(self, pcm: bytes) -> str:
        import numpy as np

        validate_pcm(pcm)
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        with self._lock:
            try:
                stream = self._recognizer.create_stream()
                stream.accept_waveform(SAMPLE_RATE, samples)
                self._recognizer.decode_stream(stream)
                return stream.result.text.strip()
            except RuntimeError as exc:
                raise AudioError("离线识别失败，请缩短音频后重试", code="recognition_failed") from exc


class SpeechSegmenter:
    def __init__(self, model_dir: Path) -> None:
        import sherpa_onnx

        config = sherpa_onnx.VadModelConfig(
            silero_vad=sherpa_onnx.SileroVadModelConfig(model=str(model_dir / "silero_vad.onnx"), min_silence_duration=0.5, max_speech_duration=10),
            sample_rate=SAMPLE_RATE,
            num_threads=1,
        )
        self._vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)
        self._pending = b""

    def feed(self, pcm: bytes) -> list[bytes]:
        import numpy as np

        validate_pcm(pcm)
        complete = self._pending + pcm
        boundary = len(complete) // 1024 * 1024
        self._pending = complete[boundary:]
        for start in range(0, boundary, 1024):
            window = complete[start : start + 1024]
            self._vad.accept_waveform(np.frombuffer(window, dtype="<i2").astype(np.float32) / 32768)
        return self._drain()

    def flush(self) -> list[bytes]:
        segments: list[bytes] = []
        if self._pending:
            segments.extend(self.feed(b"\x00" * (1024 - len(self._pending))))
        self._vad.flush()
        return segments + self._drain()

    def _drain(self) -> list[bytes]:
        import numpy as np

        segments: list[bytes] = []
        while not self._vad.empty():
            values = np.asarray(self._vad.front.samples, dtype=np.float32)
            segments.append(np.clip(values * 32768, -32768, 32767).astype("<i2").tobytes())
            self._vad.pop()
        return segments
