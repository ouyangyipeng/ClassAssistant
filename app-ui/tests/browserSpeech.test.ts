import { afterEach, expect, it, vi } from "vitest";
import {
  BrowserSpeech,
  type RecognitionEvent,
} from "../src/workspace/browserSpeech";

class SpeechFixture {
  static latest: SpeechFixture;
  lang = "";
  continuous = false;
  interimResults = false;
  maxAlternatives = 1;
  onstart: (() => void) | null = null;
  onend: (() => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onresult: ((event: RecognitionEvent) => void) | null = null;
  constructor() {
    SpeechFixture.latest = this;
  }
  start = vi.fn(() => this.onstart?.());
  stop = vi.fn(() => this.onend?.());
  abort = vi.fn(() => this.onend?.());
  result(text: string, index = 0, final = true) {
    const results = Array.from({ length: index + 1 }, () => ({
      isFinal: false,
      0: { transcript: "" },
    }));
    results[index] = { isFinal: final, 0: { transcript: text } };
    this.onresult?.({ resultIndex: index, results });
  }
}

afterEach(() => vi.useRealTimers());

it("rejects a cancelled pending start immediately and aborts a late native start", async () => {
  vi.useFakeTimers();
  const failure = vi.fn();
  const capture = new BrowserSpeech(
    "zh-CN",
    vi.fn(),
    vi.fn(),
    failure,
    SpeechFixture,
  );
  const speech = SpeechFixture.latest;
  speech.start.mockImplementation(() => undefined);
  const starting = expect(capture.start()).rejects.toThrow("已取消");
  await capture.stop();
  await starting;
  speech.onstart?.();
  await vi.advanceTimersByTimeAsync(10000);
  expect(speech.abort).toHaveBeenCalledOnce();
  expect(failure).not.toHaveBeenCalled();
});

it("saves only final results and deduplicates IDs without losing repeated speech", async () => {
  const save = vi.fn().mockResolvedValue(undefined),
    partial = vi.fn();
  const capture = new BrowserSpeech(
    "auto",
    save,
    partial,
    vi.fn(),
    SpeechFixture,
  );
  await capture.start();
  const speech = SpeechFixture.latest;
  expect(speech.lang).toBe("zh-CN");
  speech.result("临时文字", 0, false);
  expect(partial).toHaveBeenLastCalledWith("临时文字");
  expect(save).not.toHaveBeenCalled();
  speech.result("课堂内容");
  speech.result("课堂内容");
  speech.result("课堂内容", 1);
  await capture.stop();
  expect(save).toHaveBeenCalledTimes(2);
  expect(save.mock.calls[0][1]).not.toBe(save.mock.calls[1][1]);
  expect(capture.unsaved()).toBe("");
});

it("flushes the last result on stop and cancels pending restarts", async () => {
  vi.useFakeTimers();
  const save = vi.fn().mockResolvedValue(undefined);
  const capture = new BrowserSpeech(
    "zh-CN",
    save,
    vi.fn(),
    vi.fn(),
    SpeechFixture,
  );
  await capture.start();
  const speech = SpeechFixture.latest;
  speech.onend?.();
  speech.stop.mockImplementation(() => {
    speech.result("最后一句");
    speech.onend?.();
  });
  await capture.stop();
  await vi.advanceTimersByTimeAsync(10000);
  expect(save).toHaveBeenCalledWith("最后一句", expect.any(String));
  expect(speech.start).toHaveBeenCalledTimes(1);
});

it("stops recognition on persistence failure and retains text for recovery", async () => {
  const failed = vi.fn();
  const capture = new BrowserSpeech(
    "zh-CN",
    vi.fn().mockRejectedValue(new Error("synthetic failure")),
    vi.fn(),
    failed,
    SpeechFixture,
  );
  await capture.start();
  SpeechFixture.latest.result("不能丢失的文字");
  await expect(capture.stop()).rejects.toThrow("未保存");
  expect(capture.unsaved()).toBe("不能丢失的文字");
  expect(SpeechFixture.latest.abort).toHaveBeenCalledTimes(1);
  expect(failed).toHaveBeenCalledTimes(1);
});

it("rejects permission denial promptly instead of reporting recording", async () => {
  const failed = vi.fn();
  const capture = new BrowserSpeech(
    "zh-CN",
    vi.fn(),
    vi.fn(),
    failed,
    SpeechFixture,
  );
  SpeechFixture.latest.start.mockImplementation(() =>
    SpeechFixture.latest.onerror?.({ error: "not-allowed" }),
  );
  await expect(capture.start()).rejects.toThrow("权限被拒绝");
  await capture.stop();
  expect(failed).toHaveBeenCalledTimes(1);
});

it("bounds the pending queue when saving cannot keep up", async () => {
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  const failed = vi.fn();
  const capture = new BrowserSpeech(
    "zh-CN",
    () => pending,
    vi.fn(),
    failed,
    SpeechFixture,
  );
  await capture.start();
  for (let index = 0; index < 40; index++)
    SpeechFixture.latest.result(`文字${index}`, index);
  expect(failed).toHaveBeenCalledTimes(1);
  expect(capture.unsaved().split("\n")).toHaveLength(21);
  release();
  await expect(capture.stop()).rejects.toThrow("未保存");
});
