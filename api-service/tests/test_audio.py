import io
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from classfox.audio import AudioError, SpeechSegmenter, decode_wav, pcm_to_wav


def test_pcm_wav_roundtrip_preserves_samples() -> None:
    pcm = b"\x10\x00\xf0\xff" * 16000
    assert decode_wav(pcm_to_wav(pcm)) == pcm


@pytest.mark.parametrize("rate,channels,width", [(48000, 1, 2), (16000, 2, 2), (16000, 1, 1)])
def test_wav_requires_supported_audio_shape(rate: int, channels: int, width: int) -> None:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(b"\x00" * 32000)
    with pytest.raises(AudioError):
        decode_wav(output.getvalue())


@pytest.mark.parametrize("data", [b"not-wav", b"", b"RIFF\x00\x00\x00\x00WAVE"])
def test_invalid_audio_is_explicit_error(data: bytes) -> None:
    with pytest.raises(AudioError):
        decode_wav(data)


def test_audio_duration_and_sample_alignment_are_bounded() -> None:
    with pytest.raises(AudioError):
        pcm_to_wav(b"\x00")
    with pytest.raises(AudioError):
        decode_wav(pcm_to_wav(b"\x00\x00" * (31 * 16000)))


def test_flush_keeps_segment_completed_by_padding(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sherpa_onnx = pytest.importorskip("sherpa_onnx")

    class Detector:
        def __init__(self, config: object, *, buffer_size_in_seconds: int) -> None:
            self.ready = False
            self.front = SimpleNamespace(samples=[0.25, -0.25])

        def accept_waveform(self, values: object) -> None:
            self.ready = True

        def empty(self) -> bool:
            return not self.ready

        def pop(self) -> None:
            self.ready = False

        def flush(self) -> None:
            pass

    monkeypatch.setattr(sherpa_onnx, "VoiceActivityDetector", Detector)
    segmenter = SpeechSegmenter(tmp_path)
    assert segmenter.feed(b"\x00\x00") == []
    assert segmenter.flush() == [b"\x00\x20\x00\xe0"]
