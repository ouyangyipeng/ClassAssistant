# 本地模型验证记录

日期：2026-09-22。机器为 Apple M4 Pro、48 GiB 内存（`sysctl` 已核对）；测试只使用公开模型、公开样本和合成问题，不使用真实课堂或用户密钥。

## 已完成

- Python 3.12.13，macOS arm64；`sherpa-onnx` 与 `sherpa-onnx-core` 1.13.8 原生导入、`uv pip check` 通过。
- SenseVoiceSmall INT8：`csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17`，revision `2365baeacb507f821a0c8120fcee3d484dba7a07`。模型及 tokens 哈希已写入 `classfox/model_catalog.py`。
- 官方 `test_wavs/zh.wav`，SHA-256 `b77f1794fe374a0ba1ee1dc458bfaf9349496cbbfc32780c50ba3c5a7ad8e373`，16 kHz、单声道、16 位 PCM，5.592 秒。2 个 CPU 推理线程；加载 0.575 秒，识别 0.111 秒，RTF 0.020。输出“开饭时间早上9点至下午5点。”。这是单样本运行证据，不是教室准确率测量。
- Silero VAD，SHA-256 `9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6`，643,854 字节。上述样本产生 1 个语音片段（起始采样 11,872，长度 77,216）。
- llama.cpp 官方稳定版 `v0.4.1` 的版本指针为 `b10964`，运行程序报告 `0.4.1-dev (build 10964, commit b29c606e2)`。macOS arm64 资产 SHA-256 `033c845c1df9bf945ff37bb193238b40910b2244be3e1e637b2ceb5878f1a6f5`，11,149,739 字节，已验证解压及执行。Windows x64/macOS x64 仅核对了官方资产和哈希，尚未运行。
- Qwen3.5 0.8B Q8：`ggml-org/Qwen3.5-0.8B-GGUF`，revision `8fea620810c4afa23dd6443f999a48574c1611a3`。833,592,096 字节，SHA-256 `37ae482d336108d23516fa35e8e0c4126688d81018b87178a18d752a1357814f`。加载 0.966 秒；8,192 token context，单并发，关闭 thinking。合成问题首段 0.155 秒、总计 0.345 秒。
- **0.8B 候选未通过正确性检查**：“二叉树的前序遍历是什么？”输出同时声称从根开始、最后访问根，逻辑错误。仅可认定运行路径通过，不能把速度当成质量证据；正在核对更强候选。
- 本地 LLM 验证使用随机 loopback 端口和随机访问凭据；只停止验证脚本自身持有的模型进程，退出确认完成。
- Qwen3.5 4B Q4_K_M：`unsloth/Qwen3.5-4B-GGUF`，revision `e87f176479d0855a907a41277aca2f8ee7a09523`，2,740,937,888 字节，SHA-256 `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4`。这是 Unsloth 提供的量化件，基础模型来自 Qwen，不能称为 Qwen 官方 GGUF。
- 4B 通过产品 `OwnedModelProcess` 与 `LLMService` 路径验证：32,768 token context、单并发、8 CPU threads、关闭 thinking，加载约 1.868 秒。初版 prompt 会引入多余核实清单；将通用职责与救场格式分离后重新验证了下表三个合成问题，未观察到相同错误。

| 4B 精简提示词检查 | 首段文字 | 总耗时 | 人工核对 |
| --- | --- | --- | --- |
| 二叉树前序遍历，一句话 | 1.661 秒 | 2.360 秒 | 根、左、右顺序正确，无旧候选的矛盾 |
| 已知作业为第 1–4 题，第 5 题是否必须交 | 0.176 秒 | 1.179 秒 | 说明原文未提及，不虚构要求 |
| 二分查找课堂整理，不超过 120 字 | 0.241 秒 | 1.059 秒 | 保留有序前提、折半、复杂度、小测、边界条件和作业 |

以上为当前机器、固定公开模型的功能抽查，不是广泛质量评测或其他硬件性能承诺；默认候选调整为 4B，0.8B 不进入发布目录。原始合成问题/响应证据保存在临时验证目录的 `qwen35-4b-refined-prompt-validation.json`。

- 实际 `ModelInstaller` 使用已校验缓存完成 ASR 和 4B 安装、独立加载/推理探针，最终均为 `ready`。缓存目录和产品式安装均位于 `/private/tmp/classfox-model-validation/product-install`，不进入发布包；尚未走图形界面。
- 实际 FastAPI + 受管本地模型完成“开始课堂 → 写入合成原文 → 救场 → 停止课堂 → 自动总结 → 笔记持久化 → 应用退出”。答案“数组必须有序。”正确，总结保存且原文仍保留 1 条；应用 lifespan 完成模型进程清理。
- 全链路首个请求观察到 19.805 秒首段延迟，后续总结首段为 0.316 秒、总计 3.666 秒。另一次独立分项测量为完整性校验 1.112 秒、模型启动 0.942 秒，**这些分项尚不能解释首个请求的全部延迟**，不把它归因于某个未经证实的环节。增加显式模型预热入口供首次使用流程调用，后续需用同一运行中的分段计时继续检查。

## 来源与许可

- [Sherpa SenseVoice 模型与公开样本](https://k2-fsa.github.io/sherpa/onnx/sense-voice/pretrained.html)
- [转换模型发布页](https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17)：其 LICENSE 指向 FunASR 模型协议。
- [FunASR Model License 1.1](https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE) 和 [维护者的许可澄清](https://github.com/QwenAudio/SenseVoice/issues/334)：保留模型名称、来源和作者归属。不要将权重标为代码的 MIT 许可。
- [Qwen3.5 0.8B 原始模型](https://huggingface.co/Qwen/Qwen3.5-0.8B)：Apache-2.0；[ggml-org 转换件](https://huggingface.co/ggml-org/Qwen3.5-0.8B-GGUF) 同样标注 Apache-2.0。
- [llama.cpp b10964 官方运行包](https://github.com/ggml-org/llama.cpp/releases/tag/b10964)：保留包内 LICENSE。

## 待验证

- 更强本地 LLM 的基础题、给定课堂原文约束、长课堂总结与取消。
- 产品级安装状态、加载检查、受控模型进程和 API 已接入；图形界面一键安装与桌面包装验证尚未完成。
- 真实麦克风、设备切换、长期录音及噪声表现尚未验证；不读取周边真实声音来替代公开夹具。
- Windows x64/macOS x64 发布包尚未构建和安装验证。

## 2026-09-22：冷启动分解与预热边界

同一台 M4 Pro / 48 GiB，受管 Qwen3.5 4B Q4_K_M / llama.cpp b10964 / 32,768 context。隔离数据目录通过模型副本引用已有校验安装，输入为固定合成课堂：“二分查找要求数组有序。问题：数组必须满足什么前提？”连续两次 API 救场，未使用真实课堂或在线服务。

- 冷进程请求：首字 17,830 ms，总计 18,922 ms，外层 wall 18.930 s。模型完整性检查 1.174 s，模型启动到就绪 14.550 s，连接准备（含二者）15.725 s，HTTP headers 0.006 s。
- 紧接的第二次请求：首字 57 ms，总计 1,111 ms，wall 1.115 s；复用已就绪进程，HTTP headers 0.004 s。
- 两次均成功且包含有序前提；lifespan 结束后 own model PID 已清理。这里仅统计一个冷/热样本，不是准确率或速度 SLA。
- 结果说明本次首次等待主要发生在模型加载阶段；不能据此宣称所有冷请求都固定为此耗时。保留明确的“准备问答模型”入口，让用户课前预热，不在打开应用时自动占用数 GB 内存。
- 检查发现启动中的 PID 曾被当作 ready，导致同时预热与救场可能报错。新增真实本机进程回归先复现错误，再将 ready 与实际握手完成绑定；并发请求等待同一次 startup，5 项模型 API/进程测试通过。
