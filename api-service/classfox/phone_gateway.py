import asyncio
import ipaddress
import logging
import socket
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from time import monotonic

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from classfox.phone_commands import PhoneClassrooms
from classfox.phone_pairing import Envelope, PairingDenied, Pairings

logger = logging.getLogger(__name__)
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(network) for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


class GatewayServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        # The desktop launcher alone owns process signals and shutdown.
        yield


class PhoneGateway:
    def __init__(self, classrooms: PhoneClassrooms) -> None:
        self.classrooms = classrooms
        self.pairings = Pairings(classrooms)
        self.address: str | None = None
        self.port: int | None = None
        self._server: GatewayServer | None = None
        self._serving: asyncio.Task[None] | None = None
        self._maintenance: asyncio.Task[None] | None = None
        self._socket: socket.socket | None = None
        self._lifecycle = asyncio.Lock()

    def status(self) -> dict[str, JsonValue]:
        listening = self._server is not None and self._server.started and self._serving is not None and not self._serving.done()
        connections: list[JsonValue] = [pair for pair in self.pairings.status()]
        return {"listening": listening, "address": self.address, "port": self.port, "connections": connections}

    async def start(self, address: str, *, allow_loopback: bool = False) -> None:
        ip = ipaddress.IPv4Address(address)
        if not any(ip in network for network in PRIVATE_NETWORKS) and not (allow_loopback and ip.is_loopback):
            raise ValueError("请输入此电脑 Wi-Fi 的局域网 IPv4 地址，例如 192.168.1.20")
        async with self._lifecycle:
            if self._server is not None:
                raise ValueError("手机连接已开启，请先关闭后再更换地址")
            self.pairings = Pairings(self.classrooms)
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                self._socket.bind((str(ip), 0))
                self._socket.setblocking(False)
                self.address, self.port = str(ip), self._socket.getsockname()[1]
                config = uvicorn.Config(
                    self._application(),
                    access_log=False,
                    log_level="warning",
                    lifespan="off",
                    timeout_graceful_shutdown=3,
                    timeout_keep_alive=5,
                    limit_concurrency=16,
                    backlog=32,
                )
                self._server = GatewayServer(config)
                self._serving = asyncio.create_task(self._server.serve(sockets=[self._socket]), name="phone-gateway")
                async with asyncio.timeout(5):
                    while not self._server.started and not self._serving.done():
                        await asyncio.sleep(0.01)
                if not self._server.started:
                    raise ValueError("手机入口未能启动，请检查所选网络")
                self._maintenance = asyncio.create_task(self._maintain(), name="phone-expiry")
            except BaseException:
                await self._close()
                raise

    async def offer(self) -> dict[str, JsonValue]:
        async with self._lifecycle:
            if not self.status()["listening"] or self.address is None or self.port is None:
                raise ValueError("请先开启电脑的手机连接入口")
            return await self.pairings.offer(self.address, self.port)

    async def _maintain(self) -> None:
        while self._serving and not self._serving.done():
            await self.pairings.expire()
            await asyncio.sleep(0.5)
        await self.pairings.close()

    async def close(self) -> None:
        async with self._lifecycle:
            await self._close()

    async def _close(self) -> None:
        server, self._server = self._server, None
        if server:
            server.should_exit = True
        if self._maintenance:
            self._maintenance.cancel()
            await asyncio.gather(self._maintenance, return_exceptions=True)
            self._maintenance = None
        await self.pairings.close()
        if self._serving:
            await asyncio.gather(self._serving, return_exceptions=True)
            self._serving = None
        if self._socket:
            self._socket.close()
            self._socket = None
        self.address, self.port = None, None

    def _application(self) -> FastAPI:
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        host, pairings = f"{self.address}:{self.port}", self.pairings
        recent: deque[float] = deque(maxlen=60)

        @app.post("/phone/v1")
        async def message(request: Request) -> JSONResponse:
            if request.headers.get("origin") is not None or request.headers.get("host") != host or request.url.query:
                return failure(403)
            if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
                return failure(415)
            now = monotonic()
            if len(recent) == 60 and now - recent[0] < 1:
                return failure(429)
            recent.append(now)
            try:
                raw = await bounded_body(request)
                envelope = Envelope.model_validate_json(raw)
                response = await pairings.receive(envelope)
                return JSONResponse(response, headers={"Cache-Control": "no-store"})
            except HTTPException as error:
                return failure(error.status_code)
            except TimeoutError:
                return failure(408)
            except (ValidationError, ValueError, RecursionError):
                return failure(400)
            except PairingDenied:
                return failure(403)
            except Exception as error:
                logger.error("Phone gateway request failed: %s", type(error).__name__)
                return failure(503)

        return app


async def bounded_body(request: Request) -> bytes:
    raw = bytearray()
    async with asyncio.timeout(5):
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 1024 * 1024:
                raise HTTPException(413)
            raw.extend(chunk)
    return bytes(raw)


def failure(status: int) -> JSONResponse:
    return JSONResponse({"error": "connection_rejected"}, status_code=status, headers={"Cache-Control": "no-store"})


class GatewayStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address: str = Field(min_length=7, max_length=15)


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_nonce: str = Field(pattern=r"^[a-f0-9]{64}$")


def phone_routes() -> APIRouter:
    router = APIRouter(prefix="/api/v2/phone")

    @router.get("/addresses")
    async def addresses() -> dict[str, JsonValue]:
        try:
            async with asyncio.timeout(3):
                results = await asyncio.to_thread(socket.getaddrinfo, socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM)
            found = {str(result[4][0]) for result in results}
            private: list[JsonValue] = [address for address in sorted(found) if any(ipaddress.IPv4Address(address) in network for network in PRIVATE_NETWORKS)]
            return {"addresses": private, "message": "" if private else "未自动找到局域网地址，请查看系统 Wi-Fi 详情后填写"}
        except (OSError, TimeoutError):
            return {"addresses": [], "message": "暂时无法发现网络地址，请查看系统 Wi-Fi 详情后填写"}

    @router.get("")
    async def status(request: Request) -> dict[str, JsonValue]:
        gateway: PhoneGateway = request.app.state.phone_gateway
        return gateway.status()

    @router.post("")
    async def start(request: Request, payload: GatewayStart) -> dict[str, JsonValue]:
        gateway: PhoneGateway = request.app.state.phone_gateway
        await gateway.start(payload.address)
        return gateway.status()

    @router.delete("")
    async def close(request: Request) -> dict[str, JsonValue]:
        gateway: PhoneGateway = request.app.state.phone_gateway
        await gateway.close()
        return gateway.status()

    @router.post("/offers")
    async def offer(request: Request) -> dict[str, JsonValue]:
        gateway: PhoneGateway = request.app.state.phone_gateway
        return await gateway.offer()

    @router.post("/{pair_id}/approve")
    async def approve(request: Request, pair_id: str, payload: Approval) -> dict[str, bool]:
        gateway: PhoneGateway = request.app.state.phone_gateway
        try:
            gateway.pairings.approve(pair_id, payload.client_nonce)
        except PairingDenied:
            raise HTTPException(409, "配对已过期或手机连接已变化，请重新扫码") from None
        return {"approved": True}

    @router.delete("/{pair_id}")
    async def revoke(request: Request, pair_id: str) -> dict[str, bool]:
        gateway: PhoneGateway = request.app.state.phone_gateway
        await gateway.pairings.revoke(pair_id)
        return {"revoked": True}

    return router
