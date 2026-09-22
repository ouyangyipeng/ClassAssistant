import { BrowserSpeech } from "./browserSpeech";
import type { Session, Source, Status } from "./domain";
import { WorkspaceStore } from "./store";

export class CaptureController {
  private browser: BrowserSpeech | null = null;
  private browserSessionId: string | null = null;
  private urgentStop: Promise<void> | null = null;
  constructor(private store: WorkspaceStore) {}

  private create(sessionId: string): BrowserSpeech {
    const store = this.store;
    return new BrowserSpeech(
      store.getSnapshot().settings?.asr.language ?? "zh-CN",
      (text, source_id) =>
        store.api.post(`/sessions/${sessionId}/entries`, { text, source_id }),
      (partial) => store.patch({ partial }),
      (message) => {
        store.patch({
          error: message,
          unsaved: this.browser?.unsaved() || null,
        });
        void store.api
          .post(`/sessions/${sessionId}/pause`)
          .catch((error) => store.report(error));
      },
    );
  }

  async start(
    name: string,
    source: Source,
    material_id: string | null,
  ): Promise<void> {
    const store = this.store;
    try {
      const session = await store.api.post<Session>(
        "/sessions",
        { course_name: name, source, material_id },
        120000,
      );
      store.patch({ current: session, source });
      if (source === "browser") {
        try {
          this.browserSessionId = session.id;
          this.browser = this.create(session.id);
          await this.browser.start();
        } catch (error) {
          await store.api.post(`/sessions/${session.id}/pause`);
          throw error;
        }
      }
      await store.select(session.id);
    } finally {
      await store.refresh();
    }
  }

  async stopBrowser(): Promise<void> {
    const active = this.browser;
    this.browser = null;
    this.browserSessionId = null;
    if (!active) return;
    try {
      await active.stop();
    } catch (error) {
      this.store.patch({ unsaved: active.unsaved() || null });
      this.store.report(error);
    }
  }

  async synchronize(): Promise<void> {
    const { current } = this.store.getSnapshot();
    if (
      this.browser &&
      (current?.id !== this.browserSessionId ||
        !["starting", "recording"].includes(current.status))
    ) {
      const browser = this.browser,
        id = this.browserSessionId;
      // An older WebSocket pause can arrive after the HTTP resume response.
      const status = await this.store.api.request<Status>("/status");
      if (browser !== this.browser || id !== this.browserSessionId) return;
      if (
        status.session?.id === id &&
        status.session.status === "recording" &&
        status.source === "browser"
      )
        return;
      await this.stopBrowser();
    }
  }

  async control(action: "pause" | "resume" | "stop"): Promise<void> {
    const store = this.store,
      state = store.getSnapshot(),
      current = state.current;
    if (!current) return;
    if (action !== "resume" && current.status === "starting") {
      if (this.urgentStop) return this.urgentStop;
      this.urgentStop = (async () => {
        store.patch({ stopping: true });
        try {
          await this.stopBrowser();
          await store.api.post(
            `/sessions/${current.id}/${action}`,
            undefined,
            15000,
          );
        } catch (error) {
          store.report(error);
        } finally {
          try {
            await store.refresh();
          } finally {
            store.patch({ stopping: false });
          }
        }
      })().finally(() => {
        this.urgentStop = null;
      });
      return this.urgentStop;
    }
    await store.action(async () => {
      if (action !== "resume") await this.stopBrowser();
      try {
        const updated = await store.api.post<Session>(
          `/sessions/${current.id}/${action}`,
          undefined,
          120000,
        );
        store.patch({ current: action === "stop" ? null : updated });
        if (action === "resume" && state.source === "browser") {
          try {
            this.browserSessionId = current.id;
            this.browser = this.create(current.id);
            await this.browser.start();
          } catch (error) {
            await store.api.post(`/sessions/${current.id}/pause`);
            throw error;
          }
        }
      } finally {
        await store.refresh();
      }
    });
  }

  async recoverBrowser(): Promise<void> {
    const { current, source } = this.store.getSnapshot();
    if (
      current?.status === "recording" &&
      source === "browser" &&
      !this.browser
    ) {
      await this.store.api.post(`/sessions/${current.id}/pause`);
      await this.store.refresh();
      this.store.report(
        new Error(
          "页面已重新打开，浏览器录音已暂停。点击继续可重新授权并恢复。",
        ),
      );
    }
  }
}

export async function nativeWindow(
  action: "minimize" | "close" | "toggleMaximize",
): Promise<void> {
  if (!("__TAURI_INTERNALS__" in window)) return;
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  await getCurrentWindow()[action]();
}

export async function windowMode(compact: boolean): Promise<void> {
  if (!("__TAURI_INTERNALS__" in window)) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("set_window_mode", { compact });
}
