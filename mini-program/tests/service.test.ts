import { afterEach, expect, it, vi } from "vitest";
import { ClassFox } from "../src/service";
import { defaultSettings } from "../src/core/providers";
import { GenerationCancelled } from "../src/platform/llm";

const fake = vi.hoisted(() => ({
  recognition: (_value: { text: string; sourceId: string; final: boolean }) =>
    undefined as void,
  generate: vi.fn(),
  speechStart: vi.fn(),
  speechClose: vi.fn(),
  speechFinish: vi.fn(),
}));
vi.mock("../src/platform/speech", () => ({
  DashSpeech: class {
    constructor(emit: typeof fake.recognition) {
      fake.recognition = emit;
    }
    start = fake.speechStart;
    close = fake.speechClose;
    finish = fake.speechFinish;
    async feed() {
      fake.recognition({
        text: "停止前的最后一句",
        sourceId: "final",
        final: true,
      });
    }
  },
}));
vi.mock("../src/platform/llm", async (original) => ({
  ...(await original<typeof import("../src/platform/llm")>()),
  generate: fake.generate,
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});
function fixture() {
  const records = new Map<string, unknown>();
  let serial = 0,
    quota = false,
    holdPermission = false,
    permission: (() => void) | undefined;
  let holdRandom = false,
    randomReply: (() => void) | undefined;
  let onStart = () => undefined as void,
    onStop = () => undefined as void;
  let onFrame = (_event: { frameBuffer: ArrayBuffer; isLastFrame: boolean }) =>
    undefined as void;
  const manager = {
    onStart(fn: typeof onStart) {
      onStart = fn;
    },
    onStop(fn: (event: { tempFilePath: string }) => void) {
      onStop = () => fn({ tempFilePath: "" });
    },
    onFrameRecorded(fn: typeof onFrame) {
      onFrame = fn;
    },
    onError() {},
    onInterruptionBegin() {},
    start: vi.fn(() => queueMicrotask(onStart)),
    stop: vi.fn(() =>
      queueMicrotask(() => {
        onFrame({ frameBuffer: new ArrayBuffer(32), isLastFrame: true });
        onStop();
      }),
    ),
  };
  vi.stubGlobal("wx", {
    getStorageSync: (key: string) => records.get(key),
    setStorageSync: (key: string, value: unknown) => {
      if (quota) throw new Error("quota");
      records.set(key, structuredClone(value));
    },
    getStorageInfoSync: () => ({ keys: [...records.keys()] }),
    removeStorageSync: (key: string) => records.delete(key),
    getRecorderManager: () => manager,
    getRandomValues(options: WechatMiniprogram.GetRandomValuesOption) {
      randomReply = () =>
        options.success?.({
          randomValues: new Uint8Array(options.length).fill(++serial).buffer,
          errMsg: "ok",
        });
      if (!holdRandom) randomReply();
    },
    authorize(options: WechatMiniprogram.AuthorizeOption) {
      permission = () => options.success?.({ errMsg: "ok" });
      if (!holdPermission) permission();
    },
    vibrateShort: vi.fn(),
  });
  fake.speechStart.mockResolvedValue(undefined);
  fake.speechFinish.mockResolvedValue(undefined);
  return {
    app: new ClassFox(),
    records,
    manager,
    quota: (value: boolean) => {
      quota = value;
    },
    hold: () => {
      holdPermission = true;
    },
    approve: () => permission?.(),
    holdRandom: () => {
      holdRandom = true;
      randomReply = undefined;
    },
    randomPending: () => !!randomReply,
    randomReply: () => randomReply?.(),
  };
}

it("retains unsaved transcript on quota failure and recovers without deleting prior text", async () => {
  const f = fixture();
  await f.app.create("系统课");
  await f.app.append("已保存原文");
  f.quota(true);
  await f.app.append("尚未保存的文字");
  expect(f.app.snapshot.record?.entries).toHaveLength(1);
  expect(f.app.snapshot.unsaved.map((entry) => entry.text)).toEqual([
    "尚未保存的文字",
  ]);
  expect(() => f.app.load("a".repeat(32))).toThrow("保存并结束");
  f.quota(false);
  f.app.retryUnsaved();
  await f.app.finishClass();
  expect(f.app.repository.list()[0].entries.map((entry) => entry.text)).toEqual(
    ["已保存原文", "尚未保存的文字"],
  );
  expect(f.app.snapshot.unsaved).toEqual([]);
});
it("cannot forward retained keys to another provider or region", () => {
  const f = fixture();
  f.app.configure(defaultSettings, {
    llm: "synthetic-llm",
    speech: "synthetic-speech",
  });
  expect(f.app.credentialStatus()).toEqual({ llm: true, speech: true });
  f.app.configure(
    { ...defaultSettings, llmProvider: "deepseek", speechRegion: "singapore" },
    { llm: "", speech: "" },
  );
  expect(f.app.credentialStatus()).toEqual({ llm: false, speech: false });
  expect(JSON.stringify([...f.records.values()])).not.toContain("synthetic-");
});
it("backgrounding during authorization prevents a late approval from starting recording", async () => {
  const f = fixture();
  await f.app.create("课程");
  f.hold();
  const starting = f.app.startRecording();
  expect(f.app.snapshot.capture).toBe("starting");
  f.app.background();
  f.approve();
  await starting;
  await f.app.stopRecording();
  expect(f.manager.start).not.toHaveBeenCalled();
  expect(fake.speechStart).not.toHaveBeenCalled();
  expect(f.app.snapshot.capture).toBe("idle");
  expect(f.app.snapshot.record?.status).toBe("paused");
});
it("backgrounding drains the final frame into the same class without automatic restart", async () => {
  const f = fixture();
  f.app.configure(defaultSettings, { llm: "", speech: "synthetic-speech" });
  await f.app.create("课程");
  await f.app.startRecording();
  expect(f.app.snapshot.capture).toBe("recording");
  f.app.background();
  await f.app.stopRecording();
  f.app.foregrounded();
  expect(f.app.snapshot.record?.entries.map((entry) => entry.text)).toEqual([
    "停止前的最后一句",
  ]);
  expect(f.app.snapshot.capture).toBe("idle");
  expect(f.manager.start).toHaveBeenCalledOnce();
  expect(fake.speechFinish).toHaveBeenCalledOnce();
});
it("cancelled generation keeps partial text visible but never saves it as a complete note", async () => {
  const f = fixture();
  await f.app.create("课程");
  await f.app.append("课堂原文");
  let reject!: (error: Error) => void;
  const cancel = vi.fn(() => reject(new GenerationCancelled()));
  fake.generate.mockImplementation(
    (
      _provider: string,
      _model: string,
      _key: string,
      _messages: unknown,
      emit: (part: string) => void,
    ) => {
      emit("部分笔记");
      return {
        done: new Promise((_resolve, no) => {
          reject = no;
        }),
        cancel,
      };
    },
  );
  const job = f.app.ask("summary");
  const rejected = expect(job).rejects.toThrow("取消");
  f.app.background();
  await rejected;
  expect(f.app.snapshot.answer).toBe("部分笔记");
  expect(f.app.snapshot.record?.notes).toEqual([]);
  expect(f.app.snapshot.generating).toBe(false);
  expect(cancel).toHaveBeenCalledOnce();
});

it("cancels a completed model answer while its note ID is still being generated", async () => {
  const f = fixture();
  await f.app.create("课程");
  await f.app.append("原文");
  f.holdRandom();
  fake.generate.mockReturnValue({
    done: Promise.resolve("模型已完成"),
    cancel() {},
  });
  const job = f.app.ask("summary"),
    rejected = expect(job).rejects.toThrow("取消");
  await vi.waitFor(() => expect(f.randomPending()).toBe(true));
  f.app.background();
  f.randomReply();
  await rejected;
  expect(f.app.snapshot.record?.notes).toEqual([]);
  expect(f.app.snapshot.generating).toBe(false);
});
