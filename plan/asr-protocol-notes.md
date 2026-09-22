# 语音协议依据与验证边界

核对时间：2026-09-22。下面的来源用于新实现，不代表已用真实账户调用。

- 火山引擎[大模型流式语音识别 API](https://www.volcengine.com/docs/6561/1354869)：官方 HTML 可读取，搜索工具页面提取失败后通过 HTTPS 获取并检查原文。优化双向地址为 `bigmodel_async`；消息标志 0/2 不含序号，1/3 含序号；2/3 表示最后一包。依据 header 长度读取 payload size，gzip 解压设定上限。启用 utterances，仅 definite 句子写原文。新控制台用 `X-Api-Key`，旧控制台用 App Key + Access Key；1.0 和 2.0 的 resource ID 明确区分。
- 阿里云[实时识别 WebSocket 接口](https://help.aliyun.com/zh/model-studio/fun-asr-realtime-websocket-api)、[客户端事件](https://help.aliyun.com/zh/model-studio/fun-asr-client-events)、[服务端事件](https://help.aliyun.com/zh/model-studio/fun-asr-server-events)：先等待 task-started 再发 PCM，发送 finish-task 后等待最后识别结果及 task-finished。heartbeat 不作转录；只有 sentence_end 句子持久化。现有 DashScope 北京/新加坡域名仍受支持；业务空间新域名不在本次首版配置范围。
- `websockets 17.1` 已安装源码：使用 `additional_headers`，禁用代理继承；重定向策略显式拒绝，避免 Seed 自定义鉴权头传给其他主机。
- `SpeechRecognition 3.17.0` 已安装源码：旧 Google 路径默认是通用接口且可随时失效。兼容适配指定 HTTPS，并设置 operation timeout；界面和文档必须将其标注为在线兼容模式，不能称为本地离线识别或生产 SLA。
- `OpenAI 2.54.0` 已安装源码与真实 SDK + MockTransport：使用 WAV multipart、JSON text 响应、无自动重试、明确总时限，错误正文不向调用者回传。

桌面麦克风、原生识别与 provider 在受管子进程中执行。父进程只处理结构化事件，保存原文和管理状态；它只终止自己持有的进程。密钥经匿名 stdin 管道传入，不进入 argv、配置文件或日志。停止等待末句有 15 秒上限；超时会提示最后一段可能不完整，不能将其显示为完整识别。

现有证据包括协议夹具、真实本机模拟 WebSocket、合成捕获子进程、公开 WAV 的实际离线模型/API 识别。未验证真实麦克风权限与设备录音、Seed/DashScope/OpenAI/Google 真实账户、Windows/Intel Mac 声音设备；后续各平台证据需分别补充。
