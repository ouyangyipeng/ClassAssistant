/**
 * 上课摸鱼搭子 - 主应用组件
 * =========================
 * 整合所有子组件，管理全局状态
 */

import { useCallback, useEffect, useState } from "react";
import TitleBar from "./components/TitleBar";
import ToolBar from "./components/ToolBar";
import AlertOverlay from "./components/AlertOverlay";
import RescuePanel from "./components/RescuePanel";
import CatchupPanel from "./components/CatchupPanel";
import StartMonitorPanel from "./components/StartMonitorPanel";
import SettingsPanel from "./components/SettingsPanel";
import ToastContainer, { type ToastMessage } from "./components/Toast";
import { useWebSocket } from "./hooks/useWebSocket";
import classFoxIcon from "../src-tauri/icons/icon.png";
import {
  uploadPPT,
  startMonitor,
  pauseMonitor,
  resumeMonitor,
  stopMonitorWithSummary,
} from "./services/api";
import { applyUiStyleSettings, readUiStyleSettings } from "./services/preferences";

// Toast ID 计数器
let toastId = 0;

function SplashScreen() {
  return (
    <div className="splash-scene flex h-full w-full items-center justify-center bg-transparent">
      <div className="startup-card flex flex-col items-center bg-transparent px-6 py-5 text-center">
        <div className="startup-ring mb-4 flex h-24 w-24 items-center justify-center rounded-full border border-cyan-300/20 bg-white/6">
          <img src={classFoxIcon} alt="课狐 ClassFox" className="startup-logo h-14 w-14 object-contain" />
        </div>
        <p className="text-base font-semibold tracking-[0.18em] text-white/92">课狐启动中</p>
        <p className="mt-2 text-[11px] leading-6 text-cyan-50/70">ClassFox — Hears what you miss.</p>
      </div>
    </div>
  );
}

function MainApp() {
  // ---- 状态管理 ----
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [showRescuePanel, setShowRescuePanel] = useState(false);
  const [showCatchupPanel, setShowCatchupPanel] = useState(false);
  const [showStartMonitorPanel, setShowStartMonitorPanel] = useState(false);
  const [showSettingsPanel, setShowSettingsPanel] = useState(false);
  const [citeRefreshToken, setCiteRefreshToken] = useState(0);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [activeCourseName, setActiveCourseName] = useState("");

  // WebSocket 连接
  const { lastAlert, alertActive, connect, disconnect, dismissAlert } =
    useWebSocket();

  useEffect(() => {
    applyUiStyleSettings(readUiStyleSettings());
  }, []);

  // ---- Toast 管理 ----
  const addToast = useCallback(
    (text: string, type: ToastMessage["type"] = "info") => {
      const id = ++toastId;
      setToasts((prev) => [...prev, { id, text, type }]);
    },
    []
  );

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // ---- 上传 PPT ----
  const handleUpload = useCallback(
    async (file: File) => {
      setIsLoading(true);
      try {
        const res = await uploadPPT(file);
        addToast(res.message, "success");
        setCiteRefreshToken((prev) => prev + 1);
      } catch (err) {
        addToast(
          `上传失败: ${err instanceof Error ? err.message : "未知错误"}`,
          "error"
        );
      } finally {
        setIsLoading(false);
      }
    },
    [addToast]
  );

  // ---- 开始/停止摸鱼 ----
  const handleStopMonitor = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await stopMonitorWithSummary();
      disconnect();
      setIsMonitoring(false);
      setIsPaused(false);
      setActiveCourseName("");
      addToast(res.message, "info");
      if (res.summary?.filename) {
        addToast(`已自动生成总结: ${res.summary.filename}`, "success");
      } else if (res.summary_error) {
        addToast(res.summary_error, "error");
      }
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const { LogicalSize } = await import("@tauri-apps/api/dpi");
        await getCurrentWindow().setSize(new LogicalSize(320, 80));
      } catch {
        /* 忽略窗口操作错误 */
      }
    } catch (err) {
      addToast(
        `操作失败: ${err instanceof Error ? err.message : "未知错误"}`,
        "error"
      );
    } finally {
      setIsLoading(false);
    }
  }, [disconnect, addToast]);

  const handleOpenStartMonitor = useCallback(() => {
    setShowStartMonitorPanel(true);
  }, []);

  const handlePauseResume = useCallback(async () => {
    setIsLoading(true);
    try {
      if (isPaused) {
        const res = await resumeMonitor();
        connect();
        setIsPaused(false);
        addToast(res.message, "success");
      } else {
        const res = await pauseMonitor();
        disconnect();
        setIsPaused(true);
        addToast(res.message, "info");
      }
    } catch (err) {
      addToast(
        `操作失败: ${err instanceof Error ? err.message : "未知错误"}`,
        "error"
      );
    } finally {
      setIsLoading(false);
    }
  }, [isPaused, connect, disconnect, addToast]);

  const handleStartMonitorConfirm = useCallback(
    async ({ courseName, citeFilename }: { courseName: string; citeFilename: string | null }) => {
      await startMonitor({
        course_name: courseName,
        cite_filename: citeFilename,
      });
      connect();
      setIsMonitoring(true);
      setIsPaused(false);
      setActiveCourseName(courseName);
      setShowStartMonitorPanel(false);
      addToast(courseName ? `开始摸鱼模式 🎣 ${courseName}` : "开始摸鱼模式 🎣", "success");
    },
    [connect, addToast]
  );

  // ---- 救场 ----
  const handleRescue = useCallback(() => {
    dismissAlert();
    setShowRescuePanel(true);
  }, [dismissAlert]);

  // ---- 关闭救场面板 ----
  const handleCloseRescue = useCallback(() => {
    setShowRescuePanel(false);
  }, []);

  // ---- 老师讲到哪了 ----
  const handleCatchup = useCallback(() => {
    dismissAlert();
    setShowCatchupPanel(true);
  }, [dismissAlert]);

  // ---- 关闭进度面板 ----
  const handleCloseCatchup = useCallback(() => {
    setShowCatchupPanel(false);
  }, []);

  const handleOpenSettings = useCallback(() => {
    setShowSettingsPanel(true);
  }, []);

  const handleCloseSettings = useCallback(() => {
    setShowSettingsPanel(false);
  }, []);

  return (
    <div className="app-shell relative h-full w-full overflow-hidden rounded-[var(--window-radius)] border border-[var(--theme-shell-border)] shadow-2xl backdrop-blur-xl">
      {/* 标题栏 */}
      <TitleBar isMonitoring={isMonitoring} isPaused={isPaused} courseName={activeCourseName} />

      {/* 工具栏（非救场/进度模式时显示） */}
      {!showRescuePanel && !showCatchupPanel && !showStartMonitorPanel && !showSettingsPanel && (
        <ToolBar
          isMonitoring={isMonitoring}
          isPaused={isPaused}
          isLoading={isLoading}
          courseName={activeCourseName}
          onUpload={handleUpload}
          onStartMonitor={handleOpenStartMonitor}
          onStopMonitor={handleStopMonitor}
          onPauseResume={handlePauseResume}
          onCatchup={handleCatchup}
          onSettings={handleOpenSettings}
        />
      )}

      <StartMonitorPanel
        visible={showStartMonitorPanel}
        onClose={() => setShowStartMonitorPanel(false)}
        onConfirm={handleStartMonitorConfirm}
        refreshToken={citeRefreshToken}
      />

      <SettingsPanel
        visible={showSettingsPanel}
        onClose={handleCloseSettings}
        onSaved={(message) => addToast(message, "success")}
      />

      {/* 救场面板 */}
      <RescuePanel visible={showRescuePanel} onClose={handleCloseRescue} />

      {/* 课堂进度面板 */}
      <CatchupPanel visible={showCatchupPanel} onClose={handleCloseCatchup} />

      {/* 点名警报覆盖层 */}
      <AlertOverlay
        active={alertActive && !showRescuePanel}
        level={lastAlert?.level ?? "danger"}
        keywords={lastAlert?.keywords ?? []}
        text={lastAlert?.text ?? ""}
        onRescue={handleRescue}
        onCatchup={handleCatchup}
        onDismiss={dismissAlert}
      />

      {/* Toast 提示 */}
      <ToastContainer messages={toasts} onRemove={removeToast} />
    </div>
  );
}

export default function App() {
  const [windowLabel, setWindowLabel] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;

    (async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        if (!disposed) {
          setWindowLabel(getCurrentWindow().label);
        }
      } catch {
        if (!disposed) {
          setWindowLabel("main");
        }
      }
    })();

    return () => {
      disposed = true;
    };
  }, []);

  if (windowLabel === null) {
    return null;
  }

  if (windowLabel === "splash") {
    return <SplashScreen />;
  }
  return <MainApp />;
}
