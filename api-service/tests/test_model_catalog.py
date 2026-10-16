import pytest

from classfox.download_sources import MODELSCOPE_QWEN, download_sources
from classfox.downloads import Asset
from classfox.model_catalog import CATALOG, runtime_asset


def test_domestic_source_keeps_original_asset_and_install_fingerprint() -> None:
    model = CATALOG["qwen35-4b"]
    asset = model.files[0]
    original = model.model_dump_json()
    assert download_sources(asset) == (MODELSCOPE_QWEN, asset.url)
    assert model.model_dump_json() == original
    assert "modelscope" not in original


@pytest.mark.parametrize("asset", CATALOG["sensevoice-small"].files[:3], ids=lambda asset: asset.filename)
def test_speech_download_prefers_pinned_domestic_copy_without_changing_install(asset: Asset) -> None:
    model = CATALOG["sensevoice-small"]
    original = model.model_dump_json()
    sources = download_sources(asset)
    base = "https://modelscope.cn/models/gomodels/sherpa/resolve/590473aaa26eed19b270a424cb641972ae56482d/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
    assert sources == (f"{base}/{asset.filename}", asset.url)
    assert model.model_dump_json() == original


@pytest.mark.parametrize("architecture", ["arm64", "x86_64"])
def test_runtime_rejects_older_macos_before_downloading(monkeypatch: pytest.MonkeyPatch, architecture: str) -> None:
    monkeypatch.setattr("classfox.model_catalog.platform.system", lambda: "Darwin")
    monkeypatch.setattr("classfox.model_catalog.platform.machine", lambda: architecture)
    monkeypatch.setattr("classfox.model_catalog.platform.mac_ver", lambda: ("13.2.1", ("", "", ""), architecture))
    with pytest.raises(ValueError, match="13.3"):
        runtime_asset()
    monkeypatch.setattr("classfox.model_catalog.platform.mac_ver", lambda: ("13.3", ("", "", ""), architecture))
    assert "macos" in runtime_asset().filename
