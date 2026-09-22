import type { Json } from "./phoneCrypto";
import type { Entry } from "./records";

export function object(value: Json | undefined): Record<string, Json> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("电脑返回的数据格式无效");
  return value;
}
export function identifier(value: Json | undefined): string {
  if (typeof value !== "string" || !/^[0-9a-f]{32}$/.test(value))
    throw new Error("电脑返回的标识无效");
  return value;
}
export function remoteEntry(value: Json | undefined, sessionId: string): Entry {
  const entry = object(value);
  if (
    entry.session_id !== sessionId ||
    typeof entry.id !== "number" ||
    !Number.isSafeInteger(entry.id) ||
    entry.id < 1 ||
    typeof entry.text !== "string" ||
    Array.from(entry.text).length > 8000 ||
    typeof entry.created_at !== "string" ||
    !Number.isFinite(Date.parse(entry.created_at))
  )
    throw new Error("电脑返回的原文格式无效");
  return {
    id: `remote:${entry.id}`,
    remoteId: entry.id,
    text: entry.text,
    at: entry.created_at,
  };
}
