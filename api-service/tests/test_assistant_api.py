import asyncio
from pathlib import Path

import httpx

from classfox.app import create_app
from classfox.assistant import Assistant
from classfox.config import RuntimeConfig
from classfox.settings import LLMSettings, Preferences, SettingsStore
from tests.test_llm import ControlledStream, TestCredentials


async def test_stop_returns_while_summary_is_running_and_cancel_releases_provider(tmp_path: Path) -> None:
    SettingsStore(tmp_path / "preferences.json").save(Preferences(llm=LLMSettings(managed=False)))
    body = ControlledStream()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=body))
    app = create_app(RuntimeConfig(data_dir=tmp_path, api_token="synthetic-token"), credentials=TestCredentials(), provider_transport=transport)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost", headers={"Authorization": "Bearer synthetic-token"}) as client,
    ):
        started = await client.post("/api/v2/sessions", json={"course_name": "独立总结", "source": "text"})
        session_id = started.json()["id"]
        await client.post(f"/api/v2/sessions/{session_id}/entries", json={"text": "课堂原文", "source_id": "one"})
        result = await asyncio.wait_for(client.post(f"/api/v2/sessions/{session_id}/stop"), 1)
        assert result.status_code == 200
        assert result.json()["status"] == "stopped"
        jobs = (await client.get("/api/v2/assistant")).json()
        assert len(jobs) == 1
        assert jobs[0]["kind"] == "summary"
        assistant: Assistant = app.state.assistant
        subscription = assistant.events.subscribe("desktop")
        async with asyncio.timeout(20):
            while (await subscription.queue.get()).type != "assistant.delta":
                pass
        cancelled = await client.delete(f"/api/v2/assistant/{jobs[0]['id']}")
        assert cancelled.json()["status"] == "cancelled"
        assert body.closed
        await client.post(f"/api/v2/sessions/{session_id}/stop")
        assert len((await client.get("/api/v2/assistant")).json()) == 1
        assert (await client.post("/api/v2/sessions", json={"course_name": "下一堂", "source": "text"})).status_code == 201
        assert not assistant.store.list_summaries(session_id)


async def test_assistant_api_validates_empty_summary_and_auth(client: httpx.AsyncClient) -> None:
    session_id = (await client.post("/api/v2/sessions", json={"source": "text"})).json()["id"]
    path = f"/api/v2/sessions/{session_id}/assistant"
    assert (await client.post(path, json={"kind": "summary"})).status_code == 409
    assert (await client.post(path, json={"kind": "followup"})).status_code == 422
    assert (await client.post(path, json={"kind": "rescue"}, headers={"Authorization": "Bearer wrong"})).status_code == 401
    assert (await client.get("/api/v2/assistant/unknown")).status_code == 404
