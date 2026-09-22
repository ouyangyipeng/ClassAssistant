import { afterEach, expect, it, vi } from "vitest";
import { CaptureController } from "../src/workspace/capture";
import { Client } from "../src/workspace/client";
import { WorkspaceStore } from "../src/workspace/store";
import type { Session } from "../src/workspace/domain";

const fake = vi.hoisted(() => ({ start: vi.fn(), stop: vi.fn() }));
vi.mock("../src/workspace/browserSpeech", () => ({
  BrowserSpeech: class {
    start = fake.start;
    stop = fake.stop;
    unsaved() {
      return "";
    }
  },
}));
afterEach(() => vi.clearAllMocks());
const session: Session = {
  id: "classroom",
  owner_id: "desktop",
  course_name: "测试",
  material_id: null,
  status: "paused",
  created_at: "2026-09-22T00:00:00Z",
  ended_at: null,
};

it("confirms current server state before stopping a resumed browser on a delayed pause event", async () => {
  let current = { ...session, status: "recording" as const } as Session;
  const store = new WorkspaceStore(
    new Client(
      { baseUrl: "http://127.0.0.1:12345", token: "synthetic" },
      async (input) =>
        Response.json(
          String(input).endsWith("/status")
            ? { session: current, source: "browser" }
            : current,
        ),
    ),
  );
  vi.spyOn(store, "refresh").mockResolvedValue(undefined);
  store.patch({ current: session, source: "browser" });
  fake.start.mockResolvedValue(undefined);
  fake.stop.mockResolvedValue(undefined);
  const capture = new CaptureController(store);
  await capture.control("resume");
  expect(store.getSnapshot().current?.status).toBe("recording");
  store.patch({ current: session });
  await capture.synchronize();
  expect(fake.stop).not.toHaveBeenCalled();
  current = { ...session, status: "paused" };
  await capture.synchronize();
  expect(fake.stop).toHaveBeenCalledOnce();
});

it("can stop pending native startup while the ordinary action lock is busy", async () => {
  const paths: string[] = [];
  const store = new WorkspaceStore(
    new Client(
      { baseUrl: "http://127.0.0.1:12345", token: "synthetic" },
      async (input) => {
        paths.push(new URL(String(input)).pathname);
        return Response.json({ ...session, status: "stopped" });
      },
    ),
  );
  vi.spyOn(store, "refresh").mockResolvedValue(undefined);
  store.patch({
    current: { ...session, status: "starting" },
    source: "microphone",
    busy: true,
  });
  const capture = new CaptureController(store);
  await Promise.all([capture.control("stop"), capture.control("stop")]);
  expect(paths.filter((path) => path.endsWith("/stop"))).toHaveLength(1);
  expect(store.getSnapshot().stopping).toBe(false);
  expect(store.getSnapshot().busy).toBe(true);
});
