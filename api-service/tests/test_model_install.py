import asyncio
import hashlib
from pathlib import Path

import httpx

from classfox.events import EventBus
from classfox.model_catalog import ModelDefinition
from classfox.model_install import ModelInstaller
from tests.test_downloads import asset


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


async def test_cancel_during_probe_never_marks_ready(tmp_path: Path) -> None:
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
        installer.start("test-asr")
        await asyncio.wait_for(loading.wait(), 2)
        await installer.cancel("test-asr")
        assert stopped.is_set()
        assert installer.status("test-asr").status == "cancelled"
        assert installer.installed_path("test-asr") is None
        await installer.close()
