import { useState, type ReactNode } from "react";
import {
  Check,
  Cpu,
  KeyRound,
  Mic,
  Palette,
  RefreshCw,
  SlidersHorizontal,
  FolderInput,
  Smartphone,
} from "lucide-react";
import type {
  CredentialName,
  Credentials,
  ModelInfo,
  Preferences,
} from "./domain";
import { Modal } from "./primitives";
import { ModelSettings } from "./ModelSettings";
import { PhoneSettings } from "./PhoneSettings";
import { WorkspaceStore } from "./store";
import { importAppearance, legacyAppearanceKey } from "./appearance";
import { describeImport, type LegacyImportResult } from "./legacyImport";

type Tab =
  "models" | "providers" | "audio" | "phone" | "preferences" | "import";
const tabs: { id: Tab; label: string; icon: ReactNode }[] = [
  { id: "models", label: "本地模型", icon: <Cpu size={17} /> },
  { id: "providers", label: "问答服务", icon: <KeyRound size={17} /> },
  { id: "audio", label: "语音与麦克风", icon: <Mic size={17} /> },
  { id: "phone", label: "微信预览 · v2.5", icon: <Smartphone size={17} /> },
  {
    id: "preferences",
    label: "提醒与外观",
    icon: <SlidersHorizontal size={17} />,
  },
  { id: "import", label: "导入旧版本", icon: <FolderInput size={17} /> },
];

const providerPresets = [
  {
    id: "dashscope",
    label: "阿里云百炼 · 北京",
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
  },
  {
    id: "dashscope-intl",
    label: "阿里云百炼 · 新加坡",
    base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
  },
  {
    id: "deepseek",
    label: "DeepSeek",
    base_url: "https://api.deepseek.com",
    model: "deepseek-flash",
  },
];

function SecretField({
  name,
  title,
  store,
  credentials,
}: {
  name: CredentialName;
  title: string;
  store: WorkspaceStore;
  credentials: Credentials | null;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  async function update(remove: boolean) {
    setBusy(true);
    try {
      await store.api.request(`/credentials/${name}`, {
        method: remove ? "DELETE" : "PUT",
        body: remove ? undefined : JSON.stringify({ value: value.trim() }),
      });
      setValue("");
      await store.refreshCredentials();
    } catch (error) {
      store.report(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="secret-field">
      <label>
        {title}
        <span className={credentials?.[name] ? "success-text" : "muted"}>
          {credentials?.[name] ? " 已配置" : " 未配置"}
        </span>
        <input
          type="password"
          autoComplete="off"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="输入新凭据，不会显示已保存的内容"
        />
      </label>
      <div className="row">
        <button
          className="button secondary small"
          disabled={!value.trim() || busy}
          onClick={() => void update(false)}
        >
          保存凭据
        </button>
        {credentials?.[name] && (
          <button
            className="text-button"
            disabled={busy}
            onClick={() => void update(true)}
          >
            移除
          </button>
        )}
      </div>
    </div>
  );
}

export function Settings({
  store,
  preferences,
  models,
  credentials,
  credentialError,
  close,
  initialTab = "models",
}: {
  store: WorkspaceStore;
  preferences: Preferences;
  models: ModelInfo[];
  credentials: Credentials | null;
  credentialError: string | null;
  close: () => void;
  initialTab?: Tab;
}) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const [draft, setDraft] = useState<Preferences>(structuredClone(preferences));
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [preset, setPreset] = useState("custom");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const save = async (value = draft) => {
    setSaving(true);
    setSaved(false);
    try {
      const settings = await store.api.request<Preferences>("/settings", {
        method: "PUT",
        body: JSON.stringify(value),
      });
      setDraft(settings);
      store.patch({ settings });
      setSaved(true);
      return true;
    } catch (error) {
      store.report(error);
      return false;
    } finally {
      setSaving(false);
    }
  };
  const update = (value: Preferences) => {
    setDraft(value);
    setSaved(false);
    setTestResult(null);
  };
  const setLLM = (change: Partial<Preferences["llm"]>) =>
    update({ ...draft, llm: { ...draft.llm, ...change } });
  async function testConnection() {
    setTesting(true);
    setTestResult(null);
    try {
      if (!(await save())) return;
      const result = await store.api.post<{
        ok: boolean;
        first_token_ms: number;
        total_ms: number;
      }>("/assistant/test", undefined, 45000);
      if (result.ok)
        setTestResult(
          `连接成功 · 首字 ${result.first_token_ms} ms · 总耗时 ${result.total_ms} ms`,
        );
    } catch (error) {
      store.report(error);
    } finally {
      setTesting(false);
    }
  }
  return (
    <Modal title="设置" close={close} wide>
      <div className="settings-layout">
        <nav className="settings-nav" aria-label="设置分类">
          {tabs.map((item) => (
            <button
              key={item.id}
              aria-current={tab === item.id ? "page" : undefined}
              onClick={() => setTab(item.id)}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </nav>
        <div className="settings-body">
          {store.getSnapshot().error && (
            <p role="alert" className="notice error">
              {store.getSnapshot().error}
            </p>
          )}
          {credentialError && (
            <p role="alert" className="notice error">
              {credentialError}。已安装的离线功能仍可使用。
            </p>
          )}
          {tab === "models" && (
            <ModelSettings
              store={store}
              models={models}
              preferences={draft}
              save={(value) => void save(value)}
            />
          )}
          {tab === "providers" && (
            <section className="settings-section">
              <div className="section-heading">
                <h3>选择课堂问答服务</h3>
                <p>
                  语音和问答可以分别选择。云端模式会把问题及必要的课堂内容发送给所选服务商。
                </p>
              </div>
              <label>
                运行方式
                <select
                  value={
                    draft.llm.mode === "byok"
                      ? "byok"
                      : draft.llm.managed
                        ? "managed"
                        : "external"
                  }
                  onChange={(event) =>
                    setLLM({
                      mode: event.target.value === "byok" ? "byok" : "local",
                      managed: event.target.value === "managed",
                    })
                  }
                >
                  <option value="managed">课狐管理的本地模型</option>
                  <option value="external">已有本地模型服务</option>
                  <option value="byok">云端服务 · 自带 API Key</option>
                </select>
              </label>
              {(draft.llm.mode === "byok" || !draft.llm.managed) && (
                <>
                  {draft.llm.mode === "byok" && (
                    <label>
                      服务商预设
                      <select
                        value={preset}
                        onChange={(event) => {
                          setPreset(event.target.value);
                          const selected = providerPresets.find(
                            (value) => value.id === event.target.value,
                          );
                          if (selected)
                            setLLM({
                              base_url: selected.base_url,
                              model: selected.model,
                            });
                        }}
                      >
                        <option value="custom">自定义兼容服务</option>
                        {providerPresets.map((value) => (
                          <option key={value.id} value={value.id}>
                            {value.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <label>
                    兼容 OpenAI 的服务地址
                    <input
                      type="url"
                      value={draft.llm.base_url}
                      onChange={(event) => {
                        setPreset("custom");
                        setLLM({ base_url: event.target.value });
                      }}
                      placeholder="https://api.example.com/v1"
                    />
                  </label>
                  <label>
                    模型名称
                    <input
                      value={draft.llm.model}
                      onChange={(event) =>
                        setLLM({ model: event.target.value })
                      }
                      placeholder="服务商提供的模型 ID"
                    />
                  </label>
                </>
              )}
              {draft.llm.mode === "byok" && (
                <SecretField
                  name="llm"
                  title="问答 API Key"
                  store={store}
                  credentials={credentials}
                />
              )}
              <div className="field-grid">
                <label>
                  响应时限（秒）
                  <input
                    type="number"
                    min={5}
                    max={180}
                    value={draft.llm.timeout_seconds}
                    onChange={(event) =>
                      setLLM({ timeout_seconds: Number(event.target.value) })
                    }
                  />
                </label>
                <label>
                  上下文字数上限
                  <input
                    type="number"
                    min={1000}
                    max={64000}
                    step={1000}
                    value={draft.llm.context_characters}
                    onChange={(event) =>
                      setLLM({ context_characters: Number(event.target.value) })
                    }
                  />
                </label>
              </div>
              <p className="field-help">
                课狐管理的本地模型会采用适合该模型的上下文预算。桌面密钥保存在系统凭据存储中。
              </p>
              <button
                className="button secondary"
                disabled={testing || saving}
                onClick={() => void testConnection()}
              >
                {testing ? "正在测试连接…" : "保存配置并测试连接"}
              </button>
              <p className="field-help">
                只发送一句连接测试，不发送课堂内容。云端按服务商规则计费；更换服务地址后请填写对应的
                API Key。
              </p>
              {testResult && (
                <p role="status" className="success-text">
                  {testResult}
                </p>
              )}
            </section>
          )}
          {tab === "audio" && (
            <AudioSettings
              store={store}
              draft={draft}
              update={update}
              credentials={credentials}
            />
          )}
          {tab === "phone" && <PhoneSettings store={store} />}
          {tab === "preferences" && (
            <PreferencesSettings draft={draft} update={update} />
          )}
          {tab === "import" && (
            <ImportSettings
              store={store}
              imported={() => {
                const settings = store.getSnapshot().settings;
                if (settings) {
                  setDraft(structuredClone(settings));
                  setSaved(false);
                }
              }}
            />
          )}
          {tab !== "import" && tab !== "models" && (
            <div className="settings-footer">
              <span role="status" className="success-text">
                {saved && (
                  <>
                    <Check size={16} /> 已保存
                  </>
                )}
              </span>
              <button
                className="button"
                disabled={saving}
                onClick={() => void save()}
              >
                {saving ? "正在保存…" : "保存设置"}
              </button>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}

function AudioSettings({
  store,
  draft,
  update,
  credentials,
}: {
  store: WorkspaceStore;
  draft: Preferences;
  update: (value: Preferences) => void;
  credentials: Credentials | null;
}) {
  const [devices, setDevices] = useState<
    { id: number; name: string; default: boolean }[]
  >([]);
  const [checking, setChecking] = useState(false);
  const [deviceResult, setDeviceResult] = useState<string | null>(null);
  const asr = draft.asr;
  const set = (change: Partial<Preferences["asr"]>) =>
    update({ ...draft, asr: { ...asr, ...change } });
  return (
    <section className="settings-section">
      <div className="section-heading">
        <h3>语音识别与输入设备</h3>
        <p>
          设备权限与识别连接会在开始上课时检查。更改设置后，从下一次开始或恢复录音生效。
        </p>
      </div>
      <label>
        识别方式
        <select
          value={asr.mode}
          onChange={(event) =>
            set({ mode: event.target.value as Preferences["asr"]["mode"] })
          }
        >
          <option value="offline">离线 · SenseVoice</option>
          <option value="dashscope">阿里云 · Fun-ASR</option>
          <option value="seed-asr">火山引擎 · 豆包语音</option>
          <option value="openai">兼容 OpenAI 的音频识别</option>
          <option value="webspeech">浏览器语音识别</option>
          <option value="google">Google 在线兼容模式</option>
        </select>
      </label>
      <div className="field-grid">
        <label>
          识别语言
          <select
            value={asr.language}
            onChange={(event) => set({ language: event.target.value })}
          >
            <option value="zh-CN">中文</option>
            <option value="en-US">英语</option>
            <option value="ja-JP">日语</option>
            <option value="ko-KR">韩语</option>
            <option value="yue-CN">粤语</option>
            <option value="auto">自动检测（服务支持时）</option>
          </select>
        </label>
        <label>
          麦克风
          <select
            value={asr.input_device ?? "default"}
            onChange={(event) =>
              set({
                input_device:
                  event.target.value === "default"
                    ? null
                    : Number(event.target.value),
              })
            }
          >
            <option value="default">系统默认设备</option>
            {devices.map((device) => (
              <option key={device.id} value={device.id}>
                {device.name}
                {device.default ? "（默认）" : ""}
              </option>
            ))}
          </select>
        </label>
      </div>
      <button
        className="button secondary small"
        disabled={checking}
        onClick={async () => {
          setChecking(true);
          try {
            const list =
              await store.api.request<typeof devices>("/audio/devices");
            setDevices(list);
            setDeviceResult(
              list.length
                ? `检测到 ${list.length} 个输入设备`
                : "未检测到输入设备，请连接麦克风",
            );
          } catch (error) {
            store.report(error);
          } finally {
            setChecking(false);
          }
        }}
      >
        <RefreshCw size={14} className={checking ? "spin" : ""} />
        检测麦克风
      </button>
      {deviceResult && (
        <p className="field-help" role="status">
          {deviceResult}
        </p>
      )}
      {asr.mode === "dashscope" && (
        <>
          <label>
            接入地域
            <select
              value={asr.dashscope_region}
              onChange={(event) =>
                set({
                  dashscope_region: event.target.value as
                    "beijing" | "singapore",
                })
              }
            >
              <option value="beijing">北京</option>
              <option value="singapore">新加坡</option>
            </select>
          </label>
          <label>
            语音模型
            <input
              value={asr.dashscope_model}
              onChange={(event) => set({ dashscope_model: event.target.value })}
            />
          </label>
          <SecretField
            name="dashscope"
            title="阿里云 API Key"
            store={store}
            credentials={credentials}
          />
        </>
      )}
      {asr.mode === "seed-asr" && (
        <>
          <label>
            已开通的语音资源
            <select
              value={asr.seed_resource_id}
              onChange={(event) =>
                set({ seed_resource_id: event.target.value })
              }
            >
              {[
                "volc.seedasr.sauc.duration",
                "volc.seedasr.sauc.concurrent",
                "volc.bigasr.sauc.duration",
                "volc.bigasr.sauc.concurrent",
              ].map((id) => (
                <option key={id} value={id}>
                  {id.includes("seedasr") ? "2.0" : "1.0"} ·{" "}
                  {id.endsWith("duration") ? "按时长" : "并发包"}
                </option>
              ))}
            </select>
          </label>
          <SecretField
            name="seed_api"
            title="新控制台 API Key"
            store={store}
            credentials={credentials}
          />
          <details>
            <summary>使用旧控制台 App ID 与 Access Token</summary>
            <SecretField
              name="seed_app"
              title="App ID"
              store={store}
              credentials={credentials}
            />
            <SecretField
              name="seed_access"
              title="Access Token"
              store={store}
              credentials={credentials}
            />
          </details>
          <p className="field-help">
            配置了新 API Key 时优先使用新控制台凭据。
          </p>
        </>
      )}
      {asr.mode === "openai" && (
        <>
          <label>
            语音服务地址
            <input
              type="url"
              value={asr.base_url}
              onChange={(event) => set({ base_url: event.target.value })}
            />
          </label>
          <label>
            语音模型
            <input
              value={asr.model}
              onChange={(event) => set({ model: event.target.value })}
            />
          </label>
          <SecretField
            name="asr"
            title="语音 API Key"
            store={store}
            credentials={credentials}
          />
        </>
      )}
      {asr.mode === "webspeech" && (
        <p className="notice">
          是否可用取决于当前浏览器或桌面
          WebView；通常需要联网。不可用时，可选择离线识别或直接输入课堂文字。
        </p>
      )}
      {asr.mode === "google" && (
        <p className="notice">
          这是旧版在线兼容接口，不是离线识别。网络与服务可用性没有保证，建议优先选择其他模式。
        </p>
      )}
    </section>
  );
}

function PreferencesSettings({
  draft,
  update,
}: {
  draft: Preferences;
  update: (value: Preferences) => void;
}) {
  const setAppearance = (change: Partial<Preferences["appearance"]>) =>
    update({ ...draft, appearance: { ...draft.appearance, ...change } });
  return (
    <section className="settings-section">
      <div className="section-heading">
        <h3>让课狐适合你的课堂</h3>
        <p>提醒只基于已识别的文字。建议同时添加姓名、昵称和老师常用的称呼。</p>
      </div>
      <label>
        点名关键词（每行一个）
        <textarea
          rows={3}
          value={draft.keywords.join("\n")}
          onChange={(event) =>
            update({ ...draft, keywords: event.target.value.split("\n") })
          }
          placeholder="例如：你的姓名、学号、昵称"
        />
      </label>
      <label>
        重点提醒词（每行一个）
        <textarea
          rows={3}
          value={draft.warning_keywords.join("\n")}
          onChange={(event) =>
            update({
              ...draft,
              warning_keywords: event.target.value.split("\n"),
            })
          }
        />
      </label>
      <label className="check-label">
        <input
          type="checkbox"
          checked={draft.auto_summary}
          onChange={(event) =>
            update({ ...draft, auto_summary: event.target.checked })
          }
        />
        结束后自动整理笔记
        <span className="field-help">云端模型会消耗你的服务商额度。</span>
      </label>
      <h4 className="subheading">
        <Palette size={16} />
        外观
      </h4>
      <div className="field-grid">
        <label>
          主题
          <select
            value={draft.appearance.theme}
            onChange={(event) =>
              setAppearance({
                theme: event.target.value as Preferences["appearance"]["theme"],
              })
            }
          >
            <option value="system">跟随系统</option>
            <option value="light">浅色</option>
            <option value="dark">深色</option>
          </select>
        </label>
        <label>
          强调色
          <select
            value={draft.appearance.accent}
            onChange={(event) =>
              setAppearance({
                accent: event.target
                  .value as Preferences["appearance"]["accent"],
              })
            }
          >
            <option value="amber">暖橙</option>
            <option value="blue">海蓝</option>
            <option value="green">森林</option>
            <option value="slate">石墨</option>
          </select>
        </label>
      </div>
      <label>
        字号 · {Math.round(draft.appearance.font_scale * 100)}%
        <input
          type="range"
          min="0.85"
          max="1.5"
          step="0.05"
          value={draft.appearance.font_scale}
          onChange={(event) =>
            setAppearance({ font_scale: Number(event.target.value) })
          }
        />
      </label>
      <label>
        窗口不透明度 · {Math.round(draft.appearance.opacity * 100)}%
        <input
          type="range"
          min="0.6"
          max="1"
          step="0.02"
          value={draft.appearance.opacity}
          onChange={(event) =>
            setAppearance({ opacity: Number(event.target.value) })
          }
        />
      </label>
      <label className="check-label">
        <input
          type="checkbox"
          checked={draft.appearance.always_on_top}
          onChange={(event) =>
            setAppearance({ always_on_top: event.target.checked })
          }
        />
        窗口保持置顶
      </label>
      <label>
        窗口圆角 · {draft.appearance.window_radius} px
        <input
          type="range"
          min="0"
          max="30"
          step="1"
          value={draft.appearance.window_radius}
          onChange={(event) =>
            setAppearance({ window_radius: Number(event.target.value) })
          }
        />
      </label>
    </section>
  );
}

function ImportSettings({
  store,
  imported,
}: {
  store: WorkspaceStore;
  imported: () => void;
}) {
  const [directory, setDirectory] = useState("");
  const [config, setConfig] = useState("");
  const [result, setResult] = useState<string | null>(null);
  return (
    <section className="settings-section">
      <div className="section-heading">
        <h3>带回旧版课堂记录</h3>
        <p>
          显式导入旧数据目录和配置；原文件会保留。旧版本已经压缩或覆盖的原文无法恢复。
        </p>
      </div>
      <label>
        旧版数据目录
        <input
          value={directory}
          onChange={(event) => setDirectory(event.target.value)}
          placeholder="旧版本中的 data 文件夹完整路径"
        />
      </label>
      <button
        className="button secondary"
        disabled={!directory.trim()}
        onClick={() =>
          void store.action(async () => {
            const response = await store.api.post<LegacyImportResult>(
              "/import",
              { directory: directory.trim() },
              60000,
            );
            await store.refresh();
            setResult(describeImport(response));
          })
        }
      >
        导入课堂与资料
      </button>
      <label>
        旧版 .env 文件
        <input
          value={config}
          onChange={(event) => setConfig(event.target.value)}
          placeholder="你自己的 .env 文件完整路径"
        />
      </label>
      <button
        className="button secondary"
        disabled={!config.trim()}
        onClick={() =>
          void store.action(async () => {
            await store.api.post("/import-config", { path: config.trim() });
            await store.refresh();
            imported();
            setResult("配置导入完成。已有设置与已配置的凭据优先保留。");
          })
        }
      >
        导入旧设置与凭据
      </button>
      {result && (
        <p role="status" className="notice success">
          {result}
        </p>
      )}
      <div className="section-heading">
        <h3>旧版外观偏好</h3>
        <p>
          读取本设备旧版应用保存的颜色、字号、透明度和圆角，映射到新的界面。原设置保留。
        </p>
      </div>
      <button
        className="button secondary"
        onClick={() =>
          void store.action(async () => {
            const preferences = store.getSnapshot().settings;
            if (!preferences) return;
            const appearance = importAppearance(
              localStorage.getItem(legacyAppearanceKey),
              preferences.appearance,
            );
            const settings = await store.api.request<Preferences>("/settings", {
              method: "PUT",
              body: JSON.stringify({ ...preferences, appearance }),
            });
            store.patch({ settings });
            imported();
            setResult("外观已导入。原来的深色方案已映射到相近的强调色。");
          })
        }
      >
        导入本机旧版外观
      </button>
    </section>
  );
}
