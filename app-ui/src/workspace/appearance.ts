import type { Preferences } from "./domain";

export const legacyAppearanceKey = "class-assistant-ui-style";

export function importAppearance(
  raw: string | null,
  current: Preferences["appearance"],
): Preferences["appearance"] {
  if (!raw) throw new Error("当前设备的应用存储中没有旧版外观设置。");
  let value: Record<string, unknown>;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
      throw new Error();
    value = parsed as Record<string, unknown>;
  } catch {
    throw new Error("旧版外观设置格式无效，原始设置已保留。");
  }
  const number = (key: string, fallback: number, min: number, max: number) => {
    const candidate = value[key];
    return typeof candidate === "number" && Number.isFinite(candidate)
      ? Math.min(max, Math.max(min, candidate))
      : fallback;
  };
  const accents: Record<string, Preferences["appearance"]["accent"]> = {
    ocean: "blue",
    sunset: "amber",
    forest: "green",
    slate: "slate",
  };
  return {
    ...current,
    theme: "dark",
    accent:
      typeof value.backgroundPreset === "string"
        ? (accents[value.backgroundPreset] ?? current.accent)
        : current.accent,
    font_scale: number("fontScale", current.font_scale, 0.85, 1.5),
    opacity: number("shellOpacity", current.opacity, 0.6, 1),
    window_radius: Math.round(
      value.version ? number("windowRadius", current.window_radius, 0, 30) : 10,
    ),
  };
}
