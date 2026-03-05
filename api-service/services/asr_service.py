"""
ASR 语音识别服务
================
支持三种模式：
  - mock:      空实现，用于开发测试
  - dashscope: 阿里云百炼 Fun-ASR 实时语音识别
  - seed-asr:  字节跳动 Seed-ASR 大模型语音识别
"""

import gzip
import json
import logging
import os
import struct
import threading
import uuid
from typing import Callable, Optional

import pyaudio
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---- 音频录制参数 ----
SAMPLE_RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
CHANNELS = int(os.getenv("AUDIO_CHANNELS", "1"))
CHUNK_SIZE = int(os.getenv("AUDIO_CHUNK_SIZE", "3200"))  # 100ms @16kHz, 16bit, mono


class BaseASR:
    """ASR 基类，定义统一接口"""

    def __init__(self, on_text: Callable[[str, bool], None]):
        """
        Args:
            on_text: 回调函数 (text, is_final)
                     text - 识别到的文本
                     is_final - 是否为一句话的最终结果
        """
        self.on_text = on_text
        self._running = False

    def start(self):
        """启动 ASR 识别"""
        raise NotImplementedError

    def stop(self):
        """停止 ASR 识别"""
        raise NotImplementedError


class MockASR(BaseASR):
    """Mock ASR - 不进行真实录音/识别，仅用于测试"""

    def start(self):
        self._running = True
        logger.info("[MockASR] started (no real recognition)")

    def stop(self):
        self._running = False
        logger.info("[MockASR] stopped")


# =====================================================================
# DashScope Fun-ASR 实现
# =====================================================================

class DashScopeASR(BaseASR):
    """
    阿里云百炼 Fun-ASR 实时语音识别
    使用 dashscope SDK 的 Recognition + RecognitionCallback
    """

    def __init__(self, on_text: Callable[[str, bool], None]):
        super().__init__(on_text)
        self._recognition = None
        self._mic: Optional[pyaudio.PyAudio] = None
        self._stream = None
        self._send_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self):
        import dashscope
        from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

        api_key = os.getenv("DASHSCOPE_API_KEY", "")
        if not api_key:
            logger.error("[DashScopeASR] DASHSCOPE_API_KEY not set")
            return

        dashscope.api_key = api_key
        dashscope.base_websocket_api_url = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"

        self._running = True
        self._stop_event.clear()

        on_text_cb = self.on_text  # capture for inner class

        class _Callback(RecognitionCallback):
            def on_open(self_cb) -> None:
                logger.info("[DashScopeASR] connection opened")

            def on_close(self_cb) -> None:
                logger.info("[DashScopeASR] connection closed")

            def on_complete(self_cb) -> None:
                logger.info("[DashScopeASR] recognition completed")

            def on_error(self_cb, message) -> None:
                logger.error("[DashScopeASR] error: %s", message.message)

            def on_event(self_cb, result: RecognitionResult) -> None:
                sentence = result.get_sentence()
                if "text" in sentence:
                    text = sentence["text"]
                    is_final = RecognitionResult.is_sentence_end(sentence)
                    if text:
                        on_text_cb(text, is_final)

        callback = _Callback()
        self._recognition = Recognition(
            model="fun-asr-realtime",
            format="pcm",
            sample_rate=SAMPLE_RATE,
            semantic_punctuation_enabled=False,
            callback=callback,
        )

        # 启动识别
        self._recognition.start()

        # 在单独线程中开启麦克风录音并推流
        self._send_thread = threading.Thread(target=self._audio_loop, daemon=True)
        self._send_thread.start()
        logger.info("[DashScopeASR] started")

    def _audio_loop(self):
        """持续从麦克风读取音频并发送到 ASR"""
        try:
            self._mic = pyaudio.PyAudio()
            self._stream = self._mic.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
            )

            while not self._stop_event.is_set():
                data = self._stream.read(CHUNK_SIZE, exception_on_overflow=False)
                if self._recognition:
                    self._recognition.send_audio_frame(data)
        except Exception:
            logger.exception("[DashScopeASR] audio loop error")
        finally:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
            if self._mic:
                self._mic.terminate()
            self._stream = None
            self._mic = None

    def stop(self):
        self._running = False
        self._stop_event.set()

        # 等待音频线程结束
        if self._send_thread and self._send_thread.is_alive():
            self._send_thread.join(timeout=3)

        # 停止 ASR（会阻塞直到 on_complete / on_error）
        if self._recognition:
            try:
                self._recognition.stop()
            except Exception:
                logger.exception("[DashScopeASR] error stopping recognition")
            self._recognition = None

        logger.info("[DashScopeASR] stopped")


# =====================================================================
# Seed-ASR (字节跳动) 实现
# =====================================================================

class SeedASR(BaseASR):
    """
    字节跳动 Seed-ASR 大模型语音识别
    通过 WebSocket 二进制协议流式交互
    """

    WS_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"

    def __init__(self, on_text: Callable[[str, bool], None]):
        super().__init__(on_text)
        self._ws = None
        self._mic: Optional[pyaudio.PyAudio] = None
        self._stream = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ---- 二进制协议辅助 ----

    @staticmethod
    def _build_header(msg_type: int, msg_flags: int, serial: int, compress: int) -> bytes:
        """构造 4 字节 header"""
        b0 = (0x1 << 4) | 0x1           # version=1, header_size=1 (4 bytes)
        b1 = (msg_type << 4) | msg_flags
        b2 = (serial << 4) | compress
        b3 = 0x00
        return bytes([b0, b1, b2, b3])

    @staticmethod
    def _build_full_request(payload_json: dict) -> bytes:
        """构造 full client request 帧"""
        header = SeedASR._build_header(
            msg_type=0x1,      # full client request
            msg_flags=0x0,
            serial=0x1,        # JSON
            compress=0x1,      # Gzip
        )
        payload_bytes = gzip.compress(json.dumps(payload_json).encode("utf-8"))
        size = struct.pack(">I", len(payload_bytes))
        return header + size + payload_bytes

    @staticmethod
    def _build_audio_frame(audio_data: bytes, is_last: bool = False) -> bytes:
        """构造 audio-only client request 帧"""
        header = SeedASR._build_header(
            msg_type=0x2,                          # audio only
            msg_flags=0x2 if is_last else 0x0,     # 0x2 = last frame
            serial=0x0,                            # no serialization
            compress=0x1,                          # Gzip
        )
        payload_bytes = gzip.compress(audio_data)
        size = struct.pack(">I", len(payload_bytes))
        return header + size + payload_bytes

    @staticmethod
    def _parse_server_response(data: bytes) -> Optional[dict]:
        """解析 full server response，返回 JSON payload 或 None"""
        if len(data) < 4:
            return None

        b1 = data[1]
        msg_type = (b1 >> 4) & 0xF

        if msg_type == 0xF:
            # error message
            if len(data) >= 12:
                err_code = struct.unpack(">I", data[4:8])[0]
                err_size = struct.unpack(">I", data[8:12])[0]
                err_msg = data[12:12 + err_size].decode("utf-8", errors="replace")
                logger.error("[SeedASR] server error %d: %s", err_code, err_msg)
            return None

        if msg_type != 0x9:
            return None

        b2 = data[2]
        compress = b2 & 0xF

        # sequence (4 bytes) + payload_size (4 bytes)
        if len(data) < 12:
            return None
        payload_size = struct.unpack(">I", data[8:12])[0]
        payload_raw = data[12:12 + payload_size]

        if compress == 0x1:
            payload_raw = gzip.decompress(payload_raw)

        try:
            return json.loads(payload_raw)
        except json.JSONDecodeError:
            return None

    def start(self):
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("[SeedASR] started")

    def _run(self):
        """工作线程：建连 → 发送 full request → 流式推音频 → 接收结果"""
        import websocket  # websocket-client 库

        app_key = os.getenv("SEED_ASR_APP_KEY", "")
        access_key = os.getenv("SEED_ASR_ACCESS_KEY", "")
        resource_id = os.getenv("SEED_ASR_RESOURCE_ID", "volc.bigasr.sauc.duration")

        if not app_key or not access_key:
            logger.error("[SeedASR] SEED_ASR_APP_KEY / SEED_ASR_ACCESS_KEY not set")
            return

        connect_id = str(uuid.uuid4())

        headers = {
            "X-Api-App-Key": app_key,
            "X-Api-Access-Key": access_key,
            "X-Api-Resource-Id": resource_id,
            "X-Api-Connect-Id": connect_id,
        }

        try:
            self._ws = websocket.create_connection(
                self.WS_URL,
                header=[f"{k}: {v}" for k, v in headers.items()],
                timeout=10,
            )

            # 1) 发送 full client request
            full_req_payload = {
                "user": {"uid": "class-assistant"},
                "audio": {
                    "format": "pcm",
                    "rate": SAMPLE_RATE,
                    "bits": 16,
                    "channel": CHANNELS,
                },
                "request": {
                    "model_name": "bigmodel",
                    "enable_punc": True,
                    "enable_itn": True,
                    "result_type": "full",
                },
            }
            self._ws.send(self._build_full_request(full_req_payload), opcode=0x2)

            # 读取 full request 的 ack
            ack = self._ws.recv()
            if isinstance(ack, bytes):
                resp = self._parse_server_response(ack)
                logger.debug("[SeedASR] full request ack: %s", resp)

            # 2) 开启麦克风，循环发送音频帧
            self._mic = pyaudio.PyAudio()
            self._stream = self._mic.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
            )

            while not self._stop_event.is_set():
                audio_data = self._stream.read(CHUNK_SIZE, exception_on_overflow=False)
                self._ws.send(self._build_audio_frame(audio_data, is_last=False), opcode=0x2)

                # 尝试非阻塞读取响应
                self._ws.settimeout(0.01)
                try:
                    resp_data = self._ws.recv()
                    if isinstance(resp_data, bytes):
                        resp = self._parse_server_response(resp_data)
                        if resp and "result" in resp:
                            text = resp["result"].get("text", "")
                            if text:
                                self.on_text(text, True)
                except websocket.WebSocketTimeoutException:
                    pass

            # 3) 发送最后一帧（负包）
            self._ws.send(self._build_audio_frame(b"", is_last=True), opcode=0x2)

            # 读取最终结果
            self._ws.settimeout(5)
            try:
                final = self._ws.recv()
                if isinstance(final, bytes):
                    resp = self._parse_server_response(final)
                    if resp and "result" in resp:
                        text = resp["result"].get("text", "")
                        if text:
                            self.on_text(text, True)
            except Exception:
                pass

        except Exception:
            logger.exception("[SeedASR] connection/stream error")
        finally:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
            if self._mic:
                self._mic.terminate()
            if self._ws:
                self._ws.close()
            self._stream = None
            self._mic = None
            self._ws = None

    def stop(self):
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("[SeedASR] stopped")


# =====================================================================
# 工厂函数
# =====================================================================

def create_asr(on_text: Callable[[str, bool], None]) -> BaseASR:
    """
    根据 ASR_MODE 环境变量创建对应的 ASR 实例

    Args:
        on_text: 文本回调 (text, is_final)

    Returns:
        BaseASR 子类实例
    """
    mode = os.getenv("ASR_MODE", "mock").lower()
    if mode == "dashscope":
        return DashScopeASR(on_text)
    elif mode == "seed-asr":
        return SeedASR(on_text)
    else:
        return MockASR(on_text)
