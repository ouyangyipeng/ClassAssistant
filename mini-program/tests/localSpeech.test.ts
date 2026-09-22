import { afterEach, expect, it, vi } from "vitest";
import { LocalSpeech } from "../src/platform/localSpeech";
import type { PhoneClient } from "../src/core/phoneClient";

afterEach(() => vi.unstubAllGlobals());
it("sends ordered immutable bounded PCM segments and flushes the remainder once", async () => {
  vi.stubGlobal("wx", {
    arrayBufferToBase64: (data: ArrayBuffer) =>
      Buffer.from(data).toString("base64"),
  });
  const requests: Array<{ source_id: string; pcm: string }> = [],
    emitted: string[] = [];
  const client = {
    async request(value: { source_id: string; pcm: string }) {
      requests.push(value);
      return {
        entry: {
          id: requests.length,
          session_id: "session",
          text: `原文${requests.length}`,
          created_at: "2026-09-22T01:00:00Z",
        },
      };
    },
  } as unknown as PhoneClient;
  const sink = new LocalSpeech(client, "session", "recording", (entry) =>
    emitted.push(entry.text),
  );
  const pcm = new Uint8Array(300000).fill(3);
  const fed = sink.feed(pcm.buffer);
  pcm.fill(9);
  await fed;
  await sink.finish();
  sink.close();
  expect(
    requests.map((value) => Buffer.from(value.pcm, "base64").length),
  ).toEqual([256000, 44000]);
  expect(requests.map((value) => value.source_id)).toEqual([
    "recording:1",
    "recording:2",
  ]);
  expect(Buffer.from(requests[0].pcm, "base64")[0]).toBe(3);
  expect(Buffer.from(requests[1].pcm, "base64")[0]).toBe(3);
  expect(emitted).toEqual(["原文1", "原文2"]);
});
it("stops accepting audio when the computer queue is full", async () => {
  vi.stubGlobal("wx", {
    arrayBufferToBase64: (data: ArrayBuffer) =>
      Buffer.from(data).toString("base64"),
  });
  const client = {
    request: () => new Promise(() => undefined),
  } as unknown as PhoneClient;
  const sink = new LocalSpeech(client, "session", "recording", () => undefined);
  void sink.feed(new ArrayBuffer(256000));
  void sink.feed(new ArrayBuffer(256000));
  void sink.feed(new ArrayBuffer(256000));
  await expect(sink.feed(new ArrayBuffer(2))).rejects.toThrow("过慢");
  await expect(sink.finish()).rejects.toThrow("中断");
});
