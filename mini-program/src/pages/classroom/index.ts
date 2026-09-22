import { service, message, type State } from "../../service";
import type { AssistantKind } from "../../core/assistant";
import { exportClassroom } from "../../core/records";
import { exportFile } from "../../platform/export";
import { utf8 } from "../../core/phoneCrypto";

export function classroomView(state: State, before = -1) {
  const record = state.record;
  const end =
    before < 0
      ? (record?.entries.length ?? 0)
      : Math.min(before, record?.entries.length ?? 0);
  let start = end,
    size = 0;
  while (start > 0 && end - start < 30) {
    const bytes = utf8(JSON.stringify(record!.entries[start - 1])).length;
    if (size + bytes > 180000) break;
    size += bytes;
    start--;
  }
  const clip = (text: string) => {
    const points = Array.from(text);
    return points.length > 20000
      ? points.slice(0, 20000).join("") +
          "\n\n…内容较长，复制回答或导出课堂可查看全文。"
      : text;
  };
  return {
    courseName: record?.courseName ?? "",
    hasClass: !!record,
    canRecord: !!record && ["paused", "recording"].includes(record.status),
    mode: record?.mode ?? state.settings.mode,
    capture: state.capture,
    generating: state.generating,
    status: record
      ? {
          paused: "待录音",
          recording: "录音中",
          stopped: "已结束",
          interrupted: "已中断",
        }[record.status]
      : "未开始",
    entries:
      record?.entries.slice(start, end).map((entry) => ({
        ...entry,
        time: new Date(entry.at).toLocaleTimeString("zh-CN", {
          hour12: false,
        }),
      })) ?? [],
    total: record?.entries.length ?? 0,
    more: start > 0,
    nextBefore: start,
    hasNewer: end < (record?.entries.length ?? 0),
    notes:
      record?.notes
        .slice(-1)
        .map((note) => ({ ...note, markdown: clip(note.markdown) })) ?? [],
    answer: clip(state.answer),
    stage: state.stage,
    error: state.error,
    keyword: state.keyword,
    interim: state.interim,
    unsaved: clip(state.unsaved.map((entry) => entry.text).join("\n")),
    paired: state.paired,
  };
}

export function registerClassroom(): void {
  Page({
    data: {
      ...classroomView(service().snapshot),
      title: "",
      draft: "",
      question: "",
      busy: false,
      before: -1,
    },
    unsubscribe: null as (() => void) | null,
    onShow() {
      service().foregrounded();
      this.unsubscribe?.();
      this.setData({ before: -1 });
      this.unsubscribe = service().subscribe((state) =>
        this.setData(classroomView(state, this.data.before)),
      );
    },
    onHide() {
      this.unsubscribe?.();
      this.unsubscribe = null;
      service().background();
    },
    onUnload() {
      this.unsubscribe?.();
    },
    async run(action: () => Promise<void>) {
      if (this.data.busy) return;
      this.setData({ busy: true });
      try {
        await action();
      } catch (error) {
        service().report(error);
      } finally {
        this.setData({ busy: false });
      }
    },
    onTitle(event: WechatMiniprogram.Input) {
      this.setData({ title: event.detail.value });
    },
    onDraft(event: WechatMiniprogram.Input) {
      this.setData({ draft: event.detail.value });
    },
    onQuestion(event: WechatMiniprogram.Input) {
      this.setData({ question: event.detail.value });
    },
    create() {
      service().foregrounded();
      void this.run(async () => {
        this.setData({ before: -1 });
        await service().create(this.data.title || "未命名课堂");
        this.setData({ title: "" });
      });
    },
    record() {
      service().foregrounded();
      // Stopping must remain usable while asynchronous startup is pending.
      const action =
        service().snapshot.capture === "idle"
          ? service().startRecording()
          : service().stopRecording();
      void action.catch((error: unknown) => service().report(error));
    },
    append() {
      void this.run(async () => {
        await service().append(this.data.draft);
        this.setData({ draft: "" });
      });
    },
    finish() {
      void this.run(() => service().finishClass());
    },
    ask(event: WechatMiniprogram.TouchEvent) {
      const kind = event.currentTarget.dataset.kind as AssistantKind;
      if (!["rescue", "catchup", "summary", "followup"].includes(kind)) return;
      void service()
        .ask(kind, kind === "followup" ? this.data.question : "")
        .catch((error: unknown) => service().report(error));
    },
    cancel() {
      service().cancelGeneration();
    },
    more() {
      const before = this.data.nextBefore;
      this.setData({ before, ...classroomView(service().snapshot, before) });
    },
    newest() {
      this.setData({ before: -1, ...classroomView(service().snapshot) });
    },
    dismiss() {
      service().clearError();
    },
    retry() {
      try {
        service().retryUnsaved();
      } catch (error) {
        service().report(error);
      }
    },
    copy(event: WechatMiniprogram.TouchEvent) {
      const target = event.currentTarget.dataset.target;
      const data =
        target === "unsaved"
          ? service()
              .snapshot.unsaved.map((entry) => entry.text)
              .join("\n")
          : target === "answer"
            ? service().snapshot.answer
            : exportClassroom(service().snapshot.record!);
      wx.setClipboardData({
        data,
        fail: () => service().report(new Error("复制失败，请选择导出文件")),
      });
    },
    export() {
      const record = service().snapshot.record;
      if (record)
        void this.run(async () => {
          await exportFile(record);
        }).catch((error: unknown) =>
          service().report(new Error(message(error))),
        );
    },
    settings() {
      wx.switchTab({ url: "/pages/settings/index" });
    },
  });
}
