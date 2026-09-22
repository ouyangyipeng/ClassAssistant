import asyncio
import gzip
import json
import struct

import httpx
import pytest
from pydantic import SecretStr
from websockets.asyncio.client import connect
from websockets.asyncio.server import ServerConnection, serve

from classfox import asr_providers
from classfox.asr_providers import ChunkSpeech, SpeechConfig, StreamingSpeech
from classfox.asr_wire import Recognition
from classfox.audio import AudioError
from classfox.settings import ASRSettings


@pytest.mark.parametrize("new_credentials", [True, False])
async def test_seed_binary_websocket_preserves_admission_audio_and_final_result(monkeypatch: pytest.MonkeyPatch, new_credentials: bool) -> None:
    rows: list[Recognition] = []
    received_audio = b""

    async def handler(socket: ServerConnection) -> None:
        nonlocal received_audio
        assert socket.request is not None
        headers = socket.request.headers
        assert headers["X-Api-Resource-Id"] == "volc.seedasr.sauc.duration"
        if new_credentials:
            assert headers["X-Api-Key"] == "synthetic-new"
            assert "X-Api-Access-Key" not in headers
        else:
            assert headers["X-Api-App-Key"] == "synthetic-app"
            assert headers["X-Api-Access-Key"] == "synthetic-access"
            assert "X-Api-Key" not in headers
        start = await socket.recv()
        assert isinstance(start, bytes) and start[1] == 0x10
        config = json.loads(gzip.decompress(start[8:]))
        assert config["audio"] == {"format": "pcm", "rate": 16000, "bits": 16, "channel": 1}
        audio = await socket.recv()
        assert isinstance(audio, bytes) and audio[1] == 0x20
        received_audio = gzip.decompress(audio[8:])
        end = await socket.recv()
        assert isinstance(end, bytes) and end[1] == 0x22 and gzip.decompress(end[8:]) == b""
        payload = gzip.compress(json.dumps({"result": {"utterances": [{"text": "课堂最后一句", "start_time": 0, "end_time": 100, "definite": True}]}}).encode())
        await socket.send(bytes([0x11, 0x93, 0x11, 0]) + struct.pack(">iI", -1, len(payload)) + payload)

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(asr_providers, "DirectConnect", lambda _url, **kwargs: connect(f"ws://127.0.0.1:{port}", **kwargs))
        keys = (
            {"seed_api": SecretStr("synthetic-new")}
            if new_credentials
            else {"seed_app": SecretStr("synthetic-app"), "seed_access": SecretStr("synthetic-access")}
        )
        speech = StreamingSpeech(SpeechConfig(settings=ASRSettings(mode="seed-asr"), keys=keys), rows.append)
        try:
            await speech.start()
            await speech.feed(b"\1\0" * 1600)
            await speech.finish()
        finally:
            await speech.close()
        assert received_audio == b"\1\0" * 1600
        assert len(rows) == 1 and rows[0].text == "课堂最后一句" and rows[0].final


async def test_dashscope_waits_for_admission_and_flushes_final_sentence(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[object] = []

    async def handler(socket: ServerConnection) -> None:
        start = json.loads(await socket.recv())
        received.append(start)
        task = start["header"]["task_id"]
        await socket.send(json.dumps({"header": {"task_id": task, "event": "task-started"}}))
        received.append(await socket.recv())
        for final in [False, True]:
            if final:
                end = json.loads(await socket.recv())
                assert end["header"]["action"] == "finish-task"
            await socket.send(
                json.dumps(
                    {
                        "header": {"task_id": task, "event": "result-generated"},
                        "payload": {
                            "output": {
                                "sentence": {"sentence_id": 1, "text": "重点知识", "sentence_end": final},
                            }
                        },
                    }
                )
            )
        await socket.send(json.dumps({"header": {"task_id": task, "event": "task-finished"}}))

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(asr_providers, "DirectConnect", lambda _url, **kwargs: connect(f"ws://127.0.0.1:{port}", **kwargs))
        rows: list[Recognition] = []
        speech = StreamingSpeech(SpeechConfig(settings=ASRSettings(mode="dashscope"), keys={"dashscope": SecretStr("synthetic")}), rows.append)
        try:
            await speech.start()
            await speech.feed(b"\0\0" * 1600)
            await speech.finish()
        finally:
            await speech.close()
        assert [(row.text, row.final) for row in rows] == [("重点知识", False), ("重点知识", True)]
        assert rows[0].source_id == rows[1].source_id
        assert received[1] == b"\0\0" * 1600


async def test_provider_disconnect_fails_and_error_never_echoes_key(monkeypatch: pytest.MonkeyPatch) -> None:
    async def handler(socket: ServerConnection) -> None:
        start = json.loads(await socket.recv())
        await socket.send(
            json.dumps(
                {
                    "header": {
                        "task_id": start["header"]["task_id"],
                        "event": "task-failed",
                        "error_message": "synthetic-private-key",
                    }
                }
            )
        )

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(asr_providers, "DirectConnect", lambda _url, **kwargs: connect(f"ws://127.0.0.1:{port}", **kwargs))
        speech = StreamingSpeech(SpeechConfig(settings=ASRSettings(mode="dashscope"), keys={"dashscope": SecretStr("synthetic-private-key")}), lambda row: None)
        with pytest.raises(AudioError) as error:
            await speech.start()
        assert "synthetic" not in str(error.value)
        await speech.close()


async def test_openai_transcription_uses_bounded_wav_and_sanitizes_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            assert b"RIFF" in request.content and b"speech.wav" in request.content
            return httpx.Response(200, json={"text": "课堂作业"})
        return httpx.Response(401, json={"error": {"message": "synthetic-private-key"}})

    class Client(httpx.AsyncClient):
        def __init__(self, *, trust_env: bool, follow_redirects: bool, timeout: httpx.Timeout) -> None:
            super().__init__(transport=httpx.MockTransport(respond), trust_env=trust_env, follow_redirects=follow_redirects, timeout=timeout)

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    speech = ChunkSpeech(SpeechConfig(settings=ASRSettings(mode="openai"), keys={"asr": SecretStr("synthetic-private-key")}))
    await speech.start()
    assert await speech.transcribe(b"\0\0" * 1600) == "课堂作业"
    with pytest.raises(AudioError) as error:
        await speech.transcribe(b"\0\0" * 1600)
    assert "synthetic-private-key" not in str(error.value)
    assert len(requests) == 2


async def test_closing_stream_interrupts_receiver(monkeypatch: pytest.MonkeyPatch) -> None:
    closed = asyncio.Event()

    async def handler(socket: ServerConnection) -> None:
        start = json.loads(await socket.recv())
        await socket.send(json.dumps({"header": {"task_id": start["header"]["task_id"], "event": "task-started"}}))
        await socket.wait_closed()
        closed.set()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(asr_providers, "DirectConnect", lambda _url, **kwargs: connect(f"ws://127.0.0.1:{port}", **kwargs))
        speech = StreamingSpeech(SpeechConfig(settings=ASRSettings(mode="dashscope"), keys={"dashscope": SecretStr("synthetic")}), lambda row: None)
        await speech.start()
        await asyncio.wait_for(speech.close(), 1)
        await asyncio.wait_for(closed.wait(), 1)
