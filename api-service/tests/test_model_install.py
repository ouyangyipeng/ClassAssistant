import asyncio
import hashlib
import zipfile
from pathlib import Path

import httpx
import pytest

from classfox.events import EventBus
from classfox.model_catalog import ModelDefinition
from classfox.model_install import ModelInstaller
from tests.test_downloads import asset


async def test_offline_import_needs_no_network_and_checks_load(tmp_path: Path) -> None:
    package = tmp_path / "model.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("model.bin", b"synthetic-model")
    observed: list[Path] = []

    async def probe(model: ModelDefinition, root: Path) -> None:
        observed.append(root)

    def no_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Offline installation must not access the network")

    async with httpx.AsyncClient(transport=httpx.MockTransport(no_network)) as client:
        installer = ModelInstaller(tmp_path / "models", EventBus(), probe, client=client, catalog={"test-asr": definition()})
        installer.start_import("test-asr", package)
        await installer.wait("test-asr")
        assert installer.status("test-asr").status == "ready"
        assert len(observed) == 1
        await installer.close()


async def test_offline_corruption_never_reaches_probe(tmp_path: Path) -> None:
    package = tmp_path / "bad.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("model.bin", b"x" * len(b"synthetic-model"))

    async def probe(model: ModelDefinition, root: Path) -> None:
        raise AssertionError("Invalid bytes cannot reach the loader")

    installer = ModelInstaller(tmp_path / "models", EventBus(), probe, catalog={"test-asr": definition()})
    try:
        installer.start_import("test-asr", package)
        await installer.wait("test-asr")
        assert installer.status("test-asr").status == "failed"
        assert "校验" in installer.status("test-asr").message
        assert installer.installed_path("test-asr") is None
    finally:
        await installer.close()


async def test_bundled_asset_avoids_external_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    resources = tmp_path / "bundled"
    resources.mkdir()
    (resources / "model.bin").write_bytes(b"synthetic-model")
    monkeypatch.setattr("classfox.model_install.bundled_assets", lambda: resources)

    async def probe(model: ModelDefinition, root: Path) -> None:
        assert (root / "model.bin").read_bytes() == b"synthetic-model"

    def no_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Bundled resources must avoid network requests")

    async with httpx.AsyncClient(transport=httpx.MockTransport(no_network)) as client:
        installer = ModelInstaller(tmp_path / "models", EventBus(), probe, client=client, catalog={"test-asr": definition()})
        installer.start("test-asr")
        await installer.wait("test-asr")
        assert installer.status("test-asr").status == "ready"
        assert (resources / "model.bin").read_bytes() == b"synthetic-model"
        await installer.close()


def definition() -> ModelDefinition:
    return ModelDefinition(
        id="test-asr",
        name="Test ASR",
        kind="asr",
        revision="test-revision",
        description="test",
        source_url="https://models.example",
        license_name="test",
        license_url="https://models.example/license",
        files=(asset(b"synthetic-model"),),
    )


async def test_install_requires_verified_files_and_successful_load_probe(tmp_path: Path) -> None:
    observed: list[Path] = []

    async def probe(model: ModelDefinition, root: Path) -> None:
        observed.append(root)
        assert hashlib.sha256((root / "model.bin").read_bytes()).hexdigest() == model.files[0].sha256

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"synthetic-model"))) as client:
        installer = ModelInstaller(tmp_path, EventBus(), probe, client=client, catalog={"test-asr": definition()})
        installer.start("test-asr")
        await installer.wait("test-asr")
        assert installer.status("test-asr").status == "ready"
        assert installer.installed_path("test-asr") == observed[0]
        installer.start("test-asr")
        await installer.wait("test-asr")
        assert len(observed) == 1
        await installer.close()


async def test_load_failure_is_not_an_installed_model(tmp_path: Path) -> None:
    async def probe(model: ModelDefinition, root: Path) -> None:
        raise RuntimeError("synthetic native runtime load failure")

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"synthetic-model"))) as client:
        installer = ModelInstaller(tmp_path, EventBus(), probe, client=client, catalog={"test-asr": definition()})
        installer.start("test-asr")
        await installer.wait("test-asr")
        assert installer.status("test-asr").status == "failed"
        assert installer.installed_path("test-asr") is None
        await installer.close()


@pytest.mark.parametrize("offline", [False, True])
async def test_cancel_during_probe_never_marks_ready(tmp_path: Path, offline: bool) -> None:
    loading = asyncio.Event()
    stopped = asyncio.Event()

    async def probe(model: ModelDefinition, root: Path) -> None:
        loading.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"synthetic-model"))) as client:
        installer = ModelInstaller(tmp_path, EventBus(), probe, client=client, catalog={"test-asr": definition()})
        if offline:
            package = tmp_path / "model.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("model.bin", b"synthetic-model")
            installer.start_import("test-asr", package)
        else:
            installer.start("test-asr")
        await asyncio.wait_for(loading.wait(), 2)
        await installer.cancel("test-asr")
        assert stopped.is_set()
        assert installer.status("test-asr").status == "cancelled"
        assert installer.installed_path("test-asr") is None
        await installer.close()
