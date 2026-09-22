import { assistant, type AssistantKind } from "./core/assistant";
import {
  PhoneClient,
  parsePairing,
  PhoneApplicationError,
} from "./core/phoneClient";
import { toHex } from "./core/phoneCrypto";
import {
  defaultSettings,
  type MemoryCredentials,
  type MobileSettings,
} from "./core/providers";
import {
  ClassroomRepository,
  type ClassroomRecord,
  type Entry,
} from "./core/records";
import { identifier, object } from "./core/remote";
import { generate, GenerationCancelled, type Generation } from "./platform/llm";
import { LocalSpeech } from "./platform/localSpeech";
import { Recorder, requestMicrophone } from "./platform/recorder";
import { DashSpeech, type AudioSink } from "./platform/speech";
import { binaryCodec, phoneTransport, secureBytes } from "./platform/wechat";

export interface State {
  settings: MobileSettings;
  record: ClassroomRecord | null;
  capture: "idle" | "starting" | "recording" | "stopping";
  generating: boolean;
  answer: string;
  stage: string;
  interim: string;
  unsaved: Entry[];
  error: string;
  keyword: string;
  paired: boolean;
  pairingCode: string;
}
const cancelled = () => new Error("录音启动已取消");
export function message(error: unknown): string {
  return error instanceof Error ? error.message : "操作未完成，请重试";
}

export class ClassFox {
  readonly repository: ClassroomRepository;
  private state: State = {
    settings: { ...defaultSettings },
    record: null,
    capture: "idle",
    generating: false,
    answer: "",
    stage: "",
    interim: "",
    unsaved: [],
    error: "",
    keyword: "",
    paired: false,
    pairingCode: "",
  };
  private listeners = new Set<(state: State) => void>();
  private credentials: MemoryCredentials = { llm: "", speech: "" };
  private client: PhoneClient | null = null;
  private recorder: Recorder;
  private sink: AudioSink | null = null;
  private recordingEpoch = 0;
  private stopTask: Promise<void> | null = null;
  private generation: Generation | null = null;
  private generationEpoch = 0;
  private generationCancelled = false;
  private foreground = true;
  private actionBusy = false;
  private keywordTime = 0;
  private pairEpoch = 0;

  constructor() {
    this.repository = new ClassroomRepository({
      get: (key) => wx.getStorageSync(key) as unknown,
      set: (key, value) => wx.setStorageSync(key, value),
      remove: (key) => wx.removeStorageSync(key),
      keys: () => wx.getStorageInfoSync().keys,
    });
    this.recorder = new Recorder(wx.getRecorderManager(), (reason) => {
      if (reason) this.patch({ error: reason });
      if (
        this.state.capture === "recording" ||
        this.state.capture === "starting"
      )
        void this.stopRecording().catch((error: unknown) => this.report(error));
    });
    try {
      this.state.settings = this.repository.settings();
      const history = this.repository.inspect();
      for (const record of history.records) {
        if (record.status === "recording" || record.status === "paused")
          this.repository.save({ ...record, status: "interrupted" });
      }
      if (history.damaged.length)
        this.state.error = `有 ${history.damaged.length} 堂课的存储格式异常，原数据仍保留，其他课堂可正常查看`;
    } catch (error) {
      this.state.error = message(error);
    }
  }

  subscribe(listener: (state: State) => void): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => {
      this.listeners.delete(listener);
    };
  }
  get snapshot(): State {
    return this.state;
  }
  private patch(update: Partial<State>): void {
    this.state = { ...this.state, ...update };
    for (const listener of this.listeners) listener(this.state);
  }
  report(error: unknown): void {
    this.patch({ error: message(error) });
  }
  clearError(): void {
    this.patch({ error: "", keyword: "" });
  }

  configure(settings: MobileSettings, keys: MemoryCredentials): void {
    if (
      this.state.capture !== "idle" ||
      this.state.generating ||
      this.actionBusy
    )
      throw new Error("请先停止录音并等待当前操作完成，再修改设置");
    if (
      this.state.record &&
      ["recording", "paused"].includes(this.state.record.status) &&
      settings.mode !== this.state.record.mode
    )
      throw new Error("请先结束当前课堂，再切换使用方式");
    if (
      !settings.model.trim() ||
      settings.model.length > 200 ||
      !settings.speechModel.trim() ||
      settings.speechModel.length > 200 ||
      settings.keywords.length > 20 ||
      settings.keywords.some((word) => !word.trim() || word.length > 30)
    )
      throw new Error("请检查模型名称和关键词长度");
    for (const key of [keys.llm, keys.speech])
      if (key.length > 4096 || /[\r\n]/.test(key))
        throw new Error("API Key 格式无效");
    this.repository.saveSettings(settings);
    this.credentials = {
      llm:
        keys.llm.trim() ||
        (settings.llmProvider === this.state.settings.llmProvider
          ? this.credentials.llm
          : ""),
      speech:
        keys.speech.trim() ||
        (settings.speechRegion === this.state.settings.speechRegion
          ? this.credentials.speech
          : ""),
    };
    this.patch({ settings, error: "" });
  }
  clearCredentials(): void {
    if (this.state.capture !== "idle" || this.state.generating)
      throw new Error("请先停止录音和生成，再清除服务凭据");
    this.credentials = { llm: "", speech: "" };
  }
  credentialStatus(): { llm: boolean; speech: boolean } {
    return { llm: !!this.credentials.llm, speech: !!this.credentials.speech };
  }

  async pair(qr: string): Promise<void> {
    if (
      this.state.capture !== "idle" ||
      this.state.generating ||
      this.actionBusy ||
      (this.state.record &&
        ["recording", "paused"].includes(this.state.record.status))
    )
      throw new Error("请先结束当前课堂，再重新配对电脑");
    const offer = parsePairing(qr),
      epoch = ++this.pairEpoch;
    this.client?.close();
    this.client = null;
    this.patch({ paired: false, pairingCode: "", error: "" });
    const nonce = await secureBytes();
    if (epoch !== this.pairEpoch) throw new Error("配对已取消");
    const client = new PhoneClient(offer, nonce, binaryCodec, phoneTransport);
    nonce.fill(0);
    this.client = client;
    await client.hello("课狐微信小程序");
    if (epoch !== this.pairEpoch) {
      client.close();
      return;
    }
    this.patch({ pairingCode: client.verificationCode });
  }
  async confirmPair(): Promise<void> {
    const client = this.client;
    if (!client) throw new Error("请先扫描电脑上的配对二维码");
    const result = await client.request({ operation: "status" });
    if (client !== this.client || result.state !== "approved")
      throw new Error("请在电脑核对数字并批准此手机");
    this.patch({ paired: true, pairingCode: "", error: "" });
  }
  private remote(record?: ClassroomRecord): PhoneClient {
    if (
      !this.state.paired ||
      !this.client?.connected ||
      (record && record.connectionId !== this.client.connectionId)
    )
      throw new Error(
        "此课堂的电脑连接已失效，请导出已同步的原文，重新配对后开始新课堂",
      );
    return this.client;
  }

  async create(courseName: string): Promise<void> {
    if (
      this.actionBusy ||
      this.state.generating ||
      this.state.capture !== "idle"
    )
      throw new Error("请等待当前操作完成");
    if (this.state.unsaved.length)
      throw new Error("请先复制或重试保存未保存的原文");
    if (
      this.state.record &&
      ["recording", "paused"].includes(this.state.record.status)
    )
      throw new Error("请先结束当前课堂");
    const name = courseName.trim();
    if (!name || Array.from(name).length > 120)
      throw new Error("课程名称请填写 1–120 字");
    this.actionBusy = true;
    let remoteId: string | undefined, client: PhoneClient | undefined;
    try {
      const id = toHex(await secureBytes(16)),
        settings = this.state.settings;
      if (settings.mode === "desktop") {
        client = this.remote();
        remoteId = identifier(
          object(
            (await client.request({ operation: "create", course_name: name }))
              .session,
          ).id,
        );
      }
      const record: ClassroomRecord = {
        schema: 1,
        id,
        courseName: name,
        mode: settings.mode,
        status: "paused",
        createdAt: new Date().toISOString(),
        entries: [],
        notes: [],
        ...(remoteId ? { remoteId, connectionId: client!.connectionId } : {}),
      };
      this.repository.save(record);
      this.patch({
        record,
        answer: "",
        stage: "",
        error: "",
        interim: "",
        keyword: "",
      });
    } catch (error) {
      if (remoteId && client) {
        try {
          await client.request({ operation: "stop", session_id: remoteId });
        } catch {
          this.report(
            new Error(
              "手机保存失败且电脑课堂未能结束，请在电脑关闭手机入口后重试",
            ),
          );
        }
      }
      throw error;
    } finally {
      this.actionBusy = false;
    }
  }

  load(id: string): void {
    if (
      this.state.capture !== "idle" ||
      this.state.generating ||
      this.actionBusy ||
      this.state.unsaved.length ||
      (this.state.record &&
        ["recording", "paused"].includes(this.state.record.status))
    )
      throw new Error("请先保存并结束当前课堂，再查看其他课堂");
    this.patch({
      record: this.repository.load(id),
      answer: "",
      interim: "",
      stage: "",
      error: "",
      keyword: "",
    });
  }

  private updateRecord(record: ClassroomRecord): void {
    this.repository.save(record);
    this.patch({ record });
  }
  private accept(classId: string, entry: Entry): void {
    const record = this.state.record;
    if (!record || record.id !== classId) return;
    try {
      const updated = this.repository.append(record, entry);
      this.patch({ record: updated, interim: "" });
      const word = this.state.settings.keywords.find((value) =>
        entry.text.includes(value),
      );
      if (word && Date.now() - this.keywordTime > 10000) {
        this.keywordTime = Date.now();
        this.patch({ keyword: word });
        wx.vibrateShort({ type: "light", fail: () => undefined });
      }
    } catch (error) {
      if (!this.state.unsaved.some((value) => value.id === entry.id))
        this.patch({ unsaved: [...this.state.unsaved, entry] });
      this.report(error);
      void this.stopRecording().catch((failure: unknown) =>
        this.report(failure),
      );
    }
  }
  retryUnsaved(): void {
    const record = this.state.record;
    if (!record) return;
    let updated = record;
    for (const entry of this.state.unsaved)
      updated = this.repository.append(updated, entry);
    this.patch({ record: updated, unsaved: [], error: "" });
  }

  async append(text: string): Promise<void> {
    const record = this.state.record;
    if (!record || ["stopped", "interrupted"].includes(record.status))
      throw new Error("请先开始一堂新课");
    if (this.actionBusy || this.state.unsaved.length)
      throw new Error("请先完成保存，再添加文字");
    if (!text.trim() || Array.from(text).length > 8000)
      throw new Error("每次可保存 1–8000 字");
    this.actionBusy = true;
    try {
      const id = toHex(await secureBytes(16));
      if (record.mode === "desktop")
        await this.remote(record).request({
          operation: "append",
          session_id: record.remoteId!,
          source_id: id,
          text: text.trim(),
        });
      this.accept(record.id, {
        id,
        text: text.trim(),
        at: new Date().toISOString(),
      });
    } finally {
      this.actionBusy = false;
    }
  }

  async startRecording(): Promise<void> {
    const record = this.state.record;
    if (!record || ["stopped", "interrupted"].includes(record.status))
      throw new Error("请先开始一堂新课");
    if (
      this.state.capture !== "idle" ||
      this.actionBusy ||
      !this.foreground ||
      this.state.unsaved.length
    )
      throw new Error("请先完成当前操作并保存原文");
    const epoch = ++this.recordingEpoch;
    const check = () => {
      if (epoch !== this.recordingEpoch || !this.foreground) throw cancelled();
    };
    this.patch({ capture: "starting", error: "", interim: "" });
    let sink: AudioSink | null = null;
    try {
      await requestMicrophone();
      check();
      const settings = this.state.settings;
      if (record.mode === "byok") {
        const speech = new DashSpeech(
          (result) => {
            if (result.final)
              this.accept(record.id, {
                id: result.sourceId,
                text: result.text,
                at: new Date().toISOString(),
              });
            else this.patch({ interim: result.text });
          },
          (error) => {
            this.report(new Error(error));
            void this.stopRecording().catch((failure: unknown) =>
              this.report(failure),
            );
          },
        );
        sink = speech;
        this.sink = sink;
        await speech.start(
          settings.speechRegion,
          settings.speechModel,
          this.credentials.speech,
        );
        check();
      } else {
        const client = this.remote(record),
          id = toHex(await secureBytes(16));
        check();
        await client.request({
          operation: "resume",
          session_id: record.remoteId!,
        });
        check();
        sink = new LocalSpeech(client, record.remoteId!, id, (entry) =>
          this.accept(record.id, entry),
        );
        this.sink = sink;
      }
      await this.recorder.start(sink);
      check();
      this.updateRecord({ ...this.state.record!, status: "recording" });
      this.patch({ capture: "recording" });
    } catch (error) {
      sink?.close();
      if (epoch === this.recordingEpoch) {
        await this.stopRecording().catch((failure: unknown) =>
          this.report(failure),
        );
        throw error;
      }
    }
  }

  stopRecording(): Promise<void> {
    if (this.stopTask) return this.stopTask;
    if (this.state.capture === "idle") return Promise.resolve();
    const wasStarting = this.state.capture === "starting",
      record = this.state.record;
    ++this.recordingEpoch;
    this.patch({ capture: "stopping" });
    if (wasStarting) this.sink?.close();
    this.stopTask = (async () => {
      let failure: unknown;
      try {
        await this.recorder.stop();
      } catch (error) {
        failure = error;
      }
      try {
        if (record?.mode === "desktop")
          await this.remote(record).request({
            operation: "pause",
            session_id: record.remoteId!,
          });
      } catch (error) {
        failure ??= error;
      }
      this.sink?.close();
      this.sink = null;
      if (record && this.state.record?.id === record.id) {
        try {
          this.updateRecord({ ...this.state.record, status: "paused" });
        } catch (error) {
          failure ??= error;
        }
      }
      this.patch({ capture: "idle", interim: "" });
      if (failure) throw failure;
    })().finally(() => {
      this.stopTask = null;
    });
    return this.stopTask;
  }

  async finishClass(): Promise<void> {
    if (this.actionBusy) throw new Error("请等待当前保存操作完成");
    this.cancelGeneration();
    await this.stopRecording();
    const record = this.state.record;
    if (!record) return;
    if (this.state.unsaved.length)
      throw new Error("请先复制或重试保存未保存的原文");
    this.actionBusy = true;
    try {
      if (record.mode === "desktop") {
        try {
          await this.remote(record).request({
            operation: "stop",
            session_id: record.remoteId!,
          });
        } catch (error) {
          this.updateRecord({ ...record, status: "interrupted" });
          throw error;
        }
      }
      this.updateRecord({ ...record, status: "stopped" });
    } finally {
      this.actionBusy = false;
    }
  }

  async ask(kind: AssistantKind, question = ""): Promise<void> {
    const record = this.state.record;
    if (!record?.entries.length) throw new Error("请先记录一些课堂原文");
    if (this.state.generating || this.actionBusy)
      throw new Error("已有操作正在进行，请等待完成");
    const epoch = ++this.generationEpoch;
    this.generationCancelled = false;
    this.patch({ generating: true, answer: "", stage: "准备生成", error: "" });
    const update = (answer: string, stage: string) => {
      if (epoch === this.generationEpoch && !this.generationCancelled)
        this.patch({ answer, stage });
    };
    const settings = { ...this.state.settings },
      key = this.credentials.llm;
    try {
      if (this.generationCancelled) throw new GenerationCancelled();
      this.generation =
        record.mode === "byok"
          ? assistant(
              record,
              kind,
              question,
              (messages, emit) =>
                generate(
                  settings.llmProvider,
                  settings.model,
                  key,
                  messages,
                  emit,
                ),
              update,
            )
          : this.remoteGeneration(record, kind, question, update);
      const output = await this.generation.done;
      if (epoch !== this.generationEpoch) return;
      if (this.generationCancelled) throw new GenerationCancelled();
      if (kind === "summary") {
        const id = toHex(await secureBytes(16));
        if (
          epoch !== this.generationEpoch ||
          this.state.record?.id !== record.id
        )
          return;
        if (this.generationCancelled) throw new GenerationCancelled();
        this.updateRecord({
          ...this.state.record,
          notes: [
            ...this.state.record.notes,
            { id, markdown: output, at: new Date().toISOString() },
          ],
        });
      }
      this.patch({
        answer: output,
        stage:
          kind === "summary"
            ? "笔记已保存，原文完整保留"
            : "已完成 · 回答仅供参考",
      });
    } catch (error) {
      if (epoch === this.generationEpoch) {
        this.patch({
          stage:
            error instanceof GenerationCancelled
              ? "已取消，部分结果未保存为笔记"
              : "生成未完成",
        });
        throw error;
      }
    } finally {
      if (epoch === this.generationEpoch) {
        this.generation = null;
        this.patch({ generating: false });
      }
    }
  }

  private remoteGeneration(
    record: ClassroomRecord,
    kind: AssistantKind,
    question: string,
    update: (text: string, stage: string) => void,
  ): Generation {
    const client = this.remote(record);
    let stopped = false,
      jobId = "",
      wake: (() => void) | undefined;
    const done = (async () => {
      let job = object(
        (
          await client.request({
            operation: "assistant.start",
            session_id: record.remoteId!,
            task: { kind, question },
          })
        ).job,
      );
      jobId = identifier(job.id);
      const deadline = Date.now() + (kind === "summary" ? 1800000 : 180000);
      while (!stopped && Date.now() < deadline) {
        if (
          job.session_id !== record.remoteId ||
          job.id !== jobId ||
          typeof job.markdown !== "string" ||
          Array.from(job.markdown).length > 64000
        )
          throw new Error("电脑回答格式无效");
        update(
          job.markdown,
          typeof job.stage === "string" ? job.stage : "正在生成",
        );
        if (job.status === "completed") return job.markdown;
        if (job.status === "failed")
          throw new Error(
            typeof job.error_message === "string"
              ? job.error_message
              : "电脑模型生成失败",
          );
        if (job.status === "cancelled") throw new GenerationCancelled();
        await new Promise<void>((resolve) => {
          const timer = setTimeout(resolve, 800);
          wake = () => {
            clearTimeout(timer);
            resolve();
          };
        });
        if (!stopped)
          job = object(
            (
              await client.request({
                operation: "assistant.get",
                job_id: jobId,
              })
            ).job,
          );
      }
      try {
        await client.request({ operation: "assistant.cancel", job_id: jobId });
      } catch {
        throw new Error("未能确认电脑任务已取消，请在电脑关闭手机入口");
      }
      if (stopped) throw new GenerationCancelled();
      throw new Error("电脑模型响应超时，请重试");
    })();
    return {
      done,
      cancel() {
        stopped = true;
        wake?.();
      },
    };
  }

  cancelGeneration(): void {
    if (!this.state.generating) return;
    this.generationCancelled = true;
    this.generation?.cancel();
    // Keep the in-flight task owned until it reports cancellation, so it cannot overlap a new task.
    this.patch({ stage: "正在取消" });
  }
  background(): void {
    this.foreground = false;
    this.cancelGeneration();
    if (this.state.capture !== "idle") {
      this.patch({ error: "离开小程序已暂停录音，回来后请手动继续" });
      void this.stopRecording().catch((error: unknown) => this.report(error));
    }
  }
  foregrounded(): void {
    this.foreground = true;
  }
}

let instance: ClassFox | undefined;
export function service(): ClassFox {
  return (instance ??= new ClassFox());
}
export { PhoneApplicationError };
