import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { randomBytes } from "node:crypto";
import { once } from "node:events";
import { expect, it } from "vitest";
import {
  PhoneApplicationError,
  PhoneClient,
  PhoneTransportError,
  parsePairing,
} from "../src/core/phoneClient";
import { identifier, object } from "../src/core/remote";

it("pairs, approves, retries once, isolates records and revokes against the real Python gateway", async () => {
  const cwd = fileURLToPath(new URL("../../api-service/", import.meta.url));
  const python =
    process.env.CLASSFOX_TEST_PYTHON ??
    fileURLToPath(
      new URL(
        process.platform === "win32"
          ? "../../api-service/.venv/Scripts/python.exe"
          : "../../api-service/.venv/bin/python",
        import.meta.url,
      ),
    );
  const child = spawn(python, ["-u", "-m", "tests.phone_interop_server"], {
    cwd,
    stdio: ["pipe", "pipe", "pipe"],
  });
  const exited = once(child, "exit");
  const lines = createInterface({ input: child.stdout })[
    Symbol.asyncIterator
  ]();
  let stderr = "";
  child.stderr.on("data", (bytes: Buffer) => {
    stderr = (stderr + bytes.toString()).slice(-3000);
  });
  async function line(): Promise<string> {
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const result = await Promise.race([
        lines.next(),
        new Promise<never>((_yes, no) => {
          timer = setTimeout(
            () => no(new Error("Owned interop fixture did not respond")),
            10000,
          );
        }),
      ]);
      if (result.done)
        throw new Error("Owned interop fixture exited before response");
      return result.value;
    } finally {
      clearTimeout(timer);
    }
  }
  let client: PhoneClient | undefined;
  try {
    const offer = parsePairing("classfox-pair-v1:" + (await line()));
    let dropResponse = false,
      retried = false;
    const codec = {
      toBase64: (bytes: Uint8Array) => Buffer.from(bytes).toString("base64"),
      fromBase64: (value: string) =>
        new Uint8Array(Buffer.from(value, "base64")),
    };
    client = new PhoneClient(
      offer,
      randomBytes(32),
      codec,
      async (_url, envelope) => {
        const result = await fetch(`http://127.0.0.1:${offer.port}/phone/v1`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(envelope),
          redirect: "error",
          signal: AbortSignal.timeout(5000),
        });
        if (result.status !== 200)
          throw new PhoneTransportError("Rejected by fixture", false);
        const body: unknown = await result.json();
        if (dropResponse) {
          dropResponse = false;
          retried = true;
          throw new PhoneTransportError(
            "Synthetic lost response after a committed side effect",
          );
        }
        return body;
      },
    );
    await client.hello("合成测试手机");
    await expect(
      client.request({ operation: "create", course_name: "未经批准" }),
    ).rejects.toBeInstanceOf(PhoneApplicationError);
    child.stdin.write("approve\n");
    const approved = JSON.parse(await line()) as {
      approved: boolean;
      code: string;
    };
    expect(approved.approved).toBe(true);
    expect(approved.code).toBe(client.verificationCode);
    expect((await client.request({ operation: "status" })).state).toBe(
      "approved",
    );
    const session = identifier(
      object(
        (
          await client.request({
            operation: "create",
            course_name: "真实加密接口",
          })
        ).session,
      ).id,
    );
    dropResponse = true;
    await client.request({
      operation: "append",
      session_id: session,
      source_id: "synthetic-fragment",
      text: "原文 🦊 不丢失",
    });
    expect(retried).toBe(true);
    const entries = (
      await client.request({ operation: "entries", session_id: session })
    ).entries;
    expect(Array.isArray(entries) && entries.length).toBe(1);
    expect(object(Array.isArray(entries) ? entries[0] : undefined).text).toBe(
      "原文 🦊 不丢失",
    );
    await expect(
      client.request({ operation: "entries", session_id: "f".repeat(32) }),
    ).rejects.toThrow("未找到");
    await expect(
      client.request({ operation: "settings" }),
    ).rejects.toBeInstanceOf(PhoneApplicationError);
    await client.request({ operation: "stop", session_id: session });
    child.stdin.write("revoke\n");
    expect((JSON.parse(await line()) as { revoked: boolean }).revoked).toBe(
      true,
    );
    await expect(client.request({ operation: "status" })).rejects.toThrow(
      "校验失败",
    );
    expect(client.connected).toBe(false);
  } finally {
    client?.close();
    child.stdin.end();
    const timer = setTimeout(() => child.kill("SIGTERM"), 5000);
    try {
      const [code] = await exited;
      expect(code, stderr).toBe(0);
    } finally {
      clearTimeout(timer);
    }
  }
}, 20000);
