import gzip
import json
import struct
import zlib
from dataclasses import dataclass

from classfox.audio import AudioError

MAX_RESPONSE = 1024 * 1024


@dataclass(frozen=True)
class Recognition:
    text: str
    source_id: str
    final: bool = True


def protocol_error() -> AudioError:
    return AudioError("语音服务返回了无效数据，请重试或检查服务配置", code="invalid_response")


def seed_packet(payload: bytes, *, audio: bool = False, final: bool = False) -> bytes:
    data = gzip.compress(payload)
    header = bytes([0x11, (0x20 if audio else 0x10) | (2 if final else 0), 0x01 if audio else 0x11, 0])
    return header + struct.pack(">I", len(data)) + data


def seed_response(message: bytes) -> tuple[dict[str, object], bool]:
    if not 8 <= len(message) <= MAX_RESPONSE or message[0] >> 4 != 1:
        raise protocol_error()
    offset = (message[0] & 15) * 4
    kind, flags = message[1] >> 4, message[1] & 15
    if offset < 4 or flags > 3 or kind not in {9, 15}:
        raise protocol_error()
    if kind == 15:
        raise AudioError("语音服务拒绝请求，请检查凭据、所选资源和可用额度", code="provider_rejected")
    if flags & 1:
        offset += 4
    if len(message) < offset + 4 or message[2] >> 4 != 1:
        raise protocol_error()
    length = struct.unpack(">I", message[offset : offset + 4])[0]
    payload = message[offset + 4 :]
    if length != len(payload):
        raise protocol_error()
    try:
        compression = message[2] & 15
        if compression == 1:
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
            payload = decoder.decompress(payload, MAX_RESPONSE + 1)
            if len(payload) > MAX_RESPONSE or not decoder.eof or decoder.unused_data:
                raise protocol_error()
        elif compression != 0:
            raise protocol_error()
        parsed = json.loads(payload)
    except (zlib.error, ValueError, UnicodeError) as exc:
        raise protocol_error() from exc
    if not isinstance(parsed, dict):
        raise protocol_error()
    return parsed, bool(flags & 2)


def text_value(value: object) -> str:
    if not isinstance(value, str) or len(value) > 8000:
        raise protocol_error()
    return value.strip()


def seed_results(payload: dict[str, object]) -> list[Recognition]:
    result = payload.get("result", {})
    if not isinstance(result, dict) or not isinstance(result.get("utterances", []), list):
        raise protocol_error()
    rows = []
    for sentence in result.get("utterances", []):
        if not isinstance(sentence, dict):
            raise protocol_error()
        text = text_value(sentence.get("text", ""))
        if not text:
            continue
        start, end = sentence.get("start_time"), sentence.get("end_time")
        if type(start) is not int or type(end) is not int or start < 0 or end < start:
            raise protocol_error()
        rows.append(Recognition(text, f"{start}:{end}", sentence.get("definite") is True))
    return rows


def dashscope_result(payload: dict[str, object]) -> Recognition | None:
    output = payload.get("output", {})
    if not isinstance(output, dict) or not isinstance(output.get("sentence", {}), dict):
        raise protocol_error()
    sentence = output.get("sentence", {})
    if sentence.get("heartbeat") is True:
        return None
    text = text_value(sentence.get("text", ""))
    if not text:
        return None
    sentence_id = sentence.get("sentence_id")
    if type(sentence_id) is not int or sentence_id < 1:
        raise protocol_error()
    return Recognition(text, str(sentence_id), sentence.get("sentence_end") is True)
