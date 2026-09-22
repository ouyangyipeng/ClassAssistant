# 执行记录：00-v1-classfox-v2.md

## 当前状态

- 用户已确认整体方案，持续实施；无需重新审批常规步骤。
- 基线 `1ea0b9b`，分支 `feat/classfox-v2`，变更已推送至 PR #13。
- v2 桌面实现、独立审查与三平台安装包门禁已完成，正在合入发布；微信正式交付推迟到 v2.5。
- 用户于 2026-09-23 授权：v2 验证完成后直接 Rebase and merge 到主分支并发布。
- 完整规格与验收条件：`00-v1-classfox-v2.md`。

## 已有证据

- 2026-09-23：`85b1bff` 的 CI run `35791742606` 全部通过，文档 run `35791742518` 通过。两种 macOS 架构各 181 项 Python 回归，Windows 180 项通过、1 项 POSIX 专用测试跳过；三个平台各 3 项 Rust 测试、6 项冻结入口测试通过并产出安装包。Intel 静态 OpenSSL 修复通过实际冻结包验证。随后只补充本记录和验证文档，应用代码、依赖、构建脚本与 CI 配置未变，复用该构建证据。

- 2026-09-23：PR `e5ebadb` 的 Windows x64、macOS arm64、Web/微信及文档 CI 通过；Intel Mac 的源码回归通过，但冻结包的 cryptography 导入失败，尚不可发布。该平台 cryptography 50 源码构建链接 Homebrew OpenSSL 动态库；改用官方支持的 `OPENSSL_STATIC=1`，由 uv 按包构建配置缓存并重建，保留当前依赖版本。最终三平台结果待新提交 CI 验证。

- 2026-09-22：公开远端与本地 main SHA 一致；issues、PR、mac/docs 分支及发布资产已检查。
- 使用 Python 3.12.13 与临时夹具复现：cite 路径越界、午夜时间窗口错误、压缩移除原文、新课覆盖旧文件。
- 16 个 Python 源文件 AST 解析及 3 个 JSON 配置解析通过；不代表运行测试。
- 新增后端包 `api-service/classfox/`，目前和旧入口并存；旧 `main.py` 尚未切换，避免在兼容 API 与桌面启动完成前切断旧路径。
- Python 3.12.13：安装并锁定 FastAPI 0.141.1、Pydantic 2.13.5、OpenAI 2.54.0 等项目依赖。API 用法已核对已安装类型/源码。
- 已实现：SQLite 独立课堂/原文/笔记/资料；显式幂等旧文本迁移；类型化非秘密配置；HTTP 鉴权/Origin/请求体边界；受限资料解析；课堂 API 与 WebSocket 鉴权/事件；重试不重复告警。
- 最新完整后端回归：`.venv/bin/python -m pytest -q` → **121 passed in 12.14s**。其后增加音频分句及错误退出处理，受影响的 `test_audio_runtime.py` / `test_speech_process.py` / `test_microphone.py` → **12 passed in 0.93s**；全量尚未再次运行。覆盖真实 loopback HTTP/WebSocket、密钥不回传、事务恢复、流式回答、取消、分段总结、下载、音频与进程边界。监听测试需要允许本机监听的执行权限。
- `.venv/bin/ruff check classfox tests`、`.venv/bin/ty check classfox tests` 通过；使用 `ruff format` 和 `isort`。
- 新增模块先运行缺失能力测试；上传、请求体大小与事件重试均观察到具体失败，再实现并全量通过。
- B 已实现 `llm.py`、`assistant_context.py`、`assistant.py` 和版本化任务 API：先输出首段文本、保存首字/总耗时、失败分类、取消关闭上游、重连查询任务快照；停止课堂与自动总结解耦。仅完整成功的总结写入笔记。
- `downloads.py`：14 个测试通过，覆盖 SHA-256、原子启用、保留已有模型、取消/续传、无效 Range、解压路径/体积/链接边界。`audio.py`：9 个测试通过，覆盖 WAV 格式、采样对齐、时长和停止时保留最后语音片段。
- `model_process.py`：2 个真实子进程测试通过，覆盖随机端口/凭据、带鉴权的就绪查询、启动失败清理、关闭幂等且不影响其他监听者。`model_install.py`：3 个测试通过，覆盖下载校验后加载、加载失败不标记完成、加载时取消。真实 probe、模型 API 与本地生成已接线并用公开模型通过。
- 本地端到端 API 已验证：受管模型 → 课堂原文 → 救场 → 停止 → 自动笔记保存 → 原文保留 → 生命周期清理。详情和延迟边界见 `model-validation.md`。
- 已接入 `speech_worker.py` / `speech_process.py` / `speech.py`：独立拥有的音频进程、私有 stdin 配置、明确就绪、10 秒有界音频队列、音量事件、暂停刷新末句、恢复与结束、错误状态、取消与超时清理。模拟捕获进程证明旧回调不串课；没有录制实际环境音频。
- ASR provider：离线 SenseVoice、OpenAI-compatible 文件识别、Seed 和 DashScope 实时 WebSocket、Google 旧兼容路径（HTTPS，依赖上游通用接口的可用性）。Seed 新/旧控制台凭据分开，默认资源为 2.0；语言和模型设置显式校验。协议和 SDK 用法已核对；无真实在线凭据，不声称在线账户实测通过。
- `/api/v2/sessions/{id}/audio` 接受有界 16 kHz 单声道 PCM WAV；SQLite 保存音频摘要回执，重复/静音片段幂等，不保存原始音频。实际公开 `zh.wav` 经子进程与 API → “开饭时间早上9点至下午5点。”，总耗时 **3.261 秒**；重试不重复识别，保留 1 条原文，进程清理通过。
- 长课堂总结按发起时的原文 ID 范围分段整理与递归合并；1,101 条记录的测试覆盖跨分页、上下文预算、覆盖全部原文和排除后来条目。救场按最近时间窗口与相关资料片段分配预算。
- DeepSeek 只读子任务因账户不支持模型而失败，主任务继续；没有获得独立审查证据。

## 决策

- 使用本仓库已有计划文件和此记录承载进度，不另建重复的隐藏 SDD 计划；新功能分支已隔离主线。
- 不运行旧开发/清理脚本：其按名称或端口强杀进程，会影响其他应用。
- 不加载/调用仓库旧 key；模板内非占位值必须从新版本移除。用户已收到吊销提示，未验证其有效性。
- 前端、Python、Rust、微信分别验证；真实凭据、AppID、真机与 Apple 签名尚未具备验证条件。
- PR #10 中转录查看、Markdown 渲染有产品价值，纳入已有课堂工作区；提示词预设评估后仅做必要的可配置项，避免引入完整提示词管理子系统。
- 后端依赖通过 `uv` 及仓库内虚拟环境管理；缓存使用 `/private/tmp/classfox-uv-cache`，不改全局环境。
- 新版 Starlette TestClient 弃用了原 httpx 适配，并依赖上游已弃用的 anyio alias。HTTP 测试改为已安装 httpx 的 `ASGITransport` + 显式应用 lifespan，不安装第二套 HTTP 客户端或压制警告；WebSocket 用真实本机服务验证。
- 模型调用不自动重试，避免流式重复、额外等待和未提示的计费；错误给出恢复动作，用户可显式重试。总时限与输出体积有界，服务端错误正文不回传、不记日志。
- 长课堂分段整理仅在请求总结时执行，不自动在录音中消耗 BYOK 配额；原文始终保存，超出模型压缩能力时明确失败并允许重试。
- macOS arm64 实测 `sherpa-onnx 1.13.8` 初次导入缺少 `libonnxruntime.dylib`；已安装 wheel 与 PyPI 元数据都声明依赖 `sherpa-onnx-core==1.13.8`，但生成的锁文件未包含它。项目显式锁定二者同版本后，原生 import 和 `uv pip check` 均通过；构建 CI 需保留原生 import 检查，不能仅验证包安装成功。
- 固定公开模型文件存于 `/private/tmp/classfox-model-validation`，SHA-256 已校验；原生模型验证细节见 `model-validation.md`。Qwen3.5 0.8B 在基础题出现明显错误，发布候选目录已调整为 Qwen3.5 4B Q4_K_M（Unsloth 转换，基础模型来自 Qwen），通过 3 项合成课堂抽查，不代表通用准确率保证。
- 受管本地问答使用 32,768 token context，上下文文本保守限制为 6,000 字符，为 UTF-8 分词及生成预留空间；BYOK 的配置预算保持独立。新增 `/api/v2/models/{id}/start` 供首次使用流程预热，生成请求也可按需启动。

## 下一步

- A：系统凭据存储与旧 `.env` 显式迁移已实现；测试只使用合成凭据，未访问真实 key 或系统 vault。仍需入口迁移与真实启动回归。
- B：基础链路已接入；继续补充 Seed 实时模拟、设备故障边界及必要回归。真实麦克风、在线服务账户和其他平台运行尚未验证。
- C：开始桌面完整工作区、紧凑条、首次配置与版本化 API/WS 接入；入口切换和兼容 API 将与 D 的桌面 bootstrap 一起完成。
- `model_probe.py` 的冻结包入口需在新 `main.py` 处理 `--probe-speech`；未冻结时已设置模块工作目录，避免 Tauri 从数据目录启动时找不到包。
- 还需复现并分解首个实际 API 请求的冷启动延迟；已记录观察值，未把独立测得的哈希或进程启动时间当成完整因果解释。
- E 的安全配对方案仍需核对微信安全随机数和成熟加密库；不能以明文 LAN bearer token 宣称私密课堂传输安全。

## 跨阶段接口

- A → B：SQLite 独立课堂与追加转录、类型化配置、应用 lifespan 负责资源。
- A/B → C：版本化 HTTP/WS 事件、认证、真实课堂状态、可取消的流式回答。
- A/B/C → D：运行目录/端口/token 由 Tauri 传入；桌面只持有并清理自己的子进程。
- A/B → E：手机课堂权限独立于桌面管理员，音频输入与采集设备解耦。
- A–E → F：每个平台证据、迁移兼容、密钥不进入资产；正式上架不以模拟测试替代。

## 2026-09-22：桌面工作区与原生启动推进

- C 已实现 React 工作区、紧凑条、原文/资料/笔记、流式助手、模型安装与预热入口、凭据和音频设置、外观及旧版偏好显式导入。`App.tsx` 已切换；旧组件暂留，等待消费者检查后清理。
- 已修复浏览器原生 `fetch` 调用上下文问题，以及 WebSpeech 临时结果阻塞最终文字保存的队列时序；停止会保存最后一句，失败保留未保存文字。补齐外部暂停/停止时浏览器录音同步。
- 17 项前端行为单元测试通过；涉及 API 调用、Unicode 流偏移、断线清理、录音队列/权限/失败保留、外观迁移、课堂快速切换和 1,000 条以上分页。失败后永久显示加载中的回归已修复。
- 真实 Chrome 端到端测试 3/3 通过（13.8 秒）：课堂创建/保存/暂停/继续/笔记/结束/刷新/导出；模型未安装后的恢复；设置/关键词提醒/服务错误。模型回答使用确定性 SSE 夹具，非在线服务质量测试。工作区、浅色/深色设置、430×150 紧凑窗口截图已检查。
- 后端 123 项测试通过（10.07 秒），ruff、ty 通过。随后新入口新增 3 项真实进程测试通过（19.10 秒），覆盖私有管道握手、身份验证、随机端口/凭据、父进程 EOF、中文空格路径与实例隔离。
- D 已重写 Python `main.py` 为无导入副作用的启动入口，接入 `--desktop`、`--speech-worker` 和 `--probe-speech`。旧无鉴权路由不再通过该入口启动；2.0 接口迁移说明待补齐。
- Tauri 新增 `backend_connection`、`set_window_mode`、原生保存对话框与原子导出；移除按进程名/端口的全局强杀。启动握手后再做带凭据的 `/api/v2/status` 检查。CSP 限制为打包资源和 loopback；macOS 麦克风用途声明已加入。Rust 首次编译与 2 项验证测试通过；完整原生窗口与安装包验证仍待完成。
- 文件保存采用官方 `tauri-plugin-dialog 2.7.3`（Tauri 2 稳定版，未采用 3.0 alpha）和现有锁文件的 tempfile 3.26.0。macOS 透明窗口按 Tauri 官方文档启用 private API，只针对直接分发安装包；不宣称可提交 Mac App Store。来源：[窗口配置](https://v2.tauri.app/reference/config/#transparent)、[文件对话框](https://v2.tauri.app/plugin/dialog/)。
- 后续必须继续验证：最近的前端历史分页/断线全量恢复变更、原生退出/重启、打包后的语音子进程与模型加载、Windows/Intel Mac 构建、WeChat 基础版以及完整审查和发布。尚未提交、推送或发布。
- 后续验证更新：历史/恢复变更后的 Chrome E2E 3/3 通过（17.4 秒），生产前端构建通过；测试文件也纳入单独 TypeScript 检查并通过。全量 Python 126/126 通过（17.17 秒），Rust Clippy 全目标零警告，3 项 Rust 测试通过（包括真实 Python 后端握手、重复连接复用及退出不影响旁路服务）。
- macOS 原生调试 `.app` 已通过 CUA 实际操作：启动连接、文本模式、中文粘贴、Cmd+Enter 保存、系统保存对话框、430×150 紧凑窗、暂停/继续、展开和“结束并退出”。导出合成原文到 `/private/tmp/classfox-native-export-20260922.txt` 并核对内容；退出后已核实父子 PID 均不存在。调试记录位于独立的 `ClassFox Development` 数据目录。此处未录制环境麦克风，也未调用真实付费服务。
- 已引入锁定的 PyInstaller 6.22.3 / hooks 2026.7，新 `classfox.spec` 首次生成独立后端目录。冻结包原生导入、实际服务握手及音频子进程验证待继续；旧构建脚本与 spec 尚待替换，不能用于发布。

## 2026-09-22：安装包验证与手机连接基础

- 已替换旧构建 spec 与根目录 Windows 脚本，新增 `scripts/build.py` / `scripts/dev.py`，使用锁定依赖、一致版本检查、冻结包自检和应用签名完整性检查；没有按进程名/端口强杀或自动复制 `.env`。脚本显式文件 lint/isort/ty 已通过，未把空目录匹配检查当作证据。
- 冻结后端 `--self-check`（含原生音频与 Keyring 后端）通过；签名后的包内后端 3 项真实启动/父进程 EOF/多实例隔离测试通过（3.76 秒）。冻结音频进程用公开 zh.wav 正确识别“开饭时间早上9点至下午5点。”，约 1.022 秒，退出成功。
- macOS 调试包以 CUA 验证启动的是包内 `Contents/Resources/backend/classfox-service`，恢复先前课堂记录。外层默认临时签名缺少资源封装的问题已修复；测试签名使用 Tauri 的 `APPLE_SIGNING_IDENTITY=-`。PyInstaller 必须将 `-` 映射为默认 ad-hoc 路径，否则显式 identity 会错误启用 hardened runtime 并拒绝无 Team ID 的 Python dylib。真实 Developer ID 则传给 PyInstaller，为嵌套二进制使用同一身份；未使用真实签名资源或关闭 Library Validation。
- 优化版 macOS arm64 `.app` 约 216 MiB，DMG 约 99 MiB，`codesign --verify --deep --strict` 与 `hdiutil verify` 均通过。该构建是进入 E 之前的打包基线；手机功能合入源码后需最终重建。未公证，不能称为 Gatekeeper #9 完全解决；Windows/Intel Mac 尚未构建。
- E 新增独立 `mini-program/`：锁定 TypeScript、微信官方类型 5.2.3、noble-ciphers/hashes 2.4.0，使用 wx 安全随机数；同一固定合成向量在 Node crypto、Python cryptography、JS noble 之间匹配。服务商预设核对官方端点；微信 `request.redirect=manual` 自 3.2.2 起支持 iOS/Android/开发者工具，BYOK 拒绝当前不支持此能力的 PC 微信。
- `phone_crypto.py` / `phone_pairing.py` / `phone_commands.py` / `phone_gateway.py`：单独 opt-in RFC1918 监听、一次性扫码、桌面核对批准、AEAD 方向/计数绑定、同密文重试、撤销/到期清理、独立 owner、手机仅受管本地 ASR/LLM 权限。协议见 `phone-protocol.md`。
- 独立协议与实现审查已执行两轮，复现的撤销清理中断与超限结果失效问题均已修复并有回归。按副作用前预留任务、shield 清理与结果缓存处理取消；原文/笔记按最大 JSON 转义上界分页。此项是有范围的工程审查，不是第三方安全认证。
- 完整后端回归 **157/157 passed in 23.27s**，ruff/ty 通过。覆盖桌面/手机 A/手机 B 隔离、拒绝材料/owner 注入、BYOK 配置切换、不读桌面凭据、迟到识别/总结写入阻断、真正回环入口关闭、最大中文/emoji/控制字符分页，以及 maintenance 过期清理途中关闭入口并取消两项助手任务。
- 桌面增加微信配对设置页、地址发现、二维码、核对数字、批准和撤销，默认不开启 LAN；前端 17 项单元测试与源码/测试 TypeScript 检查通过。Chrome E2E **4/4 通过（20.3 秒）**，包括新增配对页的主动开启、二维码消耗隐藏、nonce 绑定批准与关闭。已检查合成配对二维码截图，尚未真机扫码。
- 小程序协议客户端已实现串行计数、同密文重试、失败关闭、仅内存密钥；BYOK 流式 LLM 与 DashScope ASR 适配已接入微信 API，**13 项合成回调/协议测试通过**，TypeScript 通过。原生页面、录音生命周期、手机历史/导出与完整构建尚未完成。当前机器没有微信开发者工具，也没有 AppID，不能声称开发者工具或真机验证通过。
- 上传音频的离线处理新增 VAD，避免纯静音触发识别：源码音频子进程 + 公开 zh.wav 正确识别，2.591 秒；4 秒合成静音无转录，2.241 秒，均正常退出。此变更在上述 157 项完整回归之后，受影响测试及最终冻结包需继续验证。

## 2026-09-22：微信原生基础版与桌面录音取消

- E 已接入原生“课堂 / 回顾 / 设置”页面、BYOK 实时问答和 DashScope 语音、电脑分段音频、课堂原文/提醒/追问/分段总结、历史、复制与 Markdown 分享。构建输出共享 `runtime.js`，三个页面只注册入口，避免各自实例化状态与 RecorderManager。暂未完成微信开发者工具或真机验证。
- 手机 Key 仅保存在内存，换服务商/地区清除对应旧 Key；本机课堂有格式检查、850,000 UTF-8 字节上限、保存失败的未保存原文恢复、损坏项报告及健康历史继续可用。长原文在 UI 分页，并限制每次传给微信视图层的数据体积；复制和导出仍使用完整内容。
- 微信录音生命周期处理权限拒绝、启动取消、迟到 `onStart`、末帧、系统通话、后台、10 分钟自然结束；不自动重启。原生隐私同意组件使用 `agreePrivacyAuthorization`，授权期间离页或后台明确拒绝待处理请求。官方类型 5.2.3 的隐私监听回调声明与其内嵌文档不一致，按文档的 resolve 回调做了窄类型修正。
- 独立手机安全/生命周期审查复现并修复：模型已完成但笔记 ID 待返回时后台取消仍保存；一条损坏记录阻断全部历史；AES-GCM 加密后 Base64 编码异常未废弃通道导致 nonce 可复用。均有针对性回归。该审查为工程范围检查，不是第三方安全认证。
- **36 项手机单元测试、TypeScript 检查和构建通过**。实际构建产物的 Node VM 页面导航测试通过，验证原文持久化与唯一 RecorderManager；这不是 WXML 渲染或微信原生测试。实时音频、权限、隐私与云服务使用合成微信回调，未调用真实账户。
- `pnpm run test:interop` 通过（5.16 秒）：真实 Python 网关 + Node 手机客户端，经回环 TCP 验证配对核对、批准前拒绝、中文/emoji、提交后丢失响应的同密文重试不重复原文、越权/管理操作拒绝及撤销断开。网关和数据为测试独占，结束后退出。
- 上传 VAD 变更后的受影响后端 **29/29 回归通过（4.77 秒）**。完整后端版本证据仍是此前 157 项；后续桌面取消改动尚需最终全量回归与冻结包重建。
- D/C 补充桌面启动取消：为启动中的语音进程建立可取消任务，暂停/结束在等待课堂锁之前取消它；避免重复停止再次打断子进程清理。浏览器启动期间停止会立即结束 pending Promise，并拒绝迟到启动。合成真实进程取消/清理测试与 BrowserSpeech 回归通过；前端取消入口、延迟 pause 事件的权威状态核对已接入，最终集成检查待完成。
- 小程序具体导入、域名、数据流、资源缺口和真机验收说明见 `mini-program/README.md`。尚未提交、推送、创建 PR 或发布；大版本目标继续进行。

## 2026-09-22：资料解析、连接诊断、冷启动与发布基础

- 资料解析移至 `document_process.py` 的独立拥有进程，保留 25 MiB/解压/文字上限，增加 30 秒可执行超时、取消和临时输入清理。真实 DOCX 中文提取、损坏输入、超时/取消均有回归；冻结入口 `--parse-document` 已接入。
- 桌面新增固定短文本连接测试、预设服务商、外部 HTTPS 链接系统打开、后端恢复入口；捕获控制与迟到 pause 事件处理已完成。20 项前端单元/类型检查/生产构建通过；Chrome 6 个场景分别通过（首轮 5 个成功，连接测试断言定位修正后单项成功），包含资料上传与生成取消。
- Seed 新/旧凭据的真实回环 WebSocket 测试通过，覆盖 gzip 配置、音频、结束包与末句。无真实账户。
- 冷启动分解见 `model-validation.md`：18.922 s 冷请求中模型启动到就绪占 14.550 s；同机后续请求 1.111 s。修复加载中 PID 误判就绪，保持显式课前预热。
- 删除无新版调用方的旧 Python config/routers/services/requirements、旧 React components/services/hooks/CSS/模板图标及 npm 锁文件。旧数据和配置文件本身不删除，2.0 无鉴权 API 的不兼容变化已写入升级说明。
- 当前完整后端回归 **171/171 passed in 43.41s**；项目 isort、ruff/format、ty 均通过。脚本许可证收集的 3 项 unittest 和脚本类型检查通过；脚本 lint/format 使用后端配置，避免根目录全局规则意外改变风格。
- 新增 README、CHANGELOG、贡献规范、使用/迁移/架构/API/发布/验证文档，保留旧站主要路径；历史供应商整页复制改为当前协议概要与官方链接，修复其中失效锚点。Zensical 0.0.63 严格构建通过，无 issues；线上 Pages 未变更。
- 文档构建器调整原因：原 Material for MkDocs 官方宣布 2026-11-05 EOL。采用同团队 Zensical 的 MkDocs YAML/Markdown 兼容模式，保留页面路径和站点 URL；新依赖仅 docs group，锁定版本，不进入应用运行路径。已检查 MIT 许可和官方兼容文档。代价是文档构建器较新，需浏览器验证导航/搜索后才切换部署。
- 新增官方 action SHA 固定的三平台原生构建/测试与前端/手机回归 CI，另有文档严格构建和显式手动部署流程。尚未推送运行，不将 YAML 存在视为 CI 已通过；默认不自动合入、发布 Release 或强推 docs 分支。
- 构建将附带 Python/Node/Cargo 依赖许可清单与原生 ONNX Runtime、PortAudio、OpenSSL 说明。清单说明包含构建/其他平台依赖，不冒充完整二进制 SBOM。当前 macOS arm64 重建中，完成后需冻结包与原生回归。

## 2026-09-22 · 用户要求暂停

用户明确要求停止：额度将尽，转去处理其他项目。目标暂停，不执行新的实现、测试、提交、推送、合入或发布。

保留位置：`feat/classfox-v2` 工作区，尚未 commit / push / 创建 PR。

暂停前最新证据与变更：
- macOS arm64 DMG verbose 重试成功（104027255 bytes），`hdiutil verify` 校验有效；`.app` 的 `codesign --verify --deep --strict` 通过。仅 ad-hoc 测试签名，未公证。
- 修复 scripts 许可证测试的模块同名冲突与 CI 配置路径，3 项 unittest 和 scripts ty 均通过；新增 `.gitattributes` 后 `git diff --check` 通过。
- 独立全分支审查终结为 With fixes：P1 同目录第二实例干扰课堂；P1 后端异常退出遗留模型子进程；P2 手机暂停后手动输入不能保存；P2 旧数据导入丢弃 skipped_files。审查快照为 `/private/var/folders/72/g2pkxtqx0xlb9nth6txt4jgw0000gn/T/classfox-v2-review-6mnx04iy`，238 文件哈希未变化。
- 已开始第一个修复：新增 `classfox/instance.py` 数据目录内核独占锁；app lifespan 在 SQLite 恢复前获取锁；launcher/native 增加重复启动错误提示。**尚未完成验证：** `test_second_instance_cannot_recover_an_owned_classroom` 的原始复现为第二实例错误启动 ready；加锁后第二实例退出但 stdout 没有预期 error JSON，仍需排查 Uvicorn 启动失败路径。Rust 新增代码尚未 fmt / clippy。不要把这批 WIP 当作完成。
- 新增模型父进程 crash/kill 回归 `test_model_exits_even_when_owner_cannot_run_cleanup`，实现尚未修复；建议持有 stdin 生命周期管道的独立 supervisor 拥有真实模型子进程，EOF 时仅结束其所有的进程。尚未加入 supervisor。
- P2 两项修复尚未开始。手机应区分暂停音频与手动文字追加，仍拒绝迟到音频；导入界面应类型化响应并展示零成功/部分成功/跳过文件。
- Mac 曾锁屏，CUA 原生恢复验证未完成；停在新课堂对话框，未启动麦克风。正式 app 已运行，但没有完成测试课堂创建。

继续时：先修复并验证上述四项（当前源码含未完成 WIP），重建受影响原生产物，完成原生恢复/退出与冻结模型验证，更新验收记录；随后准备具体可审查的提交/PR，远端 Windows 和 Intel Mac CI，按授权边界处理合入与发布。微信缺 AppID/Developer Tools，仅本地构建/模拟与协议互通验证，不能声明真机或上架已验证。真实 Apple Developer ID/公证资源仍未知。保留 `/private/tmp/classfox-model-validation` 已下载模型以避免重复下载。


## 2026-09-23 · 恢复，优先 v2 桌面发布

- 用户明确恢复工作，微信正式交付移至 v2.5，并授权 v2 验证通过后直接汇入主分支发布；合入方式仍为 GitHub Rebase and merge。保留微信开发预览，界面和文档已标注。
- 四项独立审查问题均修复；复审 243 文件快照确认四项关闭、无新增阻塞。修复涉及数据目录内核独占锁、Uvicorn 启动失败握手、模型独立管道监督进程、手机仅手动输入允许 paused、导入结果类型化并显示跳过文件。
- 完整后端177项通过47.06秒；模型专项5项通过7.53秒（包括持有者崩溃、被kill、模型忽略SIGTERM的5秒强杀回退）。新增冻结入口测试待随最终包装执行。
- 桌面22项单元、类型检查、生产构建通过；Chrome六项端到端全量通过21.2秒。Rust Clippy零警告和3项测试通过。
- 初次浏览器复验因未安装Playwright专用Chromium在启动前失败；复用此前已核实的CLASSFOX_TEST_BROWSER=chrome通过，不改变测试断言。
- 264个当前工作文件凭据模式扫描未命中；此检查不冒充完整秘密审计。未读取旧.env模板值，旧值仍需所有者在服务商处吊销。
- 最新最终arm64打包进行中，远端多平台CI和PR即将开始；尚未宣称发布成功。

- 最终本机包：6项冻结启动测试通过7.40秒，覆盖同目录互斥及模型监督入口EOF；DMG校验和、嵌套签名完整性通过。冻结公开中文样本1.400秒正确识别；4秒静音0.803秒无转录。冻结监督进程实际加载Qwen3.5 4B，16.686秒回答二分查找需要有序输入，关闭后本地端口不可达。
- CUA最终安装版验证：创建合成文本课堂并保存中文/emoji；精确强杀自己持有的后端，通过“恢复本地服务”重连，原文完整保留；退出后本应用和后端PID均不再存在。未采集环境麦克风。
- PR #13已创建，初次CI发现Windows迁移路径分隔符及连接拒绝/超时差异；macOS合成HTTPServer readiness超时，收紧测试夹具为不调用reverse DNS的loopback server。跨平台修复后本机20项相关测试通过；远端复验进行中。CI仅对PR和main运行，消除同一功能分支push/PR双份构建。

- PR自动审查另指出逐文件PermissionError会中断迁移，以及微信WXML条件未用插值。已将每文件stat/read纳入错误报告，新增2项权限故障回归；微信条件统一绑定表达式，并新增构建产物条件语法检查（先复现失败，再修复）。微信仍未经过原生渲染验收，v2.5范围不变。
- 跨平台修复后的Windows与arm64 Python门禁已通过，进入原生编译；Intel依赖准备较慢，继续等待实际结果。
