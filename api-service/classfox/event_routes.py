import asyncio
import secrets
from contextlib import suppress
from typing import Literal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from classfox.config import RuntimeConfig
from classfox.events import Event, Subscription
from classfox.runtime import Classroom


class Authentication(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["auth"]
    token: SecretStr


async def authenticate(websocket: WebSocket, config: RuntimeConfig) -> bool:
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in config.allowed_origins:
        await websocket.close(code=1008)
        return False
    await websocket.accept()
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=5)
        if len(raw) > 4096:
            raise ValueError("oversized authentication")
        auth = Authentication.model_validate_json(raw)
        if secrets.compare_digest(auth.token.get_secret_value().encode("utf-8"), config.api_token.encode("utf-8")):
            return True
    except (TimeoutError, ValidationError, ValueError, TypeError):
        pass
    await websocket.close(code=1008)
    return False


async def send_events(websocket: WebSocket, subscription: Subscription) -> None:
    while True:
        event = await subscription.queue.get()
        await websocket.send_text(event.model_dump_json())


async def receive_heartbeat(websocket: WebSocket, subscription: Subscription) -> None:
    while True:
        message = await websocket.receive_text()
        if message != "ping":
            await websocket.close(code=1008)
            return
        if not subscription.queue.full():
            subscription.queue.put_nowait(Event(type="pong"))


def event_routes() -> APIRouter:
    router = APIRouter()

    @router.websocket("/api/v2/events")
    async def events(websocket: WebSocket) -> None:
        config: RuntimeConfig = websocket.app.state.config
        classroom: Classroom = websocket.app.state.classroom
        subscription: Subscription | None = None
        workers: list[asyncio.Task[None]] = []
        try:
            if not await authenticate(websocket, config):
                return
            subscription = classroom.events.subscribe("desktop")
            session = classroom.current()
            await websocket.send_json(
                {"type": "snapshot", "data": {"session": session.model_dump(mode="json") if session else None, "source": classroom.source}}
            )
            workers = [asyncio.create_task(send_events(websocket, subscription)), asyncio.create_task(receive_heartbeat(websocket, subscription))]
            completed, _ = await asyncio.wait(workers, return_when=asyncio.FIRST_COMPLETED)
            for worker in completed:
                worker.result()
        except WebSocketDisconnect:
            pass
        finally:
            if subscription:
                classroom.events.unsubscribe(subscription)
            for worker in workers:
                worker.cancel()
                with suppress(asyncio.CancelledError, WebSocketDisconnect):
                    await worker

    return router
