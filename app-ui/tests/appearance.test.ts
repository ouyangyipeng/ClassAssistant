import { expect, it } from "vitest";
import { importAppearance } from "../src/workspace/appearance";
import type { Preferences } from "../src/workspace/domain";

const current: Preferences["appearance"] = {
  theme: "system",
  accent: "amber",
  font_scale: 1,
  opacity: 0.96,
  window_radius: 12,
  always_on_top: false,
};

it("maps existing preferences without altering the source or unrelated settings", () => {
  const source = JSON.stringify({
    version: 2,
    backgroundPreset: "ocean",
    windowRadius: 18,
    shellOpacity: 0.8,
    fontScale: 1.2,
  });
  expect(importAppearance(source, current)).toEqual({
    theme: "dark",
    accent: "blue",
    font_scale: 1.2,
    opacity: 0.8,
    window_radius: 18,
    always_on_top: false,
  });
  expect(current.theme).toBe("system");
});

it("bounds malformed numbers and preserves the pre-versioned radius migration", () => {
  expect(
    importAppearance(
      '{"fontScale":9,"shellOpacity":"0.9","windowRadius":100}',
      current,
    ),
  ).toMatchObject({ font_scale: 1.5, opacity: 0.96, window_radius: 10 });
  expect(() => importAppearance(null, current)).toThrow("没有旧版");
  expect(() => importAppearance("[]", current)).toThrow("格式无效");
});
