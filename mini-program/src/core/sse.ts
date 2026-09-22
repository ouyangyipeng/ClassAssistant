import { fromUtf8 } from "./phoneCrypto";

export class CompletionStream {
  private pending: number[] = [];
  private data: string[] = [];
  private total = 0;
  private count = 0;
  private stopped = false;
  private done = false;

  constructor(private emit: (text: string) => void) {}

  feed(chunk: Uint8Array): void {
    this.total += chunk.length;
    if (this.total > 1024 * 1024) throw new Error("模型响应过大，已停止生成");
    for (const byte of chunk) {
      if (byte !== 10) {
        this.pending.push(byte);
        if (this.pending.length > 128 * 1024)
          throw new Error("模型响应格式无效");
        continue;
      }
      const line = fromUtf8(new Uint8Array(this.pending)).replace(/\r$/, "");
      this.pending = [];
      if (line === "") {
        this.event();
        continue;
      }
      if (line.startsWith("data:"))
        this.data.push(line.slice(5).replace(/^ /, ""));
    }
  }

  private event(): void {
    if (!this.data.length) return;
    const data = this.data.join("\n");
    this.data = [];
    if (data === "[DONE]") {
      this.done = true;
      return;
    }
    if (this.done) throw new Error("模型响应顺序无效");
    const value: unknown = JSON.parse(data);
    if (
      !value ||
      typeof value !== "object" ||
      !("choices" in value) ||
      !Array.isArray(value.choices)
    )
      throw new Error("模型返回格式无效");
    if (value.choices.length === 0) return;
    const choice: unknown = value.choices[0];
    if (!choice || typeof choice !== "object")
      throw new Error("模型返回格式无效");
    const reason: unknown =
      "finish_reason" in choice ? choice.finish_reason : null;
    if (reason && reason !== "stop")
      throw new Error("回答尚未完整生成，请缩短问题或换用其他模型");
    const delta: unknown = "delta" in choice ? choice.delta : null;
    const text: unknown =
      delta && typeof delta === "object" && "content" in delta
        ? delta.content
        : null;
    if (typeof text === "string" && text) {
      this.count += Array.from(text).length;
      if (this.count > 64000 || this.stopped)
        throw new Error("模型响应过长或顺序无效");
      this.emit(text);
    }
    if (reason === "stop") this.stopped = true;
  }

  finish(): void {
    if (
      !this.stopped ||
      !this.done ||
      !this.count ||
      this.pending.length ||
      this.data.length
    )
      throw new Error("模型连接提前结束；原文仍保留，可重试生成");
  }
}
