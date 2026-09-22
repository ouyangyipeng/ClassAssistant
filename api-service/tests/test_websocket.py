import asyncio
import json
import socket
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import uvicorn
from httpx import AsyncClient, MockTransport, Response
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosedError

from classfox.app import create_app
from classfox.config import RuntimeConfig
from classfox.settings import LLMSettings, Preferences, SettingsStore
from tests.test_llm import TestCredentials, delta


@pytest.fixture
async def live_service(tmp_path: Path) -> AsyncIterator[int]:
    SettingsStore(tmp_path / "preferences.json").save(Preferences(llm=LLMSettings(managed=False)))
    provider = MockTransport(lambda request: Response(200, content=delta("可直接口述的回答") + delta(finish="stop") + b"data: [DONE]\n\n"))
    app = create_app(RuntimeConfig(data_dir=tmp_path, api_token="synthetic-websocket-token"), credentials=TestCredentials(), provider_transport=provider)
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False, ws="websockets-sansio"))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(5):
                while not server.started:
                    if task.done():
                        await task
                    await asyncio.sleep(0.01)
            yield port
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, timeout=5)


async def test_websocket_authenticates_then_delivers_session_and_transcript(live_service: int) -> None:
    async with connect(f"ws://127.0.0.1:{live_service}/api/v2/events", proxy=None) as websocket:
        await websocket.send(json.dumps({"type": "auth", "token": "synthetic-websocket-token"}))
        snapshot = json.loads(await websocket.recv())
        assert snapshot["type"] == "snapshot"
        assert snapshot["data"]["session"] is None
        async with AsyncClient(base_url=f"http://127.0.0.1:{live_service}", headers={"Authorization": "Bearer synthetic-websocket-token"}) as client:
            session = (await client.post("/api/v2/sessions", json={"source": "text"})).json()
            assert json.loads(await websocket.recv())["type"] == "session"
            await client.post(f"/api/v2/sessions/{session['id']}/entries", json={"text": "真实网络事件测试", "source_id": "ws1"})
            event = json.loads(await websocket.recv())
            assert event["type"] == "transcript"
            assert event["data"]["text"] == "真实网络事件测试"


async def test_websocket_rejects_invalid_credentials_without_data(live_service: int) -> None:
    async with connect(f"ws://127.0.0.1:{live_service}/api/v2/events", proxy=None) as websocket:
        await websocket.send(json.dumps({"type": "auth", "token": "wrong"}))
        with pytest.raises(ConnectionClosedError):
            await websocket.recv()


async def test_assistant_http_task_streams_over_real_websocket(live_service: int) -> None:
    async with (
        connect(f"ws://127.0.0.1:{live_service}/api/v2/events", proxy=None) as websocket,
        AsyncClient(base_url=f"http://127.0.0.1:{live_service}", headers={"Authorization": "Bearer synthetic-websocket-token"}) as client,
    ):
        await websocket.send(json.dumps({"type": "auth", "token": "synthetic-websocket-token"}))
        await websocket.recv()
        session = (await client.post("/api/v2/sessions", json={"source": "text"})).json()
        job = (await client.post(f"/api/v2/sessions/{session['id']}/assistant", json={"kind": "rescue"})).json()
        received: list[dict[str, object]] = []
        async with asyncio.timeout(20):
            while True:
                event = json.loads(await websocket.recv())
                received.append(event)
                if event["type"] == "assistant.finished":
                    assert event["data"]["status"] == "completed"
                    break
        assert any(event["type"] == "assistant.delta" for event in received)
        snapshot = (await client.get(f"/api/v2/assistant/{job['id']}")).json()
        assert snapshot["markdown"] == "可直接口述的回答"
        assert snapshot["first_token_ms"] >= 0
