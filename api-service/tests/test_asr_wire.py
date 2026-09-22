import gzip
import json
import struct

import pytest

from classfox.asr_wire import dashscope_result, seed_packet, seed_response, seed_results
from classfox.audio import AudioError


def server_packet(payload: dict[str, object], *, flags: int = 0, compressed: bool = True, extension: bytes = b"") -> bytes:
    data = json.dumps(payload).encode()
    if compressed:
        data = gzip.compress(data)
    header = bytes([0x10 + 1 + len(extension) // 4, 0x90 | flags, 0x10 | int(compressed), 0]) + extension
    sequence = struct.pack(">i", -2 if flags & 2 else 2) if flags & 1 else b""
    return header + sequence + struct.pack(">I", len(data)) + data


@pytest.mark.parametrize("flags", [0, 1, 2, 3])
def test_seed_sequence_is_optional_and_final_flag_is_independent(flags: int) -> None:
    result, final = seed_response(server_packet({"result": {"text": "课堂"}}, flags=flags, extension=b"\0" * 4))
    assert result == {"result": {"text": "课堂"}}
    assert final == bool(flags & 2)


def test_seed_rejects_truncation_and_expansion_without_echoing_payload() -> None:
    with pytest.raises(AudioError):
        seed_response(server_packet({"result": {}})[:-1])
    with pytest.raises(AudioError):
        seed_response(server_packet({"secret": "private" * 200000}))
    message = b"do not expose secret"
    with pytest.raises(AudioError) as failure:
        seed_response(b"\x11\xf0\x00\x00" + struct.pack(">II", 401, len(message)) + message)
    assert "secret" not in str(failure.value)


def test_audio_packet_has_correct_payload_size_and_last_flag() -> None:
    packet = seed_packet(b"\0\0" * 3200, audio=True, final=True)
    assert packet[:4] == b"\x11\x22\x01\x00"
    assert struct.unpack(">I", packet[4:8])[0] == len(packet) - 8
    assert gzip.decompress(packet[8:]) == b"\0\0" * 3200


def test_seed_only_final_utterances_are_committed_with_stable_ids() -> None:
    payload: dict[str, object] = {
        "result": {
            "utterances": [
                {"text": "开饭时间", "start_time": 0, "end_time": 900, "definite": True},
                {"text": "早上九点", "start_time": 900, "end_time": 1200, "definite": False},
            ]
        }
    }
    rows = seed_results(payload)
    assert [(row.text, row.final, row.source_id) for row in rows] == [("开饭时间", True, "0:900"), ("早上九点", False, "900:1200")]
    assert seed_results(payload) == rows


def test_dashscope_heartbeat_and_empty_results_are_not_transcripts() -> None:
    assert dashscope_result({"output": {"sentence": {"heartbeat": True, "text": ""}}}) is None
    row = dashscope_result({"output": {"sentence": {"sentence_id": 1, "sentence_end": True, "text": "重点"}}})
    assert row is not None and row.final and row.text == "重点" and row.source_id == "1"
