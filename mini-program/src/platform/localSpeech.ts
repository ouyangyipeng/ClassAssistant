import type { PhoneClient } from "../core/phoneClient";
import { remoteEntry } from "../core/remote";
import type { Entry } from "../core/records";
import { binaryCodec } from "./wechat";
import type { AudioSink } from "./speech";

export class LocalSpeech implements AudioSink {
  private bytes = new Uint8Array(256000);
  private used = 0;
  private pending = 0;
  private sequence = 0;
  private closed = false;
  private finishing = false;
  private tail: Promise<void> = Promise.resolve();
  constructor(
    private client: PhoneClient,
    private sessionId: string,
    private recordingId: string,
    private emit: (entry: Entry) => void,
  ) {}

  feed(pcm: ArrayBuffer): Promise<void> {
    if (this.closed || this.finishing)
      return Promise.reject(new Error("音频连接已关闭"));
    if (
      pcm.byteLength % 2 ||
      this.pending + this.used + pcm.byteLength > 768000
    ) {
      this.close();
      return Promise.reject(new Error("电脑处理音频过慢，请暂停后重试"));
    }
    const data = new Uint8Array(pcm);
    let offset = 0;
    while (offset < data.length) {
      const size = Math.min(
        this.bytes.length - this.used,
        data.length - offset,
      );
      this.bytes.set(data.subarray(offset, offset + size), this.used);
      this.used += size;
      offset += size;
      if (this.used === this.bytes.length) this.flush();
    }
    return this.tail;
  }

  private flush(): void {
    if (!this.used) return;
    const snapshot = this.bytes.slice(0, this.used),
      source = `${this.recordingId}:${++this.sequence}`;
    this.used = 0;
    this.pending += snapshot.length;
    this.tail = this.tail
      .then(async () => {
        if (this.closed) throw new Error("音频连接已关闭");
        const result = await this.client.request({
          operation: "audio",
          session_id: this.sessionId,
          source_id: source,
          pcm: binaryCodec.toBase64(snapshot),
        });
        if (!this.closed && result.entry !== null)
          this.emit(remoteEntry(result.entry, this.sessionId));
      })
      .finally(() => {
        this.pending -= snapshot.length;
        snapshot.fill(0);
      });
    void this.tail.catch(() => undefined);
  }

  async finish(): Promise<void> {
    if (this.closed) throw new Error("音频连接已中断");
    this.finishing = true;
    this.flush();
    await this.tail;
  }

  close(): void {
    this.closed = true;
    this.bytes.fill(0);
    this.used = 0;
  }
}
