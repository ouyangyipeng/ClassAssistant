import { expect, it } from "vitest";
import { ApiError, Client, validateConnection } from "../src/workspace/client";

it("calls native fetch without rebinding its receiver and scopes the token to the request", async () => {
  const fetcher: typeof fetch = async function (this: unknown, url, init) {
    expect(this).toBeUndefined();
    expect(url).toBe("http://127.0.0.1:18865/api/v2/status");
    expect(new Headers(init?.headers).get("Authorization")).toBe(
      "Bearer synthetic",
    );
    expect(init?.redirect).toBe("error");
    return Response.json({ source: "text" });
  };
  const client = new Client(
    { baseUrl: "http://127.0.0.1:18865", token: "synthetic" },
    fetcher,
  );
  expect(await client.request("/status")).toEqual({ source: "text" });
});

it("only accepts a loopback backend and rejects credential-bearing URLs", () => {
  for (const baseUrl of [
    "https://public.example",
    "http://user:password@127.0.0.1",
    "http://127.0.0.1/?token=secret",
  ]) {
    expect(() => validateConnection({ baseUrl, token: "synthetic" })).toThrow();
  }
});

it("retains actionable server errors without treating them as successful results", async () => {
  const client = new Client(
    { baseUrl: "http://127.0.0.1:18865", token: "synthetic" },
    async () =>
      Response.json(
        { error: "model_unavailable", message: "请先安装模型" },
        { status: 503 },
      ),
  );
  await expect(
    client.post("/sessions", { source: "microphone" }),
  ).rejects.toEqual(new ApiError("请先安装模型", 503, "model_unavailable"));
});
