import {
  defaultSettings,
  llmPresets,
  speechPresets,
  type MobileSettings,
} from "./providers";
import { utf8 } from "./phoneCrypto";

export interface Entry {
  id: string;
  text: string;
  at: string;
  remoteId?: number;
}
export interface Note {
  id: string;
  markdown: string;
  at: string;
}
export interface ClassroomRecord {
  schema: 1;
  id: string;
  courseName: string;
  mode: "byok" | "desktop";
  status: "recording" | "paused" | "stopped" | "interrupted";
  createdAt: string;
  remoteId?: string;
  connectionId?: string;
  entries: Entry[];
  notes: Note[];
}
export interface LocalStorage {
  get(key: string): unknown;
  set(key: string, value: unknown): void;
  remove(key: string): void;
  keys(): string[];
}
const prefix = "classfox:v2:class:";
const settingsKey = "classfox:v2:preferences";

function isObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}
function id(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{32}$/.test(value);
}
function date(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}
function entry(value: unknown): value is Entry {
  return (
    isObject(value) &&
    typeof value.id === "string" &&
    value.id.length <= 128 &&
    typeof value.text === "string" &&
    Array.from(value.text).length <= 8000 &&
    date(value.at) &&
    (value.remoteId === undefined ||
      (typeof value.remoteId === "number" &&
        Number.isSafeInteger(value.remoteId) &&
        value.remoteId > 0))
  );
}
function note(value: unknown): value is Note {
  return (
    isObject(value) &&
    id(value.id) &&
    typeof value.markdown === "string" &&
    Array.from(value.markdown).length <= 64000 &&
    date(value.at)
  );
}
function parse(value: unknown): ClassroomRecord {
  if (
    !isObject(value) ||
    value.schema !== 1 ||
    !id(value.id) ||
    typeof value.courseName !== "string" ||
    !value.courseName.trim() ||
    value.courseName.length > 120 ||
    !["byok", "desktop"].includes(String(value.mode)) ||
    !["recording", "paused", "stopped", "interrupted"].includes(
      String(value.status),
    ) ||
    !date(value.createdAt) ||
    !Array.isArray(value.entries) ||
    !value.entries.every(entry) ||
    !Array.isArray(value.notes) ||
    !value.notes.every(note) ||
    (value.remoteId !== undefined && !id(value.remoteId)) ||
    (value.connectionId !== undefined && !id(value.connectionId))
  )
    throw new Error("此课堂记录格式无效，原始存储仍保留，请勿覆盖");
  return value as unknown as ClassroomRecord;
}

export class ClassroomRepository {
  constructor(private storage: LocalStorage) {}

  load(classId: string): ClassroomRecord {
    if (!id(classId)) throw new Error("课堂标识无效");
    const record = parse(this.storage.get(prefix + classId));
    if (record.id !== classId)
      throw new Error("课堂记录与标识不一致，原始存储仍保留");
    return record;
  }

  save(record: ClassroomRecord): void {
    const validated = parse(record);
    // Leave space under WeChat's per-key limit; storage failures never remove originals.
    if (utf8(JSON.stringify(validated)).length > 850000)
      throw new Error(
        "此课堂已接近手机存储上限，请导出原文并开始下一堂课；未保存的文字请先复制",
      );
    try {
      this.storage.set(
        prefix + record.id,
        JSON.parse(JSON.stringify(validated)),
      );
    } catch {
      throw new Error(
        "手机存储写入失败，请先复制未保存文字，再导出并清理旧课堂",
      );
    }
  }

  list(): ClassroomRecord[] {
    return this.storage
      .keys()
      .filter((key) => key.startsWith(prefix))
      .map((key) => this.load(key.slice(prefix.length)))
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  }

  inspect(): { records: ClassroomRecord[]; damaged: string[] } {
    const records: ClassroomRecord[] = [],
      damaged: string[] = [];
    for (const key of this.storage
      .keys()
      .filter((value) => value.startsWith(prefix))) {
      try {
        records.push(this.load(key.slice(prefix.length)));
      } catch {
        damaged.push(key.slice(prefix.length));
      }
    }
    return {
      records: records.sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
      damaged,
    };
  }

  remove(classId: string): void {
    if (!id(classId)) throw new Error("课堂标识无效");
    this.storage.remove(prefix + classId);
  }

  append(record: ClassroomRecord, value: Entry): ClassroomRecord {
    const existing = record.entries.find((item) => item.id === value.id);
    if (existing) {
      if (existing.text !== value.text)
        throw new Error("同一片段返回了不同文字，已停止以保护原文");
      return record;
    }
    const updated = { ...record, entries: [...record.entries, value] };
    this.save(updated);
    return updated;
  }

  settings(): MobileSettings {
    const value = this.storage.get(settingsKey);
    if (!isObject(value))
      return { ...defaultSettings, keywords: [...defaultSettings.keywords] };
    return {
      mode: value.mode === "desktop" ? "desktop" : "byok",
      llmProvider:
        typeof value.llmProvider === "string" &&
        Object.hasOwn(llmPresets, value.llmProvider)
          ? (value.llmProvider as MobileSettings["llmProvider"])
          : defaultSettings.llmProvider,
      model:
        typeof value.model === "string" &&
        value.model.trim().length > 0 &&
        value.model.length <= 200
          ? value.model
          : defaultSettings.model,
      speechRegion:
        typeof value.speechRegion === "string" &&
        Object.hasOwn(speechPresets, value.speechRegion)
          ? (value.speechRegion as MobileSettings["speechRegion"])
          : defaultSettings.speechRegion,
      speechModel:
        typeof value.speechModel === "string" &&
        value.speechModel.trim().length > 0 &&
        value.speechModel.length <= 200
          ? value.speechModel
          : defaultSettings.speechModel,
      keywords:
        Array.isArray(value.keywords) &&
        value.keywords.length <= 20 &&
        value.keywords.every(
          (keyword) =>
            typeof keyword === "string" &&
            keyword.trim().length > 0 &&
            keyword.length <= 30,
        )
          ? value.keywords
          : [...defaultSettings.keywords],
    };
  }

  saveSettings(value: MobileSettings): void {
    const { mode, llmProvider, model, speechRegion, speechModel, keywords } =
      value;
    this.storage.set(settingsKey, {
      mode,
      llmProvider,
      model,
      speechRegion,
      speechModel,
      keywords: [...keywords],
    });
  }
}

export function exportClassroom(record: ClassroomRecord): string {
  const lines = [
    `# ${record.courseName}`,
    record.createdAt,
    "",
    "## 课堂原文",
    "",
  ];
  for (const value of record.entries)
    lines.push(`[${value.at}] ${value.text}`, "");
  for (const value of record.notes)
    lines.push("## 课堂笔记", value.at, "", value.markdown, "");
  return lines.join("\n");
}
