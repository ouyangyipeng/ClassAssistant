import {
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
} from "react";
import { AudioLines, FileText, LoaderCircle, Mic, X } from "lucide-react";
import logo from "../../src-tauri/icons/icon.png";
import { Client, getConnection, saveText } from "./client";
import { CaptureController, nativeWindow, windowMode } from "./capture";
import {
  AssistantPane,
  MaterialsPane,
  NotesPane,
  StartClass,
  Transcript,
  Welcome,
} from "./Classroom";
import { Modal, shortDate } from "./primitives";
import { Settings } from "./Settings";
import { RecordingControls, Sidebar, Titlebar } from "./Shell";
import { WorkspaceStore } from "./store";

export default function Workspace() {
  const [store, setStore] = useState<WorkspaceStore | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError(null);
    void getConnection()
      .then((connection) => {
        if (active) setStore(new WorkspaceStore(new Client(connection)));
      })
      .catch((error) => {
        if (active)
          setError(error instanceof Error ? error.message : "本地服务未就绪");
      });
    return () => {
      active = false;
    };
  }, [attempt]);
  if (store)
    return (
      <WorkspaceApp
        key={attempt}
        store={store}
        reconnect={() => {
          store.stop();
          setStore(null);
          setAttempt((value) => value + 1);
        }}
      />
    );
  return (
    <div className="bootstrap">
      <img src={logo} alt="课狐" />
      <span className="eyebrow">CLASSFOX</span>
      <h1>{error ? "暂时没有连接上" : "正在准备课堂工作区"}</h1>
      <p role={error ? "alert" : "status"}>{error ?? "正在连接本地服务…"}</p>
      {error ? (
        <button
          className="button"
          onClick={() => setAttempt((value) => value + 1)}
        >
          重新连接
        </button>
      ) : (
        <LoaderCircle size={22} className="spin" />
      )}
    </div>
  );
}

function WorkspaceApp({
  store,
  reconnect,
}: {
  store: WorkspaceStore;
  reconnect: () => void;
}) {
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const [capture] = useState(() => new CaptureController(store));
  const [page, setPage] = useState<"classroom" | "materials">("classroom");
  const [tab, setTab] = useState<"transcript" | "notes">("transcript");
  const [settings, setSettings] = useState(false);
  const [start, setStart] = useState(false);
  const [closing, setClosing] = useState(false);
  const [compact, setCompact] = useState(false);
  const recoveredBrowser = useRef(false);
  const selected = state.sessions.find(
    (session) => session.id === state.selectedId,
  );
  async function restoreConnection() {
    await capture.stopBrowser();
    const current = store.getSnapshot();
    if (current.unsaved || current.partial) {
      store.patch({ unsaved: current.unsaved || current.partial });
      return;
    }
    reconnect();
  }

  useEffect(() => {
    void store.start();
    return () => {
      store.stop();
      void capture.stopBrowser();
    };
  }, [store, capture]);
  useEffect(() => {
    if (state.loaded && !recoveredBrowser.current) {
      recoveredBrowser.current = true;
      void capture.recoverBrowser().catch((error) => store.report(error));
    }
  }, [state.loaded, capture, store]);
  useEffect(() => {
    void capture.synchronize().catch((error) => store.report(error));
  }, [state.current?.id, state.current?.status, capture, store]);
  useEffect(() => {
    const appearance = state.settings?.appearance;
    if (!appearance) return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme =
        appearance.theme === "system"
          ? media.matches
            ? "dark"
            : "light"
          : appearance.theme;
      document.documentElement.dataset.accent = appearance.accent;
    };
    apply();
    media.addEventListener("change", apply);
    if ("__TAURI_INTERNALS__" in window)
      void import("@tauri-apps/api/window")
        .then(({ getCurrentWindow }) =>
          getCurrentWindow().setAlwaysOnTop(appearance.always_on_top),
        )
        .catch((error) => store.report(error));
    return () => media.removeEventListener("change", apply);
  }, [state.settings?.appearance, store]);
  async function mode(value: boolean) {
    try {
      await windowMode(value);
      setCompact(value);
    } catch (error) {
      store.report(error);
    }
  }
  const begin = () => {
    void mode(false);
    setStart(true);
  };
  const controls = (
    <RecordingControls
      state={state}
      begin={begin}
      control={(action) => capture.control(action)}
    />
  );
  const style = {
    "--font-scale": state.settings?.appearance.font_scale ?? 1,
    "--window-opacity": state.settings?.appearance.opacity ?? 0.96,
    "--radius": `${state.settings?.appearance.window_radius ?? 12}px`,
  } as CSSProperties;

  return (
    <div
      className={`workspace-shell ${compact ? "compact" : ""}`}
      style={style}
    >
      <Titlebar
        store={store}
        compact={compact}
        mode={(value) => void mode(value)}
        close={() =>
          state.current
            ? setClosing(true)
            : void nativeWindow("close").catch((error) => store.report(error))
        }
      />
      {compact ? (
        <div className="compact-body">
          <div>
            <strong>{state.current?.course_name ?? "随时准备上课"}</strong>
            {controls}
          </div>
          <button
            className="button rescue-compact"
            disabled={!state.selectedId || state.busy}
            onClick={() =>
              void store.action(async () => {
                await mode(false);
                const result = await store.api.post<{ id: string }>(
                  `/sessions/${state.selectedId}/assistant`,
                  { kind: "rescue" },
                );
                await store.fetchJob(result.id);
              })
            }
          >
            救场
          </button>
        </div>
      ) : (
        <div className="workspace-layout">
          <Sidebar
            store={store}
            state={state}
            page={page}
            navigate={(value) => {
              setPage(value);
              setTab("transcript");
            }}
            begin={begin}
            settings={() => setSettings(true)}
          />
          <main className="main-workspace">
            {!state.loaded ? (
              <div className="loading-workspace">
                <LoaderCircle className="spin" />
                <p>正在读取课堂…</p>
                {state.error && (
                  <button
                    className="button secondary"
                    onClick={() => void restoreConnection()}
                  >
                    重试连接
                  </button>
                )}
              </div>
            ) : page === "materials" ? (
              <MaterialsPane store={store} materials={state.materials} />
            ) : !selected ? (
              <Welcome begin={begin} settings={() => setSettings(true)} />
            ) : (
              <>
                <header className="class-header">
                  <div>
                    <div className="eyebrow">
                      CLASSROOM / {shortDate(selected.created_at)}
                    </div>
                    <h1>{selected.course_name}</h1>
                    <p>
                      {selected.material_id
                        ? (state.materials.find(
                            (item) => item.id === selected.material_id,
                          )?.filename ?? "已关联课程资料")
                        : "独立保存原文 · 随时回看"}
                    </p>
                  </div>
                  {controls}
                </header>
                <div className="class-content">
                  <section className="class-main">
                    <div className="class-tabs">
                      <div role="tablist" aria-label="课堂内容">
                        <button
                          role="tab"
                          aria-selected={tab === "transcript"}
                          onClick={() => setTab("transcript")}
                        >
                          <AudioLines size={16} />
                          课堂原文
                        </button>
                        <button
                          role="tab"
                          aria-selected={tab === "notes"}
                          onClick={() => setTab("notes")}
                        >
                          <FileText size={16} />
                          课堂笔记{" "}
                          {state.notes.length > 0 && (
                            <span>{state.notes.length}</span>
                          )}
                        </button>
                      </div>
                      <button
                        className="text-button"
                        onClick={() =>
                          void store.action(async () => {
                            const text = await store.api.request<string>(
                              `/sessions/${selected.id}/export`,
                              { text: true },
                            );
                            await saveText(text, "课堂原文.txt");
                          })
                        }
                      >
                        导出原文
                      </button>
                    </div>
                    {tab === "transcript" ? (
                      <Transcript
                        key={selected.id}
                        store={store}
                        state={state}
                        session={selected}
                      />
                    ) : (
                      <NotesPane
                        key={selected.id}
                        store={store}
                        state={state}
                        session={selected}
                      />
                    )}
                  </section>
                  <AssistantPane
                    key={selected.id}
                    store={store}
                    state={state}
                    session={selected}
                  />
                </div>
              </>
            )}
          </main>
        </div>
      )}
      <footer className="statusbar">
        <span>
          <i className={`connection-dot ${state.connection}`} />
          {
            {
              online: "本地服务已连接",
              connecting: "正在连接…",
              offline: "连接中断，正在重连",
              unauthorized: "连接凭据已失效",
            }[state.connection]
          }
        </span>
        {(state.connection === "offline" ||
          state.connection === "unauthorized") && (
          <button
            className="text-button"
            onClick={() => void restoreConnection()}
          >
            恢复本地服务
          </button>
        )}
        {state.current?.status === "recording" &&
          state.source === "microphone" && (
            <span className="input-meter">
              <Mic size={12} />
              <meter
                min={0}
                max={1}
                value={state.level}
                aria-label="麦克风输入音量"
              />
            </span>
          )}
        <span>ClassFox 2.0</span>
      </footer>
      {state.error && (
        <div role="alert" className="error-banner">
          <div>{state.error}</div>
          <button
            className="icon-button"
            aria-label="关闭错误提示"
            onClick={() => store.patch({ error: null })}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {state.unsaved && (
        <Modal
          title="保留未保存的识别文字"
          close={() =>
            store.report(new Error("请先导出文字，或确认已自行保留后再关闭。"))
          }
        >
          <div className="start-form">
            <p>
              这些文字尚未保存到课堂，请先复制或导出。恢复连接后可在原课堂中补充。
            </p>
            <textarea readOnly rows={8} value={state.unsaved} />
            <div className="modal-footer">
              <button
                className="button secondary"
                onClick={() => store.patch({ unsaved: null, partial: "" })}
              >
                我已保留，关闭
              </button>
              <button
                className="button"
                onClick={() =>
                  void saveText(state.unsaved!, "未保存的课堂文字.txt").catch(
                    (error) => store.report(error),
                  )
                }
              >
                导出文字
              </button>
            </div>
          </div>
        </Modal>
      )}
      {state.alert && (
        <div className={`class-alert ${state.alert.level}`} role="alert">
          <div>
            <span className="eyebrow">
              {state.alert.level === "danger" ? "可能点到你了" : "课堂重点提醒"}
            </span>
            <strong>{state.alert.keywords.join(" · ")}</strong>
            <p>{state.alert.text}</p>
          </div>
          <button
            className="button"
            onClick={() => {
              const id = state.alert!.session_id;
              store.patch({ alert: null });
              setPage("classroom");
              void mode(false);
              void store.select(id);
            }}
          >
            查看课堂
          </button>
          <button
            className="icon-button"
            aria-label="忽略提醒"
            onClick={() => store.patch({ alert: null })}
          >
            <X size={17} />
          </button>
        </div>
      )}
      {start && (
        <StartClass
          store={store}
          state={state}
          close={() => setStart(false)}
          cancel={() => capture.control("stop")}
          start={async (name, source, material) => {
            await capture.start(name, source, material);
            setPage("classroom");
            setTab("transcript");
          }}
        />
      )}
      {settings && state.settings && (
        <Settings
          store={store}
          preferences={state.settings}
          models={state.models}
          credentials={state.credentials}
          credentialError={state.credentialError}
          close={() => setSettings(false)}
        />
      )}
      {closing && (
        <Modal title="结束课堂并退出？" close={() => setClosing(false)}>
          <div className="start-form">
            <p>
              退出后录音会停止，已保存的原文会保留。仍在生成的回答可能被取消。
            </p>
            <div className="modal-footer">
              <button
                className="button secondary"
                onClick={() => setClosing(false)}
              >
                留在课堂
              </button>
              <button
                className="button"
                disabled={state.busy}
                onClick={async () => {
                  await capture.control("stop");
                  if (!store.getSnapshot().current)
                    await nativeWindow("close").catch((error) =>
                      store.report(error),
                    );
                }}
              >
                结束并退出
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
