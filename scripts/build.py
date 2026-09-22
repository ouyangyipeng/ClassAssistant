"""Build ClassFox on the target OS with locked dependencies and native runtime checks."""

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "api-service"
UI = ROOT / "app-ui"


def executable(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise RuntimeError(f"请先安装 {name}，再运行构建命令")
    return found


def run(command: list[str], directory: Path, *, environment: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=directory, env=environment, check=True)


def check_versions() -> str:
    version = tomllib.loads((SERVICE / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    versions = [
        json.loads((UI / "package.json").read_text(encoding="utf-8"))["version"],
        json.loads((UI / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))["version"],
        tomllib.loads((UI / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8"))["package"]["version"],
    ]
    for statement in ast.parse((SERVICE / "classfox" / "__init__.py").read_text(encoding="utf-8")).body:
        if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__version__" for target in statement.targets):
            versions.append(ast.literal_eval(statement.value))
            break
    else:
        raise RuntimeError("后端缺少协议版本，无法验证桌面握手兼容性")
    if any(value != version for value in versions):
        raise RuntimeError("前端、后端和原生版本不一致，请同步版本后构建")
    return version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-only", action="store_true")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Generate a debug application for local verification",
    )
    parser.add_argument("--bundles", help="Tauri bundle targets, e.g. app,dmg or nsis")
    parser.add_argument("--verbose", action="store_true", help="Show native packaging diagnostics")
    args = parser.parse_args()
    try:
        check_versions()
        run(
            [
                executable("uv"),
                "sync",
                "--locked",
                "--extra",
                "audio",
                "--extra",
                "bundle",
            ],
            SERVICE,
        )
        python = SERVICE / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        run([str(python), "-m", "PyInstaller", "--noconfirm", "classfox.spec"], SERVICE)
        backend = SERVICE / "dist" / "classfox-service" / ("classfox-service.exe" if sys.platform == "win32" else "classfox-service")
        run([str(backend), "--self-check"], ROOT)
        if args.backend_only:
            return 0
        pnpm = executable("pnpm")
        run([pnpm, "install", "--frozen-lockfile"], UI)
        run([str(python), str(ROOT / "scripts" / "licenses.py")], ROOT)
        command = [
            pnpm,
            "exec",
            "tauri",
            "build",
            "--config",
            "src-tauri/tauri.release.conf.json",
        ]
        if args.verbose:
            command.append("--verbose")
        if args.debug:
            command.append("--debug")
        if args.bundles:
            command.extend(["--bundles", args.bundles])
        environment = dict(os.environ)
        if sys.platform == "darwin":
            environment.setdefault("APPLE_SIGNING_IDENTITY", "-")
        run(command, UI, environment=environment)
        if sys.platform == "darwin":
            profile = "debug" if args.debug else "release"
            bundle = UI / "src-tauri" / "target" / profile / "bundle" / "macos" / "课狐ClassFox.app"
            run(["codesign", "--verify", "--deep", "--strict", str(bundle)], ROOT)
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"构建未完成：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
