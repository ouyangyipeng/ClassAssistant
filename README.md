# 课狐 ClassFox 2.0

<img src="docs/img/logo透明背景.png" alt="课狐 ClassFox" width="120" />

课狐把课堂转录、关键词提醒、即时问答和课后笔记放在一个桌面工作区里。每堂课独立保存原文；可以下载本地语音与问答模型，也可以使用自己的服务商 API Key（BYOK）。微信小程序计划在 v2.5 正式交付，已有开发预览代码。

**v2.0 聚焦桌面体验、原文保留和本地模型。** 安装包、在线账户实测、微信真机和商店上架分别验收，具体边界见 [验证记录](docs/project/validation.md)。微信预览没有公开 AppID，不属于 v2.0 正式验收范围。

[下载安装包](https://github.com/ouyangyipeng/ClassAssistant/releases) · [首次使用](docs/user-guide/quickstart.md) · [升级与数据迁移](docs/user-guide/migration.md) · [微信小程序](mini-program/README.md) · [更新记录](CHANGELOG.md)

## 2.0 的主要变化

- **课堂原文保留**：SQLite 按课堂保存转录、资料和笔记。总结使用原文快照，成功后另存笔记；失败、取消和新开课堂不会覆盖旧原文。
- **本地模型安装**：应用内下载 SenseVoiceSmall INT8、Qwen3.5 4B Q4_K_M 与固定版本 llama.cpp，检查文件摘要及加载结果，支持取消和重试。
- **流式课堂助手**：救场、进度、追问和总结逐段显示，提供取消、首字耗时与总耗时；长课按段整理，明确报告超时和服务商错误。
- **桌面工作区**：完整课堂视图与置顶紧凑窗、原文搜索、PPTX/PDF/DOCX/TXT/Markdown 资料、历史笔记、原生保存对话框、浅色/深色外观。
- **跨平台进程管理**：Tauri 启动带身份验证的本机后端，只清理本实例持有的子进程。应用目录只读，用户数据放在系统用户目录。
- **v2.5 微信开发预览（尚未正式交付）**：手机录音、原文、提醒、问答、笔记和导出；Key 默认仅驻留内存。连接电脑时使用一次性扫码、双端核对和加密消息，手机只能访问自己的课堂。

## 选择使用方式

| 方式 | 所需资源 | 课堂内容去向 |
| --- | --- | --- |
| 桌面本地模式 | 下载语音和问答模型；足够磁盘、内存 | 在电脑上处理，原文保存在本机 |
| 桌面 BYOK | ASR 和 LLM 可分别配置自己的服务 | 相应音频或文字发送到选定服务商 |
| 手机独立 BYOK（v2.5 预览） | 微信项目可运行；预设服务商 Key；网络 | 音频和文字分别发送到所选 ASR、LLM 服务商 |
| 手机连接电脑（v2.5 预览） | 同一可互通局域网；电脑运行课狐并已安装本地模型 | 加密传给电脑处理；电脑和手机各保存手机课堂记录 |

本地问答权重约 2.74 GB，语音模型约 240 MB，安装还需要临时空间。运行内存与响应速度取决于设备和上下文。模型不随桌面安装包内置，首次安装需要联网。手机首版不在手机上运行离线大模型。

## 首次使用

1. 打开「设置 → 本地模型」完成模型安装，或在「问答服务」「语音与麦克风」配置 BYOK。
2. 本地模式可先点「准备问答模型」，把首次加载安排在课前。BYOK 可用固定短文本测试连接。
3. 检测麦克风，填写关键词。录音前确认已取得参与者的知情同意。
4. 开始一堂课，选择麦克风、浏览器语音、文本输入或分段音频上传。系统听写可直接输入文本框。
5. 需要时发起救场、进度或追问；结束后整理笔记并导出。

浏览器语音依赖 WebView 和网络，不等于离线识别。模型回答和识别结果可能有误，需要结合原始课堂内容核实。

## 从源码运行

需要 Python 3.12、[uv](https://docs.astral.sh/uv/getting-started/installation/)、Node.js 22+、pnpm 12.4.2、Rust 和 [Tauri 平台构建依赖](https://v2.tauri.app/start/prerequisites/)。本次验证使用 Python 3.12.13 / Node.js 24。

```bash
git clone https://github.com/ouyangyipeng/ClassAssistant.git
cd ClassAssistant
uv run --no-project --python 3.12 scripts/dev.py
```

Windows 也可运行根目录 `dev.bat`。启动脚本使用锁定依赖和独立后端，不会按名称或端口强杀其他程序，也不会创建或覆盖 `.env`。

```bash
# macOS 本机架构应用与 DMG；默认仅临时签名
uv run --no-project --python 3.12 scripts/build.py --bundles app,dmg

# Windows x64 安装程序（在 Windows 上运行）
uv run --no-project --python 3.12 scripts/build.py --bundles nsis
```

构建、签名、回归和发布门禁见 [开发指南](docs/getting-started/development.md) 与 [打包说明](docs/getting-started/packaging.md)。微信源码有独立的 [构建与配置说明](mini-program/README.md)。

## 数据和升级

桌面正式版数据目录为 macOS 的 `~/Library/Application Support/ClassFox` 或 Windows 的 `%LOCALAPPDATA%\ClassFox`。调试版使用 `ClassFox Development`。数据库包含课堂文本，备份应在正常退出应用后复制整个数据目录。

旧版 `data/`、`.env` 与外观偏好可在设置中分别导入。旧文件保留，重复导入相同文本不重复创建记录。旧版本已经压缩或覆盖掉的原文无法恢复。2.0 不分发共享试用 Key，不继续开放旧的无鉴权 API；第三方调用方请阅读 [接口迁移说明](docs/developer/api-reference.md)。

## 贡献与许可

欢迎提供可复现的问题、脱敏日志和改进建议，参见 [贡献指南](CONTRIBUTING.md)。macOS 分支和 WebSpeech 等历史贡献的处理记录见 [issues 与分支](docs/project/maintenance.md)。

项目代码使用 [MIT License](LICENSE)。语音模型、问答模型、运行时和第三方依赖各自遵循上游许可，见 [第三方说明](THIRD_PARTY_NOTICES.md)。

macOS 本地问答使用的 llama.cpp 官方运行时最低要求 **13.3**，安装前会检查；较旧系统仍可选择 BYOK 或已有兼容服务。
