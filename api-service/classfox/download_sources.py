"""Alternate locations for identical, pinned model bytes."""

from classfox.downloads import Asset

QWEN_SHA256 = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"
MODELSCOPE_QWEN = "https://modelscope.cn/models/unsloth/Qwen3.5-4B-GGUF/resolve/167b4afc359863325cb4164418c715421b4e9118/Qwen3.5-4B-Q4_K_M.gguf"


def download_sources(asset: Asset) -> tuple[str, ...]:
    # Locations are deliberately separate from the installed-model fingerprint.
    if asset.sha256 == QWEN_SHA256:
        return MODELSCOPE_QWEN, asset.url
    return (asset.url,)
