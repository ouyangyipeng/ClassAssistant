"""
监控服务路由
============
处理录音启停、关键词监控、WebSocket 推送
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import List, Optional
from services.monitor_service import MonitorService

router = APIRouter()

# 全局监控服务实例
monitor_service = MonitorService()


class KeywordUpdateRequest(BaseModel):
    """自定义关键词更新请求"""
    keywords: List[str]  # 用户自定义关键词列表


@router.post("/start_monitor")
async def start_monitor():
    """
    开始摸鱼模式
    - 启动麦克风录音
    - 启动 ASR 语音转文字
    - 启动关键词监控
    """
    result = await monitor_service.start()
    return result


@router.post("/stop_monitor")
async def stop_monitor():
    """
    停止监控
    - 停止录音
    - 停止 ASR
    """
    result = await monitor_service.stop()
    return result


@router.post("/update_keywords")
async def update_keywords(request: KeywordUpdateRequest):
    """
    更新用户自定义关键词
    - 追加到内置关键词列表中
    """
    monitor_service.update_custom_keywords(request.keywords)
    return {
        "status": "success",
        "all_keywords": monitor_service.get_all_keywords()
    }


@router.get("/keywords")
async def get_keywords():
    """获取当前所有监控关键词"""
    return {
        "builtin": monitor_service.builtin_keywords,
        "custom": monitor_service.custom_keywords,
        "all": monitor_service.get_all_keywords()
    }


@router.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """
    WebSocket 端点 - 实时推送点名警报
    前端连接此 WebSocket 后，当检测到关键词时会收到警报消息
    """
    await websocket.accept()
    # 注册此 WebSocket 连接到监控服务
    monitor_service.register_websocket(websocket)
    try:
        while True:
            # 保持连接，等待前端消息（如心跳）
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        monitor_service.unregister_websocket(websocket)
