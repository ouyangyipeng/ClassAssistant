/**
 * 警报覆盖层组件
 * ===============
 * 点名触发时，整个悬浮窗闪烁红光并显示「救场」按钮
 */

import { useEffect, useState } from "react";

interface AlertOverlayProps {
  /** 是否激活警报 */
  active: boolean;
  /** 触发警报的关键词 */
  keywords: string[];
  /** 触发的原文 */
  text: string;
  /** 点击救场按钮 */
  onRescue: () => void;
  /** 点击忽略/关闭 */
  onDismiss: () => void;
}

export default function AlertOverlay({
  active,
  keywords,
  text,
  onRescue,
  onDismiss,
}: AlertOverlayProps) {
  const [flash, setFlash] = useState(false);

  // 闪烁效果
  useEffect(() => {
    if (!active) return;

    const interval = setInterval(() => {
      setFlash((prev) => !prev);
    }, 500);

    return () => clearInterval(interval);
  }, [active]);

  // 窗口激活到前台（当检测到点名时）
  useEffect(() => {
    if (active) {
      (async () => {
        try {
          const { getCurrentWindow } = await import("@tauri-apps/api/window");
          const win = getCurrentWindow();
          await win.setFocus();
          // 调大窗口以显示警报
          await win.setSize(new (await import("@tauri-apps/api/dpi")).LogicalSize(320, 200));
        } catch (e) {
          console.error("窗口操作失败:", e);
        }
      })();
    }
  }, [active]);

  if (!active) return null;

  return (
    <div
      className={`absolute inset-0 z-50 flex flex-col items-center justify-center
                  rounded-2xl transition-all duration-300
                  ${flash ? "bg-red-600/40" : "bg-red-900/30"}
                  border-2 ${flash ? "border-red-400" : "border-red-600/50"}
                  backdrop-blur-md`}
    >
      {/* 警报标题 */}
      <div className="flex items-center gap-2 mb-2">
        <span className="text-2xl animate-bounce">🚨</span>
        <span className="text-lg font-bold text-red-200">检测到点名!</span>
        <span className="text-2xl animate-bounce">🚨</span>
      </div>

      {/* 触发信息 */}
      <div className="text-xs text-red-200/80 mb-1">
        关键词: {keywords.join(", ")}
      </div>
      <div className="text-xs text-red-200/60 mb-3 px-4 text-center line-clamp-2">
        "{text}"
      </div>

      {/* 操作按钮 */}
      <div className="flex gap-3">
        <button
          onClick={onRescue}
          className="px-6 py-2 text-sm font-bold rounded-xl
                     bg-red-500 text-white shadow-lg shadow-red-500/50
                     hover:bg-red-400 hover:scale-105
                     active:scale-95 transition-all duration-150
                     animate-pulse"
        >
          🆘 救场!
        </button>
        <button
          onClick={onDismiss}
          className="px-4 py-2 text-xs rounded-xl
                     bg-white/10 text-white/60
                     hover:bg-white/20 hover:text-white/80
                     transition-all duration-150"
        >
          忽略
        </button>
      </div>
    </div>
  );
}
