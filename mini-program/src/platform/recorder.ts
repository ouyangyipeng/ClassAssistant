import type { AudioSink } from "./speech";

interface Completion {
  promise: Promise<void>;
  resolve(): void;
  reject(error: Error): void;
}
function completion(): Completion {
  let resolve!: () => void, reject!: (error: Error) => void;
  const promise = new Promise<void>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  void promise.catch(() => undefined);
  return { promise, resolve, reject };
}

export async function requestMicrophone(): Promise<void> {
  const authorize = () =>
    new Promise<void>((resolve, reject) =>
      wx.authorize({
        scope: "scope.record",
        success: () => resolve(),
        fail: () =>
          reject(
            new Error(
              "尚未获得麦克风权限。可使用文字记录，或到微信权限设置中允许录音",
            ),
          ),
      }),
    );
  if (typeof wx.requirePrivacyAuthorize === "function") {
    await new Promise<void>((resolve, reject) =>
      wx.requirePrivacyAuthorize({
        success: () => resolve(),
        fail: () =>
          reject(
            new Error("请先同意录音相关的隐私说明；也可以继续使用文字记录"),
          ),
      }),
    );
  }
  await authorize();
}

// WeChat has one RecorderManager and no off-listener API. Own it once per app.
export class Recorder {
  private sink: AudioSink | null = null;
  private ready = completion();
  private stopped = completion();
  private state: "idle" | "starting" | "recording" | "stopping" | "fault" =
    "idle";
  private timer: ReturnType<typeof setTimeout> | undefined;
  private draining = false;
  private reason = "";

  constructor(
    private manager: WechatMiniprogram.RecorderManager,
    private ended: (message: string) => void,
  ) {
    manager.onStart(() => this.onStart());
    manager.onFrameRecorded(({ frameBuffer }) => {
      if (!this.sink || this.draining || this.state === "fault") return;
      if (frameBuffer.byteLength)
        void this.sink
          .feed(frameBuffer)
          .catch(() =>
            this.fail("音频发送失败，录音已停止；最后一段可能不完整"),
          );
    });
    manager.onStop((result) => {
      if (result.tempFilePath)
        wx.getFileSystemManager().unlink({
          filePath: result.tempFilePath,
          fail: () =>
            this.ended("临时录音未能清理，请在微信设置中清理小程序缓存"),
        });
      void this.onStop();
    });
    manager.onError(() =>
      this.fail("录音失败，请检查麦克风权限及是否被其他应用占用"),
    );
    manager.onInterruptionBegin(() => {
      void this.stop(
        "录音被系统通话中断，原文已保留；回到课堂后可手动继续",
      ).catch(() => undefined);
    });
  }

  start(sink: AudioSink): Promise<void> {
    if (this.state !== "idle") {
      sink.close();
      return Promise.reject(
        new Error("麦克风尚未停止，请稍后重试；若持续异常请重开小程序"),
      );
    }
    this.sink = sink;
    this.ready = completion();
    this.stopped = completion();
    this.state = "starting";
    this.draining = false;
    this.reason = "";
    this.timer = setTimeout(
      () => this.fail("麦克风启动超时，请重开小程序后重试"),
      10000,
    );
    try {
      this.manager.start({
        duration: 600000,
        sampleRate: 16000,
        numberOfChannels: 1,
        format: "PCM",
        frameSize: 8,
      });
    } catch {
      this.fail("无法启动麦克风，请更新微信后重试");
    }
    return this.ready.promise;
  }

  private onStart(): void {
    if (this.state !== "starting") {
      this.manager.stop();
      return;
    }
    clearTimeout(this.timer);
    this.state = "recording";
    this.ready.resolve();
  }

  stop(message = ""): Promise<void> {
    if (this.state === "idle") return Promise.resolve();
    if (this.state === "fault")
      return Promise.reject(new Error("麦克风状态异常，请重开小程序"));
    if (this.state === "stopping") return this.stopped.promise;
    this.reason = message;
    this.state = "stopping";
    this.ready.reject(new Error("录音启动已取消"));
    clearTimeout(this.timer);
    this.timer = setTimeout(
      () => this.fail("麦克风未能及时停止，请重开小程序；最后一句可能不完整"),
      10000,
    );
    this.manager.stop();
    return this.stopped.promise;
  }

  private async onStop(): Promise<void> {
    if (this.state === "idle" || this.draining) return;
    const natural = this.state === "recording",
      sink = this.sink;
    const failed = this.state === "fault";
    this.draining = true;
    this.state = "stopping";
    clearTimeout(this.timer);
    this.ready.reject(new Error("录音已停止"));
    try {
      if (!failed) await sink?.finish();
      this.stopped.resolve();
    } catch {
      this.reason = "录音已停止，最后一句未能完整识别；已保存的原文不受影响";
      this.stopped.reject(new Error(this.reason));
    } finally {
      sink?.close();
      this.sink = null;
      this.state = "idle";
      this.draining = false;
      this.ended(
        this.reason ||
          (natural ? "本段录音达到微信时长限制或已结束，请点击继续录音" : ""),
      );
    }
  }

  private fail(message: string): void {
    if (this.state === "idle" || this.state === "fault") return;
    clearTimeout(this.timer);
    this.reason = message;
    this.state = "fault";
    this.sink?.close();
    this.ready.reject(new Error(message));
    this.stopped.reject(new Error(message));
    this.manager.stop();
    this.ended(message);
  }
}
