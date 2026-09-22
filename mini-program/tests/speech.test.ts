import { afterEach, expect, it, vi } from "vitest";
import { DashSpeech, type Recognition } from "../src/platform/speech";

afterEach(() => vi.unstubAllGlobals());
function fixture() {
  let opened = () => undefined;
  let message: (event: { data: string }) => void = () => undefined;
  let closed = () => undefined;
  const sent: Array<string | ArrayBuffer> = [];
  const close = vi.fn(() => closed());
  vi.stubGlobal("wx", {
    getDeviceInfo: () => ({ platform: "android" }),
    getAppBaseInfo: () => ({ SDKVersion: "3.2.2" }),
    getRandomValues(options: WechatMiniprogram.GetRandomValuesOption) {
      options.success?.({
        randomValues: new Uint8Array(16).fill(1).buffer,
        errMsg: "ok",
      });
    },
    connectSocket() {
      return {
        onOpen(callback: typeof opened) {
          opened = callback;
          queueMicrotask(opened);
        },
        onMessage(callback: typeof message) {
          message = callback;
        },
        onError() {},
        onClose(callback: typeof closed) {
          closed = callback;
        },
        close,
        send(options: WechatMiniprogram.SocketTaskSendOption) {
          sent.push(options.data);
          options.success?.({ errMsg: "ok" });
          if (typeof options.data !== "string") return;
          const data = JSON.parse(options.data) as {
            header: { action: string; task_id: string };
          };
          queueMicrotask(() =>
            emit(
              data.header.action === "run-task"
                ? "task-started"
                : "task-finished",
              {},
            ),
          );
        },
      };
    },
  });
  function emit(event: string, payload: object, id = "01".repeat(16)) {
    message({
      data: JSON.stringify({ header: { event, task_id: id }, payload }),
    });
  }
  return { sent, emit, close };
}
it("waits for task startup, deduplicates final sentences and drains on finish", async () => {
  const api = fixture(),
    results: Recognition[] = [],
    errors: string[] = [];
  const speech = new DashSpeech(
    (result) => results.push(result),
    (error) => errors.push(error),
  );
  await speech.start("beijing", "fun-asr-realtime", "synthetic-test-key");
  await speech.feed(new ArrayBuffer(3200));
  const payload = {
    output: {
      sentence: { text: "课堂重点", sentence_id: 1, sentence_end: true },
    },
  };
  api.emit("result-generated", payload);
  api.emit("result-generated", payload);
  await speech.finish();
  expect(results).toHaveLength(1);
  expect(results[0].final).toBe(true);
  expect(api.sent).toHaveLength(3);
  expect(api.close).toHaveBeenCalledOnce();
  expect(errors).toEqual([]);
});
it("rejects cross-task messages without saving their text", async () => {
  const api = fixture(),
    results: Recognition[] = [],
    errors: string[] = [];
  const speech = new DashSpeech(
    (result) => results.push(result),
    (error) => errors.push(error),
  );
  await speech.start("beijing", "fun-asr-realtime", "synthetic-test-key");
  api.emit(
    "result-generated",
    {
      output: {
        sentence: { text: "其他课堂", sentence_id: 1, sentence_end: true },
      },
    },
    "wrong-task",
  );
  expect(results).toEqual([]);
  expect(errors).toHaveLength(1);
  await expect(speech.feed(new ArrayBuffer(320))).rejects.toThrow("未就绪");
});
