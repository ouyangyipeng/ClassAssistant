/**
 * 救场面板组件
 * =============
 * 展示 LLM 分析的课堂上下文、老师问题和建议答案
 */

import { useEffect, useState } from "react";
import { emergencyRescue } from "../services/api";

interface RescuePanelProps {
  /** 面板是否可见 */
  visible: boolean;
  /** 关闭面板 */
  onClose: () => void;
}

interface RescueData {
  context: string;
  question: string;
  answer: string;
}

export default function RescuePanel({ visible, onClose }: RescuePanelProps) {
  const [data, setData] = useState<RescueData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 面板打开时自动请求救场数据
  useEffect(() => {
    if (!visible) return;

    setLoading(true);
    setError(null);

    emergencyRescue()
      .then((res) => {
        setData({
          context: res.context,
          question: res.question,
          answer: res.answer,
        });
      })
      .catch((err) => {
        setError(err.message || "请求失败");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [visible]);

  // 面板打开时调大窗口
  useEffect(() => {
    (async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const { LogicalSize } = await import("@tauri-apps/api/dpi");
        const win = getCurrentWindow();
        if (visible) {
          await win.setSize(new LogicalSize(400, 480));
        } else {
          // 恢复小窗口
          await win.setSize(new LogicalSize(320, 80));
        }
      } catch (e) {
        console.error("窗口尺寸调整失败:", e);
      }
    })();
  }, [visible]);

  if (!visible) return null;

  return (
    <div className="flex flex-col gap-2 p-3 animate-in fade-in duration-300">
      {/* 加载中 */}
      {loading && (
        <div className="flex items-center justify-center py-8 text-white/60">
          <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2" />
          <span className="text-sm">正在分析课堂内容...</span>
        </div>
      )}

      {/* 错误提示 */}
      {error && (
        <div className="p-3 rounded-xl bg-red-500/20 border border-red-500/30 text-red-300 text-xs">
          ⚠️ {error}
        </div>
      )}

      {/* 救场数据 */}
      {data && !loading && (
        <>
          {/* 课堂内容概要 */}
          <div className="p-3 rounded-xl bg-blue-500/10 border border-blue-500/20">
            <div className="flex items-center gap-1.5 mb-1.5">
              <span className="text-sm">📖</span>
              <span className="text-xs font-semibold text-blue-300">目前课堂内容</span>
            </div>
            <p className="text-xs text-white/80 leading-relaxed">{data.context}</p>
          </div>

          {/* 老师问题 */}
          <div className="p-3 rounded-xl bg-yellow-500/10 border border-yellow-500/20">
            <div className="flex items-center gap-1.5 mb-1.5">
              <span className="text-sm">❓</span>
              <span className="text-xs font-semibold text-yellow-300">老师问题</span>
            </div>
            <p className="text-xs text-white/90 leading-relaxed font-medium">{data.question}</p>
          </div>

          {/* 建议答案 */}
          <div className="p-3 rounded-xl bg-green-500/10 border border-green-500/20">
            <div className="flex items-center gap-1.5 mb-1.5">
              <span className="text-sm">💡</span>
              <span className="text-xs font-semibold text-green-300">建议答案</span>
            </div>
            <p className="text-xs text-white/90 leading-relaxed">{data.answer}</p>
          </div>
        </>
      )}

      {/* 关闭按钮 */}
      <button
        onClick={onClose}
        className="mt-1 px-4 py-1.5 text-xs rounded-lg
                   bg-white/10 text-white/60 
                   hover:bg-white/20 hover:text-white 
                   transition-all duration-150 self-center"
      >
        收起面板
      </button>
    </div>
  );
}
