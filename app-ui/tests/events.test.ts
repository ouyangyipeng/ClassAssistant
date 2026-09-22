import { afterEach, describe, expect, it, vi } from "vitest";
import { applyDelta, EventConnection, mergeJob } from "../src/workspace/events";
import type { Job } from "../src/workspace/domain";

const job: Job = {
  id: "job",
  session_id: "class",
  kind: "rescue",
  status: "running",
  created_at: "2026-09-22T00:00:00Z",
  markdown: "课堂🦊",
  stage: "正在生成",
  first_token_ms: 100,
  total_ms: null,
  summary_id: null,
  error_code: null,
  error_message: null,
  through_entry_id: 1,
};

class FakeSocket {
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  send = vi.fn();
  close = vi.fn((code = 1000) => this.onclose?.({ code }));
  event(value: unknown) {
    this.onmessage?.({ data: JSON.stringify(value) });
  }
}

afterEach(() => vi.useRealTimers());

describe("stream recovery", () => {
  it("uses Python Unicode offsets and does not duplicate chunks", () => {
    const next = applyDelta(job, {
      offset: 3,
      text: "：答案",
      first_token_ms: 100,
    });
    expect(next?.markdown).toBe("课堂🦊：答案");
    expect(applyDelta(next!, { offset: 3, text: "：答案" })).toBe(next);
    expect(applyDelta(job, { offset: 9, text: "遗漏" })).toBeNull();
    expect(applyDelta(job, { offset: 2, text: "🦊重叠" })).toBeNull();
  });
  it("does not restore cancelled jobs or truncate an answer with an older snapshot", () => {
    const cancelled = { ...job, status: "cancelled" as const };
    expect(mergeJob(cancelled, job)).toBe(cancelled);
    expect(applyDelta(cancelled, { offset: 3, text: "迟到" })).toBe(cancelled);
    expect(mergeJob(job, { ...job, markdown: "" })).toBe(job);
    expect(mergeJob(job, { ...job, status: "completed" })).toHaveProperty(
      "status",
      "completed",
    );
  });
  it("authenticates in the first frame and cancels reconnect on disposal", () => {
    vi.useFakeTimers();
    const sockets: FakeSocket[] = [];
    const handler = vi.fn(),
      status = vi.fn();
    const connection = new EventConnection(
      { baseUrl: "http://127.0.0.1:12345", token: "synthetic" },
      handler,
      status,
      () => {
        const socket = new FakeSocket();
        sockets.push(socket);
        return socket as unknown as WebSocket;
      },
    );
    connection.start();
    connection.start();
    expect(sockets).toHaveLength(1);
    sockets[0].onopen?.();
    expect(sockets[0].send).toHaveBeenCalledWith(
      '{"type":"auth","token":"synthetic"}',
    );
    sockets[0].event({ type: "snapshot", data: {} });
    expect(status).toHaveBeenLastCalledWith("online");
    sockets[0].close(1006);
    connection.stop();
    vi.advanceTimersByTime(60000);
    expect(sockets).toHaveLength(1);
    connection.start();
    sockets[0].event({ type: "transcript", data: {} });
    expect(handler).toHaveBeenCalledTimes(1);
    connection.stop();
  });
  it("does not loop when credentials are rejected", () => {
    vi.useFakeTimers();
    const socket = new FakeSocket(),
      factory = vi.fn(() => socket as unknown as WebSocket),
      status = vi.fn();
    const connection = new EventConnection(
      { baseUrl: "http://127.0.0.1:12345", token: "synthetic" },
      vi.fn(),
      status,
      factory,
    );
    connection.start();
    socket.close(1008);
    vi.advanceTimersByTime(60000);
    expect(factory).toHaveBeenCalledTimes(1);
    expect(status).toHaveBeenLastCalledWith("unauthorized");
    connection.stop();
  });
});
