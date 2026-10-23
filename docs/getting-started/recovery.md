# 换机恢复与项目交接

代码、依赖锁文件、品牌素材、模型清单和构建流程都保存在 [GitHub 仓库](https://github.com/ouyangyipeng/ClassAssistant)。最新正式安装包为 [ClassFox 2.1.1](https://github.com/ouyangyipeng/ClassAssistant/releases/tag/v2.1.1)，三平台安装包和 `SHA256SUMS.txt` 作为 Release 资产保存。

## 在新电脑恢复开发

准备 Python 3.12、uv、Node.js 24、pnpm 12.4.2 和 Rust；平台编译工具见[环境准备](environment.md)。随后执行：

```bash
git clone https://github.com/ouyangyipeng/ClassAssistant.git
cd ClassAssistant
git fetch --all --tags
uv sync --project api-service --python 3.12 --locked --extra audio --extra bundle --group docs
pnpm --dir app-ui install --frozen-lockfile
pnpm --dir mini-program install --frozen-lockfile
```

新工作从主线建立功能分支，再启动开发环境：

```bash
git switch -c feat/your-change origin/main
uv run --no-project --python 3.12 scripts/dev.py
```

主线已包含 2.1.1 功能和官网更新。若需复现发布源码，使用 `git switch --detach v2.1.1`；远端 `mac`、`docs` 及既有功能分支保留历史，正常继续开发使用 `origin/main`。

测试命令见[开发与验证](development.md)。构建当前电脑的平台安装包：

```bash
uv run --no-project --python 3.12 scripts/build.py
```

构建时会重新获取并核对平台运行包和 VAD。`.venv/`、`node_modules/`、`target/`、`release/`、`dist/`、`site/` 和本地验证缓存均可重建，恢复开发无需复制旧电脑的这些目录。不要将依赖环境或旧的绝对路径作为源码的一部分。

## 模型与安装包

- 问答模型优先使用魔搭 `unsloth/Qwen3.5-4B-GGUF` 的固定提交。
- 语音模型的权重、词表和许可优先使用魔搭 `gomodels/sherpa` 的固定提交。
- 固定版本、大小和 SHA-256 见 `api-service/classfox/model_catalog.py` 与 `download_sources.py`；现有原始源作为备用。模型来源与安装指纹分离，已有可用安装保持兼容。
- 用户在 App 内下载安装模型；网盘只分发安装包。[可订阅下载目录](https://pan.baidu.com/s/5Wc6Xt2IZ9ehisotPnstGow)与[官网](https://class.nexa-lang.com/#download)保持一致。
- 维护者确有离线包需求时可运行 `scripts/offline_models.py`，日常使用按[国内下载指南](../user-guide/offline-models.md)在 App 内安装。

重新发布前执行三平台 CI，并核对 Release 资产名称、大小和校验和；具体流程见[打包与发布](packaging.md)。macOS 包仍为 ad-hoc 签名，Windows 包未使用商业代码签名。

## 课堂数据与凭据

源码恢复与个人课堂数据分开处理。正式版 macOS 数据位于 `~/Library/Application Support/ClassFox/`，开发版使用 `ClassFox Development/`；Windows 使用 `platformdirs` 解析的 `ClassFox` 用户数据目录。

需要迁移课堂数据时，先正常退出应用，再将对应数据目录备份到私密存储。`classfox.sqlite3` 保存课堂、原文和笔记；如存在同名 `-wal`、`-shm` 文件，应与数据库一起保留。`preferences.json` 等配置按目录一并备份，`models/` 可通过 App 重新下载。

API Key 使用系统凭据存储，服务名为 `ClassFox`。代码仓库和 Release 不保存 Key；换机后在 App 中重新配置自己的服务商凭据。不要将课堂数据库、真实配置、`.env` 或钥匙串导出内容上传到公开仓库。

## 官网、域名和后续工作

GitHub Pages 从 `main` 通过 `.github/workflows/docs.yml` 构建，使用 `deploy=true` 手动部署。阿里云 DNS 中 `class` 的 CNAME 指向 `ouyangyipeng.github.io`；自定义域名为 `class.nexa-lang.com`，HTTPS 由 GitHub Pages 提供。仓库清理不改变这些线上配置。

微信小程序继续按 v2.5 开发预览管理：代码、36 项单元测试、构建产物检查和 Python/Node 回环互通保留；正式 AppID、微信开发者工具、真机、隐私与域名配置及上架仍需完成。入口为 `mini-program/README.md`。

截至 2026-10-23，历史 issue #3、#6、#9、#12 仍开放；处理依据和剩余范围见 [Issues 与历史分支](../project/maintenance.md)。恢复演练与既有发布证据见[验证范围](../project/validation.md)。
