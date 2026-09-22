import { afterEach, expect, it, vi } from "vitest";
import { generate, GenerationCancelled } from "../src/platform/llm";
import { utf8 } from "../src/core/phoneCrypto";

afterEach(() => vi.unstubAllGlobals());
function fixture() {
  let options: WechatMiniprogram.RequestOption<ArrayBuffer>;
  let chunks: (value: { data: ArrayBuffer }) => void = () => undefined;
  let headers: (value: { statusCode: number }) => void = () => undefined;
  const abort = vi.fn();
  vi.stubGlobal("wx", {
    getDeviceInfo: () => ({ platform: "ios" }),
    getAppBaseInfo: () => ({ SDKVersion: "3.2.2" }),
    request(value: WechatMiniprogram.RequestOption<ArrayBuffer>) {
      options = value;
      return {
        abort,
        onChunkReceived(callback: typeof chunks) {
          chunks = callback;
        },
        onHeadersReceived(callback: typeof headers) {
          headers = callback;
        },
      };
    },
  });
  return {
    abort,
    request: () => options,
    chunk: (text: string) => chunks({ data: utf8(text).buffer }),
    header: (code: number) => headers({ statusCode: code }),
  };
}
it("uses fixed HTTPS preset and prevents credential-bearing redirects", async () => {
  const api = fixture();
  const job = generate(
    "deepseek",
    "deepseek-flash",
    "synthetic-test-key",
    [{ role: "user", content: "问题" }],
    () => undefined,
  );
  expect(api.request().url).toBe("https://api.deepseek.com/chat/completions");
  expect(api.request().redirect).toBe("manual");
  const rejection = expect(job.done).rejects.toThrow("保护凭据");
  api.header(302);
  await rejection;
  expect(api.abort).toHaveBeenCalledOnce();
});
it("streams partial text but rejects truncated responses and supports cancellation", async () => {
  const api = fixture(),
    text: string[] = [];
  const job = generate(
    "dashscope",
    "qwen-plus",
    "synthetic-test-key",
    [],
    (part) => text.push(part),
  );
  api.chunk(
    'data: {"choices":[{"delta":{"content":"原文对应的答案"},"finish_reason":null}]}\n\n',
  );
  expect(text.join("")).toBe("原文对应的答案");
  const rejection = expect(job.done).rejects.toThrow(GenerationCancelled);
  job.cancel();
  await rejection;
  expect(api.abort).toHaveBeenCalledOnce();
});
it("fails closed on unsupported PC redirect handling without sending a key", () => {
  const request = vi.fn();
  vi.stubGlobal("wx", {
    getDeviceInfo: () => ({ platform: "mac" }),
    getAppBaseInfo: () => ({ SDKVersion: "3.9.0" }),
    request,
  });
  expect(() =>
    generate(
      "dashscope",
      "qwen-plus",
      "synthetic-test-key",
      [],
      () => undefined,
    ),
  ).toThrow("iOS/Android");
  expect(request).not.toHaveBeenCalled();
});

it("requires both a successful finish reason and completed stream before reporting success", async () => {
  const api = fixture(),
    text: string[] = [];
  const job = generate(
    "dashscope",
    "qwen-plus",
    "synthetic-test-key",
    [],
    (part) => text.push(part),
  );
  api.chunk(
    'data: {"choices":[{"delta":{"content":"完整内容"},"finish_reason":null}]}\n\n',
  );
  api.chunk(
    'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
  );
  api.request().success?.({
    statusCode: 200,
    data: new ArrayBuffer(0),
    header: {},
    cookies: [],
    errMsg: "ok",
  } as unknown as WechatMiniprogram.RequestSuccessCallbackResult<ArrayBuffer>);
  expect(await job.done).toBe("完整内容");
  expect(text.join("")).toBe("完整内容");
});

it("rejects an apparently successful HTTP response that ended mid-answer", async () => {
  const api = fixture();
  const job = generate(
    "dashscope",
    "qwen-plus",
    "synthetic-test-key",
    [],
    () => undefined,
  );
  api.chunk(
    'data: {"choices":[{"delta":{"content":"不完整内容"},"finish_reason":null}]}\n\n',
  );
  const rejected = expect(job.done).rejects.toThrow("提前结束");
  api.request().success?.({
    statusCode: 200,
    data: new ArrayBuffer(0),
    header: {},
    cookies: [],
    errMsg: "ok",
  } as unknown as WechatMiniprogram.RequestSuccessCallbackResult<ArrayBuffer>);
  await rejected;
});
