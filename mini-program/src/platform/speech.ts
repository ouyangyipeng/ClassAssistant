import { speechPresets, type SpeechRegion } from "../core/providers";
import { toHex } from "../core/phoneCrypto";
import { requireMobileByok, secureBytes } from "./wechat";

export interface Recognition {
  text: string;
  sourceId: string;
  final: boolean;
}
export interface AudioSink {
  feed(pcm: ArrayBuffer): Promise<void>;
  finish(): Promise<void>;
  close(): void;
}
interface Deferred {
  promise: Promise<void>;
  resolve(): void;
  reject(error: Error): void;
}
function deferred(): Deferred {
  let resolve!: () => void, reject!: (error: Error) => void;
  const promise = new Promise<void>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  void promise.catch(() => undefined);
  return { promise, resolve, reject };
}
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("语音响应格式无效");
  return value as Record<string, unknown>;
}

export class DashSpeech implements AudioSink {
  private socket: WechatMiniprogram.SocketTask | null = null;
  private taskId = "";
  private ready = deferred();
  private finished = deferred();
  private tail: Promise<void> = Promise.resolve();
  private pendingBytes = 0;
  private closed = false;
  private finishing = false;
  private finishSent = false;
  private completed = false;
  private started = false;
  private finalIds = new Map<number, string>();

  constructor(
    private emit: (result: Recognition) => void,
    private failure: (message: string) => void,
  ) {}

  async start(region: SpeechRegion, model: string, key: string): Promise<void> {
    requireMobileByok();
    if (!key.trim() || key.length > 4096 || /[\r\n]/.test(key))
      throw new Error("请先填写有效的语音 API Key");
    if (
      !Object.hasOwn(speechPresets, region) ||
      !model.trim() ||
      model.length > 200
    )
      throw new Error("语音模型配置无效");
    this.taskId = toHex(await secureBytes(16));
    if (this.closed) throw new Error("语音连接已取消");
    const timer = setTimeout(
      () => this.fail("语音连接超时，请检查网络与服务配置"),
      12000,
    );
    try {
      this.socket = wx.connectSocket({
        url: speechPresets[region].url,
        header: { Authorization: `Bearer ${key.trim()}` },
        timeout: 10000,
        fail: () => this.fail("语音服务连接失败，请检查网络与凭据"),
      });
      this.socket.onOpen(() => {
        void this.send(
          JSON.stringify({
            header: {
              action: "run-task",
              task_id: this.taskId,
              streaming: "duplex",
            },
            payload: {
              task_group: "audio",
              task: "asr",
              function: "recognition",
              model: model.trim(),
              parameters: {
                format: "pcm",
                sample_rate: 16000,
                semantic_punctuation_enabled: false,
                max_sentence_silence: 800,
                heartbeat: true,
              },
              input: {},
            },
          }),
        ).catch(() => this.fail("无法启动语音服务，请重试"));
      });
      this.socket.onMessage((event) => this.message(event.data));
      this.socket.onError(() =>
        this.fail("语音连接发生错误，请检查网络、凭据与额度"),
      );
      this.socket.onClose(() => {
        if (!this.closed && !this.completed)
          this.fail("语音连接提前断开，最后一句可能不完整");
      });
      await this.ready.promise;
    } catch (error) {
      this.close();
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  private message(data: string | ArrayBuffer): void {
    if (this.closed) return;
    try {
      if (typeof data !== "string" || data.length > 1024 * 1024)
        throw new Error("语音响应格式无效");
      const message = record(JSON.parse(data)),
        header = record(message.header);
      if (header.task_id !== this.taskId)
        throw new Error("语音响应不属于当前课堂");
      if (header.event === "task-failed") {
        this.fail("语音服务拒绝请求，请检查 Key、模型、地区与额度");
        return;
      }
      if (header.event === "task-started") {
        this.started = true;
        this.ready.resolve();
        return;
      }
      if (!this.started) throw new Error("语音响应顺序无效");
      if (this.completed) throw new Error("语音任务已经结束");
      if (header.event === "task-finished") {
        if (!this.finishSent) throw new Error("语音连接提前结束");
        this.completed = true;
        this.finished.resolve();
        return;
      }
      if (header.event !== "result-generated") return;
      const sentence = record(record(record(message.payload).output).sentence);
      if (sentence.heartbeat === true || sentence.text === "") return;
      if (
        typeof sentence.text !== "string" ||
        Array.from(sentence.text).length > 8000 ||
        typeof sentence.sentence_id !== "number" ||
        !Number.isInteger(sentence.sentence_id) ||
        sentence.sentence_id < 1
      )
        throw new Error("语音响应格式无效");
      const text = sentence.text.trim(),
        id = sentence.sentence_id,
        final = sentence.sentence_end === true;
      if (!text) return;
      if (this.finalIds.has(id)) {
        if (final && this.finalIds.get(id) !== text)
          throw new Error("语音服务重复片段内容不一致");
        return;
      }
      if (final) {
        if (this.finalIds.size >= 10000)
          throw new Error("本次录音片段过多，请暂停后继续");
        this.finalIds.set(id, text);
      }
      this.emit({ text, sourceId: `${this.taskId}:${id}`, final });
    } catch {
      this.fail("语音响应格式或顺序无效，已暂停以保护课堂记录");
    }
  }

  feed(pcm: ArrayBuffer): Promise<void> {
    if (this.closed || this.finishing || !this.started)
      return Promise.reject(new Error("语音连接未就绪"));
    if (
      !pcm.byteLength ||
      pcm.byteLength % 2 ||
      this.pendingBytes + pcm.byteLength > 320000
    ) {
      this.fail("语音发送积压或格式无效，请检查网络后继续");
      return Promise.reject(new Error("语音发送队列已停止"));
    }
    this.pendingBytes += pcm.byteLength;
    const snapshot = pcm.slice(0);
    const result = this.tail
      .then(() => this.send(snapshot))
      .finally(() => {
        this.pendingBytes -= pcm.byteLength;
      });
    this.tail = result;
    void result.catch(() => this.fail("语音发送失败，最后一段可能不完整"));
    return result;
  }

  private send(data: string | ArrayBuffer): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!this.socket || this.closed) {
        reject(new Error("语音连接已关闭"));
        return;
      }
      const timer = setTimeout(() => reject(new Error("语音发送超时")), 5000);
      this.socket.send({
        data,
        success() {
          clearTimeout(timer);
          resolve();
        },
        fail() {
          clearTimeout(timer);
          reject(new Error("语音发送失败"));
        },
      });
    });
  }

  async finish(): Promise<void> {
    if (this.closed) throw new Error("语音连接已中断，最后一句可能不完整");
    this.finishing = true;
    const timer = setTimeout(
      () => this.fail("等待语音末句超时，最后一句可能不完整"),
      15000,
    );
    try {
      await this.tail;
      this.finishSent = true;
      await this.send(
        JSON.stringify({
          header: {
            action: "finish-task",
            task_id: this.taskId,
            streaming: "duplex",
          },
          payload: { input: {} },
        }),
      );
      await this.finished.promise;
    } finally {
      clearTimeout(timer);
      this.close();
    }
  }

  private fail(message: string): void {
    if (this.closed) return;
    this.ready.reject(new Error(message));
    this.finished.reject(new Error(message));
    this.close();
    this.failure(message);
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;
    this.ready.reject(new Error("语音连接已关闭"));
    this.finished.reject(new Error("语音连接已关闭"));
    this.socket?.close({ code: 1000, reason: "ClassFox stopped" });
  }
}
