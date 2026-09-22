import platform
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from classfox.downloads import Asset


class ModelDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    name: str
    kind: Literal["asr", "llm"]
    revision: str
    description: str
    source_url: str
    license_name: str
    license_url: str
    files: tuple[Asset, ...]


SENSEVOICE_SOURCE = "https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
SENSEVOICE_REVISION = "2365baeacb507f821a0c8120fcee3d484dba7a07"
QWEN_SOURCE = "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF"
QWEN_REVISION = "e87f176479d0855a907a41277aca2f8ee7a09523"
LLAMA_VERSION = "b10964"


def hf_asset(source: str, revision: str, filename: str, size: int, sha256: str) -> Asset:
    return Asset(url=f"{source}/resolve/{revision}/{filename}", filename=filename, size=size, sha256=sha256)


CATALOG: dict[str, ModelDefinition] = {
    "sensevoice-small": ModelDefinition(
        id="sensevoice-small",
        name="SenseVoiceSmall INT8",
        kind="asr",
        revision=SENSEVOICE_REVISION,
        description="在电脑上识别普通话、粤语、英语、日语和韩语；语音数据无需上传。含 Silero VAD 语音分段模型。",
        source_url=SENSEVOICE_SOURCE,
        license_name="FunASR Model License 1.1 / Silero MIT",
        license_url="https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE",
        files=(
            hf_asset(SENSEVOICE_SOURCE, SENSEVOICE_REVISION, "model.int8.onnx", 239233841, "c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51"),
            hf_asset(SENSEVOICE_SOURCE, SENSEVOICE_REVISION, "tokens.txt", 315894, "f449eb28dc567533d7fa59be34e2abca8784f771850c78a47fb731a31429a1dc"),
            hf_asset(SENSEVOICE_SOURCE, SENSEVOICE_REVISION, "LICENSE", 71, "221c6df10b0931a5629adad671ea48fb7747e034c414b6d2bfa275bc3dd4ea17"),
            Asset(
                url="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx",
                filename="silero_vad.onnx",
                size=643854,
                sha256="9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6",
            ),
        ),
    ),
    "qwen35-4b": ModelDefinition(
        id="qwen35-4b",
        name="Qwen3.5 4B Q4_K_M",
        kind="llm",
        revision=QWEN_REVISION,
        description="本地课堂问答与笔记整理，下载约 2.74 GB。使用 Qwen 原始模型的 Unsloth 量化版本；复杂问题仍需核实。",
        source_url=QWEN_SOURCE,
        license_name="Apache-2.0",
        license_url="https://www.apache.org/licenses/LICENSE-2.0",
        files=(hf_asset(QWEN_SOURCE, QWEN_REVISION, "Qwen3.5-4B-Q4_K_M.gguf", 2740937888, "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"),),
    ),
}

RUNTIMES = {
    ("Darwin", "arm64"): ("macos-arm64.tar.gz", 11149739, "033c845c1df9bf945ff37bb193238b40910b2244be3e1e637b2ceb5878f1a6f5"),
    ("Darwin", "x86_64"): ("macos-x64.tar.gz", 11199948, "03430a394d0a169a5e6d8f01c09f48cf58eb026af6fc95940a4a528e2e50cf38"),
    ("Windows", "amd64"): ("win-cpu-x64.zip", 18427629, "917f39c076402c421224824607397af20f53625a60defc20e8dd22446bf4c5d7"),
}


def runtime_asset() -> Asset:
    key = (platform.system(), platform.machine().lower())
    if key not in RUNTIMES:
        raise ValueError("此平台暂不支持自动安装本地问答运行时；可以连接已有的兼容模型服务")
    if key[0] == "Darwin":
        version = platform.mac_ver()[0].split(".")
        if len(version) < 2 or not all(part.isdigit() for part in version[:2]):
            raise ValueError("无法确认 macOS 版本；本地问答需要 macOS 13.3 或以上")
        if tuple(int(part) for part in version[:2]) < (13, 3):
            raise ValueError("本地问答运行时需要 macOS 13.3 或以上；当前系统可使用 BYOK 或自建兼容服务")
    suffix, size, digest = RUNTIMES[key]
    filename = f"llama-{LLAMA_VERSION}-bin-{suffix}"
    return Asset(url=f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_VERSION}/{filename}", filename=filename, size=size, sha256=digest)
