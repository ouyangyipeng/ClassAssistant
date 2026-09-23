import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const python = path.join(
  root,
  "api-service",
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  expect: { timeout: 10000 },
  use: {
    ...devices["Desktop Chrome"],
    channel: process.env.CLASSFOX_TEST_BROWSER || undefined,
    baseURL: "http://127.0.0.1:1420",
    viewport: { width: 1280, height: 820 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `"${python}" -m http.server 18866 --bind 127.0.0.1 --directory website`,
      cwd: root,
      port: 18866,
      reuseExistingServer: false,
    },
    {
      command: `"${python}" tests/ui_server.py`,
      cwd: path.join(root, "api-service"),
      env: { PYTHONPATH: "." },
      port: 18865,
      reuseExistingServer: false,
    },
    {
      command: "pnpm exec vite",
      cwd: path.join(root, "app-ui"),
      env: {
        CLASSFOX_DEV_TOKEN: "synthetic-ui-test-token",
        CLASSFOX_PORT: "18865",
      },
      port: 1420,
      reuseExistingServer: false,
    },
  ],
});
