import asyncio
import json
import logging
import os
import subprocess
import sys
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from classfox.audio import AudioError
from classfox.speech_worker import WorkerRequest

SpeechEvent = Callable[[dict[str, object]], None]
logger = logging.getLogger(__name__)


def worker_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--speech-worker"]
    return [sys.executable, "-m", "classfox.speech_worker"]


class SpeechProcess:
    def __init__(self, emit: SpeechEvent, *, command: list[str] | None = None) -> None:
        self._emit = emit
        self._command = command or worker_command()
        self._process: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task[None] | None = None
        self._ready: asyncio.Future[None] | None = None
        self._failure: AudioError | None = None

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process is not None and self._process.returncode is None else None

    async def start(self, request: WorkerRequest, *, timeout: float = 90) -> None:
        if self._process is not None:
            raise AudioError("语音识别已启动", code="already_running")
        environment = {
            name: value
            for name, value in os.environ.items()
            if name in {"PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TMP", "TEMP", "TMPDIR", "LANG"}
        }
        environment.update({"PYTHONUNBUFFERED": "1", "PYINSTALLER_RESET_ENVIRONMENT": "1"})
        self._ready = asyncio.get_running_loop().create_future()
        payload = request.model_dump(mode="json")
        if request.config is not None:
            payload["config"]["keys"] = {key: value.get_secret_value() for key, value in request.config.keys.items()}
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self._command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=Path(__file__).resolve().parent.parent,
                env=environment,
                limit=128 * 1024,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            assert self._process.stdin is not None
            self._reader = asyncio.create_task(self._read())
            async with asyncio.timeout(timeout):
                self._process.stdin.write(json.dumps(payload).encode() + b"\n")
                await self._process.stdin.drain()
                await asyncio.shield(self._ready)
                self.check()
        except BaseException as exc:
            await self.close()
            if isinstance(exc, (TimeoutError, OSError)):
                raise AudioError("语音识别启动失败或超时，请检查设备权限和模型安装", code="startup_failed") from exc
            raise

    def _fail(self, error: AudioError) -> None:
        self._failure = error
        if self._ready is not None and not self._ready.done():
            self._ready.set_result(None)
        try:
            self._emit({"type": "error", "code": error.code, "message": str(error)})
        except Exception as exc:
            logger.error("Could not publish speech failure: %s", type(exc).__name__)

    async def _read(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        finished = False
        try:
            while True:
                line = await asyncio.wait_for(self._process.stdout.readline(), 45 if self._ready is not None and self._ready.done() else 90)
                if not line:
                    break
                event = json.loads(line)
                if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                    raise ValueError("Invalid worker event")
                kind = event["type"]
                if kind == "ready" and self._ready is not None and not self._ready.done():
                    self._ready.set_result(None)
                elif kind == "error":
                    self._fail(AudioError(str(event.get("message", "语音识别失败")), code=str(event.get("code", "audio_unavailable"))))
                    return
                elif kind == "done":
                    finished = True
                else:
                    self._emit(event)
            result = await self._process.wait()
            if not finished or result != 0 or (self._ready is not None and not self._ready.done()):
                raise AudioError("语音进程意外退出，原文已保留；请检查设备或模型后恢复", code="worker_exited")
        except Exception:
            self._fail(AudioError("语音进程意外退出或返回无效数据，原文已保留；请恢复识别", code="worker_exited"))
        finally:
            if self._failure is not None:
                await self._terminate()

    def check(self) -> None:
        if self._failure is not None:
            raise self._failure

    async def wait(self, *, timeout: float = 60) -> None:
        assert self._reader is not None
        try:
            async with asyncio.timeout(timeout):
                await asyncio.shield(self._reader)
            self.check()
        except TimeoutError as exc:
            raise AudioError("语音处理超时，最后一段可能未识别；原文已保留", code="speech_timeout") from exc
        finally:
            await self.close()

    async def stop(self, *, timeout: float = 15) -> None:
        process = self._process
        if process is None:
            return
        try:
            if process.returncode is None and process.stdin is not None:
                with suppress(BrokenPipeError, ConnectionResetError):
                    process.stdin.write(b'{"action":"stop"}\n')
                    await process.stdin.drain()
            await self.wait(timeout=timeout)
        finally:
            await self.close()

    async def close(self) -> None:
        process = self._process
        if process is None:
            return
        await self._terminate()
        if self._reader is not None and not self._reader.done():
            self._reader.cancel()
            with suppress(asyncio.CancelledError):
                await self._reader
        if self._ready is not None and not self._ready.done():
            self._ready.cancel()
        self._process = None

    async def _terminate(self) -> None:
        process = self._process
        if process is None:
            return
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 2)
            except TimeoutError:
                with suppress(ProcessLookupError):
                    process.kill()
                await process.wait()
