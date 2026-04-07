"""
ASR 语音识别服务
================
支持五种模式：
  - local:     免费语音识别（Google Speech API，无需密钥，需联网）
  - webspeech: 浏览器 Web Speech 识别前端采集，后端只接收文本
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
from json import JSONDecodeError
from typing import Any, Callable, Optional

from dotenv import load_dotenv

try:
    import pyaudio
except Exception:  # pragma: no cover - optional dependency in browser-only mode; handle ImportError/OSError/etc.
    pyaudio = None

load_dotenv()

logger = logging.getLogger(__name__)

# ---- 音频录制参数 ----
SAMPLE_RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
CHANNELS = int(os.getenv("AUDIO_CHANNELS", "1"))
CHUNK_SIZE = int(os.getenv("AUDIO_CHUNK_SIZE", "3200"))  # 100ms @16kHz, 16bit, mono


def normalize_asr_mode(value: str | None) -> str:
    if value is None:
        return "local"
    return value.strip().lower() or "local"


def get_effective_asr_mode(asr: "BaseASR | None") -> str:
    if isinstance(asr, BrowserSpeechASR):
        return "webspeech"
    if isinstance(asr, LocalASR):
        return "local"
    if isinstance(asr, DashScopeASR):
        return "dashscope"
    if isinstance(asr, SeedASR):
        return "seed-asr"
    if isinstance(asr, MockASR):
        return "mock"
    return "mock"


def _require_pyaudio(mode_name: str):
    if pyaudio is None:
        raise RuntimeError(
            f"{mode_name} 需要 PyAudio，但当前环境未安装麦克风相关依赖。"
            "请先安装 requirements-mic.txt，例如执行：pip install -r requirements-mic.txt"
        )


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

    @property
    def is_running(self) -> bool:
        """公开运行状态，避免外部直接耦合内部字段实现。"""
        return self._running


class MockASR(BaseASR):
    """Mock ASR - 不进行真实录音/识别，仅用于测试"""

    def start(self):
        self._running = True
        logger.info("[MockASR] started (no real recognition)")

    def stop(self):
        self._running = False
        logger.info("[MockASR] stopped")


class BrowserSpeechASR(BaseASR):
    """WebSpeech 模式占位实现 - 不占用麦克风，由前端注入识别结果。"""

    def start(self):
        self._running = True
        logger.info("[BrowserSpeechASR] started (frontend text injection mode)")

    def stop(self):
        self._running = False
        logger.info("[BrowserSpeechASR] stopped")


# =====================================================================
# 本地免费 ASR 实现（Google Speech API，无需密钥）
# =====================================================================

class LocalASR(BaseASR):
    """
    本地免费 ASR - 使用 SpeechRecognition + Google 免费语音识别 API
    无需任何 API 密钥，需要联网。
    以分段方式识别：录音至静音 → 发送识别 → 返回结果。
    """

    def __init__(self, on_text: Callable[[str, bool], None]):
        super().__init__(on_text)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self):
        _require_pyaudio("LocalASR")
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("[LocalASR] started")

    def _run(self):
        """工作线程：持续监听麦克风，分段识别"""
        import speech_recognition as sr

        recognizer = sr.Recognizer()
        # 降低能量阈值 & 加快停顿判定，提升响应速度
        recognizer.energy_threshold = 220
        recognizer.dynamic_energy_threshold = True
        recognizer.dynamic_energy_adjustment_damping = 0.12
        recognizer.dynamic_energy_adjustment_ratio = 1.4
        recognizer.pause_threshold = 0.9
        recognizer.phrase_threshold = 0.35
        recognizer.non_speaking_duration = 0.45

        mic = sr.Microphone(sample_rate=SAMPLE_RATE)

        try:
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                logger.info("[LocalASR] ambient noise adjusted, listening...")

                while not self._stop_event.is_set():
                    try:
                        audio = recognizer.listen(
                            source,
                            timeout=5,            # 最长等待 5 秒
                            phrase_time_limit=15,  # 单段最长 15 秒
                        )
                    except sr.WaitTimeoutError:
                        continue

                    if self._stop_event.is_set():
                        break

                    # 在子线程中异步识别，避免阻塞监听循环
                    threading.Thread(
                        target=self._recognize,
                        args=(recognizer, audio),
                        daemon=True,
                    ).start()
        except Exception:
            logger.exception("[LocalASR] microphone error")

    def _recognize(self, recognizer, audio):
        """调用 Google 免费 API 识别一段音频"""
        import speech_recognition as sr
        try:
            text = recognizer.recognize_google(audio, language="zh-CN")
            if text and self._running:
                self.on_text(text, True)
        except sr.UnknownValueError:
            pass  # 没听清，正常忽略
        except sr.RequestError as e:
            logger.error("[LocalASR] Google API error: %s", e)
        except Exception:
            logger.exception("[LocalASR] recognition error")

    def stop(self):
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("[LocalASR] stopped")


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
        self._mic: Optional[Any] = None
        self._stream = None
        self._send_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self):
        _require_pyaudio("DashScopeASR")
        import dashscope
        from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

        api_key = os.getenv("DASHSCOPE_API_KEY", "")
        if not api_key:
            raise RuntimeError("DashScopeASR requires DASHSCOPE_API_KEY in .env")

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

    # WS_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"
    WS_URL = os.getenv("SEED_ASR_WS_URL", "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async")

    def __init__(self, on_text: Callable[[str, bool], None]):
        super().__init__(on_text)
        self._ws = None
        self._mic: Optional[Any] = None
        self._stream = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._seen_utterances: set[tuple[int | None, int | None, str]] = set()

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
        try:
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

            if payload_size <= 0 or not payload_raw:
                return None

            if compress == 0x1:
                payload_raw = gzip.decompress(payload_raw)

            if not payload_raw:
                return None

            try:
                return json.loads(payload_raw)
            except JSONDecodeError:
                preview = payload_raw[:80].decode("utf-8", errors="replace")
                logger.debug("[SeedASR] skip non-json response payload: %s", preview)
                return None
        except Exception:
            logger.exception("[SeedASR] failed to parse server response")
            return None

    def start(self):
        _require_pyaudio("SeedASR")
        app_key = os.getenv("SEED_ASR_APP_KEY", "")
        access_key = os.getenv("SEED_ASR_ACCESS_KEY", "")
        if not app_key or not access_key:
            raise RuntimeError("SeedASR requires SEED_ASR_APP_KEY and SEED_ASR_ACCESS_KEY in .env")
        self._running = True
        self._stop_event.clear()
        self._seen_utterances.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("[SeedASR] started")

    def _process_response(self, resp_data):
        """处理单条服务端响应，提取文本并回调"""
        if not isinstance(resp_data, bytes):
            return
        try:
            resp = self._parse_server_response(resp_data)
            if resp and isinstance(resp.get("result"), dict):
                result = resp["result"]
                utterances = result.get("utterances") or []

                for utterance in utterances:
                    text = (utterance.get("text") or "").strip()
                    if not text or not utterance.get("definite"):
                        continue

                    utterance_key = (
                        utterance.get("start_time"),
                        utterance.get("end_time"),
                        text,
                    )
                    if utterance_key in self._seen_utterances:
                        continue

                    self._seen_utterances.add(utterance_key)
                    logger.info("[SeedASR] definite utterance: %s", text[:80])
                    self.on_text(text, True)

                if utterances:
                    last_utterance = utterances[-1]
                    partial_text = (last_utterance.get("text") or "").strip()
                    if partial_text and not last_utterance.get("definite"):
                        self.on_text(partial_text, False)
                else:
                    text = (result.get("text") or "").strip()
                    if text:
                        logger.info("[SeedASR] partial text: %s", text[:80])
                        self.on_text(text, False)
        except Exception:
            logger.exception("[SeedASR] error processing server response")

    def _recv_loop(self):
        """独立接收线程：持续读取服务端响应"""
        import websocket
        while not self._stop_event.is_set():
            try:
                if self._ws is None:
                    break
                resp_data = self._ws.recv()
                self._process_response(resp_data)
            except (websocket.WebSocketTimeoutException, TimeoutError):
                continue
            except websocket.WebSocketConnectionClosedException:
                logger.info("[SeedASR] connection closed by server")
                break
            except Exception:
                if not self._stop_event.is_set():
                    logger.exception("[SeedASR] recv error")
                break

    def _run(self):
        """工作线程：建连 → 发送 full request → 流式推音频（接收在独立线程）"""
        import websocket  # websocket-client 库

        app_key = os.getenv("SEED_ASR_APP_KEY", "")
        access_key = os.getenv("SEED_ASR_ACCESS_KEY", "")
        resource_id = os.getenv("SEED_ASR_RESOURCE_ID", "volc.seedasr.sauc.duration")

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

        logger.info("[SeedASR] connecting to %s (resource_id=%s)", self.WS_URL, resource_id)

        recv_thread = None
        try:
            self._ws = websocket.create_connection(
                self.WS_URL,
                header=[f"{k}: {v}" for k, v in headers.items()],
                timeout=10,
            )
            logger.info("[SeedASR] websocket connected")

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
                    "show_utterances": True,
                    # 在流式优化版中显式开启静音判停，让一句结束后尽快产出 definite 分句。
                    "end_window_size": 800,
                    "force_to_speech_time": 1000,
                    "result_type": "single",
                },
            }
            self._ws.send(self._build_full_request(full_req_payload), opcode=0x2)

            # 读取 full request 的 ack
            ack = self._ws.recv()
            if isinstance(ack, bytes):
                resp = self._parse_server_response(ack)
                logger.info("[SeedASR] full request ack: %s", resp)

            # 2) 启动独立接收线程
            self._ws.settimeout(1)  # recv 线程每秒检查一次 stop_event
            recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            recv_thread.start()

            # 3) 开启麦克风，循环发送音频帧
            self._mic = pyaudio.PyAudio()
            self._stream = self._mic.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
            )

            logger.info("[SeedASR] microphone opened, streaming audio...")

            while not self._stop_event.is_set():
                audio_data = self._stream.read(CHUNK_SIZE, exception_on_overflow=False)
                try:
                    self._ws.send(self._build_audio_frame(audio_data, is_last=False), opcode=0x2)
                except Exception:
                    if not self._stop_event.is_set():
                        logger.exception("[SeedASR] send error")
                    break

            # 4) 发送最后一帧（负包）
            try:
                self._ws.send(self._build_audio_frame(b"", is_last=True), opcode=0x2)
            except Exception:
                pass

            # 等待接收线程处理完最终结果
            if recv_thread and recv_thread.is_alive():
                recv_thread.join(timeout=5)

        except Exception:
            logger.exception("[SeedASR] connection/stream error")
        finally:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
            if self._mic:
                self._mic.terminate()
            if self._ws:
                try:
                    self._ws.close()
                except Exception:
                    pass
            self._stream = None
            self._mic = None
            self._ws = None
            if recv_thread and recv_thread.is_alive():
                recv_thread.join(timeout=2)

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
    mode = normalize_asr_mode(os.getenv("ASR_MODE"))
    if mode == "local":
        return LocalASR(on_text)
    elif mode in {"webspeech", "browser", "edge-webspeech"}:
        return BrowserSpeechASR(on_text)
    elif mode == "dashscope":
        return DashScopeASR(on_text)
    elif mode == "seed-asr":
        return SeedASR(on_text)
    else:
        return MockASR(on_text)
