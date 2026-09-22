import { afterEach, expect, it, vi } from "vitest";
import { Recorder, requestMicrophone } from "../src/platform/recorder";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
function fixture() {
  let start = () => undefined as void,
    stop = () => undefined as void,
    interrupt = () => undefined as void;
  let frame = (_value: { frameBuffer: ArrayBuffer; isLastFrame: boolean }) =>
    undefined as void;
  const manager = {
    onStart(fn: typeof start) {
      start = fn;
    },
    onStop(
      fn: (value: {
        tempFilePath: string;
        duration: number;
        fileSize: number;
      }) => void,
    ) {
      stop = () =>
        fn({
          tempFilePath: "wxfile://test-owned",
          duration: 1000,
          fileSize: 32,
        });
    },
    onFrameRecorded(fn: typeof frame) {
      frame = fn;
    },
    onError() {},
    onInterruptionBegin(fn: typeof interrupt) {
      interrupt = fn;
    },
    start: vi.fn(),
    stop: vi.fn(),
  };
  const unlink = vi.fn(),
    ended = vi.fn();
  vi.stubGlobal("wx", { getFileSystemManager: () => ({ unlink }) });
  const sink = {
    feed: vi.fn(async () => undefined),
    finish: vi.fn(async () => undefined),
    close: vi.fn(),
  };
  return {
    recorder: new Recorder(
      manager as unknown as WechatMiniprogram.RecorderManager,
      ended,
    ),
    sink,
    ended,
    unlink,
    manager,
    start: () => start(),
    stop: () => stop(),
    interrupt: () => interrupt(),
    frame: () => frame({ frameBuffer: new ArrayBuffer(8), isLastFrame: true }),
  };
}

it("cancels a pending start and stops a late native start before allowing another recording", async () => {
  const f = fixture();
  const ready = f.recorder.start(f.sink);
  const rejected = expect(ready).rejects.toThrow("取消");
  const stopped = f.recorder.stop();
  f.start();
  expect(f.manager.stop).toHaveBeenCalledTimes(2);
  f.frame();
  f.stop();
  await rejected;
  await stopped;
  expect(f.sink.feed).toHaveBeenCalledOnce();
  expect(f.sink.finish).toHaveBeenCalledOnce();
  expect(f.unlink).toHaveBeenCalledWith(
    expect.objectContaining({ filePath: "wxfile://test-owned" }),
  );
});
it("flushes final audio on interruption and never restarts without the user", async () => {
  const f = fixture(),
    started = f.recorder.start(f.sink);
  f.start();
  await started;
  f.interrupt();
  f.frame();
  f.stop();
  await Promise.resolve();
  await Promise.resolve();
  expect(f.sink.finish).toHaveBeenCalledOnce();
  expect(f.ended).toHaveBeenCalledWith(expect.stringContaining("系统通话"));
  expect(f.manager.start).toHaveBeenCalledOnce();
});
it("times out a missing start, closes the sink and stops any late native start", async () => {
  vi.useFakeTimers();
  const f = fixture(),
    rejection = expect(f.recorder.start(f.sink)).rejects.toThrow("超时");
  await vi.advanceTimersByTimeAsync(10000);
  await rejection;
  f.start();
  expect(f.manager.stop).toHaveBeenCalledTimes(2);
  expect(f.sink.close).toHaveBeenCalled();
  await expect(f.recorder.start(f.sink)).rejects.toThrow("尚未停止");
});
it("explains microphone denial without requesting a recording", async () => {
  vi.stubGlobal("wx", {
    authorize: (options: WechatMiniprogram.AuthorizeOption) =>
      options.fail?.({ errMsg: "denied" }),
  });
  await expect(requestMicrophone()).rejects.toThrow("文字记录");
});
