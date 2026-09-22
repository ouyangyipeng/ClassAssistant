from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient, MockTransport, Response

from classfox.app import create_app
from classfox.config import RuntimeConfig
from classfox.settings import LLMSettings, Preferences, SettingsStore


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    token = "synthetic-api-test-token"
    SettingsStore(tmp_path / "preferences.json").save(Preferences(llm=LLMSettings(managed=False)))
    app = create_app(RuntimeConfig(data_dir=tmp_path, api_token=token), provider_transport=MockTransport(lambda request: Response(503)))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost", headers={"Authorization": f"Bearer {token}"}) as test_client,
    ):
        yield test_client
