import asyncio
import logging
import secrets
import sqlite3
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Annotated

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from classfox import __version__
from classfox.assistant import Assistant
from classfox.assistant_context import TaskRequest
from classfox.assistant_routes import assistant_routes
from classfox.audio import AudioError
from classfox.audio_routes import audio_routes
from classfox.config import RuntimeConfig
from classfox.credential_routes import credential_routes
from classfox.credentials import CredentialError, Credentials, SystemCredentials
from classfox.event_routes import event_routes
from classfox.events import Event, EventBus
from classfox.instance import DataDirectoryInUse, data_directory_lock
from classfox.library_routes import library_routes
from classfox.llm import LLMError, LLMService
from classfox.model_install import ModelInstaller
from classfox.model_probe import probe_model, runtime_executable
from classfox.model_process import ModelEndpoint, ModelProcessError, OwnedModelProcess
from classfox.model_routes import model_routes
from classfox.models import Session, SessionCreate, TextInput, TranscriptEntry
from classfox.phone_commands import PhoneClassrooms
from classfox.phone_gateway import PhoneGateway, phone_routes
from classfox.runtime import Classroom
from classfox.settings import Preferences, SettingsStore
from classfox.speech import SpeechService
from classfox.storage import Store

logger = logging.getLogger(__name__)


class AccessBoundary:
    def __init__(self, app: ASGIApp, config: RuntimeConfig) -> None:
        self.app = app
        self.config = config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        origin = request.headers.get("origin")
        if origin is not None and origin not in self.config.allowed_origins:
            await JSONResponse({"error": "origin_denied", "message": "此来源无权访问课堂服务"}, status_code=403)(scope, receive, send)
            return
        if request.url.path != "/api/health":
            expected = f"Bearer {self.config.api_token}"
            if not secrets.compare_digest(request.headers.get("authorization", "").encode("utf-8"), expected.encode("utf-8")):
                await JSONResponse({"error": "unauthorized", "message": "连接凭据无效，请重新连接应用"}, status_code=401)(scope, receive, send)
                return
        limit = self.config.upload_limit + 1024 * 1024 if request.headers.get("content-type", "").startswith("multipart/") else 256 * 1024
        try:
            length = int(request.headers.get("content-length", "0"))
            if length < 0:
                raise ValueError
        except ValueError:
            await JSONResponse({"error": "invalid_length", "message": "无效的请求长度"}, status_code=400)(scope, receive, send)
            return
        if length > limit:
            await JSONResponse({"error": "too_large", "message": "请求体积过大，请拆分后提交"}, status_code=413)(scope, receive, send)
            return
        received = 0

        async def bounded_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(status_code=413, detail="请求体积过大，请拆分后提交")
            return message

        await self.app(scope, bounded_receive, send)


def create_app(
    config: RuntimeConfig | None = None,
    *,
    credentials: Credentials | None = None,
    provider_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    runtime_config = config or RuntimeConfig.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as resources:
            try:
                resources.enter_context(data_directory_lock(runtime_config.data_dir))
            except DataDirectoryInUse:
                app.state.data_directory_in_use = True
                raise
            store = Store(runtime_config.data_dir / "classfox.sqlite3")
            resources.callback(store.close)
            store.recover_interrupted_sessions()
            settings = SettingsStore(runtime_config.data_dir / "preferences.json")
            classroom = Classroom(store, settings, EventBus())
            owned_model = OwnedModelProcess()
            resources.push_async_callback(owned_model.close)
            models = ModelInstaller(runtime_config.data_dir / "models", classroom.events, probe_model)
            resources.push_async_callback(models.close)

            async def local_model(model_id: str) -> ModelEndpoint:
                definition = models.catalog.get(model_id)
                if definition is None or definition.kind != "llm":
                    raise ModelProcessError("请选择可用的本地问答模型")
                if owned_model.ready:
                    return owned_model.endpoint()
                directory = await models.verified_path(model_id)
                if directory is None:
                    raise ModelProcessError("请先在模型管理中安装本地问答模型")
                weights = next(asset.filename for asset in definition.files if asset.filename.endswith(".gguf"))
                return await owned_model.start([str(runtime_executable(directory))], directory / weights)

            app.state.classroom = classroom
            app.state.models = models
            app.state.owned_model = owned_model
            app.state.local_model = local_model
            app.state.config = runtime_config
            app.state.credentials = credentials if credentials is not None else SystemCredentials()
            speech = SpeechService(settings, app.state.credentials, models)
            classroom.speech = speech
            app.state.speech = speech
            resources.push_async_callback(speech.close)
            assistant = Assistant(store, settings, classroom.events, LLMService(app.state.credentials, transport=provider_transport, local_model=local_model))
            resources.push_async_callback(assistant.close)
            resources.push_async_callback(classroom.close)
            app.state.assistant = assistant
            gateway = PhoneGateway(PhoneClassrooms(classroom, assistant, speech))
            app.state.phone_gateway = gateway
            resources.push_async_callback(gateway.close)
            app.state.parse_gate = asyncio.Semaphore(2)
            yield

    app = FastAPI(title="ClassFox", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(AccessBoundary, config=runtime_config)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime_config.allowed_origins),
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_errors(app)
    app.include_router(classroom_routes())
    app.include_router(library_routes())
    app.include_router(event_routes())
    app.include_router(credential_routes())
    app.include_router(assistant_routes())
    app.include_router(model_routes())
    app.include_router(audio_routes())
    app.include_router(phone_routes())

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy", "version": __version__}

    return app


def register_errors(app: FastAPI) -> None:
    @app.exception_handler(LLMError)
    async def llm_error(_request: Request, error: LLMError) -> JSONResponse:
        return JSONResponse({"error": error.code, "message": str(error)}, status_code=503)

    @app.exception_handler(AudioError)
    async def audio_error(_request: Request, error: AudioError) -> JSONResponse:
        return JSONResponse({"error": error.code, "message": str(error)}, status_code=422 if error.code == "invalid_audio" else 503)

    @app.exception_handler(ModelProcessError)
    async def model_error(_request: Request, error: ModelProcessError) -> JSONResponse:
        return JSONResponse({"error": "local_model_unavailable", "message": str(error)}, status_code=503)

    @app.exception_handler(CredentialError)
    async def credential_error(_request: Request, error: CredentialError) -> JSONResponse:
        return JSONResponse({"error": "credential_store_unavailable", "message": str(error)}, status_code=503)

    @app.exception_handler(KeyError)
    async def missing(_request: Request, _error: KeyError) -> JSONResponse:
        return JSONResponse({"error": "not_found", "message": "未找到请求的课堂或资料"}, status_code=404)

    @app.exception_handler(ValueError)
    async def conflict(_request: Request, error: ValueError) -> JSONResponse:
        return JSONResponse({"error": "invalid_state", "message": str(error)}, status_code=409)

    @app.exception_handler(RequestValidationError)
    async def invalid(_request: Request, _error: RequestValidationError) -> JSONResponse:
        # Validation errors contain submitted values, which may include credentials.
        return JSONResponse({"error": "invalid_request", "message": "请求格式无效，请检查输入内容"}, status_code=422)

    @app.exception_handler(OSError)
    async def storage_error(_request: Request, error: OSError) -> JSONResponse:
        logger.error("Storage operation failed: %s", type(error).__name__)
        return JSONResponse({"error": "storage_error", "message": "文件操作失败，请检查可用空间和目录权限"}, status_code=503)

    @app.exception_handler(sqlite3.Error)
    async def database_error(_request: Request, error: sqlite3.Error) -> JSONResponse:
        logger.error("Database operation failed: %s", type(error).__name__)
        return JSONResponse({"error": "storage_error", "message": "课堂记录保存失败，请检查磁盘空间并重试"}, status_code=503)


def classroom_routes() -> APIRouter:
    router = APIRouter(prefix="/api/v2")

    @router.get("/status")
    async def status(request: Request) -> dict[str, object]:
        classroom: Classroom = request.app.state.classroom
        session = classroom.current()
        return {"session": session.model_dump(mode="json") if session else None, "source": classroom.source}

    @router.get("/settings")
    async def settings(request: Request) -> Preferences:
        classroom: Classroom = request.app.state.classroom
        return classroom.settings.load()

    @router.put("/settings")
    async def save_settings(request: Request, preferences: Preferences) -> Preferences:
        classroom: Classroom = request.app.state.classroom
        classroom.settings.save(preferences)
        return preferences

    @router.get("/sessions")
    async def sessions(request: Request, limit: Annotated[int, Query(ge=1, le=500)] = 100, offset: Annotated[int, Query(ge=0)] = 0) -> list[Session]:
        classroom: Classroom = request.app.state.classroom
        return classroom.store.list_sessions(limit=limit, offset=offset)

    @router.post("/sessions", status_code=201)
    async def start(request: Request, payload: SessionCreate) -> Session:
        classroom: Classroom = request.app.state.classroom
        return await classroom.start(payload)

    @router.get("/sessions/{session_id}/entries")
    async def entries(request: Request, session_id: str, after_id: Annotated[int, Query(ge=0)] = 0) -> list[TranscriptEntry]:
        classroom: Classroom = request.app.state.classroom
        classroom.store.get_session(session_id, owner_id="desktop")
        return classroom.store.list_entries(session_id, after_id=after_id)

    @router.post("/sessions/{session_id}/entries", status_code=201)
    async def ingest(request: Request, session_id: str, payload: TextInput) -> TranscriptEntry:
        classroom: Classroom = request.app.state.classroom
        return classroom.ingest(session_id, payload.text, payload.source_id)

    @router.post("/sessions/{session_id}/stop")
    async def stop(request: Request, session_id: str) -> Session:
        classroom: Classroom = request.app.state.classroom
        was_active = classroom.active_id == session_id
        session = await classroom.stop(session_id)
        if was_active and classroom.settings.load().auto_summary and classroom.store.entry_extent(session_id)[1]:
            assistant: Assistant = request.app.state.assistant
            try:
                assistant.start(session_id, TaskRequest(kind="summary"))
            except ValueError:
                classroom.events.publish(
                    "desktop", Event(type="summary_deferred", session_id=session_id, data={"message": "录音已停止；生成任务繁忙，请从课堂记录中手动整理笔记"})
                )
        return session

    @router.post("/sessions/{session_id}/pause")
    async def pause(request: Request, session_id: str) -> Session:
        classroom: Classroom = request.app.state.classroom
        return await classroom.pause(session_id)

    @router.post("/sessions/{session_id}/resume")
    async def resume(request: Request, session_id: str) -> Session:
        classroom: Classroom = request.app.state.classroom
        return await classroom.resume(session_id)

    @router.get("/sessions/{session_id}/export")
    async def export(request: Request, session_id: str) -> PlainTextResponse:
        classroom: Classroom = request.app.state.classroom
        classroom.store.get_session(session_id, owner_id="desktop")
        return PlainTextResponse(classroom.store.export_session(session_id), headers={"Content-Disposition": 'attachment; filename="classroom.txt"'})

    return router
