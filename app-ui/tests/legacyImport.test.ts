import { expect, it } from "vitest";
import { describeImport } from "../src/workspace/legacyImport";

it("reports skipped migration files even when nothing was imported", () => {
  const text = describeImport({ session_id: null, materials: 0, notes: 0, skipped_files: ["class_transcript.txt"] });
  expect(text).toContain("未导入任何记录");
  expect(text).toContain("class_transcript.txt");
  expect(text).not.toContain("导入完成");
});

it("distinguishes partial imports and describes deduplicated results", () => {
  const text = describeImport({ session_id: "class", materials: 2, notes: 3, skipped_files: ["cite/failed.txt"] });
  expect(text).toContain("课堂 1 堂、资料 2 份、笔记 3 份");
  expect(text).toContain("复用已有记录");
  expect(text).toContain("cite/failed.txt");
});
