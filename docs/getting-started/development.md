# 开发与验证

## 启动桌面

在仓库根目录执行：

```bash
uv run --no-project --python 3.12 scripts/dev.py
```

Windows 可运行 `dev.bat`。脚本同步锁定依赖、启动 Vite 和 Tauri，由原生进程通过私有管道启动自己的后端。开发数据目录独立于正式版。如果调试 `.app` 中已有打包后端，原生端优先使用该资源；修改 Python 后需重建，或使用没有嵌入后端的源码开发运行。

无需复制 `.env.example`。API-only 开发可在私有环境中设置 `CLASSFOX_API_TOKEN` 后运行 `api-service/main.py`；不得把真实 token 写入命令历史、URL、代码或公开日志。独立服务仍仅监听 loopback。

## 后端

在 `api-service/` 中执行：

```bash
uv sync --locked --extra audio --extra bundle
uv run --no-sync isort --check-only classfox tests main.py
uv run --no-sync ruff check classfox tests main.py
uv run --no-sync ruff format --check classfox tests main.py
uv run --no-sync ty check
uv run --no-sync pytest -q
```

测试包含真实本机 HTTP/WebSocket、拥有的子进程、临时 SQLite、模拟 provider 和取消/越权场景。测试目录和凭据均为合成数据；监听受限的沙箱需要允许回环监听。测试不会录制环境麦克风或调用真实付费服务。

## 桌面前端与 Rust

在 `app-ui/` 中执行：

```bash
pnpm install --frozen-lockfile
pnpm typecheck
pnpm test
pnpm build
pnpm exec playwright install chromium
pnpm test:e2e
```

浏览器 E2E 自动启动临时 API 和合成流式服务，使用固定测试端口 1420 / 18865；端口被占用时失败，不停止其他程序。在 CI Linux 上用 `playwright install --with-deps chromium` 安装浏览器依赖。

在 `app-ui/src-tauri/` 中执行：

```bash
cargo fmt --all -- --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
```

原生测试验证握手、重复连接、退出和实例隔离。GUI、麦克风、签名公证、真机微信需要分别验证，不能由上述测试替代。

## 微信与文档

在 `mini-program/` 中依次执行 `pnpm typecheck`、`pnpm test`、`pnpm build`、`pnpm test:bundle`、`pnpm test:interop`。最后一项启动真实 Python 网关并与 Node 客户端通过回环 TCP 互通，使用 `api-service/.venv`。

文档保持原 Pages 的页面路径及 `mkdocs.yml` 格式，使用锁定的 Zensical 构建。在仓库根目录执行：

```bash
uv sync --project api-service --locked --extra audio --extra bundle --group docs
uv run --project api-service --no-sync zensical build --strict
uv run --project api-service --no-sync zensical serve
```

生成目录 `site/` 不提交。文档源在主线维护，旧 `docs` 发布分支先保留；切换部署前检查页面、搜索和旧链接。Material for MkDocs 已公告将于 2026-11-05 结束常规维护，迁移依据见 [上游公告](https://github.com/squidfunk/mkdocs-material/issues/8523) 与 [兼容指南](https://zensical.org/docs/compatibility/mkdocs/migration/)。
