import pytest

from classfox.model_catalog import runtime_asset


@pytest.mark.parametrize("architecture", ["arm64", "x86_64"])
def test_runtime_rejects_older_macos_before_downloading(monkeypatch: pytest.MonkeyPatch, architecture: str) -> None:
    monkeypatch.setattr("classfox.model_catalog.platform.system", lambda: "Darwin")
    monkeypatch.setattr("classfox.model_catalog.platform.machine", lambda: architecture)
    monkeypatch.setattr("classfox.model_catalog.platform.mac_ver", lambda: ("13.2.1", ("", "", ""), architecture))
    with pytest.raises(ValueError, match="13.3"):
        runtime_asset()
    monkeypatch.setattr("classfox.model_catalog.platform.mac_ver", lambda: ("13.3", ("", "", ""), architecture))
    assert "macos" in runtime_asset().filename
