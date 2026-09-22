import argparse
import asyncio
import json
import multiprocessing
import os
import socket
import sys
import threading
from pathlib import Path
from typing import BinaryIO, TextIO

from pydantic import BaseModel, ConfigDict

from classfox import __version__
from classfox.config import RuntimeConfig


class DesktopStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_dir: Path | None = None


def watch_parent(source: BinaryIO, loop: asyncio.AbstractEventLoop, stop: asyncio.Event) -> None:
    while True:
        line = source.readline(1025)
        try:
            command = json.loads(line) if line and len(line) <= 1024 else None
        except ValueError:
            command = None
        if not isinstance(command, dict) or command.get("action") == "stop":
            if not loop.is_closed():
                loop.call_soon_threadsafe(stop.set)
            return


async def serve_desktop(config: RuntimeConfig, commands: BinaryIO, output: TextIO) -> int:
    import uvicorn

    from classfox.app import create_app

    stop = asyncio.Event()
    threading.Thread(target=watch_parent, args=(commands, asyncio.get_running_loop(), stop), daemon=True).start()
    app = create_app(config)
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False, timeout_graceful_shutdown=5))

    async def run_server(listener: socket.socket) -> None:
        try:
            await server.serve(sockets=[listener])
        except SystemExit as exc:
            # Uvicorn exits on lifespan failure; keep the private error handshake alive.
            if exc.code != uvicorn.config.STARTUP_FAILURE:
                raise

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        # The OS keeps this socket reserved through startup, avoiding port-selection races.
        listener.bind(("127.0.0.1", 0))
        listener.setblocking(False)
        port = listener.getsockname()[1]
        serving = asyncio.create_task(run_server(listener))
        parent_exit = asyncio.create_task(stop.wait())
        try:
            while not server.started and not serving.done() and not stop.is_set():
                await asyncio.sleep(0.02)
            if server.started and not stop.is_set():
                output.write(json.dumps({"type": "ready", "version": __version__, "port": port, "token": config.api_token}) + "\n")
                output.flush()
            elif getattr(app.state, "data_directory_in_use", False):
                output.write(json.dumps({"type": "error", "code": "DataDirectoryInUse"}) + "\n")
                output.flush()
            await asyncio.wait({serving, parent_exit}, return_when=asyncio.FIRST_COMPLETED)
            server.should_exit = True
            await serving
            return 0 if server.started else 1
        finally:
            parent_exit.cancel()
            await asyncio.gather(parent_exit, return_exceptions=True)
            if not serving.done():
                server.should_exit = True
                await serving


def desktop_main() -> int:
    # Only this private inherited pipe receives the connection credential, never logs or argv.
    output = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    commands = os.fdopen(os.dup(sys.stdin.fileno()), "rb", buffering=0)
    try:
        payload = commands.readline(65537)
        if not payload or len(payload) > 65536:
            raise ValueError("Invalid desktop startup request")
        start = DesktopStart.model_validate_json(payload)
        config = RuntimeConfig(data_dir=start.data_dir.resolve()) if start.data_dir else RuntimeConfig()
        return asyncio.run(serve_desktop(config, commands, output))
    except Exception as error:
        output.write(json.dumps({"type": "error", "code": type(error).__name__, "message": "本地服务启动失败，请检查数据目录权限或重新安装"}) + "\n")
        output.flush()
        return 1
    finally:
        output.close()


def main(arguments: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    arguments = sys.argv[1:] if arguments is None else arguments
    if arguments == ["--self-check"]:
        from classfox.selfcheck import self_check

        return self_check()
    if arguments and arguments[0] == "--probe-speech":
        from classfox.model_probe import speech_probe_main

        return speech_probe_main(arguments[1:])
    if arguments == ["--speech-worker"]:
        from classfox.speech_worker import main as speech_main

        speech_main()
        return 0
    if arguments == ["--parse-document"]:
        from classfox.document_process import main as document_main

        document_main()
        return 0
    if arguments == ["--model-worker"]:
        from classfox.model_worker import main as model_main

        return model_main()
    parser = argparse.ArgumentParser(description="ClassFox local classroom service")
    parser.add_argument("--desktop", action="store_true", help="Use the private desktop startup and lifetime protocol")
    args = parser.parse_args(arguments)
    if args.desktop:
        return desktop_main()
    if not os.environ.get("CLASSFOX_API_TOKEN"):
        parser.error("请使用项目的一体化启动命令；单独启动服务需通过 CLASSFOX_API_TOKEN 配置本地访问凭据")
    import uvicorn

    from classfox.app import create_app

    config = RuntimeConfig.from_environment()
    uvicorn.run(create_app(config), host="127.0.0.1", port=config.port, access_log=False)
    return 0
