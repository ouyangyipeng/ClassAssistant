# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

root = Path(SPECPATH)
identity = os.environ.get("APPLE_SIGNING_IDENTITY")
# PyInstaller enables hardened runtime for any explicit identity; its default
# already applies ad-hoc signatures without incompatible library validation.
if identity == "-":
    identity = None
datas = copy_metadata("keyring") + collect_data_files("sherpa_onnx", includes=["*.txt", "*.json"])
binaries = collect_dynamic_libs("sherpa_onnx")
hiddenimports = collect_submodules("uvicorn") + [
    "speech_recognition.recognizers.google",
    "keyring.backends.fail",
    "keyring.backends.chainer",
    "keyring.backends.macOS" if sys.platform == "darwin" else "keyring.backends.Windows",
]

analysis = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "tkinter", "matplotlib", "torch", "torchaudio", "transformers"],
    noarchive=False,
)
# The upstream sounddevice hook collects every platform's libraries from its wheel.
if sys.platform == "darwin":
    analysis.binaries = [item for item in analysis.binaries if not item[0].lower().endswith(".dll")]
    analysis.datas = [item for item in analysis.datas if not item[0].lower().endswith(".dll")]

archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    [("u", None, "OPTION")],
    exclude_binaries=True,
    name="classfox-service",
    console=True,
    strip=False,
    upx=False,
    argv_emulation=False,
    codesign_identity=(identity or None) if sys.platform == "darwin" else None,
    entitlements_file=str(root.parent / "app-ui" / "src-tauri" / "Entitlements.plist") if sys.platform == "darwin" else None,
)
COLLECT(executable, analysis.binaries, analysis.datas, name="classfox-service", strip=False, upx=False)
