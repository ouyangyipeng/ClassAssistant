import { useState } from "react";
import { Check, Cpu, Download, LoaderCircle, Mic, Play, X } from "lucide-react";
import type { ModelInfo, Preferences } from "./domain";
import { fileSize } from "./primitives";
import { WorkspaceStore } from "./store";

export function ModelSettings({
  store,
  models,
  preferences,
  save,
}: {
  store: WorkspaceStore;
  models: ModelInfo[];
  preferences: Preferences;
  save: (value: Preferences) => void;
}) {
  const [warming, setWarming] = useState(false);
  const [warm, setWarm] = useState(false);
  const install = (id: string, cancel: boolean) => {
    void store.action(async () => {
      await store.api.request(`/models/${id}/install`, {
        method: cancel ? "DELETE" : "POST",
      });
      await store.refresh();
    });
  };
  return (
    <section className="settings-section">
      <div className="section-heading">
        <h3>模型在你的电脑上运行</h3>
        <p>
          下载后无需联网处理课堂内容。第一次加载会稍慢，开始上课前可先准备问答模型。
        </p>
      </div>
      <div className="model-list">
        {models.map(({ model, installation }) => {
          const working = ["downloading", "verifying", "loading"].includes(
            installation.status,
          );
          const ready = installation.status === "ready";
          const percent = installation.total_bytes
            ? Math.min(
                100,
                (installation.downloaded_bytes / installation.total_bytes) *
                  100,
              )
            : 0;
          return (
            <article key={model.id} className="model-row">
              <div className="model-symbol">
                {model.kind === "asr" ? <Mic size={21} /> : <Cpu size={21} />}
              </div>
              <div className="model-info">
                <div className="row">
                  <span className="eyebrow">
                    {model.kind === "asr" ? "语音识别" : "课堂问答"}
                  </span>
                  <span className="muted">
                    {fileSize(
                      model.files.reduce((total, file) => total + file.size, 0),
                    )}
                  </span>
                </div>
                <h4>{model.name}</h4>
                <p>{model.description}</p>
                <a
                  className="text-link"
                  href={model.license_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {model.license_name}
                </a>
                <div
                  className={`installation-message ${installation.status === "failed" ? "error-text" : ""}`}
                  role="status"
                >
                  {ready ? (
                    <Check size={14} />
                  ) : working ? (
                    <LoaderCircle size={14} className="spin" />
                  ) : null}
                  {installation.message}
                </div>
                {working && (
                  <progress
                    max={100}
                    value={percent}
                    aria-label={`${model.name} 下载进度`}
                  />
                )}
              </div>
              <button
                className={ready ? "button secondary" : "button"}
                disabled={ready}
                onClick={() => install(model.id, working)}
              >
                {ready ? (
                  <Check size={16} />
                ) : working ? (
                  <X size={16} />
                ) : (
                  <Download size={16} />
                )}
                {ready
                  ? "已安装"
                  : working
                    ? "取消"
                    : installation.status === "failed"
                      ? "重试安装"
                      : "下载安装"}
              </button>
            </article>
          );
        })}
      </div>
      <div className="settings-footer inline">
        <button
          className="button"
          disabled={
            warming ||
            !models.some(
              (item) =>
                item.model.kind === "llm" &&
                item.installation.status === "ready",
            )
          }
          onClick={async () => {
            setWarming(true);
            setWarm(false);
            try {
              await store.api.post(
                `/models/${preferences.llm.local_model_id}/start`,
                undefined,
                150000,
              );
              setWarm(true);
            } catch (error) {
              store.report(error);
            } finally {
              setWarming(false);
            }
          }}
        >
          {warming ? (
            <LoaderCircle className="spin" size={16} />
          ) : (
            <Play size={16} />
          )}
          {warming ? "正在准备模型…" : warm ? "问答模型已就绪" : "准备问答模型"}
        </button>
        <button
          className="button secondary"
          onClick={() =>
            save({
              ...preferences,
              llm: { ...preferences.llm, mode: "local", managed: true },
              asr: { ...preferences.asr, mode: "offline" },
            })
          }
        >
          使用本地语音与问答
        </button>
      </div>
      <p className="field-help">
        下载需要互联网和额外的临时磁盘空间。安装包含文件校验与模型加载检查；具体速度取决于电脑性能。
        macOS 上的本地问答需要 13.3 或以上，较旧系统可选择 BYOK。
      </p>
    </section>
  );
}
