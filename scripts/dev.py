"""Start the desktop workspace with its own authenticated backend process."""

import subprocess
import sys

from build import SERVICE, UI, executable, run


def main() -> int:
    try:
        run([executable("uv"), "sync", "--locked", "--extra", "audio"], SERVICE)
        pnpm = executable("pnpm")
        run([pnpm, "install", "--frozen-lockfile"], UI)
        run([pnpm, "exec", "tauri", "dev"], UI)
    except KeyboardInterrupt:
        return 130
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"开发环境未启动：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
