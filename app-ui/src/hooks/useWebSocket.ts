/**
 * WebSocket 连接 Hook
 * ====================
 * 管理与后端的 WebSocket 连接，接收实时点名警报
 */

import { useState, useEffect, useRef, useCallback } from "react";

/** 警报消息类型 */
export interface AlertMessage {
  type: "keyword_alert";
  keywords: string[];
  text: string;
  timestamp: string;
}

const WS_URL = "ws://127.0.0.1:8765/api/ws/alerts";

export function useWebSocket() {
  const [isConnected, setIsConnected] = useState(false);
  const [lastAlert, setLastAlert] = useState<AlertMessage | null>(null);
  const [alertActive, setAlertActive] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /** 建立 WebSocket 连接 */
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      setIsConnected(true);
      console.log("[WS] 已连接到警报服务");

      // 心跳保活，每 30 秒发一次 ping
      heartbeatRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send("ping");
        }
      }, 30000);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as AlertMessage;
        if (data.type === "keyword_alert") {
          console.log("[WS] 收到点名警报:", data);
          setLastAlert(data);
          setAlertActive(true);
        }
      } catch {
        // pong 或其他非 JSON 消息忽略
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      console.log("[WS] 连接断开，5 秒后重连...");
      if (heartbeatRef.current) clearInterval(heartbeatRef.current);
      // 自动重连
      setTimeout(connect, 5000);
    };

    ws.onerror = (err) => {
      console.error("[WS] 连接错误:", err);
      ws.close();
    };

    wsRef.current = ws;
  }, []);

  /** 断开连接 */
  const disconnect = useCallback(() => {
    if (heartbeatRef.current) clearInterval(heartbeatRef.current);
    wsRef.current?.close();
    wsRef.current = null;
    setIsConnected(false);
  }, []);

  /** 清除警报状态 */
  const dismissAlert = useCallback(() => {
    setAlertActive(false);
  }, []);

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    isConnected,
    lastAlert,
    alertActive,
    connect,
    disconnect,
    dismissAlert,
  };
}
