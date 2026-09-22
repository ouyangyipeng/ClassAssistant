import importlib
import json
import platform
import sys


def self_check() -> int:
    modules = [
        "fastapi",
        "uvicorn",
        "openai",
        "pypdf",
        "pptx",
        "docx",
        "sherpa_onnx",
        "sounddevice",
        "numpy",
        "cryptography.hazmat.primitives.ciphers.aead",
        "classfox.phone_crypto",
        "classfox.document_process",
        "classfox.model_worker",
    ]
    modules.append("keyring.backends.macOS" if sys.platform == "darwin" else "keyring.backends.Windows")
    failures: dict[str, str] = {}
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception as error:
            failures[name] = type(error).__name__
    print(json.dumps({"status": "failed" if failures else "ready", "platform": sys.platform, "architecture": platform.machine(), "failures": failures}))
    return 1 if failures else 0
