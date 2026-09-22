import { Client } from "./client";
import type {
  Alert,
  Credentials,
  Entry,
  Installation,
  Job,
  Material,
  ModelInfo,
  Note,
  Preferences,
  ServerEvent,
  Session,
  Source,
  Status,
} from "./domain";
import {
  applyDelta,
  EventConnection,
  mergeJob,
  type ConnectionStatus,
} from "./events";

export interface WorkspaceState {
  connection: ConnectionStatus;
  loaded: boolean;
  error: string | null;
  busy: boolean;
  current: Session | null;
  source: Source;
  sessions: Session[];
  selectedId: string | null;
  entries: Entry[];
  notes: Note[];
  jobs: Job[];
  materials: Material[];
  models: ModelInfo[];
  settings: Preferences | null;
  credentials: Credentials | null;
  credentialError: string | null;
  alert: Alert | null;
  partial: string;
  level: number;
  stopping: boolean;
  selectionLoading: boolean;
  unsaved: string | null;
  moreSessions: boolean;
}

const initial: WorkspaceState = {
  connection: "connecting",
  loaded: false,
  error: null,
  busy: false,
  current: null,
  source: "text",
  sessions: [],
  selectedId: null,
  entries: [],
  notes: [],
  jobs: [],
  materials: [],
  models: [],
  settings: null,
  credentials: null,
  credentialError: null,
  alert: null,
  partial: "",
  level: 0,
  stopping: false,
  selectionLoading: false,
  unsaved: null,
  moreSessions: false,
};

function upsert<T extends { id: string | number }>(list: T[], value: T): T[] {
  return list.some((item) => item.id === value.id)
    ? list.map((item) => (item.id === value.id ? value : item))
    : [value, ...list];
}

export class WorkspaceStore {
  private state: WorkspaceState = { ...initial };
  private listeners = new Set<() => void>();
  private events: EventConnection;
  private generation = 0;
  private selectionVersion = 0;
  private controller: AbortController | null = null;
  private refreshing: Promise<void> | null = null;
  private sessionLimit = 100;
  private statusRevision = 0;
  private modelRevision = 0;
  readonly getSnapshot = () => this.state;
  readonly subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  constructor(readonly api: Client) {
    this.events = new EventConnection(
      api.connection,
      (event) => this.onEvent(event),
      (connection) => this.patch({ connection }),
    );
  }
  patch(update: Partial<WorkspaceState>): void {
    this.state = { ...this.state, ...update };
    this.listeners.forEach((listener) => listener());
  }
  report(error: unknown): void {
    this.patch({
      error: error instanceof Error ? error.message : "操作未完成，请重试",
    });
  }

  async start(): Promise<void> {
    const generation = ++this.generation;
    this.controller = new AbortController();
    try {
      await this.refresh();
      if (generation === this.generation) this.events.start();
    } catch (error) {
      if (generation === this.generation) this.report(error);
    }
  }
  stop(): void {
    this.generation++;
    this.selectionVersion++;
    this.controller?.abort();
    this.events.stop();
    this.refreshing = null;
  }

  async refresh(): Promise<void> {
    if (this.refreshing) return this.refreshing;
    const refreshing = this.loadOverview();
    this.refreshing = refreshing;
    try {
      await refreshing;
    } finally {
      if (this.refreshing === refreshing) this.refreshing = null;
    }
  }

  private async loadOverview(): Promise<void> {
    const signal = this.controller?.signal;
    const statusRevision = this.statusRevision,
      modelRevision = this.modelRevision;
    const [status, sessions, settings, materials, models] = await Promise.all([
      this.api.request<Status>("/status", { signal }),
      this.loadSessions(signal),
      this.api.request<Preferences>("/settings", { signal }),
      this.api.request<Material[]>("/materials", { signal }),
      this.api.request<ModelInfo[]>("/models", { signal }),
    ]);
    if (signal?.aborted) return;
    const selectedId =
      this.state.selectedId ??
      status.session?.id ??
      sessions.items[0]?.id ??
      null;
    const sessionUpdates =
      statusRevision === this.statusRevision
        ? sessions.items
        : [
            ...new Map(
              [...sessions.items, ...this.state.sessions].map((session) => [
                session.id,
                session,
              ]),
            ).values(),
          ].sort((a, b) => b.created_at.localeCompare(a.created_at));
    this.patch({
      ...(statusRevision === this.statusRevision
        ? { current: status.session, source: status.source }
        : {}),
      sessions: sessionUpdates,
      moreSessions: sessions.more,
      settings,
      materials,
      models:
        modelRevision === this.modelRevision
          ? models
          : models.map(
              (model) =>
                this.state.models.find(
                  (current) => current.model.id === model.model.id,
                ) ?? model,
            ),
      loaded: true,
      selectedId,
    });
    await Promise.all([
      this.loadSelection(selectedId),
      this.refreshCredentials(),
    ]);
  }

  private async loadSessions(
    signal?: AbortSignal,
  ): Promise<{ items: Session[]; more: boolean }> {
    const items: Session[] = [];
    let page: Session[] = [];
    while (items.length < this.sessionLimit) {
      page = await this.api.request<Session[]>(
        `/sessions?limit=100&offset=${items.length}`,
        { signal },
      );
      items.push(...page);
      if (page.length < 100) break;
    }
    return { items, more: page.length === 100 };
  }

  async moreHistory(): Promise<void> {
    await this.action(async () => {
      this.sessionLimit += 100;
      await this.refresh();
    });
  }

  async refreshCredentials(): Promise<void> {
    const signal = this.controller?.signal;
    try {
      const credentials = await this.api.request<Credentials>("/credentials", {
        signal,
      });
      if (signal?.aborted) return;
      this.patch({ credentials, credentialError: null });
    } catch (error) {
      if (signal?.aborted) return;
      this.patch({
        credentialError:
          error instanceof Error ? error.message : "无法读取凭据状态",
      });
    }
  }

  async select(selectedId: string): Promise<void> {
    this.patch({
      selectedId,
      entries: [],
      notes: [],
      jobs: [],
      partial: "",
      selectionLoading: true,
    });
    try {
      await this.loadSelection(selectedId);
    } catch (error) {
      this.report(error);
    }
  }

  async loadSelection(sessionId = this.state.selectedId): Promise<void> {
    if (!sessionId) return;
    const version = ++this.selectionVersion;
    const signal = this.controller?.signal;
    try {
      const entries: Entry[] = [];
      let after = 0;
      while (true) {
        const page = await this.api.request<Entry[]>(
          `/sessions/${sessionId}/entries?after_id=${after}`,
          { signal },
        );
        entries.push(...page);
        if (page.length < 1000) break;
        after = page[page.length - 1].id;
      }
      const [notes, jobs] = await Promise.all([
        this.api.request<Note[]>(`/sessions/${sessionId}/summaries`, {
          signal,
        }),
        this.api.request<Job[]>(`/assistant?session_id=${sessionId}`, {
          signal,
        }),
      ]);
      if (
        version !== this.selectionVersion ||
        sessionId !== this.state.selectedId ||
        signal?.aborted
      )
        return;
      const combined = new Map(entries.map((entry) => [entry.id, entry]));
      this.state.entries.forEach((entry) => {
        if (entry.session_id === sessionId) combined.set(entry.id, entry);
      });
      // Events arriving during the snapshot query may already have advanced a running answer.
      const mergedJobs = new Map(
        this.state.jobs
          .filter((job) => job.session_id === sessionId)
          .map((job) => [job.id, job]),
      );
      jobs.forEach((job) =>
        mergedJobs.set(job.id, mergeJob(mergedJobs.get(job.id), job)),
      );
      this.patch({
        entries: [...combined.values()].sort((a, b) => a.id - b.id),
        notes,
        jobs: [...mergedJobs.values()],
        selectionLoading: false,
      });
    } finally {
      if (
        version === this.selectionVersion &&
        sessionId === this.state.selectedId &&
        !signal?.aborted
      )
        this.patch({ selectionLoading: false });
    }
  }

  private session(session: Session): void {
    this.statusRevision++;
    const active = !["stopped", "interrupted"].includes(session.status);
    this.patch({
      sessions: upsert(this.state.sessions, session),
      current: active
        ? session
        : this.state.current?.id === session.id
          ? null
          : this.state.current,
      selectedId: this.state.selectedId ?? session.id,
      stopping: false,
      partial: "",
      level: session.status === "recording" ? this.state.level : 0,
    });
  }

  private onEvent(event: ServerEvent): void {
    const data = event.data;
    switch (event.type) {
      case "snapshot": {
        this.statusRevision++;
        const status = data as unknown as Status;
        this.patch({
          current: status.session,
          source: status.source,
          stopping: false,
        });
        if (status.session) this.session(status.session);
        void this.refresh().catch((error) => this.report(error));
        break;
      }
      case "resync_required":
        void this.refresh().catch((error) => this.report(error));
        break;
      case "session":
        this.session(data as unknown as Session);
        break;
      case "transcript": {
        const entry = data as unknown as Entry;
        if (entry.session_id === this.state.selectedId)
          this.patch({
            entries: upsert(this.state.entries, entry).sort(
              (a, b) => a.id - b.id,
            ),
            partial: "",
          });
        break;
      }
      case "alert":
        this.patch({
          alert: { ...data, session_id: event.session_id } as Alert,
        });
        break;
      case "audio.partial":
        if (event.session_id === this.state.selectedId)
          this.patch({ partial: String(data.text ?? "") });
        break;
      case "audio.level":
        this.patch({ level: typeof data.peak === "number" ? data.peak : 0 });
        break;
      case "audio.stopping":
        this.patch({ stopping: true });
        break;
      case "audio.error":
        this.patch({
          error: String(data.message ?? "语音识别已停止"),
          stopping: false,
          level: 0,
          partial: "",
        });
        break;
      case "summary_deferred":
        this.patch({ error: String(data.message) });
        break;
      case "model.installation": {
        this.modelRevision++;
        const installation = data as unknown as Installation;
        this.patch({
          models: this.state.models.map((model) =>
            model.model.id === installation.model_id
              ? { ...model, installation }
              : model,
          ),
        });
        break;
      }
      case "assistant.delta": {
        if (event.session_id !== this.state.selectedId) break;
        const job = this.state.jobs.find((job) => job.id === data.id);
        const updated = job ? applyDelta(job, data) : null;
        if (updated) this.patch({ jobs: upsert(this.state.jobs, updated) });
        else if (typeof data.id === "string") void this.fetchJob(data.id);
        break;
      }
      case "assistant.progress":
      case "assistant.finished": {
        const job = data as unknown as Job;
        if (job.session_id === this.state.selectedId) {
          this.patch({
            jobs: upsert(
              this.state.jobs,
              mergeJob(
                this.state.jobs.find((item) => item.id === job.id),
                job,
              ),
            ),
          });
          if (job.summary_id)
            void this.loadSelection().catch((error) => this.report(error));
        }
        break;
      }
    }
  }

  async fetchJob(id: string): Promise<void> {
    try {
      const job = await this.api.request<Job>(`/assistant/${id}`);
      if (job.session_id === this.state.selectedId)
        this.patch({
          jobs: upsert(
            this.state.jobs,
            mergeJob(
              this.state.jobs.find((item) => item.id === job.id),
              job,
            ),
          ),
        });
    } catch (error) {
      this.report(error);
    }
  }

  async action<T>(operation: () => Promise<T>): Promise<T | undefined> {
    if (this.state.busy) return undefined;
    this.patch({ busy: true, error: null });
    try {
      return await operation();
    } catch (error) {
      this.report(error);
      return undefined;
    } finally {
      this.patch({ busy: false });
    }
  }
}
