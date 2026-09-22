import { expect, it } from "vitest";
import { Client } from "../src/workspace/client";
import { WorkspaceStore } from "../src/workspace/store";
import type { Entry } from "../src/workspace/domain";

const entry = (session_id: string, id = 1): Entry => ({
  id,
  session_id,
  text: `${session_id}原文`,
  created_at: "2026-09-22T00:00:00Z",
  source_id: null,
});
function storeWith(handler: (url: URL) => Promise<Response> | Response) {
  return new WorkspaceStore(
    new Client(
      { baseUrl: "http://127.0.0.1:12345", token: "synthetic" },
      async (input) => handler(new URL(String(input))),
    ),
  );
}

it("ignores late responses from the previously selected classroom", async () => {
  let release!: (response: Response) => void;
  const waiting = new Promise<Response>((resolve) => {
    release = resolve;
  });
  const store = storeWith((url) =>
    url.pathname.includes("/sessions/first/entries")
      ? waiting
      : Response.json(
          url.pathname.includes("/entries") ? [entry("second")] : [],
        ),
  );
  const previous = store.select("first");
  await store.select("second");
  release(Response.json([entry("first")]));
  await previous;
  expect(store.getSnapshot().selectedId).toBe("second");
  expect(store.getSnapshot().entries).toEqual([entry("second")]);
});

it("ends loading after a failed selection so the user can recover", async () => {
  const store = storeWith(() => {
    throw new Error("synthetic disconnect");
  });
  await store.select("first");
  expect(store.getSnapshot().selectionLoading).toBe(false);
  expect(store.getSnapshot().error).toContain("无法连接");
});

it("loads transcript pages past 1000 entries without dropping streamed arrivals", async () => {
  const store = storeWith((url) => {
    if (!url.pathname.includes("/entries")) return Response.json([]);
    const after = Number(url.searchParams.get("after_id"));
    return Response.json(
      after
        ? [entry("first", 1001)]
        : Array.from({ length: 1000 }, (_, index) => entry("first", index + 1)),
    );
  });
  await store.select("first");
  expect(store.getSnapshot().entries).toHaveLength(1001);
  expect(store.getSnapshot().entries.at(-1)?.id).toBe(1001);
});
