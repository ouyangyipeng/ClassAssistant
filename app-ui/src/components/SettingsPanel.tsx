import { useEffect, useMemo, useState } from "react";
import { getSettings, saveSettings } from "../services/api";
import {
  DEFAULT_UI_STYLE_SETTINGS,
  applyUiStyleSettings,
  readUiStyleSettings,
  saveUiStyleSettings,
  type UiStyleSettings,
} from "../services/preferences";

type EnvFieldConfig = {
  key: string;
  label: string;
  placeholder?: string;
  type?: "text" | "password" | "number" | "select";
  options?: Array<{ label: string; value: string }>;
};

const ENV_SECTIONS: Array<{ title: string; fields: EnvFieldConfig[] }> = [
  {
    title: "模型与接口",
    fields: [
      { key: "LLM_BASE_URL", label: "LLM Base URL", placeholder: "https://api.openai.com/v1" },
      { key: "LLM_API_KEY", label: "LLM API Key", type: "password", placeholder: "输入模型 API Key" },
      { key: "LLM_MODEL", label: "LLM 模型名", placeholder: "gpt-4o-mini" },
      {
        key: "ASR_MODE",
        label: "ASR 模式",
        type: "select",
        options: [
          { label: "本地识别 local", value: "local" },
          { label: "Edge / 浏览器识别 webspeech", value: "webspeech" },
          { label: "Mock 测试", value: "mock" },
          { label: "DashScope", value: "dashscope" },
          { label: "Seed-ASR", value: "seed-asr" },
        ],
      },
      {
        key: "WEBSPEECH_LANG",
        label: "WebSpeech 语言",
        type: "select",
        options: [
          { label: "中文 zh-CN", value: "zh-CN" },
          { label: "英文 en-US", value: "en-US" },
        ],
      },
      { key: "API_PORT", label: "后端端口", type: "number", placeholder: "8765" },
    ],
  },
  {
    title: "Seed-ASR",
    fields: [
      { key: "SEED_ASR_APP_KEY", label: "Seed APP Key", type: "password" },
      { key: "SEED_ASR_ACCESS_KEY", label: "Seed Access Key", type: "password" },
      { key: "SEED_ASR_RESOURCE_ID", label: "Seed Resource ID", placeholder: "volc.seedasr.sauc.duration" },
      { key: "SEED_ASR_WS_URL", label: "Seed WebSocket URL", placeholder: "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async" },
    ],
  },
  {
    title: "音频与其他",
    fields: [
      { key: "DASHSCOPE_API_KEY", label: "DashScope API Key", type: "password" },
      { key: "AUDIO_SAMPLE_RATE", label: "采样率", type: "number", placeholder: "16000" },
      { key: "AUDIO_CHANNELS", label: "声道数", type: "number", placeholder: "1" },
      { key: "AUDIO_CHUNK_SIZE", label: "Chunk Size", type: "number", placeholder: "3200" },
    ],
  },
];

const ALL_ENV_KEYS = ENV_SECTIONS.flatMap((section) => section.fields.map((field) => field.key));

function createEmptyEnvValues() {
  return Object.fromEntries(ALL_ENV_KEYS.map((key) => [key, ""])) as Record<string, string>;
}

function parseEnvContent(content: string) {
  const values = createEmptyEnvValues();
  const extras: string[] = [];

  for (const line of content.split(/\r?\n/)) {
    if (!line.trim()) {
      extras.push(line);
      continue;
    }

    if (line.trimStart().startsWith("#")) {
      extras.push(line);
      continue;
    }

    const separatorIndex = line.indexOf("=");
    if (separatorIndex === -1) {
      extras.push(line);
      continue;
    }

    const key = line.slice(0, separatorIndex).trim();
    const value = line.slice(separatorIndex + 1);
    if (ALL_ENV_KEYS.includes(key)) {
      values[key] = value;
    } else {
      extras.push(line);
    }
  }

  return { values, extraContent: extras.join("\n").trim() };
}

function buildEnvContent(values: Record<string, string>, extraContent: string) {
  const lines: string[] = [];
  for (const section of ENV_SECTIONS) {
    lines.push(`# ${section.title}`);
    for (const field of section.fields) {
      const value = values[field.key]?.trim();
      if (value) {
        lines.push(`${field.key}=${value}`);
      }
    }
    lines.push("");
  }

  const extra = extraContent.trim();
  if (extra) {
    lines.push("# 其他原始配置");
    lines.push(extra);
  }

  return `${lines.join("\n").trim()}\n`;
}

interface SettingsPanelProps {
  visible: boolean;
  onClose: () => void;
  onSaved: (message: string) => void;
}

export default function SettingsPanel({ visible, onClose, onSaved }: SettingsPanelProps) {
  const [envValues, setEnvValues] = useState<Record<string, string>>(createEmptyEnvValues);
  const [extraContent, setExtraContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [path, setPath] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [styleSettings, setStyleSettings] = useState<UiStyleSettings>(DEFAULT_UI_STYLE_SETTINGS);

  const styleSummary = useMemo(
    () => `${styleSettings.backgroundPreset} / 圆角 ${styleSettings.windowRadius}px / 透明度 ${Math.round(styleSettings.shellOpacity * 100)}%`,
    [styleSettings]
  );

  useEffect(() => {
    if (!visible) return;

    setLoading(true);
    setError(null);
    setStyleSettings(readUiStyleSettings());
    getSettings()
      .then((res) => {
        const parsed = parseEnvContent(res.content);
        setEnvValues(parsed.values);
        setExtraContent(parsed.extraContent);
        setPath(res.path);
      })
      .catch((err) => setError(err.message || "读取设置失败"))
      .finally(() => setLoading(false));
  }, [visible]);

  useEffect(() => {
    if (!visible) return;

    (async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const { LogicalSize } = await import("@tauri-apps/api/dpi");
        const win = getCurrentWindow();
        await win.setSize(new LogicalSize(480, 520));
      } catch {
        /* 忽略窗口操作错误 */
      }
    })();
  }, [visible]);

  if (!visible) return null;

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await saveSettings(buildEnvContent(envValues, extraContent));
      saveUiStyleSettings(styleSettings);
      applyUiStyleSettings(styleSettings);
      onSaved(res.message);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleFieldChange = (key: string, value: string) => {
    setEnvValues((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="flex h-full flex-col overflow-hidden p-4 text-white/85 animate-in fade-in duration-300">
      <div className="flex items-center justify-between border-b border-white/10 pb-2 mb-2">
        <h2 className="text-sm font-semibold text-white">系统设置</h2>
        {path && <p className="text-[10px] text-white/35 truncate max-w-[200px]">{path}</p>}
      </div>

      <div className="flex-1 min-h-0 overflow-hidden flex flex-col relative">
        {loading ? (
          <div className="flex flex-1 items-center justify-center py-10 text-sm text-white/55">正在读取设置...</div>
        ) : (
          <div className="flex-1 space-y-3 overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-white/10 pb-24">
            {ENV_SECTIONS.map((section) => (
              <section key={section.title} className="rounded-[var(--window-radius)] border border-white/10 bg-white/6 p-3">
                <h3 className="mb-2 text-[11px] font-semibold text-white/90">{section.title}</h3>
                <div className="grid gap-3 md:grid-cols-2">
                  {section.fields.map((field) => (
                    <label key={field.key} className="flex flex-col gap-1">
                      <span className="text-[10px] text-white/58">{field.label}</span>
                      {field.type === "select" ? (
                        <>
                          <select
                            value={envValues[field.key] || ""}
                            onChange={(e) => handleFieldChange(field.key, e.target.value)}
                            className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white outline-none transition focus:border-cyan-400/50"
                          >
                            <option value="">请选择</option>
                            {field.options?.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                          {field.key === "ASR_MODE" ? (
                            <span className="text-[10px] text-white/45">webspeech 依赖 Edge/WebView2 的 SpeechRecognition，并需要麦克风权限。</span>
                          ) : field.key === "WEBSPEECH_LANG" ? (
                            <span className="text-[10px] text-white/45">仅在 webspeech 模式下生效，默认使用 zh-CN。</span>
                          ) : null}
                        </>
                      ) : (
                        <input
                          type={field.type ?? "text"}
                          value={envValues[field.key] || ""}
                          onChange={(e) => handleFieldChange(field.key, e.target.value)}
                          placeholder={field.placeholder}
                          className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white outline-none transition focus:border-cyan-400/50 focus:bg-white/8"
                        />
                      )}
                    </label>
                  ))}
                </div>
              </section>
            ))}

            <section className="rounded-[var(--window-radius)] border border-white/10 bg-white/6 p-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-[11px] font-semibold text-white/90">前端外观</h3>
                  <p className="mt-0.5 text-[10px] text-white/45">{styleSummary}</p>
                </div>
                <div className={`style-preview style-preview--${styleSettings.backgroundPreset} h-8 w-16 rounded-lg border border-white/10`} />
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <label className="flex flex-col gap-1">
                  <span className="text-[10px] text-white/58">背景主题</span>
                  <select
                    value={styleSettings.backgroundPreset}
                    onChange={(e) => setStyleSettings((prev) => ({ ...prev, backgroundPreset: e.target.value as UiStyleSettings["backgroundPreset"] }))}
                    className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white outline-none transition focus:border-cyan-400/50"
                  >
                    <option value="ocean">Ocean</option>
                    <option value="sunset">Sunset</option>
                    <option value="forest">Forest</option>
                    <option value="slate">Slate</option>
                  </select>
                </label>

                <label className="flex flex-col gap-1">
                  <span className="text-[10px] text-white/58">圆角 {styleSettings.windowRadius}px</span>
                  <input
                    type="range"
                    min="10"
                    max="28"
                    value={styleSettings.windowRadius}
                    onChange={(e) => setStyleSettings((prev) => ({ ...prev, windowRadius: Number(e.target.value) }))}
                    className="h-1.5"
                  />
                </label>

                <label className="flex flex-col gap-1">
                  <span className="text-[10px] text-white/58">透明度 {Math.round(styleSettings.shellOpacity * 100)}%</span>
                  <input
                    type="range"
                    min="55"
                    max="95"
                    value={Math.round(styleSettings.shellOpacity * 100)}
                    onChange={(e) => setStyleSettings((prev) => ({ ...prev, shellOpacity: Number(e.target.value) / 100 }))}
                    className="h-1.5"
                  />
                </label>

                <label className="flex flex-col gap-1">
                  <span className="text-[10px] text-white/58">缩放 {styleSettings.fontScale.toFixed(2)}x</span>
                  <input
                    type="range"
                    min="90"
                    max="115"
                    value={Math.round(styleSettings.fontScale * 100)}
                    onChange={(e) => setStyleSettings((prev) => ({ ...prev, fontScale: Number(e.target.value) / 100 }))}
                    className="h-1.5"
                  />
                </label>
              </div>
            </section>

            <section className="rounded-[var(--window-radius)] border border-white/10 bg-white/6 p-3">
              <h3 className="mb-2 text-[11px] font-semibold text-white/90">高级原始配置</h3>
              <textarea
                value={extraContent}
                onChange={(e) => setExtraContent(e.target.value)}
                aria-label="其他原始配置"
                title="其他原始配置"
                placeholder="..."
                className="min-h-24 w-full resize-y rounded-lg border border-white/10 bg-white/5 p-2 font-mono text-[10px] leading-5 text-white outline-none transition focus:border-cyan-400/50 focus:bg-white/7"
                spellCheck={false}
              />
            </section>
          </div>
        )}

        {error && <div className="absolute bottom-20 left-0 right-0 rounded-lg border border-red-500/30 bg-red-500/15 px-2 py-1 text-[10px] text-red-200">⚠️ {error}</div>}

        <div className="absolute bottom-3 left-0 right-0 flex items-center justify-end gap-2 rounded-xl border border-white/10 bg-[#1a1c1e]/96 px-3 py-3 shadow-[0_-12px_24px_rgba(0,0,0,0.18)] mt-auto">
          <button
            onClick={onClose}
            disabled={saving}
            className="rounded-lg bg-white/8 px-4 py-1.5 text-xs text-white/70 transition hover:bg-white/14 hover:text-white disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={saving || loading}
            className="rounded-lg bg-cyan-500/20 px-4 py-1.5 text-xs font-semibold text-cyan-200 transition hover:bg-cyan-500/30 disabled:opacity-50"
          >
            {saving ? "保存中..." : "保存设置"}
          </button>
        </div>
      </div>
    </div>
  );
}