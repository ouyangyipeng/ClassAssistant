"""Alternate locations for identical, pinned model bytes."""

from classfox.downloads import Asset

QWEN_SHA256 = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"
MODELSCOPE_QWEN = "https://modelscope.cn/models/unsloth/Qwen3.5-4B-GGUF/resolve/167b4afc359863325cb4164418c715421b4e9118/Qwen3.5-4B-Q4_K_M.gguf"
MODELSCOPE_SENSEVOICE = (
    "https://modelscope.cn/models/gomodels/sherpa/resolve/590473aaa26eed19b270a424cb641972ae56482d/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
)
SENSEVOICE_FILES = {
    "c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51": "model.int8.onnx",
    "f449eb28dc567533d7fa59be34e2abca8784f771850c78a47fb731a31429a1dc": "tokens.txt",
    "221c6df10b0931a5629adad671ea48fb7747e034c414b6d2bfa275bc3dd4ea17": "LICENSE",
}


def download_sources(asset: Asset) -> tuple[str, ...]:
    # Locations are deliberately separate from the installed-model fingerprint.
    if asset.sha256 == QWEN_SHA256:
        return MODELSCOPE_QWEN, asset.url
    if filename := SENSEVOICE_FILES.get(asset.sha256):
        return f"{MODELSCOPE_SENSEVOICE}/{filename}", asset.url
    return (asset.url,)
