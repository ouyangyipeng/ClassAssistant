# Third-party components

ClassFox source code is MIT-licensed. Third-party packages, downloaded models,
and native runtimes retain their own licenses. The application's generated
`legal/DEPENDENCY_LICENSES.txt` contains license texts available from the
installed Python environment, frontend production dependencies and Cargo
dependency graph, plus supplemental native library notices. The inventory
can include build-only and other-platform dependencies; it is not a binary
SBOM or a security certification.

## Downloaded models and runtime

Models are downloaded only after the user chooses installation. Fixed
revisions, filenames, sizes and SHA-256 values are defined in
`api-service/classfox/model_catalog.py`.

| Component | Source | License |
| --- | --- | --- |
| SenseVoiceSmall INT8 ONNX | [sherpa-onnx conversion](https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17) | [FunASR Model License 1.1](https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE) |
| Silero VAD | [sherpa-onnx model distribution](https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models) | [MIT](https://github.com/snakers4/silero-vad/blob/master/LICENSE) |
| Qwen3.5 4B Q4_K_M | [Unsloth GGUF conversion](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF) of Qwen | Apache-2.0 |
| llama.cpp b10964 | [ggml-org release](https://github.com/ggml-org/llama.cpp/releases/tag/b10964) | MIT |

The project's MIT license does not replace the model license. Consult the
linked license before redistribution or use beyond your own evaluation.

## Application packages

React, Tauri, FastAPI, OpenAI's Python SDK, document parsers and their
dependencies are listed with the exact installed versions by the build.
The frozen backend includes Python, sherpa-onnx, ONNX Runtime, NumPy and
PortAudio through sounddevice. PyInstaller's distribution exception applies
to its bootloader; its complete upstream COPYING text is included in the
generated notices.

The WeChat bundle includes noble-ciphers and noble-hashes under MIT; their
license texts are copied to `mini-program/dist/THIRD_PARTY_LICENSES.txt`.
Documentation is built with Zensical (MIT); documentation tooling is not
required to run the desktop application.

## Contributions

ClassFox preserves its original project license and contributor history.
The macOS and WebSpeech work in PRs #8, #10 and #11 informed the 2.0
compatibility requirements; see `docs/project/maintenance.md` for the
integration decisions and original pull request links.
