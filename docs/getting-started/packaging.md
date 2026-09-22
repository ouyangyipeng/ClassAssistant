# 打包与发布

## 构建目标

在目标 OS 和架构原生构建。macOS Apple Silicon、macOS Intel、Windows x64 分别产出资产，不使用单机成功代表其他平台通过。

```bash
# 在仓库根目录；仅构建后端
uv run --no-project --python 3.12 scripts/build.py --backend-only

# macOS 当前架构
uv run --no-project --python 3.12 scripts/build.py --bundles app,dmg

# Windows x64
uv run --no-project --python 3.12 scripts/build.py --bundles nsis
```

构建脚本检查 Python、前端、Cargo、Tauri 和握手版本一致，使用锁文件，运行冻结后端自检，再构建桌面。输出位于 `app-ui/src-tauri/target/release/bundle/`；冻结后端在 `api-service/dist/classfox-service/`。源码运行 `.venv` 不随桌面分发。

包内不包含 `.env`、共享 Key、课堂数据库或模型权重。用户首次启动后选择本地下载或 BYOK。所有资源在应用目录内读取，课堂和模型数据写入用户目录。

## 签名状态

macOS 缺少 `APPLE_SIGNING_IDENTITY` 时使用临时 ad-hoc 签名。它用于验证包内完整性，**不代表 Apple Developer ID 签名、公证或 Gatekeeper 放行**。PyInstaller 嵌套二进制与外层应用必须使用一致身份；不能通过关闭 Library Validation 掩盖签名错误。

正式 Developer ID 签名、公证需要维护者自己的 Apple 资源，通过受保护的 CI secret 或本地凭据配置，不写进源码。按照 [Tauri macOS 签名文档](https://v2.tauri.app/distribute/sign/macos/) 配置，并验证 `codesign --verify --deep --strict`、公证票据和下载后的真实安装。Windows Authenticode 同样独立验收；未签名包可能触发系统信誉提示。

## 验证与发布顺序

1. 使用最终源码运行 Python、前端、微信、Rust 和文档检查。
2. 目标平台原生构建并执行冻结后端自检、握手/父进程退出、资料解析及包内语音测试。
3. 检查原生窗口、系统导出、退出、后端恢复、中文与空格路径、安装升级后数据保留。
4. 按平台记录麦克风、模型、签名、公证和已知限制，核对许可证与资产 SHA-256。
5. 完成整个改动的独立审查，PR rebase 到最新默认分支，满足 CI 和维护者审查门禁。
6. 获得合入授权后使用 Rebase and merge，基于同一通过验证的提交打版本标签并发布资产。

构建工作流仅上传 CI 产物，不自动创建 GitHub Release，也不自动合入 PR。现有空附件草稿不属于本次清理范围。

## 文档部署

文档构建工作流可生成静态站点。当前仓库 Pages 仍从 `docs` 分支根目录发布；现有地址为 `http://oyyp.nexa-lang.com/ClassAssistant/`。切换到 GitHub Actions 部署需维护者确认 Pages 的发布来源，再手动触发部署，保留现有域名与路径。不会自动强推或删除 `docs` 分支。
