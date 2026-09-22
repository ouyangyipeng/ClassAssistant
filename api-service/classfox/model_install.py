import asyncio
import hashlib
import logging
import os
import shutil
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel

from classfox.downloads import Asset, DownloadError, digest_matches, download_asset, unpack_archive
from classfox.events import Event, EventBus
from classfox.model_catalog import CATALOG, ModelDefinition, runtime_asset

logger = logging.getLogger(__name__)
ModelProbe = Callable[[ModelDefinition, Path], Awaitable[None]]


async def disk_operation[**P, R](operation: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    task = asyncio.create_task(asyncio.to_thread(operation, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # A native copy/extract cannot be cancelled; finish it before staging cleanup.
        await task
        raise


class Installation(BaseModel):
    model_id: str
    status: Literal["missing", "downloading", "verifying", "loading", "ready", "failed", "cancelled"] = "missing"
    downloaded_bytes: int = 0
    total_bytes: int = 0
    message: str = "尚未安装"


class InstalledModel(BaseModel):
    directory: str
    fingerprint: str
    verified_at: datetime


class ModelInstaller:
    def __init__(
        self,
        root: Path,
        events: EventBus,
        probe: ModelProbe,
        *,
        client: httpx.AsyncClient | None = None,
        catalog: dict[str, ModelDefinition] | None = None,
    ) -> None:
        self.root = root
        self.events = events
        self._probe = probe
        self._client = client or httpx.AsyncClient(trust_env=False)
        self._owns_client = client is None
        self.catalog = CATALOG if catalog is None else catalog
        self._states: dict[str, Installation] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def _definition(self, model_id: str) -> ModelDefinition:
        if model_id not in self.catalog:
            raise KeyError("未找到此模型")
        return self.catalog[model_id]

    def _assets(self, definition: ModelDefinition) -> list[Asset]:
        return [*definition.files, *([runtime_asset()] if definition.kind == "llm" else [])]

    def _fingerprint(self, definition: ModelDefinition) -> str:
        content = definition.model_dump_json() + "".join(asset.sha256 for asset in self._assets(definition))
        return hashlib.sha256(content.encode()).hexdigest()

    def installed_path(self, model_id: str) -> Path | None:
        definition = self._definition(model_id)
        marker = self.root / f"{model_id}.json"
        if not marker.is_file():
            return None
        try:
            record = InstalledModel.model_validate_json(marker.read_text(encoding="utf-8"))
            if record.fingerprint != self._fingerprint(definition) or not record.directory.isalnum() or len(record.directory) != 32:
                return None
            directory = self.root / "installed" / record.directory
            if not directory.is_dir() or directory.is_symlink():
                return None
            if any(
                not (directory / asset.filename).is_file() or (directory / asset.filename).stat().st_size != asset.size for asset in self._assets(definition)
            ):
                return None
            return directory
        except (OSError, ValueError):
            return None

    def status(self, model_id: str) -> Installation:
        self._definition(model_id)
        if model_id in self._states:
            return self._states[model_id].model_copy()
        if self.installed_path(model_id):
            return Installation(model_id=model_id, status="ready", message="已安装并通过加载检查")
        return Installation(model_id=model_id)

    async def verified_path(self, model_id: str) -> Path | None:
        directory = self.installed_path(model_id)
        if directory is None:
            return None
        if await disk_operation(self._verify, self._definition(model_id), directory):
            return directory
        state = Installation(model_id=model_id, status="failed", message="已安装文件未通过完整性检查，请重新安装")
        self._states[model_id] = state
        self._publish(state)
        return None

    def start(self, model_id: str) -> Installation:
        definition = self._definition(model_id)
        if model_id in self._tasks:
            return self.status(model_id)
        assets = self._assets(definition)
        state = Installation(model_id=model_id, status="verifying", total_bytes=sum(asset.size for asset in assets), message="正在检查安装状态")
        self._states[model_id] = state
        task = asyncio.create_task(self._install(definition, state), name=f"install-{model_id}")
        self._tasks[model_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(model_id, None))
        self._publish(state)
        return state.model_copy()

    async def wait(self, model_id: str) -> None:
        if task := self._tasks.get(model_id):
            await asyncio.shield(task)

    async def cancel(self, model_id: str) -> Installation:
        self._definition(model_id)
        if task := self._tasks.get(model_id):
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            state = self._states[model_id]
            state.status, state.message = "cancelled", "已取消；已下载部分可在重试时继续"
            self._publish(state)
        return self.status(model_id)

    async def close(self) -> None:
        for model_id in list(self._tasks):
            await self.cancel(model_id)
        if self._owns_client:
            await self._client.aclose()

    def _publish(self, state: Installation) -> None:
        self.events.publish("desktop", Event(type="model.installation", data=state.model_dump(mode="json")))

    async def _install(self, definition: ModelDefinition, state: Installation) -> None:
        staging: Path | None = None
        try:
            if (existing := self.installed_path(definition.id)) and await disk_operation(self._verify, definition, existing):
                state.status, state.message = "ready", "已安装并通过完整性检查"
                state.downloaded_bytes = state.total_bytes
                return
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if shutil.disk_usage(self.root).free < state.total_bytes * 2 + 256 * 1024**2:
                raise DownloadError("磁盘空间不足，需为下载和安装预留约两倍模型大小及运行库空间")
            files = await self._download(definition, state)
            staging = self.root / "installed" / uuid4().hex
            staging.mkdir(parents=True, mode=0o700)
            for artifact, source in files:
                destination = staging / artifact.filename
                await disk_operation(shutil.copyfile, source, destination)
            state.status, state.message = "loading", "正在验证模型能否加载"
            self._publish(state)
            if definition.kind == "llm":
                await disk_operation(unpack_archive, staging / runtime_asset().filename, staging / "runtime")
            await self._probe(definition, staging)
            self._mark_ready(definition, staging)
            staging = None
            state.status, state.message = "ready", "已安装并通过加载检查"
        except asyncio.CancelledError:
            state.status, state.message = "cancelled", "已取消；已下载部分可在重试时继续"
        except Exception as error:
            logger.error("Model installation failed: %s", type(error).__name__)
            state.status = "failed"
            state.message = str(error) if isinstance(error, DownloadError) else "模型安装或加载失败；请检查网络、磁盘空间和可用内存后重试"
        finally:
            if staging is not None:
                # Only this attempt's freshly-created staging directory is removed.
                try:
                    await disk_operation(shutil.rmtree, staging)
                except OSError as error:
                    logger.error("Model staging cleanup failed: %s", type(error).__name__)
                    state.message += "；临时文件清理失败，请检查目录权限"
            self._publish(state)

    async def _download(self, definition: ModelDefinition, state: Installation) -> list[tuple[Asset, Path]]:
        state.status, state.message = "downloading", "正在下载模型与运行库"
        files: list[tuple[Asset, Path]] = []
        completed = 0
        last_update = 0.0

        def progress(count: int) -> None:
            nonlocal last_update
            state.downloaded_bytes = completed + count
            now = monotonic()
            if now - last_update >= 0.1 or state.downloaded_bytes == state.total_bytes:
                self._publish(state)
                last_update = now

        for asset in self._assets(definition):
            path = self.root / "downloads" / asset.sha256 / asset.filename
            await download_asset(self._client, asset, path, progress)
            files.append((asset, path))
            completed += asset.size
        return files

    def _verify(self, definition: ModelDefinition, directory: Path) -> bool:
        return all(digest_matches(directory / asset.filename, asset) for asset in self._assets(definition))

    def _mark_ready(self, definition: ModelDefinition, directory: Path) -> None:
        marker = self.root / f"{definition.id}.json"
        temporary = marker.with_suffix(".tmp")
        record = InstalledModel(directory=directory.name, fingerprint=self._fingerprint(definition), verified_at=datetime.now(UTC))
        with temporary.open("w", encoding="utf-8") as output:
            output.write(record.model_dump_json())
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, marker)
