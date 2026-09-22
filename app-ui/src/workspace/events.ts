import type { Connection, Job, ServerEvent } from "./domain";

export type ConnectionStatus =
  "connecting" | "online" | "offline" | "unauthorized";

export class EventConnection {
  private socket: WebSocket | null = null;
  private retry: ReturnType<typeof setTimeout> | null = null;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private stopped = true;
  private attempts = 0;
  private lastMessage = 0;

  constructor(
    private connection: Connection,
    private onEvent: (event: ServerEvent) => void,
    private onStatus: (status: ConnectionStatus) => void,
    private factory: (url: string) => WebSocket = (url) => new WebSocket(url),
  ) {}

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.connect();
  }
  stop(): void {
    this.stopped = true;
    if (this.retry) clearTimeout(this.retry);
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.retry = this.heartbeat = null;
    const socket = this.socket;
    this.socket = null;
    socket?.close(1000);
  }

  private connect(): void {
    if (this.stopped || this.socket) return;
    this.onStatus("connecting");
    const socket = this.factory(
      `${this.connection.baseUrl.replace(/^http:/, "ws:")}/api/v2/events`,
    );
    this.socket = socket;
    const current = () => !this.stopped && this.socket === socket;
    socket.onopen = () => {
      if (current())
        socket.send(
          JSON.stringify({ type: "auth", token: this.connection.token }),
        );
    };
    socket.onmessage = (message) => {
      if (!current()) return;
      this.lastMessage = Date.now();
      try {
        const event = JSON.parse(message.data) as ServerEvent;
        if (
          typeof event.type !== "string" ||
          typeof event.data !== "object" ||
          event.data === null
        )
          throw new Error("Invalid event");
        if (event.type === "snapshot") {
          this.attempts = 0;
          this.onStatus("online");
          if (this.heartbeat) clearInterval(this.heartbeat);
          this.heartbeat = setInterval(() => {
            if (!current()) return;
            if (Date.now() - this.lastMessage > 45000) socket.close();
            else socket.send("ping");
          }, 20000);
        }
        if (event.type !== "pong") this.onEvent(event);
      } catch {
        this.onEvent({ type: "resync_required", data: {} });
      }
    };
    socket.onerror = () => {
      if (current()) this.onStatus("offline");
    };
    socket.onclose = (event) => {
      if (!current()) return;
      this.socket = null;
      if (this.heartbeat) clearInterval(this.heartbeat);
      this.heartbeat = null;
      if (event.code === 1008) {
        this.onStatus("unauthorized");
        return;
      }
      this.onStatus("offline");
      this.retry = setTimeout(
        () => {
          this.retry = null;
          this.connect();
        },
        Math.min(10000, 500 * 2 ** this.attempts++),
      );
    };
  }
}

export function applyDelta(
  job: Job,
  data: Record<string, unknown>,
): Job | null {
  if (["completed", "failed", "cancelled"].includes(job.status)) return job;
  if (typeof data.text !== "string" || typeof data.offset !== "number")
    return null;
  // Python offsets count Unicode code points; JavaScript string.length counts UTF-16 units.
  const length = Array.from(job.markdown).length;
  if (data.offset < length)
    return data.offset + Array.from(data.text).length <= length ? job : null;
  if (data.offset > length) return null;
  return {
    ...job,
    status: "running",
    markdown: job.markdown + data.text,
    stage: "正在生成",
    first_token_ms:
      typeof data.first_token_ms === "number"
        ? data.first_token_ms
        : job.first_token_ms,
  };
}

export function mergeJob(current: Job | undefined, incoming: Job): Job {
  if (!current) return incoming;
  const terminal = (job: Job) =>
    ["completed", "failed", "cancelled"].includes(job.status);
  if (terminal(incoming)) return incoming;
  if (terminal(current)) return current;
  return current.markdown.length > incoming.markdown.length
    ? current
    : incoming;
}
