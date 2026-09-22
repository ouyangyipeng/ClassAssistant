import asyncio
import json
import os
import signal
import socket
import sys
from contextlib import suppress
from pathlib import Path

import httpx
import pytest

from classfox.model_process import ModelProcessError, OwnedModelProcess

SERVER = """
import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int)
args, _ = parser.parse_known_args()
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_GET(self):
        if self.headers.get('Authorization') != 'Bearer ' + os.environ['LLAMA_API_KEY']:
            self.send_response(401)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({'data': [{'id': 'classfox-local'}]}).encode())
HTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
"""


async def test_owned_model_authenticates_health_and_closes_only_its_process(tmp_path: Path) -> None:
    executable = tmp_path / "test_server.py"
    executable.write_text(SERVER)
    model = tmp_path / "model.gguf"
    model.write_bytes(b"synthetic")
    manager = OwnedModelProcess()
    with socket.socket() as unrelated:
        unrelated.bind(("127.0.0.1", 0))
        unrelated.listen()
        original_port = unrelated.getsockname()[1]
        endpoint = await manager.start([sys.executable, str(executable)], model, startup_seconds=5)
        assert endpoint.key not in repr(endpoint)
        assert manager.pid != os.getpid()
        async with httpx.AsyncClient(base_url=endpoint.base_url, trust_env=False) as client:
            assert (await client.get("/models")).status_code == 401
            assert (await client.get("/models", headers={"Authorization": "Bearer " + endpoint.key})).status_code == 200
        await manager.close()
        await manager.close()
        assert manager.pid is None
        assert unrelated.getsockname()[1] == original_port
        with pytest.raises(ModelProcessError):
            manager.endpoint()


async def test_failed_model_startup_does_not_report_ready(tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"synthetic")
    manager = OwnedModelProcess()
    with pytest.raises(ModelProcessError):
        await manager.start([sys.executable, "-c", "raise SystemExit(3)"], model, startup_seconds=2)
    assert manager.pid is None


@pytest.mark.parametrize("shutdown", ["crash", "kill", "stubborn"])
async def test_model_exits_even_when_owner_cannot_run_cleanup(tmp_path: Path, shutdown: str) -> None:
    executable, model, pid_file = tmp_path / "test_server.py", tmp_path / "model.gguf", tmp_path / "child.pid"
    executable.write_text(
        SERVER.replace(
            "HTTPServer(('127.0.0.1', args.port), Handler).serve_forever()",
            (f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\nHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()"),
        )
    )
    model.write_bytes(b"synthetic")
    if shutdown == "stubborn":
        executable.write_text("import signal\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n" + executable.read_text())
    owner_code = f"""
import asyncio, json, os, sys
from pathlib import Path
from classfox.model_process import OwnedModelProcess
async def run():
    manager = OwnedModelProcess()
    endpoint = await manager.start([sys.executable, {str(executable)!r}], Path({str(model)!r}), startup_seconds=10)
    print(json.dumps({{'url': endpoint.base_url}}), flush=True)
    await asyncio.to_thread(sys.stdin.readline)
    os._exit(0)
asyncio.run(run())
"""
    owner = await asyncio.create_subprocess_exec(sys.executable, "-c", owner_code, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
    child_closed = False
    try:
        assert owner.stdout is not None and owner.stdin is not None
        ready = json.loads(await asyncio.wait_for(owner.stdout.readline(), 15))
        if shutdown == "crash":
            owner.stdin.write(b"crash\n")
            await owner.stdin.drain()
        else:
            owner.kill()
        await asyncio.wait_for(owner.wait(), 5)
        async with httpx.AsyncClient(trust_env=False, timeout=0.5) as client:
            async with asyncio.timeout(8):
                while True:
                    try:
                        await client.get(ready["url"] + "/models")
                    except httpx.TransportError:
                        child_closed = True
                        break
                    await asyncio.sleep(0.05)
    finally:
        if owner.returncode is None:
            owner.kill()
            await owner.wait()
        if not child_closed and pid_file.exists():
            with suppress(ProcessLookupError):
                os.kill(int(pid_file.read_text()), signal.SIGTERM)
