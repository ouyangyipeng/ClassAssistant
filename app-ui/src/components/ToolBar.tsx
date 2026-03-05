/**
 * 工具栏组件
 * ==========
 * 包含「上传资料」和「开始摸鱼」两个核心按钮
 */

import { useRef } from "react";

interface ToolBarProps {
  /** 是否正在监控 */
  isMonitoring: boolean;
  /** 是否正在加载中 */
  isLoading: boolean;
  /** 点击上传资料 */
  onUpload: (file: File) => void;
  /** 点击开始/停止摸鱼 */
  onToggleMonitor: () => void;
  /** 点击生成总结 */
  onSummary: () => void;
}

export default function ToolBar({
  isMonitoring,
  isLoading,
  onUpload,
  onToggleMonitor,
  onSummary,
}: ToolBarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  /** 触发文件选择 */
  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  /** 文件选中后回调 */
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onUpload(file);
      // 清空 input 以允许重复上传同一文件
      e.target.value = "";
    }
  };

  return (
    <div className="flex items-center gap-2 px-2 pb-2">
      {/* 隐藏的文件选择器 */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pptx,.ppt"
        className="hidden"
        onChange={handleFileChange}
        aria-label="上传PPT文件"
      />

      {/* 上传资料按钮 */}
      <button
        onClick={handleUploadClick}
        disabled={isLoading}
        className="flex-1 px-3 py-1.5 text-xs font-medium rounded-lg
                   bg-blue-500/20 text-blue-300 border border-blue-500/30
                   hover:bg-blue-500/30 hover:border-blue-400/50
                   disabled:opacity-50 disabled:cursor-not-allowed
                   transition-all duration-200 backdrop-blur-sm"
        title="上传课程 PPT 资料"
      >
        📄 上传资料
      </button>

      {/* 开始/停止摸鱼按钮 */}
      <button
        onClick={onToggleMonitor}
        disabled={isLoading}
        className={`flex-1 px-3 py-1.5 text-xs font-medium rounded-lg
                   border transition-all duration-200 backdrop-blur-sm
                   disabled:opacity-50 disabled:cursor-not-allowed
                   ${
                     isMonitoring
                       ? "bg-red-500/20 text-red-300 border-red-500/30 hover:bg-red-500/30"
                       : "bg-green-500/20 text-green-300 border-green-500/30 hover:bg-green-500/30"
                   }`}
        title={isMonitoring ? "停止监控" : "开始录音与监控"}
      >
        {isMonitoring ? "⏹ 停止摸鱼" : "🎣 开始摸鱼"}
      </button>

      {/* 课后总结按钮（仅在非监控时显示） */}
      {!isMonitoring && (
        <button
          onClick={onSummary}
          disabled={isLoading}
          className="px-3 py-1.5 text-xs font-medium rounded-lg
                     bg-purple-500/20 text-purple-300 border border-purple-500/30
                     hover:bg-purple-500/30 hover:border-purple-400/50
                     disabled:opacity-50 disabled:cursor-not-allowed
                     transition-all duration-200 backdrop-blur-sm"
          title="生成课后总结笔记"
        >
          📝
        </button>
      )}
    </div>
  );
}
