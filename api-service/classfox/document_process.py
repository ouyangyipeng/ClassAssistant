import asyncio
import json
import os
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory

from classfox.documents import MAX_FILE_SIZE, MAX_TEXT_LENGTH, DocumentError, parse_document

OUTPUT_LIMIT = MAX_TEXT_LENGTH * 4 + 65536


def worker_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--parse-document"]
    return [sys.executable, "-m", "classfox.document_process"]


async def terminate(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    with suppress(ProcessLookupError):
        process.terminate()
    try:
        await asyncio.wait_for(process.wait(), 2)
    except TimeoutError:
        with suppress(ProcessLookupError):
            process.kill()
        await process.wait()


async def read_result(process: asyncio.subprocess.Process, payload: bytes) -> str:
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write(payload)
    await process.stdin.drain()
    process.stdin.close()
    output = bytearray()
    while chunk := await process.stdout.read(min(65536, OUTPUT_LIMIT + 1 - len(output))):
        output.extend(chunk)
        if len(output) > OUTPUT_LIMIT:
            raise DocumentError("资料解析输出过大，请拆分后上传")
    if await process.wait() != 0:
        raise DocumentError("资料解析进程未能完成，请重新导出后上传")
    result = json.loads(output)
    if not isinstance(result, dict):
        raise DocumentError("资料解析返回无效结果")
    if result.get("error"):
        raise DocumentError(str(result["error"]))
    text = result.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
        raise DocumentError("资料文字为空或过长，请重新导出后上传")
    return text


async def parse_isolated(data: bytes, filename: str, *, timeout: float = 30, command: list[str] | None = None) -> str:
    if len(data) > MAX_FILE_SIZE:
        raise DocumentError("资料超过 25 MiB，请拆分后上传")
    # A timed-out thread keeps parsing. An owned process provides an enforceable deadline.
    with TemporaryDirectory(prefix="classfox-document-") as directory:
        source = Path(directory) / "source"
        source.write_bytes(data)
        source.chmod(0o600)
        environment = {
            name: value
            for name, value in os.environ.items()
            if name in {"PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TMP", "TEMP", "TMPDIR", "LANG"}
        }
        environment.update({"PYTHONUNBUFFERED": "1", "PYINSTALLER_RESET_ENVIRONMENT": "1"})
        process = await asyncio.create_subprocess_exec(
            *(command or worker_command()),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=Path(__file__).resolve().parent.parent,
            env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            async with asyncio.timeout(timeout):
                return await read_result(process, json.dumps({"path": str(source), "filename": filename}).encode() + b"\n")
        except TimeoutError as exc:
            raise DocumentError("资料解析超过 30 秒，请拆分或重新导出后上传") from exc
        except (ValueError, OSError) as exc:
            if isinstance(exc, DocumentError):
                raise
            raise DocumentError("资料解析失败，请重新导出后上传") from exc
        finally:
            cleanup = asyncio.create_task(terminate(process))
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                await cleanup
                raise


def main() -> None:
    output = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
    with open(os.devnull, "w") as sink:
        os.dup2(sink.fileno(), sys.stdout.fileno())
        os.dup2(sink.fileno(), sys.stderr.fileno())
    try:
        payload = json.loads(sys.stdin.readline(65537))
        source = Path(payload["path"])
        with source.open("rb") as stream:
            data = stream.read(MAX_FILE_SIZE + 1)
        result = {"text": parse_document(data, str(payload["filename"]))}
    except DocumentError as exc:
        result = {"error": str(exc)}
    except Exception:
        result = {"error": "资料损坏或无法读取，请重新导出后上传"}
    try:
        output.write(json.dumps(result, ensure_ascii=False))
        output.flush()
    finally:
        output.close()


if __name__ == "__main__":
    main()
