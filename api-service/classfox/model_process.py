import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

import httpx


class ModelProcessError(Exception):
    pass


@dataclass(frozen=True)
class ModelEndpoint:
    base_url: str
    key: str = field(repr=False)
    model: str = "classfox-local"
    context_characters: int = 6000


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class OwnedModelProcess:
    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._endpoint: ModelEndpoint | None = None
        self._model: Path | None = None
        self._lock = asyncio.Lock()

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process is not None and self._process.returncode is None else None

    @property
    def ready(self) -> bool:
        return self.pid is not None and self._endpoint is not None

    def endpoint(self) -> ModelEndpoint:
        if self.pid is None or self._endpoint is None:
            raise ModelProcessError("本地问答模型尚未运行，请在模型管理中启动或重新安装")
        return self._endpoint

    async def start(self, command: list[str], model: Path, *, startup_seconds: float = 120) -> ModelEndpoint:
        async with self._lock:
            if self.pid is not None and self._model == model:
                return self.endpoint()
            await self._stop()
            if not model.is_file():
                raise ModelProcessError("本地模型文件不存在，请先完成下载")
            port, key = available_port(), secrets.token_urlsafe(32)
            endpoint = ModelEndpoint(base_url=f"http://127.0.0.1:{port}/v1", key=key)
            arguments = [
                *command,
                "-m",
                str(model),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--alias",
                endpoint.model,
                "--ctx-size",
                "32768",
                "--parallel",
                "1",
                "--threads",
                str(min(8, max(2, (os.cpu_count() or 4) // 2))),
                "--reasoning",
                "off",
                "--no-webui",
                "--log-disable",
            ]
            environment = {
                name: value
                for name, value in os.environ.items()
                if name in {"PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TMP", "TEMP", "TMPDIR", "LANG"}
            }
            environment["LLAMA_API_KEY"] = key
            environment.update({"PYTHONUNBUFFERED": "1", "PYINSTALLER_RESET_ENVIRONMENT": "1"})
            supervisor = [sys.executable, "--model-worker"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "classfox.model_worker"]
            try:
                self._process = await asyncio.create_subprocess_exec(
                    *supervisor,
                    env=environment,
                    cwd=Path(__file__).resolve().parent.parent,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                assert self._process.stdin is not None
                self._process.stdin.write(json.dumps(arguments).encode() + b"\n")
                await self._process.stdin.drain()
                await self._wait_ready(endpoint, startup_seconds)
            except BaseException as error:
                await self._stop()
                if isinstance(error, (OSError, TimeoutError)):
                    raise ModelProcessError("本地模型启动失败或超时，请检查可用内存和安装状态") from error
                raise
            self._model, self._endpoint = model, endpoint
            return endpoint

    async def _wait_ready(self, endpoint: ModelEndpoint, seconds: float) -> None:
        async with (
            asyncio.timeout(seconds),
            httpx.AsyncClient(base_url=endpoint.base_url, headers={"Authorization": f"Bearer {endpoint.key}"}, trust_env=False, timeout=2) as client,
        ):
            while True:
                if self.pid is None:
                    raise ModelProcessError("本地模型进程已退出，请检查模型文件、运行库和可用内存")
                try:
                    response = await client.get("/models")
                    if response.status_code == 200 and any(item.get("id") == endpoint.model for item in response.json().get("data", [])):
                        return
                except (httpx.HTTPError, ValueError, AttributeError, TypeError):
                    pass
                await asyncio.sleep(0.1)

    async def close(self) -> None:
        async with self._lock:
            await self._stop()

    async def _stop(self) -> None:
        process, self._process = self._process, None
        self._endpoint, self._model = None, None
        if process is None:
            return
        if process.stdin is not None:
            process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), 8)
        except TimeoutError:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()
