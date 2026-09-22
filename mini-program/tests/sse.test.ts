import { expect, it } from "vitest";
import { CompletionStream } from "../src/core/sse";
import { utf8 } from "../src/core/phoneCrypto";

function event(text: string, reason: string | null = null) {
  return `data: ${JSON.stringify({ choices: [{ delta: { content: text }, finish_reason: reason }] })}\r\n\r\n`;
}
it("preserves Chinese and emoji across every byte boundary", () => {
  const pieces: string[] = [],
    stream = new CompletionStream((text) => pieces.push(text));
  const bytes = utf8(event("课堂 🦊") + event("", "stop") + "data: [DONE]\n\n");
  for (const byte of bytes) stream.feed(new Uint8Array([byte]));
  stream.finish();
  expect(pieces.join("")).toBe("课堂 🦊");
});
it("never treats truncated or partial generation as a completed note", () => {
  const partial = new CompletionStream(() => undefined);
  partial.feed(utf8(event("部分文字")));
  expect(() => partial.finish()).toThrow("提前结束");
  expect(() => partial.feed(utf8(event("", "length")))).toThrow("尚未完整");
});
