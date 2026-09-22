import asyncio
import hashlib
import io
import tarfile
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from classfox.downloads import Asset, DownloadError, download_asset, unpack_archive


def asset(data: bytes) -> Asset:
    return Asset(url="https://models.example/model.bin", filename="model.bin", size=len(data), sha256=hashlib.sha256(data).hexdigest())


async def test_download_checks_digest_and_only_promotes_complete_file(tmp_path: Path) -> None:
    payload = b"complete-model"
    destination = tmp_path / "model.bin"
    progress: list[int] = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=payload))) as client:
        await download_asset(client, asset(payload), destination, progress.append)
    assert destination.read_bytes() == payload
    assert progress[-1] == len(payload)
    assert not destination.with_suffix(".bin.partial").exists()


async def test_wrong_digest_never_replaces_existing_install(tmp_path: Path) -> None:
    destination = tmp_path / "model.bin"
    destination.write_bytes(b"previous-working-model")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"bad"))) as client:
        with pytest.raises(DownloadError):
            await download_asset(client, asset(b"new"), destination, lambda count: None)
    assert destination.read_bytes() == b"previous-working-model"


async def test_interrupted_download_resumes_with_validated_range(tmp_path: Path) -> None:
    payload = b"complete-model"
    destination = tmp_path / "model.bin"
    destination.with_suffix(".bin.partial").write_bytes(payload[:4])

    def provider(request: httpx.Request) -> httpx.Response:
        assert request.headers["range"] == "bytes=4-"
        return httpx.Response(206, content=payload[4:], headers={"content-range": f"bytes 4-{len(payload) - 1}/{len(payload)}"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        await download_asset(client, asset(payload), destination, lambda count: None)
    assert destination.read_bytes() == payload


async def test_cancel_preserves_partial_and_closes_connection(tmp_path: Path) -> None:
    progressed = asyncio.Event()
    closed = asyncio.Event()
    payload = b"m" * (128 * 1024)

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield payload[:65536]
            await asyncio.Event().wait()

        async def aclose(self) -> None:
            closed.set()

    def progress(count: int) -> None:
        if count:
            progressed.set()

    destination = tmp_path / "model.bin"
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=Body()))) as client:
        task = asyncio.create_task(download_asset(client, asset(payload), destination, progress))
        await asyncio.wait_for(progressed.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert closed.is_set()
    assert destination.with_suffix(".bin.partial").read_bytes() == payload[:65536]
    assert not destination.exists()


@pytest.mark.parametrize("content_range", ["bytes 0-9/14", "bytes 4-13/99", "not-a-range"])
async def test_invalid_resume_metadata_is_rejected(tmp_path: Path, content_range: str) -> None:
    payload = b"complete-model"
    destination = tmp_path / "model.bin"
    destination.with_suffix(".bin.partial").write_bytes(payload[:4])
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(206, content=payload[4:], headers={"content-range": content_range}))
    ) as client:
        with pytest.raises(DownloadError):
            await download_asset(client, asset(payload), destination, lambda count: None)
    assert not destination.exists()


@pytest.mark.parametrize("filename", ["../escape", "/absolute", "folder/../../escape", "C:\\escape"])
def test_archive_rejects_escaping_paths(tmp_path: Path, filename: str) -> None:
    archive = tmp_path / "runtime.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        item = tarfile.TarInfo(filename)
        item.size = 3
        output.addfile(item, io.BytesIO(b"bad"))
    with pytest.raises(DownloadError):
        unpack_archive(archive, tmp_path / "unpacked", max_bytes=100)
    assert not (tmp_path / "escape").exists()


def test_archive_expansion_is_bounded_before_writing(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        item = tarfile.TarInfo("huge.bin")
        item.size = 101
        output.addfile(item, io.BytesIO(b"x" * 101))
    with pytest.raises(DownloadError):
        unpack_archive(archive, tmp_path / "unpacked", max_bytes=100)
    assert not (tmp_path / "unpacked" / "huge.bin").exists()


def test_runtime_library_links_are_materialized_as_files(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        item = tarfile.TarInfo("bin/library.1.dylib")
        item.size, item.mode = 3, 0o755
        output.addfile(item, io.BytesIO(b"lib"))
        link = tarfile.TarInfo("bin/library.dylib")
        link.type, link.linkname = tarfile.SYMTYPE, "library.1.dylib"
        output.addfile(link)
    unpack_archive(archive, tmp_path / "unpacked", max_bytes=10)
    library = tmp_path / "unpacked" / "bin" / "library.dylib"
    assert not library.is_symlink()
    assert library.read_bytes() == b"lib"


def test_archive_rejects_link_escape(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        link = tarfile.TarInfo("escape")
        link.type, link.linkname = tarfile.SYMTYPE, "../../outside"
        output.addfile(link)
    with pytest.raises(DownloadError):
        unpack_archive(archive, tmp_path / "unpacked")
