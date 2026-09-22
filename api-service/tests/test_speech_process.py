import asyncio
import sys
from pathlib import Path

import pytest
from pydantic import SecretStr

from classfox.asr_providers import SpeechConfig
from classfox.audio import AudioError
from classfox.settings import ASRSettings
from classfox.speech_process import SpeechProcess
from classfox.speech_worker import WorkerRequest


def worker(tmp_path: Path, code: str) -> list[str]:
    script = tmp_path / "worker.py"
    script.write_text("import sys,json,time\n" + code)
    return [sys.executable, "-u", str(script)]


async def test_ready_stop_flush_and_private_stdin(tmp_path: Path) -> None:
    events: list[dict[str, object]] = []
    command = worker(
        tmp_path,
        """
config=json.loads(sys.stdin.readline())
assert config['config']['keys']['asr']=='synthetic-private-key'
assert 'synthetic-private-key' not in ' '.join(sys.argv)
print(json.dumps({'type':'ready'}),flush=True)
assert json.loads(sys.stdin.readline())['action']=='stop'
print(json.dumps({'type':'transcript','text':'最后一句','source_id':'last'}),flush=True)
print(json.dumps({'type':'done'}),flush=True)
""",
    )
    process = SpeechProcess(events.append, command=command)
    await process.start(
        WorkerRequest(action="microphone", config=SpeechConfig(settings=ASRSettings(mode="openai"), keys={"asr": SecretStr("synthetic-private-key")}))
    )
    assert process.pid is not None
    await process.stop()
    assert events == [{"type": "transcript", "text": "最后一句", "source_id": "last"}]
    assert process.pid is None
    await process.close()


async def test_hung_worker_is_killed_with_bounded_wait(tmp_path: Path) -> None:
    process = SpeechProcess(
        lambda event: None,
        command=worker(
            tmp_path,
            """
sys.stdin.readline()
print(json.dumps({'type':'ready'}),flush=True)
time.sleep(30)
""",
        ),
    )
    await process.start(WorkerRequest(action="devices"))
    with pytest.raises(AudioError, match="超时"):
        await asyncio.wait_for(process.stop(timeout=0.1), 3)
    assert process.pid is None


async def test_crash_before_ready_fails_start_and_releases_process(tmp_path: Path) -> None:
    events: list[dict[str, object]] = []
    process = SpeechProcess(events.append, command=worker(tmp_path, "sys.stdin.readline()\nsys.exit(7)\n"))
    with pytest.raises(AudioError):
        await process.start(WorkerRequest(action="devices"), timeout=1)
    assert process.pid is None and events[0]["type"] == "error"


async def test_cancel_during_start_releases_child(tmp_path: Path) -> None:
    process = SpeechProcess(lambda event: None, command=worker(tmp_path, "sys.stdin.readline()\ntime.sleep(30)\n"))
    task = asyncio.create_task(process.start(WorkerRequest(action="devices")))
    for _ in range(100):
        if process.pid is not None:
            break
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.pid is None


async def test_error_before_ready_returns_actionable_message(tmp_path: Path) -> None:
    command = worker(tmp_path, "sys.stdin.readline()\nprint(json.dumps({'type':'error','code':'device_unavailable','message':'检查麦克风'}),flush=True)\n")
    process = SpeechProcess(lambda event: None, command=command)
    with pytest.raises(AudioError, match="检查麦克风"):
        await process.start(WorkerRequest(action="devices"), timeout=1)
    assert process.pid is None
