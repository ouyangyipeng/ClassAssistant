import asyncio
import hashlib
import os
import re
import shutil
import stat
import tarfile
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DownloadError(Exception):
    pass


class Asset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    url: str
    filename: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    size: int = Field(gt=0, le=10 * 1024**3)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("url")
    @classmethod
    def https_only(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("模型下载必须来自公开 HTTPS 地址")
        return value


def digest_matches(path: Path, asset: Asset) -> bool:
    if not path.is_file() or path.stat().st_size != asset.size:
        return False
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest() == asset.sha256


async def download_asset(client: httpx.AsyncClient, asset: Asset, destination: Path, progress: Callable[[int], None]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if await asyncio.to_thread(digest_matches, destination, asset):
        progress(asset.size)
        return
    partial = destination.with_suffix(destination.suffix + ".partial")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset >= asset.size:
        if await asyncio.to_thread(digest_matches, partial, asset):
            os.replace(partial, destination)
            progress(asset.size)
            return
        partial.unlink()
        offset = 0
    if shutil.disk_usage(destination.parent).free < asset.size - offset + 16 * 1024**2:
        raise DownloadError("磁盘空间不足，请释放空间后重试")
    try:
        await _receive(client, asset, partial, offset, progress)
    except httpx.HTTPError as exc:
        raise DownloadError("模型下载中断，请检查网络后重试；已下载部分会保留") from exc
    if not await asyncio.to_thread(digest_matches, partial, asset):
        partial.unlink(missing_ok=True)
        raise DownloadError("模型完整性校验失败，未启用该文件；请重试下载")
    os.replace(partial, destination)


async def _receive(client: httpx.AsyncClient, asset: Asset, partial: Path, offset: int, progress: Callable[[int], None]) -> None:
    headers = {"Accept-Encoding": "identity"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    async with client.stream("GET", asset.url, headers=headers, follow_redirects=True, timeout=httpx.Timeout(30, connect=10)) as response:
        response.raise_for_status()
        if response.url.scheme != "https":
            raise DownloadError("下载被重定向到不安全地址，已停止")
        if response.status_code == 206:
            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("content-range", ""))
            if not match or tuple(map(int, match.groups())) != (offset, asset.size - 1, asset.size):
                raise DownloadError("下载服务器返回了无效的续传范围，请稍后重试")
        elif response.status_code == 200:
            offset = 0
        else:
            raise DownloadError("下载服务器未返回完整模型文件，请稍后重试")
        with partial.open("ab" if offset else "wb") as output:
            progress(offset)
            async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                offset += len(chunk)
                if offset > asset.size:
                    raise DownloadError("下载文件超过预期大小，已停止")
                output.write(chunk)
                progress(offset)
            output.flush()
            os.fsync(output.fileno())


def safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or not path.parts:
        raise DownloadError("运行时压缩包包含无效路径")
    return path


def unpack_archive(source: Path, destination: Path, *, max_bytes: int = 256 * 1024**2) -> None:
    try:
        if source.suffix == ".zip":
            _unpack_zip(source, destination, max_bytes)
        else:
            _unpack_tar(source, destination, max_bytes)
    except (tarfile.TarError, zipfile.BadZipFile, EOFError) as exc:
        raise DownloadError("运行时压缩包损坏，请重新下载") from exc


def _unpack_zip(source: Path, destination: Path, max_bytes: int) -> None:
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        if len(entries) > 10000 or sum(entry.file_size for entry in entries) > max_bytes:
            raise DownloadError("运行时压缩包超出解压限制")
        names: set[str] = set()
        for entry in entries:
            safe_member(entry.filename)
            if stat.S_ISLNK(entry.external_attr >> 16) or entry.filename.casefold() in names:
                raise DownloadError("运行时压缩包包含重复路径或不支持的链接")
            names.add(entry.filename.casefold())
        destination.mkdir(parents=True, mode=0o700)
        for entry in entries:
            target = destination / entry.filename
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
                continue
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with archive.open(entry) as reader, target.open("xb") as writer:
                shutil.copyfileobj(reader, writer, length=1024 * 1024)
            target.chmod(0o700 if entry.external_attr >> 16 & 0o111 else 0o600)


def _resolve_tar_link(entry: tarfile.TarInfo, entries: dict[str, tarfile.TarInfo]) -> tarfile.TarInfo:
    seen: set[str] = set()
    while entry.issym():
        if entry.name in seen:
            raise DownloadError("运行时压缩包包含循环链接")
        seen.add(entry.name)
        safe_member(entry.linkname)
        target = str(safe_member(str(PurePosixPath(entry.name).parent / entry.linkname)))
        if target not in entries:
            raise DownloadError("运行时压缩包链接目标不存在")
        entry = entries[target]
    if not entry.isfile():
        raise DownloadError("运行时压缩包链接目标不是普通文件")
    return entry


def _unpack_tar(source: Path, destination: Path, max_bytes: int) -> None:
    with tarfile.open(source, "r:*") as archive:
        entries: dict[str, tarfile.TarInfo] = {}
        names: set[str] = set()
        for entry in archive:
            safe_member(entry.name)
            if not (entry.isfile() or entry.isdir() or entry.issym()) or entry.name.casefold() in names:
                raise DownloadError("运行时压缩包包含特殊文件或重复路径")
            entries[entry.name] = entry
            names.add(entry.name.casefold())
            if len(entries) > 10000:
                raise DownloadError("运行时压缩包文件数量超限")
        resolved = {name: _resolve_tar_link(entry, entries) for name, entry in entries.items() if not entry.isdir()}
        if sum(entry.size for entry in resolved.values()) > max_bytes:
            raise DownloadError("运行时压缩包超出解压限制")
        destination.mkdir(parents=True, mode=0o700)
        for name, entry in resolved.items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            reader = archive.extractfile(entry)
            if reader is None:
                raise DownloadError("运行时压缩包缺少文件内容")
            # Copy validated link targets so no archive-controlled symlink is ever created.
            with reader, target.open("xb") as writer:
                shutil.copyfileobj(reader, writer, length=1024 * 1024)
            target.chmod(0o700 if entry.mode & 0o111 else 0o600)
