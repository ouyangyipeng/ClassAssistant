# ClassFox desktop workspace

React 19 / TypeScript / Vite / Tauri 2. Start the integrated desktop from the repository root with `uv run --no-project --python 3.12 scripts/dev.py`.

`src/workspace/` contains the authenticated API client, classroom store, event recovery, capture lifecycle and UI. `src-tauri/` owns the Python backend and native window/export operations. The browser development server binds only to loopback. It requires an explicitly configured development backend; the packaged application receives private connection details through Tauri IPC.

```bash
pnpm install --frozen-lockfile
pnpm typecheck
pnpm test
pnpm build
pnpm exec playwright install chromium
pnpm test:e2e
```

E2E tests require the Python environment in `../api-service/.venv`; they launch isolated local API and synthetic provider fixtures. They do not use real service credentials or record the environment microphone. Set `CLASSFOX_TEST_BROWSER=chrome` only when deliberately testing an installed Chrome.

See [development](../docs/getting-started/development.md) and [packaging](../docs/getting-started/packaging.md) for native dependencies and verification boundaries.
