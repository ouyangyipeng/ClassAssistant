from pathlib import Path
from typing import Literal

import pytest
from httpx import ASGITransport, AsyncClient

from classfox.app import create_app
from classfox.config import RuntimeConfig
from classfox.credentials import CredentialName
from classfox.settings import SettingsStore


class MemoryCredentials:
    def __init__(self) -> None:
        self.values: dict[CredentialName, str] = {}

    def get(self, name: CredentialName) -> str | None:
        return self.values.get(name)

    def set(self, name: CredentialName, value: str | None) -> None:
        if value is None:
            self.values.pop(name, None)
        else:
            self.values[name] = value


async def test_credential_save_and_delete_never_return_secret(tmp_path: Path) -> None:
    credentials = MemoryCredentials()
    app = create_app(RuntimeConfig(data_dir=tmp_path, api_token="synthetic-token"), credentials=credentials)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app), base_url="http://localhost", headers={"Authorization": "Bearer synthetic-token"}) as client,
    ):
        saved = await client.put("/api/v2/credentials/llm", json={"value": "synthetic-provider-key"})
        assert saved.status_code == 200
        assert credentials.get("llm") == "synthetic-provider-key"
        assert "synthetic-provider-key" not in saved.text
        assert (await client.get("/api/v2/credentials")).json()["llm"] is True
        assert "synthetic-provider-key" not in (await client.get("/api/v2/settings")).text
        assert (await client.delete("/api/v2/credentials/llm")).status_code == 200
        assert credentials.get("llm") is None
        bad = await client.put("/api/v2/credentials/llm", json={"value": "synthetic-provider-key", "extra": "private-fixture"})
        assert bad.status_code == 422
        assert "private-fixture" not in bad.text
    assert not any("synthetic-provider-key" in path.read_text() for path in tmp_path.glob("*.json"))


def test_explicit_legacy_settings_import_preserves_existing_keys_and_source(tmp_path: Path) -> None:
    from classfox.credentials import import_legacy_settings

    source = tmp_path / "old.env"
    text = "LLM_BASE_URL=https://api.example.org/v1\nLLM_API_KEY=synthetic-old-key\nLLM_MODEL=old-model\nASR_MODE=local\n"
    source.write_text(text)
    credentials = MemoryCredentials()
    credentials.set("llm", "synthetic-existing-key")
    settings = SettingsStore(tmp_path / "settings.json")
    result = import_legacy_settings(source, settings, credentials)
    assert credentials.get("llm") == "synthetic-existing-key"
    assert settings.load().llm.model == "old-model"
    assert settings.load().asr.mode == "google"
    assert source.read_text() == text
    assert "synthetic-old-key" not in repr(result)
    assert "synthetic-old-key" not in settings.path.read_text()


@pytest.mark.parametrize("kind", ["missing", "example"])
def test_legacy_import_requires_a_real_user_config(tmp_path: Path, kind: Literal["missing", "example"]) -> None:
    from classfox.credentials import import_legacy_settings

    source = tmp_path / ("missing.env" if kind == "missing" else ".env.example")
    if kind == "example":
        source.write_text("LLM_API_KEY=synthetic-template-key")
    with pytest.raises(ValueError):
        import_legacy_settings(source, SettingsStore(tmp_path / "settings.json"), MemoryCredentials())
