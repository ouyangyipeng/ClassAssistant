from pathlib import Path

import httpx

from classfox.app import create_app
from classfox.config import RuntimeConfig
from classfox.settings import LLMSettings, Preferences, SettingsStore
from tests.test_llm import TestCredentials, delta


async def test_probe_requires_admin_and_returns_sanitized_failures(tmp_path: Path) -> None:
    SettingsStore(tmp_path / "preferences.json").save(Preferences(llm=LLMSettings(mode="byok", base_url="https://provider.example/v1")))
    app = create_app(
        RuntimeConfig(data_dir=tmp_path, api_token="synthetic-admin"),
        credentials=TestCredentials(),
        provider_transport=httpx.MockTransport(lambda request: httpx.Response(401, json={"error": {"message": "do-not-expose-synthetic-key"}})),
    )
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost") as client:
        assert (await client.post("/api/v2/assistant/test")).status_code == 401
        result = await client.post("/api/v2/assistant/test", headers={"Authorization": "Bearer synthetic-admin"})
        assert result.status_code == 503
        assert result.json()["error"] == "invalid_key"
        assert "do-not-expose" not in result.text


async def test_probe_reports_timings_without_creating_a_classroom(tmp_path: Path) -> None:
    SettingsStore(tmp_path / "preferences.json").save(
        Preferences(llm=LLMSettings(mode="byok", base_url="https://provider.example/v1", model="synthetic-model"))
    )
    app = create_app(
        RuntimeConfig(data_dir=tmp_path, api_token="synthetic-admin"),
        credentials=TestCredentials(),
        provider_transport=httpx.MockTransport(lambda request: httpx.Response(200, content=delta("成功", finish="stop") + b"data: [DONE]\n\n")),
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost", headers={"Authorization": "Bearer synthetic-admin"}) as client,
    ):
        result = await client.post("/api/v2/assistant/test")
        assert result.status_code == 200
        assert result.json()["ok"] and result.json()["total_ms"] >= 0
        assert result.json()["model"] == "synthetic-model"
        assert (await client.get("/api/v2/sessions")).json() == []
