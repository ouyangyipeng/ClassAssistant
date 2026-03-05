/**
 * 上课摸鱼搭子 - 主应用组件
 * =========================
 * 整合所有子组件，管理全局状态
 */

import { useState, useCallback } from "react";
import TitleBar from "./components/TitleBar";
import ToolBar from "./components/ToolBar";
import AlertOverlay from "./components/AlertOverlay";
import RescuePanel from "./components/RescuePanel";
import ToastContainer, { type ToastMessage } from "./components/Toast";
import { useWebSocket } from "./hooks/useWebSocket";
import {
  uploadPPT,
  startMonitor,
  stopMonitor,
  generateSummary,
} from "./services/api";

// Toast ID 计数器
let toastId = 0;

export default function App() {
  // ---- 状态管理 ----
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [showRescuePanel, setShowRescuePanel] = useState(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  // WebSocket 连接
  const { lastAlert, alertActive, connect, disconnect, dismissAlert } =
    useWebSocket();

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
  const handleToggleMonitor = useCallback(async () => {
    setIsLoading(true);
    try {
      if (isMonitoring) {
        // 停止监控
        await stopMonitor();
        disconnect();
        setIsMonitoring(false);
        addToast("监控已停止", "info");
        // 恢复小窗口
        try {
          const { getCurrentWindow } = await import(
            "@tauri-apps/api/window"
          );
          const { LogicalSize } = await import("@tauri-apps/api/dpi");
          await getCurrentWindow().setSize(new LogicalSize(320, 80));
        } catch {
          /* 忽略窗口操作错误 */
        }
      } else {
        // 启动监控
        await startMonitor();
        connect(); // 建立 WebSocket 接收警报
        setIsMonitoring(true);
        addToast("开始摸鱼模式 🎣", "success");
      }
    } catch (err) {
      addToast(
        `操作失败: ${err instanceof Error ? err.message : "未知错误"}`,
        "error"
      );
    } finally {
      setIsLoading(false);
    }
  }, [isMonitoring, connect, disconnect, addToast]);

  // ---- 救场 ----
  const handleRescue = useCallback(() => {
    dismissAlert();
    setShowRescuePanel(true);
  }, [dismissAlert]);

  // ---- 关闭救场面板 ----
  const handleCloseRescue = useCallback(() => {
    setShowRescuePanel(false);
  }, []);

  // ---- 课后总结 ----
  const handleSummary = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await generateSummary();
      addToast(`笔记已生成: ${res.filename}`, "success");
    } catch (err) {
      addToast(
        `生成失败: ${err instanceof Error ? err.message : "未知错误"}`,
        "error"
      );
    } finally {
      setIsLoading(false);
    }
  }, [addToast]);

  return (
    <div className="relative w-full h-screen bg-gray-900/80 backdrop-blur-xl rounded-2xl overflow-hidden border border-white/10 shadow-2xl">
      {/* 标题栏 */}
      <TitleBar isMonitoring={isMonitoring} />

      {/* 工具栏（非救场模式时显示） */}
      {!showRescuePanel && (
        <ToolBar
          isMonitoring={isMonitoring}
          isLoading={isLoading}
          onUpload={handleUpload}
          onToggleMonitor={handleToggleMonitor}
          onSummary={handleSummary}
        />
      )}

      {/* 救场面板 */}
      <RescuePanel visible={showRescuePanel} onClose={handleCloseRescue} />

      {/* 点名警报覆盖层 */}
      <AlertOverlay
        active={alertActive && !showRescuePanel}
        keywords={lastAlert?.keywords ?? []}
        text={lastAlert?.text ?? ""}
        onRescue={handleRescue}
        onDismiss={dismissAlert}
      />

      {/* Toast 提示 */}
      <ToastContainer messages={toasts} onRemove={removeToast} />
    </div>
  );
}
