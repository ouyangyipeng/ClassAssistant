import type { Connection } from "./domain";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
  }
}

export function validateConnection(value: Connection): Connection {
  const url = new URL(value.baseUrl);
  if (
    url.protocol !== "http:" ||
    url.hostname !== "127.0.0.1" ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    !value.token
  ) {
    throw new Error("本地服务连接信息无效，请重新启动课狐");
  }
  return { baseUrl: url.origin, token: value.token };
}

export async function getConnection(): Promise<Connection> {
  if ("__TAURI_INTERNALS__" in window) {
    const { invoke } = await import("@tauri-apps/api/core");
    return validateConnection(await invoke<Connection>("backend_connection"));
  }
  const response = await fetch("/__classfox", { cache: "no-store" });
  if (!response.ok)
    throw new Error(
      "未连接本地课堂服务。开发时请使用项目的一体化启动命令，桌面端请重新打开应用。",
    );
  return validateConnection(await response.json());
}

export class Client {
  readonly connection: Connection;
  constructor(
    connection: Connection,
    private fetcher: typeof fetch = fetch,
  ) {
    this.connection = validateConnection(connection);
  }

  async request<T>(
    path: string,
    options: RequestInit & { timeout?: number; text?: boolean } = {},
  ): Promise<T> {
    const controller = new AbortController();
    const { timeout = 20000, text = false, ...init } = options;
    const cancel = () => controller.abort();
    const timer = setTimeout(cancel, timeout);
    const signal = options.signal;
    signal?.addEventListener("abort", cancel, { once: true });
    if (signal?.aborted) cancel();
    try {
      const headers = new Headers(init.headers);
      headers.set("Authorization", `Bearer ${this.connection.token}`);
      if (init.body && !(init.body instanceof FormData))
        headers.set("Content-Type", "application/json");
      const fetcher = this.fetcher;
      const response = await fetcher(
        `${this.connection.baseUrl}/api/v2${path}`,
        {
          ...init,
          headers,
          signal: controller.signal,
          redirect: "error",
          cache: "no-store",
        },
      );
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new ApiError(
          typeof error?.message === "string"
            ? error.message
            : typeof error?.detail === "string"
              ? error.detail
              : "请求未完成，请重试",
          response.status,
          error?.error ?? "request_failed",
        );
      }
      return text
        ? ((await response.text()) as T)
        : ((await response.json()) as T);
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (signal?.aborted) throw new DOMException("已取消", "AbortError");
      if (controller.signal.aborted)
        throw new ApiError(
          "等待本地服务超时，请查看课堂状态后重试",
          0,
          "timeout",
        );
      throw new ApiError(
        "无法连接本地课堂服务，请检查应用是否仍在运行",
        0,
        "disconnected",
      );
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", cancel);
    }
  }

  post<T>(path: string, body?: unknown, timeout?: number): Promise<T> {
    return this.request(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
      timeout,
    });
  }
}

export async function saveText(
  content: string,
  filename: string,
): Promise<void> {
  if ("__TAURI_INTERNALS__" in window) {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("export_text", { content, filename });
    return;
  }
  const url = URL.createObjectURL(
    new Blob([content], { type: "text/plain;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
