import asyncio
import io
import json
import os
import socket
import sys
from pathlib import Path

import httpx
import pytest
from docx import Document

from classfox.model_process import available_port
from tests.test_model_process import SERVER


async def launch(directory: Path) -> tuple[asyncio.subprocess.Process, dict[str, object]]:
    executable = os.environ.get("CLASSFOX_TEST_BACKEND")
    command = [executable] if executable else [sys.executable, "-u", "main.py"]
    process = await asyncio.create_subprocess_exec(
        *command,
        "--desktop",
        cwd=Path(__file__).resolve().parents[1],
        env={key: value for key, value in os.environ.items() if key in {"PATH", "HOME", "SYSTEMROOT", "WINDIR", "TMP", "TEMP", "TMPDIR", "LANG"}},
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write((json.dumps({"data_dir": str(directory)}) + "\n").encode())
    await process.stdin.drain()
    try:
        ready = json.loads(await asyncio.wait_for(process.stdout.readline(), 20))
        return process, ready
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise


async def close(process: asyncio.subprocess.Process) -> None:
    if process.stdin:
        process.stdin.close()
    try:
        await asyncio.wait_for(process.wait(), 8)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


@pytest.mark.parametrize("shutdown", ["command", "parent_eof"])
async def test_owned_launcher_auth_readiness_and_shutdown(tmp_path: Path, shutdown: str) -> None:
    process, ready = await launch(tmp_path / "中文 data")
    try:
        assert ready["type"] == "ready" and ready["version"] == "2.0.0"
        port, token = ready["port"], ready["token"]
        assert isinstance(port, int) and isinstance(token, str) and len(token) >= 32
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
            assert (await client.get("/api/v2/status")).status_code == 401
            response = await client.get("/api/v2/status", headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 200
            assert response.json()["session"] is None
        if shutdown == "command":
            assert process.stdin is not None
            process.stdin.write(b'{"action":"stop"}\n')
            await process.stdin.drain()
        else:
            assert process.stdin is not None
            process.stdin.close()
        assert await asyncio.wait_for(process.wait(), 8) == 0
        assert (tmp_path / "中文 data" / "classfox.sqlite3").is_file()
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0
    finally:
        await close(process)


async def test_instances_choose_distinct_ports_and_private_credentials(tmp_path: Path) -> None:
    first, first_ready = await launch(tmp_path / "first")
    second: asyncio.subprocess.Process | None = None
    try:
        second, second_ready = await launch(tmp_path / "second")
        assert first_ready["port"] != second_ready["port"]
        assert first_ready["token"] != second_ready["token"]
        await close(first)
        async with httpx.AsyncClient(trust_env=False) as client:
            assert (await client.get(f"http://127.0.0.1:{second_ready['port']}/api/health")).status_code == 200
    finally:
        await close(first)
        if second is not None:
            await close(second)


async def test_second_instance_cannot_recover_an_owned_classroom(tmp_path: Path) -> None:
    first, ready = await launch(tmp_path)
    second: asyncio.subprocess.Process | None = None
    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{ready['port']}", headers={"Authorization": f"Bearer {ready['token']}"}, trust_env=False
        ) as client:
            response = await client.post("/api/v2/sessions", json={"course_name": "Exclusive classroom", "source": "text"})
            assert response.status_code == 201
            session_id = response.json()["id"]
            second, duplicate = await launch(tmp_path)
            assert duplicate["type"] == "error"
            assert duplicate["code"] == "DataDirectoryInUse"
            assert await asyncio.wait_for(second.wait(), 5) != 0
            saved = await client.post(f"/api/v2/sessions/{session_id}/entries", json={"text": "The first classroom remains writable", "source_id": "first:1"})
            assert saved.status_code == 201
        first.kill()
        await first.wait()
        restarted, recovered = await launch(tmp_path)
        try:
            assert recovered["type"] == "ready"
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{recovered['port']}", headers={"Authorization": f"Bearer {recovered['token']}"}, trust_env=False
            ) as client:
                sessions = (await client.get("/api/v2/sessions")).json()
                assert sessions[0]["status"] == "interrupted"
                entries = (await client.get(f"/api/v2/sessions/{session_id}/entries")).json()
                assert entries[0]["text"] == "The first classroom remains writable"
        finally:
            await close(restarted)
    finally:
        await close(first)
        if second is not None:
            await close(second)


async def test_launched_backend_owns_document_parser_and_phone_stays_opt_in(tmp_path: Path) -> None:
    document = Document()
    document.add_paragraph("打包后的资料解析 🦊")
    buffer = io.BytesIO()
    document.save(buffer)
    process, ready = await launch(tmp_path / "中文 data")
    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{ready['port']}", headers={"Authorization": f"Bearer {ready['token']}"}, trust_env=False, timeout=20
        ) as client:
            uploaded = await client.post("/api/v2/materials", files={"file": ("课件.docx", buffer.getvalue())})
            assert uploaded.status_code == 201
            assert uploaded.json()["text"] == "打包后的资料解析 🦊"
            phone = await client.get("/api/v2/phone")
            assert phone.status_code == 200
            assert phone.json()["listening"] is False
    finally:
        await close(process)


async def test_model_worker_entrypoint_releases_child_on_pipe_eof(tmp_path: Path) -> None:
    executable = os.environ.get("CLASSFOX_TEST_BACKEND")
    command = [executable] if executable else [sys.executable, "-u", "main.py"]
    script = tmp_path / "synthetic_server.py"
    script.write_text(SERVER, encoding="utf-8")
    port = available_port()
    environment = {key: value for key, value in os.environ.items() if key in {"PATH", "HOME", "SYSTEMROOT", "WINDIR", "TMP", "TEMP", "TMPDIR", "LANG"}}
    environment["LLAMA_API_KEY"] = "synthetic"
    process = await asyncio.create_subprocess_exec(
        *command,
        "--model-worker",
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        assert process.stdin is not None
        process.stdin.write(json.dumps([sys.executable, str(script), "--port", str(port)]).encode() + b"\n")
        await process.stdin.drain()
        async with httpx.AsyncClient(trust_env=False, timeout=0.5) as client:
            async with asyncio.timeout(15):
                while True:
                    try:
                        assert (await client.get(f"http://127.0.0.1:{port}/models")).status_code == 401
                        break
                    except httpx.TransportError:
                        await asyncio.sleep(0.05)
        await close(process)
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0
    finally:
        await close(process)
