import json
import os
import signal
import subprocess
import sys
import threading
from contextlib import suppress


def main() -> int:
    # A separate owner survives backend crashes and observes the inherited pipe's EOF.
    request = json.loads(sys.stdin.buffer.readline(65537))
    if not isinstance(request, list) or not request or not all(isinstance(item, str) for item in request):
        return 1
    stop = threading.Event()
    threading.Thread(target=lambda: (sys.stdin.buffer.read(1), stop.set()), daemon=True).start()
    if os.name != "nt":
        signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    environment = {
        name: value
        for name, value in os.environ.items()
        if name in {"PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TMP", "TEMP", "TMPDIR", "LANG", "LLAMA_API_KEY"}
    }
    with subprocess.Popen(
        request,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    ) as child:
        try:
            while child.poll() is None and not stop.wait(0.1):
                pass
        finally:
            if child.poll() is None:
                with suppress(ProcessLookupError):
                    child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        return child.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
