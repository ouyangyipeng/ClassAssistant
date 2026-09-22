export interface RecognitionEvent {
  resultIndex: number;
  results: ArrayLike<{
    isFinal: boolean;
    [index: number]: { transcript: string };
  }>;
}
interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onresult: ((event: RecognitionEvent) => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type Constructor = new () => Recognition;

export function browserRecognition(): Constructor | null {
  const target = window as Window & {
    SpeechRecognition?: Constructor;
    webkitSpeechRecognition?: Constructor;
  };
  return target.SpeechRecognition ?? target.webkitSpeechRecognition ?? null;
}

export class BrowserSpeech {
  private recognition: Recognition;
  private stopping = false;
  private closed = false;
  private failed = false;
  private restart: ReturnType<typeof setTimeout> | null = null;
  private epoch = 0;
  private prefix = crypto.randomUUID();
  private pending: { text: string; id: string }[] = [];
  private seen = new Set<string>();
  private drain: Promise<void> | null = null;
  private ended: (() => void) | null = null;
  private startResolve: (() => void) | null = null;
  private startReject: ((reason: Error) => void) | null = null;
  private restartTimes: number[] = [];

  constructor(
    language: string,
    private save: (text: string, id: string) => Promise<unknown>,
    private partial: (text: string) => void,
    private error: (message: string) => void,
    constructor = browserRecognition(),
  ) {
    if (!constructor)
      throw new Error(
        "当前浏览器或桌面 WebView 不支持语音识别，请选择离线识别或文本输入。",
      );
    this.recognition = new constructor();
    this.recognition.lang = language === "auto" ? "zh-CN" : language;
    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.maxAlternatives = 1;
    this.recognition.onstart = () => {
      if (this.stopping || this.closed || this.failed) {
        this.recognition.abort();
        return;
      }
      this.startResolve?.();
      this.startResolve = this.startReject = null;
    };
    this.recognition.onresult = (event) => this.result(event);
    this.recognition.onerror = (event) => {
      if (this.stopping && event.error === "aborted") return;
      if (event.error === "no-speech") return;
      this.fail(
        event.error === "not-allowed" || event.error === "service-not-allowed"
          ? "浏览器麦克风或语音服务权限被拒绝，请在系统和应用设置中允许后重试。"
          : "浏览器语音识别已中断，请检查麦克风和网络后恢复。",
      );
    };
    this.recognition.onend = () => {
      this.ended?.();
      this.ended = null;
      if (this.stopping || this.failed || this.closed) return;
      this.restartTimes = this.restartTimes.filter(
        (time) => Date.now() - time < 10000,
      );
      if (this.restartTimes.length >= 3) {
        this.fail("浏览器语音连接反复中断，请改用离线或其他语音服务。");
        return;
      }
      this.restartTimes.push(Date.now());
      this.restart = setTimeout(() => {
        this.restart = null;
        if (!this.stopping && !this.failed && !this.closed) {
          this.epoch++;
          try {
            this.recognition.start();
          } catch {
            this.fail("无法恢复浏览器识别，请重新开始。");
          }
        }
      }, 400);
    };
  }

  async start(): Promise<void> {
    if (this.stopping || this.closed || this.failed)
      throw new Error("此录音已结束，请重新开始。");
    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.fail("浏览器语音启动超时，请检查权限或选择其他模式。");
      }, 10000);
      this.startResolve = () => {
        clearTimeout(timeout);
        resolve();
      };
      this.startReject = (error) => {
        clearTimeout(timeout);
        reject(error);
      };
      try {
        this.recognition.start();
      } catch {
        this.fail("无法启动浏览器语音识别，请选择其他模式。");
      }
    });
  }

  private result(event: RecognitionEvent): void {
    if (this.closed || this.failed) return;
    let interim = "";
    for (let index = event.resultIndex; index < event.results.length; index++) {
      const result = event.results[index],
        text = result[0]?.transcript?.trim();
      if (!text) continue;
      if (!result.isFinal) {
        interim += text;
        continue;
      }
      const id = `${this.prefix}:${this.epoch}:${index}`;
      if (this.seen.has(id)) continue;
      this.seen.add(id);
      this.pending.push({ text, id });
    }
    this.partial(interim);
    if (this.pending.length > 20) {
      this.fail(
        "课堂文字保存跟不上识别速度，已停止浏览器录音。请复制未保存文字后重试。",
      );
      return;
    }
    this.drainPending();
  }

  private drainPending(): void {
    if (this.drain || !this.pending.length || this.failed) return;
    this.drain = this.savePending().finally(() => {
      this.drain = null;
      // A final result can arrive between the last save and promise settlement.
      this.drainPending();
    });
  }

  private async savePending(): Promise<void> {
    while (this.pending.length && !this.failed) {
      const item = this.pending[0];
      try {
        await this.save(item.text, item.id);
        this.pending.shift();
      } catch {
        this.fail(
          "课堂文字暂时无法保存，浏览器录音已停止。请复制未保存文字后检查连接。",
        );
      }
    }
  }

  private fail(message: string): void {
    if (this.failed || this.closed) return;
    this.failed = true;
    if (this.restart) clearTimeout(this.restart);
    this.startReject?.(new Error(message));
    this.startResolve = this.startReject = null;
    this.recognition.abort();
    const unsaved = this.pending.map((item) => item.text).join("\n");
    if (unsaved) this.partial(unsaved);
    this.error(message);
  }

  async stop(): Promise<void> {
    if (this.closed) return;
    this.stopping = true;
    this.startReject?.(new Error("浏览器录音启动已取消。"));
    this.startResolve = this.startReject = null;
    if (this.restart) clearTimeout(this.restart);
    await new Promise<void>((resolve) => {
      const timer = setTimeout(() => {
        this.recognition.abort();
        resolve();
      }, 2000);
      this.ended = () => {
        clearTimeout(timer);
        resolve();
      };
      try {
        this.recognition.stop();
      } catch {
        clearTimeout(timer);
        resolve();
      }
    });
    this.closed = true;
    while (this.drain) await this.drain;
    if (this.pending.length)
      throw new Error("仍有识别文字未保存，请先复制界面中的临时文字。");
  }

  unsaved(): string {
    return this.pending.map((item) => item.text).join("\n");
  }
}
