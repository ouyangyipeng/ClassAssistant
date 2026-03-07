# 环境准备

## 适用平台

当前项目主要面向 Windows 开发和发布。虽然部分前后端代码本身具备跨平台能力，但现有脚本、麦克风流程和打包链路都按 Windows 优先设计。

## 必备软件

### Python

- 建议版本：Python 3.11
- 用途：FastAPI 后端、资料解析、ASR 接入、文档构建

### Node.js

- 建议版本：Node.js 20 或更高 LTS
- 用途：React 前端、Vite、Tauri 前端构建

### Rust

- 建议使用 rustup 安装稳定版
- 用途：Tauri 桌面壳层编译

### Visual Studio Build Tools

- 需要安装 C++ 桌面开发相关组件
- PyAudio、部分 Python 依赖和 Tauri Windows 构建会用到本机工具链

## 初次安装步骤

### 1. 创建后端虚拟环境

```powershell
cd api-service
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install pyinstaller
```

### 2. 安装前端依赖

```powershell
cd app-ui
npm install
```

### 3. 准备后端配置

在 api-service 下创建 .env，可参考 .env.example。如果仓库里暂时没有该文件，请按项目 README 中列出的字段自行创建。

### 4. 可选：准备文档依赖

如果你也要预览当前文档站点：

```powershell
python -m venv .venv-docs
.venv-docs\Scripts\pip install -r requirements-docs.txt
```

## 推荐检查项

在继续之前，建议确认：

- python --version 输出为 3.11.x 或接近版本
- node -v 可以正常执行
- rustc --version 可以正常执行
- npm install 没有残留严重错误
- api-service/.venv 下已成功安装 PyAudio、FastAPI、OpenAI 等依赖

## 环境变量建议

### 本地体验最低配置

如果你只想体验 UI 或基本链路，可先使用：

```ini
ASR_MODE=mock
API_PORT=8765
```

### 联调推荐配置

```ini
ASR_MODE=local
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=你的密钥
LLM_MODEL=deepseek-chat
API_PORT=8765
```

### 接入在线 ASR 时补充

- 使用 DashScope 时提供 DASHSCOPE_API_KEY
- 使用 Seed-ASR 时提供 APP KEY、ACCESS KEY、RESOURCE ID

## 常见安装问题

### PyAudio 安装失败

优先检查：

- 是否安装了 Visual Studio Build Tools
- Python 版本是否过新或和现有 wheel 不兼容
- 当前 shell 是否使用了正确的 .venv

### Tauri 构建失败

优先检查：

- Rust 是否正确安装
- Windows C++ 构建工具是否齐全
- Node 依赖是否安装完整