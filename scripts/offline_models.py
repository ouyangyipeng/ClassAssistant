"""Prepare portable offline ZIPs from the pinned ClassFox model catalog."""

import argparse
import asyncio
import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api-service"))

import httpx  # noqa: E402

from classfox.download_sources import download_sources  # noqa: E402
from classfox.downloads import download_asset  # noqa: E402
from classfox.model_catalog import CATALOG  # noqa: E402
from classfox.model_packages import validate_package  # noqa: E402

FUNASR_LICENSE = "https://raw.githubusercontent.com/modelscope/FunASR/58830eca4012644aac0c3218c3ccc7d98f003fda/MODEL_LICENSE"
APACHE_LICENSE = "https://www.apache.org/licenses/LICENSE-2.0.txt"


async def prepare(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(trust_env=False, follow_redirects=True, timeout=60) as client:
        for model in CATALOG.values():
            paths: list[Path] = []
            for asset in model.files:
                target = destination.parent / "offline-cache" / asset.sha256 / asset.filename
                print(f"Fetch and verify: {asset.filename}", flush=True)
                await download_asset(client, asset, target, lambda count: None, sources=download_sources(asset))
                paths.append(target)
            license_response = await client.get(FUNASR_LICENSE if model.kind == "asr" else APACHE_LICENSE)
            license_response.raise_for_status()
            package = destination / f"ClassFox-{model.id}-offline.zip"
            temporary = package.with_suffix(".zip.building")
            notice = (
                f"{model.name}\nSource: {model.source_url}\nRevision: {model.revision}\nLicense: {model.license_name}\n"
                "SenseVoiceSmall: FunASR/FunAudioLLM (Alibaba Group); ONNX INT8 conversion: csukuangfj / sherpa-onnx.\n"
                "Qwen3.5: Qwen Team; GGUF quantization: Unsloth.\n"
                "Silero VAD: Silero Team, MIT; https://github.com/snakers4/silero-vad\n"
                "Import this ZIP in ClassFox 2.1 or later: Settings > Local models > Import offline package.\n"
                "Do not unpack or rename model files. Platform runtime is included in the application installer.\n"
            )
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                for path in paths:
                    archive.write(path, path.name)
                archive.writestr("NOTICE.txt", notice)
                archive.writestr("MODEL_LICENSE", license_response.content)
                if model.kind == "asr":
                    archive.writestr("SILERO_LICENSE.txt", (ROOT / "licenses" / "LICENSE-silero-vad.txt").read_bytes())
            temporary.replace(package)
            validate_package(package.resolve(), list(model.files))
            print(f"Ready: {package.name}", flush=True)
    checksums: list[str] = []
    for package in sorted(destination.glob("*.zip")):
        with package.open("rb") as reader:
            checksums.append(f"{hashlib.file_digest(reader, 'sha256').hexdigest()}  {package.name}\n")
    (destination / "MODEL-SHA256SUMS.txt").write_text("".join(checksums), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "release" / "v2.1.1" / "ClassFox-2.1.1")
    asyncio.run(prepare(parser.parse_args().output.resolve()))
