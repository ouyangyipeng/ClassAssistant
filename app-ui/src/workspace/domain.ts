export interface Connection {
  baseUrl: string;
  token: string;
}
export type SessionStatus =
  "starting" | "recording" | "paused" | "stopped" | "interrupted" | "error";
export type Source = "microphone" | "browser" | "text" | "remote";
export interface Session {
  id: string;
  owner_id: string;
  course_name: string;
  material_id: string | null;
  status: SessionStatus;
  created_at: string;
  ended_at: string | null;
}
export interface Entry {
  id: number;
  session_id: string;
  text: string;
  created_at: string;
  source_id: string | null;
}
export interface Material {
  id: string;
  filename: string;
  characters: number;
  created_at: string;
}
export interface Note {
  id: string;
  session_id: string;
  title: string;
  markdown: string;
  created_at: string;
}
export type JobKind = "rescue" | "catchup" | "summary" | "followup";
export interface Job {
  id: string;
  session_id: string;
  kind: JobKind;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  created_at: string;
  markdown: string;
  stage: string;
  first_token_ms: number | null;
  total_ms: number | null;
  summary_id: string | null;
  error_code: string | null;
  error_message: string | null;
  through_entry_id: number;
}
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}
export interface Installation {
  model_id: string;
  status:
    | "missing"
    | "downloading"
    | "verifying"
    | "loading"
    | "ready"
    | "failed"
    | "cancelled";
  downloaded_bytes: number;
  total_bytes: number;
  message: string;
}
export interface ModelInfo {
  model: {
    id: string;
    name: string;
    kind: "asr" | "llm";
    description: string;
    source_url: string;
    license_name: string;
    license_url: string;
    files: { size: number }[];
  };
  installation: Installation;
}
export type CredentialName =
  "llm" | "asr" | "dashscope" | "seed_api" | "seed_app" | "seed_access";
export type Credentials = Record<CredentialName, boolean>;
export interface Preferences {
  version: 2;
  llm: {
    mode: "local" | "byok";
    managed: boolean;
    local_model_id: string;
    base_url: string;
    model: string;
    timeout_seconds: number;
    context_characters: number;
  };
  asr: {
    mode:
      | "offline"
      | "webspeech"
      | "google"
      | "seed-asr"
      | "dashscope"
      | "openai"
      | "mock";
    language: string;
    input_device: number | null;
    model_id: string;
    base_url: string;
    model: string;
    seed_resource_id: string;
    dashscope_model: string;
    dashscope_region: "beijing" | "singapore";
  };
  appearance: {
    theme: "system" | "light" | "dark";
    accent: "amber" | "blue" | "green" | "slate";
    font_scale: number;
    opacity: number;
    window_radius: number;
    always_on_top: boolean;
  };
  keywords: string[];
  warning_keywords: string[];
  auto_summary: boolean;
}
export interface Status {
  session: Session | null;
  source: Source;
}
export interface ServerEvent {
  type: string;
  session_id?: string | null;
  data: Record<string, unknown>;
}
export interface Alert {
  entry_id: number;
  level: "danger" | "warning";
  keywords: string[];
  text: string;
  session_id: string;
}
export const isRunning = (job: Job) =>
  job.status === "queued" || job.status === "running";
export const statusLabel: Record<SessionStatus, string> = {
  starting: "正在准备",
  recording: "记录中",
  paused: "已暂停",
  stopped: "已结束",
  interrupted: "上次意外中断",
  error: "识别已停止",
};
export const jobLabel: Record<JobKind, string> = {
  rescue: "帮我救场",
  catchup: "讲到哪里了",
  summary: "课堂笔记",
  followup: "课堂追问",
};
