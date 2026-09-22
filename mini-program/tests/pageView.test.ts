import { expect, it } from "vitest";
import { classroomView } from "../src/pages/classroom/index";
import { defaultSettings } from "../src/core/providers";
import type { State } from "../src/service";

it("pages every extreme unicode entry while keeping native view updates below the bridge limit", () => {
  const state: State = {
    settings: defaultSettings,
    capture: "idle",
    generating: false,
    answer: "🦊".repeat(64000),
    stage: "",
    interim: "",
    unsaved: [],
    error: "",
    keyword: "",
    paired: false,
    pairingCode: "",
    record: {
      schema: 1,
      id: "a".repeat(32),
      courseName: "课堂",
      mode: "byok",
      status: "stopped",
      createdAt: "2026-09-22T00:00:00Z",
      entries: Array.from({ length: 35 }, (_, id) => ({
        id: String(id),
        at: "2026-09-22T00:00:00Z",
        text: "🦊".repeat(8000),
      })),
      notes: [
        {
          id: "b".repeat(32),
          at: "2026-09-22T00:00:00Z",
          markdown: "🦊".repeat(64000),
        },
      ],
    },
  };
  const seen: string[] = [];
  let before = -1;
  while (true) {
    const page = classroomView(state, before);
    expect(Buffer.byteLength(JSON.stringify(page))).toBeLessThan(500000);
    seen.unshift(...page.entries.map((entry) => entry.id));
    if (!page.more) break;
    expect(page.nextBefore).toBeLessThan(before < 0 ? 35 : before);
    before = page.nextBefore;
  }
  expect(seen).toEqual(Array.from({ length: 35 }, (_, id) => String(id)));
  expect(state.answer).toHaveLength(128000);
});
