"""
监控服务
========
负责麦克风录音、ASR 转文字、关键词匹配与 WebSocket 警报推送
"""

import asyncio
import json
import logging
import os
import re
import threading
from datetime import datetime
from typing import List, Set

from fastapi import WebSocket

from services.asr_service import create_asr, BaseASR

logger = logging.getLogger(__name__)

# data 目录路径
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")


class MonitorService:
    """课堂监控服务 - 核心后台服务"""

    def __init__(self):
        # 内置关键词（点名相关）
        self.builtin_keywords: List[str] = [
            "点名", "随机", "抽查", "叫人", "回答", "签到",
            "哪位同学", "谁来", "站起来", "请回答"
        ]
        # 用户自定义关键词（如自己的名字）
        self.custom_keywords: List[str] = []

        # 录音状态
        self.is_monitoring: bool = False

        # ASR 实例
        self._asr: BaseASR | None = None

        # 用于从 ASR 回调线程安全地广播到 WebSocket 的事件循环
        self._loop: asyncio.AbstractEventLoop | None = None

        # WebSocket 连接池
        self._websockets: Set[WebSocket] = set()

        # 转录文件路径
        self.transcript_path = os.path.join(DATA_DIR, "class_transcript.txt")

    def get_all_keywords(self) -> List[str]:
        """获取所有关键词（内置 + 自定义）"""
        return self.builtin_keywords + self.custom_keywords

    def update_custom_keywords(self, keywords: List[str]):
        """更新用户自定义关键词"""
        self.custom_keywords = keywords

    def register_websocket(self, ws: WebSocket):
        """注册 WebSocket 连接"""
        self._websockets.add(ws)

    def unregister_websocket(self, ws: WebSocket):
        """注销 WebSocket 连接"""
        self._websockets.discard(ws)

    async def _broadcast_alert(self, message: dict):
        """向所有已连接的 WebSocket 客户端广播警报"""
        dead_connections = set()
        for ws in self._websockets:
            try:
                await ws.send_text(json.dumps(message, ensure_ascii=False))
            except Exception:
                dead_connections.add(ws)
        # 清理断开的连接
        self._websockets -= dead_connections

    def _check_keywords(self, text: str) -> List[str]:
        """
        检查文本中是否包含监控关键词

        Args:
            text: ASR 识别出的文本

        Returns:
            匹配到的关键词列表
        """
        matched = []
        all_keywords = self.get_all_keywords()
        for keyword in all_keywords:
            # 使用正则匹配，支持模糊匹配
            if re.search(re.escape(keyword), text):
                matched.append(keyword)
        return matched

    async def start(self) -> dict:
        """启动监控服务"""
        if self.is_monitoring:
            return {"status": "already_running", "message": "监控服务已在运行中"}

        self.is_monitoring = True

        # 保存当前事件循环引用，供 ASR 回调使用
        self._loop = asyncio.get_running_loop()

        # 清空/初始化转录文件
        with open(self.transcript_path, "w", encoding="utf-8") as f:
            f.write(f"=== 课堂记录 开始于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")

        # 创建 ASR 实例并启动
        self._asr = create_asr(on_text=self._on_asr_text)
        self._asr.start()

        return {"status": "started", "message": "开始摸鱼模式 🎣 录音和监控已启动"}

    async def stop(self) -> dict:
        """停止监控服务"""
        if not self.is_monitoring:
            return {"status": "not_running", "message": "监控服务未在运行"}

        self.is_monitoring = False

        # 停止 ASR
        if self._asr:
            self._asr.stop()
            self._asr = None

        # 写入结束标记
        with open(self.transcript_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n=== 课堂记录 结束于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")

        return {"status": "stopped", "message": "监控已停止"}

    def _on_asr_text(self, text: str, is_final: bool):
        """
        ASR 识别回调 (可能从非主线程调用)。

        Args:
            text: 识别到的文本
            is_final: 是否为一句话的完整结果
        """
        if not self.is_monitoring or not text.strip():
            return

        # 只处理完整句子，避免中间结果重复写入
        if not is_final:
            return

        timestamp = datetime.now().strftime("%H:%M:%S")

        # 写入转录文件
        try:
            with open(self.transcript_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {text}\n")
        except Exception:
            logger.exception("写入转录文件失败")

        # 检查关键词
        matched = self._check_keywords(text)
        if matched and self._loop:
            alert = {
                "type": "keyword_alert",
                "keywords": matched,
                "text": text,
                "timestamp": timestamp,
            }
            # 线程安全地调度广播协程
            asyncio.run_coroutine_threadsafe(self._broadcast_alert(alert), self._loop)
        #
        # === OpenAI Whisper API ===
        # from openai import OpenAI
        # client = OpenAI()
        # transcription = client.audio.transcriptions.create(
        #     model="whisper-1", file=audio_file
        # )
        # return transcription.text

        return ""  # Mock: 返回空字符串（静默）
