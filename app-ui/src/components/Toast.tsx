/**
 * Toast 提示组件
 * ==============
 * 轻量级提示消息，自动消失
 */

import { useEffect, useState } from "react";

export interface ToastMessage {
  id: number;
  text: string;
  type: "success" | "error" | "info";
}

interface ToastContainerProps {
  messages: ToastMessage[];
  onRemove: (id: number) => void;
}

export default function ToastContainer({ messages, onRemove }: ToastContainerProps) {
  return (
    <div className="fixed bottom-2 right-2 flex flex-col gap-1.5 z-[100]">
      {messages.map((msg) => (
        <ToastItem key={msg.id} message={msg} onRemove={onRemove} />
      ))}
    </div>
  );
}

function ToastItem({
  message,
  onRemove,
}: {
  message: ToastMessage;
  onRemove: (id: number) => void;
}) {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setVisible(false);
      setTimeout(() => onRemove(message.id), 300);
    }, 3000);
    return () => clearTimeout(timer);
  }, [message.id, onRemove]);

  const bgColor = {
    success: "bg-green-500/20 border-green-500/30 text-green-300",
    error: "bg-red-500/20 border-red-500/30 text-red-300",
    info: "bg-blue-500/20 border-blue-500/30 text-blue-300",
  }[message.type];

  const icon = {
    success: "✅",
    error: "❌",
    info: "ℹ️",
  }[message.type];

  return (
    <div
      className={`px-3 py-1.5 rounded-lg border text-xs backdrop-blur-sm
                  transition-all duration-300
                  ${bgColor}
                  ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"}`}
    >
      {icon} {message.text}
    </div>
  );
}
