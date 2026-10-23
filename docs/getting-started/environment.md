# 开发环境

桌面栈为 Python 3.12 + uv、Node.js 22+ + pnpm 12.4.2、Rust + Tauri 2。当前本机验证使用 macOS arm64、Python 3.12.13 和 Node.js 24；其他目标需要独立原生构建。

- macOS：安装 Xcode Command Line Tools 和对应 Rust 工具链。Intel Mac 还需先通过 Homebrew 执行 `brew install openssl@3`，再运行 `uv sync`；锁定的 cryptography 50.0.1 在该架构需要源码构建，仓库已配置静态链接 OpenSSL，详见[打包说明](packaging.md)。
- Windows x64：安装 Visual Studio C++ Build Tools、Windows SDK 与 WebView2。
- 具体系统依赖按 [Tauri 官方要求](https://v2.tauri.app/start/prerequisites/) 安装。
- Python 环境由 `uv sync --locked --extra audio --extra bundle` 在 `api-service/.venv` 中管理；不使用 conda。
- 前端分别在 `app-ui/` 和 `mini-program/` 运行 `pnpm install --frozen-lockfile`。

测试与文本输入无需真实 API Key。离线模型在应用中单独下载；CI 不下载 GB 级权重，不据此宣称本地模型质量已通过全平台测试。

下一步：[开发与验证](development.md)。

macOS 本地问答使用的 llama.cpp 官方运行时最低要求 **13.3**，安装前会检查；较旧系统仍可选择 BYOK 或已有兼容服务。
