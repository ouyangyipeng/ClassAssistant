import { afterEach, expect, it, vi } from "vitest";
import { PrivacyGate } from "../src/platform/privacy";

afterEach(() => vi.unstubAllGlobals());
it("requires an explicit native agree action and rejects pending requests on page hide", () => {
  let listener!: (resolve: (result: unknown) => void) => void;
  vi.stubGlobal("wx", {
    onNeedPrivacyAuthorization: (callback: typeof listener) => {
      listener = callback;
    },
  });
  const gate = new PrivacyGate(),
    first = vi.fn(),
    second = vi.fn(),
    visible: boolean[] = [];
  gate.subscribe((value) => visible.push(value));
  listener(first);
  listener(second);
  expect(first).not.toHaveBeenCalled();
  expect(visible.at(-1)).toBe(true);
  gate.finish(true);
  expect(first).toHaveBeenCalledWith({
    event: "agree",
    buttonId: "classfox-privacy-agree",
  });
  expect(second).toHaveBeenCalledWith({
    event: "agree",
    buttonId: "classfox-privacy-agree",
  });
  const next = vi.fn();
  listener(next);
  gate.finish(false);
  gate.finish(true);
  expect(next).toHaveBeenCalledExactlyOnceWith({ event: "disagree" });
  expect(visible.at(-1)).toBe(false);
});
