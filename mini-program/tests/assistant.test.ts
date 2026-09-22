import { expect, it, vi } from "vitest";
import { assistant, chunks, type Generate } from "../src/core/assistant";
import type { ClassroomRecord } from "../src/core/records";

const record: ClassroomRecord = {
  schema: 1,
  id: "a".repeat(32),
  courseName: "课程",
  mode: "byok",
  status: "recording",
  createdAt: "2026-09-22T00:00:00Z",
  entries: [],
  notes: [],
};
it("summarizes every snapshot segment without including later entries or truncating unicode", async () => {
  const current = {
    ...record,
    entries: Array.from({ length: 30 }, (_, i) => ({
      id: String(i),
      text: `唯一条目${i} ` + "🦊".repeat(500),
      at: record.createdAt,
    })),
  };
  const calls: string[] = [];
  const generate: Generate = (messages, emit) => {
    calls.push(messages[1].content);
    const result = calls.length < 3 ? "已归纳全部要点" : "完整笔记";
    emit(result);
    return { done: Promise.resolve(result), cancel() {} };
  };
  const result = assistant(current, "summary", "", generate, () => undefined);
  current.entries.push({
    id: "late",
    text: "后来的文字",
    at: record.createdAt,
  });
  expect(await result.done).toBe("完整笔记");
  expect(calls).toHaveLength(3);
  for (let i = 0; i < 30; i++)
    expect(calls.slice(0, 2).join("")).toContain(`唯一条目${i}`);
  expect(calls.join("")).not.toContain("后来的文字");
  expect(chunks("🦊🦊中", 2)).toEqual(["🦊🦊", "中"]);
});
it("cancels between summary calls and never returns partial output as a complete note", async () => {
  const cancel = vi.fn();
  let finish!: (value: string) => void;
  const generate: Generate = () => ({
    done: new Promise((resolve) => {
      finish = resolve;
    }),
    cancel,
  });
  const current = {
    ...record,
    entries: [{ id: "a", at: record.createdAt, text: "原文" }],
  };
  const result = assistant(current, "summary", "", generate, () => undefined);
  result.cancel();
  finish("部分结果");
  await expect(result.done).rejects.toThrow("取消");
  expect(cancel).toHaveBeenCalledOnce();
});
