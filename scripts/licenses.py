"""Collect installed dependency notices for the desktop distribution."""

import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEGAL_NAMES = ("license", "copying", "notice", "copyright")


def legal_file(path: Path) -> bool:
    return path.name.lower().startswith(LEGAL_NAMES) and path.suffix.lower() not in {
        ".py",
        ".pyc",
        ".js",
        ".svg",
        ".json",
        ".toml",
        ".rs",
    }


def license_texts(paths: list[Path]) -> list[str]:
    texts: set[str] = set()
    for path in paths:
        if not path.is_symlink() and path.is_file() and legal_file(path):
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError(f"Unexpectedly large license file: {path.name}")
            value = path.read_text(encoding="utf-8", errors="replace").strip()
            if value:
                texts.add(value)
    return sorted(texts)


def directory_licenses(root: Path) -> list[str]:
    paths: list[Path] = []
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = [
            name
            for name in folders
            if name
            not in {
                "node_modules",
                "target",
                ".git",
                "tests",
                "examples",
                "__pycache__",
            }
        ]
        paths.extend(Path(directory) / name for name in files if legal_file(Path(name)))
    return license_texts(paths)


def python_components() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for package in importlib.metadata.distributions():
        metadata = package.metadata
        paths = [Path(str(package.locate_file(path))) for path in package.files or [] if legal_file(Path(path))]
        result.append(
            {
                "ecosystem": "python",
                "name": metadata["Name"],
                "version": package.version,
                "license": metadata.get("License-Expression") or metadata.get("License") or "See upstream license",
                "texts": license_texts(paths),
            }
        )
    result.append(
        {
            "ecosystem": "runtime",
            "name": "Python",
            "version": platform.python_version(),
            "license": "PSF-2.0",
            "texts": license_texts([Path(sysconfig.get_path("stdlib")) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE.txt"]),
        }
    )
    return result


def command_json(command: list[str], directory: Path) -> Any:
    output = subprocess.check_output(command, cwd=directory, text=True, encoding="utf-8")
    return json.loads(output)


def node_components() -> list[dict[str, Any]]:
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        raise RuntimeError("pnpm is required to collect frontend licenses")
    tree = command_json([pnpm, "list", "--prod", "--depth", "Infinity", "--json"], ROOT / "app-ui")
    collected: dict[str, dict[str, Any]] = {}

    def visit(dependencies: dict[str, Any]) -> None:
        for name, value in dependencies.items():
            key = f"{name}@{value['version']}"
            if key in collected:
                continue
            directory = Path(value["path"])
            metadata = json.loads((directory / "package.json").read_text(encoding="utf-8"))
            collected[key] = {
                "ecosystem": "npm",
                "name": name,
                "version": value["version"],
                "license": metadata.get("license", "See upstream license"),
                "texts": directory_licenses(directory),
            }
            visit(value.get("dependencies", {}))

    for project in tree:
        visit(project.get("dependencies", {}))
    return list(collected.values())


def rust_components() -> list[dict[str, Any]]:
    metadata = command_json(
        ["cargo", "metadata", "--locked", "--format-version", "1"],
        ROOT / "app-ui" / "src-tauri",
    )
    return [
        {
            "ecosystem": "cargo",
            "name": package["name"],
            "version": package["version"],
            "license": package.get("license") or "See upstream license",
            "texts": directory_licenses(Path(package["manifest_path"]).parent),
        }
        for package in metadata["packages"]
        if package["source"] is not None
    ]


def main() -> None:
    destination = ROOT / "release" / "legal"
    destination.mkdir(parents=True, exist_ok=True)
    components = sorted(
        python_components() + node_components() + rust_components(),
        key=lambda value: (value["ecosystem"], value["name"], value["version"]),
    )
    heading = (
        "ClassFox third-party notices\n\n"
        "This inventory includes the Python build environment, frontend production dependencies, and Cargo lock graph. "
        "Some build-only or other-platform components may not be present in this application. "
        "License statements and texts are preserved from installed upstream packages; this is not a vulnerability scan or a complete binary SBOM.\n"
    )
    sections = [heading]
    for component in components:
        sections.append(f"\n{'=' * 72}\n{component['ecosystem']}: {component['name']} {component['version']}\nLicense: {component['license']}\n")
        sections.extend(component["texts"])
    supplemental = ROOT / "licenses"
    if supplemental.is_dir():
        sections.extend(directory_licenses(supplemental))
    (destination / "DEPENDENCY_LICENSES.txt").write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    inventory = [{key: value for key, value in component.items() if key != "texts"} for component in components]
    (destination / "DEPENDENCIES.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for filename in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(ROOT / filename, destination / filename)
    print(f"Collected notices for {len(components)} dependency entries")


if __name__ == "__main__":
    main()
