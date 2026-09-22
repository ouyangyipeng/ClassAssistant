import { useEffect, useState } from "react";
import {
  AudioLines,
  Expand,
  FolderOpen,
  Maximize2,
  Minus,
  PanelLeftClose,
  Pause,
  Play,
  Plus,
  Settings2,
  ShieldCheck,
  Square,
  X,
} from "lucide-react";
import logo from "../../src-tauri/icons/icon.png";
import { nativeWindow } from "./capture";
import { statusLabel } from "./domain";
import { shortDate, shortTime } from "./primitives";
import { WorkspaceStore, type WorkspaceState } from "./store";

export function Titlebar({
  store,
  compact,
  mode,
  close,
}: {
  store: WorkspaceStore;
  compact: boolean;
  mode: (compact: boolean) => void;
  close: () => void;
}) {
  return (
    <header className="titlebar" data-tauri-drag-region>
      <div className="titlebar-brand" data-tauri-drag-region>
        <img src={logo} alt="" />
        <b>课狐</b>
        <span>ClassFox</span>
      </div>
      {!compact && (
        <span className="titlebar-note" data-tauri-drag-region>
          专注当下，也不错过重点
        </span>
      )}
      <div className="window-controls">
        <button
          className="icon-button"
          aria-label={compact ? "展开工作区" : "切换紧凑模式"}
          onClick={() => mode(!compact)}
        >
          {compact ? <Expand size={15} /> : <PanelLeftClose size={15} />}
        </button>
        <button
          className="icon-button"
          aria-label="最小化窗口"
          onClick={() =>
            void nativeWindow("minimize").catch((error) => store.report(error))
          }
        >
          <Minus size={15} />
        </button>
        {!compact && (
          <button
            className="icon-button"
            aria-label="最大化窗口"
            onClick={() =>
              void nativeWindow("toggleMaximize").catch((error) =>
                store.report(error),
              )
            }
          >
            <Maximize2 size={13} />
          </button>
        )}
        <button
          className="icon-button close-window"
          aria-label="关闭窗口"
          onClick={close}
        >
          <X size={16} />
        </button>
      </div>
    </header>
  );
}

export function Sidebar({
  store,
  state,
  page,
  navigate,
  begin,
  settings,
}: {
  store: WorkspaceStore;
  state: WorkspaceState;
  page: string;
  navigate: (page: "classroom" | "materials") => void;
  begin: () => void;
  settings: () => void;
}) {
  return (
    <aside className="sidebar">
      <button
        className="new-class"
        disabled={!!state.current || state.connection !== "online"}
        onClick={begin}
      >
        <Plus size={16} />
        新课堂
      </button>
      <nav className="primary-nav" aria-label="工作区">
        <button
          aria-current={page === "classroom" ? "page" : undefined}
          onClick={() => navigate("classroom")}
        >
          <AudioLines size={18} />
          课堂工作区
        </button>
        <button
          aria-current={page === "materials" ? "page" : undefined}
          onClick={() => navigate("materials")}
        >
          <FolderOpen size={18} />
          课程资料<span>{state.materials.length || ""}</span>
        </button>
      </nav>
      <div className="sidebar-label">
        课堂记录 <span>{state.sessions.length}</span>
      </div>
      <nav className="session-list" aria-label="课堂历史">
        {state.sessions.map((session) => (
          <button
            key={session.id}
            className={
              state.selectedId === session.id && page === "classroom"
                ? "selected"
                : ""
            }
            onClick={() => {
              navigate("classroom");
              void store.select(session.id);
            }}
          >
            <span
              className={`session-indicator ${session.status === "recording" ? "recording" : ""}`}
            />
            <div>
              <strong>{session.course_name}</strong>
              <span>
                {shortDate(session.created_at)} ·{" "}
                {shortTime(session.created_at).slice(0, 5)}
              </span>
            </div>
          </button>
        ))}
        {!state.sessions.length && (
          <p className="no-history">
            每堂课的原文和笔记
            <br />
            都会留在这里。
          </p>
        )}
        {state.moreSessions && (
          <button
            className="text-button"
            disabled={state.busy}
            onClick={() => void store.moreHistory()}
          >
            加载更早的课堂
          </button>
        )}
      </nav>
      <div className="sidebar-bottom">
        <button onClick={settings} disabled={!state.settings}>
          <Settings2 size={17} />
          设置与模型
        </button>
        <div className="local-indicator">
          <ShieldCheck size={14} />
          <span>课堂记录保存在本机</span>
        </div>
      </div>
    </aside>
  );
}

export function RecordingControls({
  state,
  begin,
  control,
}: {
  state: WorkspaceState;
  begin: () => void;
  control: (action: "pause" | "resume" | "stop") => Promise<void>;
}) {
  const [elapsed, setElapsed] = useState("");
  useEffect(() => {
    const update = () => {
      const seconds = state.current
        ? Math.max(
            0,
            Math.floor(
              (Date.now() - Date.parse(state.current.created_at)) / 1000,
            ),
          )
        : 0;
      setElapsed(
        `${Math.floor(seconds / 60)
          .toString()
          .padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`,
      );
    };
    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, [state.current?.id]);
  return (
    <div className="recording-controls">
      {state.current ? (
        <>
          <span className={`status-pill status-${state.current.status}`}>
            <span
              className={
                state.current.status === "recording" ? "live-dot" : "status-dot"
              }
            />
            {state.stopping ? "正在结束…" : statusLabel[state.current.status]}{" "}
            <time>{elapsed}</time>
          </span>
          <button
            className="icon-button"
            disabled={
              state.busy ||
              state.stopping ||
              state.current.status === "starting"
            }
            aria-label={
              state.current.status === "recording" ? "暂停记录" : "继续记录"
            }
            onClick={() =>
              void control(
                state.current!.status === "recording" ? "pause" : "resume",
              )
            }
          >
            {state.current.status === "recording" ? (
              <Pause size={17} />
            ) : (
              <Play size={17} />
            )}
          </button>
          <button
            className="icon-button stop-recording"
            aria-label="结束课堂"
            disabled={
              (state.busy && state.current.status !== "starting") ||
              state.stopping
            }
            onClick={() => void control("stop")}
          >
            <Square size={15} />
          </button>
        </>
      ) : (
        <button
          className="button"
          disabled={state.connection !== "online"}
          onClick={begin}
        >
          <Plus size={17} />
          开始上课
        </button>
      )}
    </div>
  );
}
