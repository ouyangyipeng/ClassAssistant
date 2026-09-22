import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

from classfox.audio import OfflineSpeech, SpeechSegmenter
from classfox.model_catalog import ModelDefinition
from classfox.model_process import ModelProcessError, OwnedModelProcess


def runtime_executable(directory: Path) -> Path:
    name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    matches = list((directory / "runtime").rglob(name))
    if len(matches) != 1 or matches[0].is_symlink():
        raise ModelProcessError("问答运行库不完整，请重新安装模型")
    return matches[0]


async def probe_model(definition: ModelDefinition, directory: Path) -> None:
    if definition.kind == "asr":
        await probe_speech(directory)
        return
    model = next((asset for asset in definition.files if asset.filename.endswith(".gguf")), None)
    if model is None:
        raise ModelProcessError("模型清单缺少问答权重")
    manager = OwnedModelProcess()
    try:
        endpoint = await manager.start([str(runtime_executable(directory))], directory / model.filename)
        async with httpx.AsyncClient(base_url=endpoint.base_url, headers={"Authorization": f"Bearer {endpoint.key}"}, trust_env=False, timeout=60) as client:
            response = await client.post(
                "/chat/completions",
                json={"model": endpoint.model, "messages": [{"role": "user", "content": "回复一个字：好"}], "max_tokens": 32},
            )
            response.raise_for_status()
            if not response.json()["choices"][0]["message"]["content"].strip():
                raise ModelProcessError("模型未返回有效内容")
    finally:
        await manager.close()


async def probe_speech(directory: Path) -> None:
    command = [sys.executable, "--probe-speech"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "classfox.model_probe"]
    working_directory = None if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    process = await asyncio.create_subprocess_exec(
        *command,
        str(directory),
        cwd=working_directory,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        if await asyncio.wait_for(process.wait(), 90) != 0:
            raise ModelProcessError("离线语音模型无法加载，请检查运行库、内存或重新下载")
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


def speech_probe_main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check offline speech model loading in an isolated process")
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(arguments)
    try:
        speech = OfflineSpeech(args.directory)
        speech.transcribe(b"\x00\x00" * 16000)
        vad = SpeechSegmenter(args.directory)
        vad.feed(b"\x00\x00" * 16000)
        vad.flush()
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}))
        return 1
    print(json.dumps({"status": "ready"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(speech_probe_main())
