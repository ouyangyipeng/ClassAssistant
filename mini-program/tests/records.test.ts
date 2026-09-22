import { expect, it } from "vitest";
import {
  ClassroomRepository,
  exportClassroom,
  type ClassroomRecord,
} from "../src/core/records";
import { defaultSettings } from "../src/core/providers";

function fixture() {
  const records = new Map<string, unknown>();
  let fail = false;
  const repository = new ClassroomRepository({
    get: (key) => records.get(key),
    set(key, value) {
      if (fail) throw new Error("Quota");
      records.set(key, value);
    },
    remove: (key) => records.delete(key),
    keys: () => [...records.keys()],
  });
  return {
    records,
    repository,
    fail: () => {
      fail = true;
    },
  };
}
const record: ClassroomRecord = {
  schema: 1,
  id: "a".repeat(32),
  courseName: "课堂",
  mode: "byok",
  status: "recording",
  createdAt: "2026-09-22T01:00:00Z",
  entries: [],
  notes: [],
};

it("preserves immutable originals, idempotent segments and export after notes", () => {
  const { repository } = fixture();
  const entry = { id: "fragment", text: "原文 🦊", at: record.createdAt };
  const current = repository.append(record, entry);
  expect(record.entries).toHaveLength(0);
  expect(repository.append(current, entry).entries).toHaveLength(1);
  expect(() => repository.append(current, { ...entry, text: "改变" })).toThrow(
    "不同文字",
  );
  repository.save({
    ...current,
    notes: [{ id: "b".repeat(32), markdown: "总结", at: record.createdAt }],
    status: "stopped",
  });
  expect(exportClassroom(repository.load(record.id))).toContain("原文 🦊");
  expect(repository.list()).toHaveLength(1);
});
it("failed persistence keeps previous saved text and rejects unbounded records", () => {
  const { repository, fail } = fixture();
  repository.save(record);
  fail();
  expect(() =>
    repository.append(record, {
      id: "new",
      text: "尚未写入",
      at: record.createdAt,
    }),
  ).toThrow("存储写入失败");
  expect(repository.load(record.id).entries).toEqual([]);
  const huge = {
    ...record,
    entries: Array.from({ length: 30 }, (_, index) => ({
      id: String(index),
      text: "🦊".repeat(8000),
      at: record.createdAt,
    })),
  };
  expect(() => repository.save(huge)).toThrow("存储上限");
});
it("never persists keys when saving settings and rejects corrupted history", () => {
  const { records, repository } = fixture();
  repository.saveSettings({
    ...defaultSettings,
    llmKey: "synthetic-secret",
  } as typeof defaultSettings);
  expect(JSON.stringify([...records.values()])).not.toContain(
    "synthetic-secret",
  );
  records.set("classfox:v2:class:" + record.id, {
    ...record,
    entries: "broken",
  });
  expect(() => repository.load(record.id)).toThrow("原始存储仍保留");
  expect(records.size).toBe(2);
});

it("reports damaged records while keeping healthy classrooms available and originals untouched", () => {
  const { repository, records } = fixture();
  repository.save(record);
  const key = "classfox:v2:class:" + "b".repeat(32),
    damaged = { corrupted: "original" };
  records.set(key, damaged);
  const history = repository.inspect();
  expect(history.records.map((value) => value.id)).toEqual([record.id]);
  expect(history.damaged).toEqual(["b".repeat(32)]);
  expect(records.get(key)).toBe(damaged);
});
