import asyncio
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from classfox.app import create_app
from classfox.config import RuntimeConfig
from classfox.model_process import ModelEndpoint, OwnedModelProcess
from tests.test_model_process import SERVER


async def test_catalog_reports_uninstalled_models_without_starting_downloads(client: AsyncClient) -> None:
    response = await client.get("/api/v2/models")
    assert response.status_code == 200
    assert {item["model"]["kind"] for item in response.json()} == {"asr", "llm"}
    assert all(item["installation"]["status"] == "missing" for item in response.json())
    assert (await client.post("/api/v2/models/unknown/install")).status_code == 404
    assert (await client.post("/api/v2/models/qwen35-4b/install", headers={"Authorization": "Bearer wrong"})).status_code == 401
    assert (await client.get("/api/v2/models/runtime")).json() == {"ready": False}
    start = await client.post("/api/v2/models/qwen35-4b/start")
    assert start.status_code == 503
    assert start.json()["error"] == "local_model_unavailable"


async def test_missing_managed_model_has_actionable_job_error(client: AsyncClient) -> None:
    preferences = (await client.get("/api/v2/settings")).json()
    preferences["llm"]["managed"] = True
    await client.put("/api/v2/settings", json=preferences)
    session = (await client.post("/api/v2/sessions", json={"source": "text"})).json()
    job = (await client.post(f"/api/v2/sessions/{session['id']}/assistant", json={"kind": "rescue", "question": "什么是二叉树？"})).json()
    async with asyncio.timeout(2):
        while (result := (await client.get(f"/api/v2/assistant/{job['id']}")).json())["status"] in {"running", "queued"}:
            await asyncio.sleep(0.01)
    assert result["status"] == "failed"
    assert result["error_code"] == "local_model_unavailable"
    assert "安装" in result["error_message"]


async def test_preparing_model_is_not_ready_and_parallel_requests_wait(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app(RuntimeConfig(data_dir=tmp_path, api_token="synthetic-model-start-token"))
    loading, release = asyncio.Event(), asyncio.Event()
    server = tmp_path / "synthetic_server.py"
    server.write_text(SERVER)
    original_start, original_wait = OwnedModelProcess.start, OwnedModelProcess._wait_ready

    async def wait(self: OwnedModelProcess, endpoint: ModelEndpoint, seconds: float) -> None:
        loading.set()
        await release.wait()
        await original_wait(self, endpoint, seconds)

    async def start(self: OwnedModelProcess, command: list[str], model: Path, *, startup_seconds: float = 120) -> ModelEndpoint:
        return await original_start(self, [sys.executable, str(server)], model, startup_seconds=5)

    async def verified(model_id: str) -> Path:
        return tmp_path

    monkeypatch.setattr(OwnedModelProcess, "start", start)
    monkeypatch.setattr(OwnedModelProcess, "_wait_ready", wait)
    monkeypatch.setattr("classfox.app.runtime_executable", lambda path: server)
    async with app.router.lifespan_context(app):
        models = app.state.models
        monkeypatch.setattr(models, "verified_path", verified)
        definition = models.catalog["qwen35-4b"]
        (tmp_path / next(asset.filename for asset in definition.files if asset.filename.endswith(".gguf"))).write_bytes(b"synthetic")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://localhost", headers={"Authorization": "Bearer synthetic-model-start-token"}
        ) as http:
            tasks = [asyncio.create_task(http.post("/api/v2/models/qwen35-4b/start"))]
            try:
                await asyncio.wait_for(loading.wait(), 2)
                assert app.state.owned_model.pid is not None
                assert (await http.get("/api/v2/models/runtime")).json() == {"ready": False}
                tasks.append(asyncio.create_task(http.post("/api/v2/models/qwen35-4b/start")))
                await asyncio.sleep(0.02)
                assert not tasks[1].done()
                release.set()
                responses = await asyncio.wait_for(asyncio.gather(*tasks), 5)
                assert all(response.status_code == 200 for response in responses)
                assert (await http.get("/api/v2/models/runtime")).json() == {"ready": True}
            finally:
                release.set()
                await asyncio.gather(*tasks, return_exceptions=True)
