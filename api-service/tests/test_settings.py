from pathlib import Path

import pytest
from pydantic import ValidationError

from classfox.settings import Preferences, SettingsStore


def test_preferences_persist_without_embedding_credentials(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    store = SettingsStore(path)
    preferences = Preferences.model_validate(
        {"keywords": ["小王", "学号 123"], "llm": {"mode": "byok", "base_url": "https://api.example.org/v1", "model": "classroom-model"}}
    )
    store.save(preferences)
    loaded = SettingsStore(path).load()
    assert loaded.keywords == ["小王", "学号 123"]
    assert loaded.llm.model == "classroom-model"
    with pytest.raises(ValidationError):
        Preferences.model_validate({"llm": {"api_key": "synthetic-test-key"}})
    assert "synthetic-test-key" not in path.read_text()


@pytest.mark.parametrize("url", ["file:///tmp/foo", "https://user:pass@example.org", "https://example.org/?api_key=test", "http://example.org"])
def test_provider_url_rejects_unsafe_transport_and_embedded_credentials(url: str) -> None:
    with pytest.raises(ValidationError):
        Preferences.model_validate({"llm": {"mode": "byok", "base_url": url}})


def test_invalid_saved_preferences_are_reported_instead_of_silently_reset(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    path.write_text('{"keywords": 123}', encoding="utf-8")
    with pytest.raises(ValueError, match="配置文件"):
        SettingsStore(path).load()
    assert path.read_text() == '{"keywords": 123}'


def test_local_endpoint_and_keyword_normalization() -> None:
    preferences = Preferences.model_validate({"keywords": [" 小王 ", "", "小王", "同学"], "llm": {"base_url": "http://127.0.0.1:8080/v1/"}})
    assert preferences.keywords == ["小王", "同学"]
    assert preferences.llm.base_url == "http://127.0.0.1:8080/v1"
