import asyncio
import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import Literal, TypedDict

from cryptography.exceptions import InvalidTag
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, ValidationError

from classfox.audio import AudioError
from classfox.phone_commands import COMMAND, Hello, PhoneClassrooms, Status
from classfox.phone_crypto import MessageTooLarge, PhoneCipher


class PairingDenied(Exception):
    pass


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: StrictInt = Field(ge=1, le=1)
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    client_nonce: str = Field(pattern=r"^[a-f0-9]{64}$")
    counter: StrictInt = Field(ge=1, lt=2**32)
    ciphertext: str = Field(min_length=24, max_length=956000)


class Reply(TypedDict):
    version: Literal[1]
    counter: int
    ciphertext: str


@dataclass
class Pair:
    id: str
    secret: bytes = field(repr=False)
    deadline: float
    state: Literal["offered", "pending", "approved"] = "offered"
    valid: bool = True
    name: str = ""
    client_nonce: str = ""
    cipher: PhoneCipher | None = field(default=None, repr=False)
    counter: int = 0
    fingerprint: bytes = field(default=b"", repr=False)
    task: asyncio.Task[Reply] | None = field(default=None, repr=False)
    response: Reply | None = field(default=None, repr=False)
    window_started: float = 0
    requests: int = 0

    @property
    def owner(self) -> str:
        return "phone:" + self.id


class Pairings:
    def __init__(self, classrooms: PhoneClassrooms, *, clock: Callable[[], float] = monotonic) -> None:
        self.classrooms, self.clock = classrooms, clock
        self._pairs: dict[str, Pair] = {}
        self._retiring: dict[str, asyncio.Task[None]] = {}
        self._management = asyncio.Lock()

    def guard(self, pair: Pair) -> None:
        if not pair.valid or self.clock() >= pair.deadline or self._pairs.get(pair.id) is not pair:
            raise PairingDenied

    async def offer(self, address: str, port: int) -> dict[str, JsonValue]:
        async with self._management:
            for pair in list(self._pairs.values()):
                if pair.state != "approved" or not pair.valid or self.clock() >= pair.deadline:
                    await self.revoke(pair.id)
            if len(self._pairs) >= 4:
                raise ValueError("最多连接 4 台手机，请先撤销不再使用的连接")
            pair = Pair(secrets.token_hex(16), secrets.token_bytes(32), self.clock() + 120)
            self._pairs[pair.id] = pair
            return {"version": 1, "address": address, "port": port, "id": pair.id, "secret": pair.secret.hex(), "expires_in": 120}

    def status(self) -> list[dict[str, JsonValue]]:
        return [
            {
                "id": pair.id,
                "name": pair.name,
                "client_nonce": pair.client_nonce,
                "state": pair.state,
                "verification_code": pair.cipher.verification_code if pair.cipher else None,
                "expires_in": max(0, round(pair.deadline - self.clock())),
            }
            for pair in self._pairs.values()
            if pair.valid and self.clock() < pair.deadline
        ]

    def approve(self, pair_id: str, client_nonce: str) -> None:
        pair = self._pairs.get(pair_id)
        if pair is None:
            raise PairingDenied
        self.guard(pair)
        if pair.state != "pending" or not secrets.compare_digest(pair.client_nonce, client_nonce):
            raise PairingDenied
        pair.state = "approved"
        pair.deadline = self.clock() + 8 * 3600

    def _claim(self, pair: Pair, envelope: Envelope) -> None:
        if envelope.counter != 1:
            raise PairingDenied
        cipher = PhoneCipher(pair.secret, pair.id, bytes.fromhex(envelope.client_nonce))
        message = cipher.open("c2s", 1, envelope.ciphertext)
        # A valid tag consumes the offer even if the authenticated hello is malformed.
        pair.cipher, pair.client_nonce, pair.secret = cipher, envelope.client_nonce, b""
        pair.state = "pending"
        try:
            command = COMMAND.validate_python(message)
            if not isinstance(command, Hello):
                raise ValueError("Expected hello")
            pair.name = command.name
        except ValueError:
            pair.valid = False
            raise PairingDenied from None

    async def receive(self, envelope: Envelope) -> Reply:
        pair = self._pairs.get(envelope.id)
        if pair is None:
            raise PairingDenied
        self.guard(pair)
        try:
            if pair.cipher is None:
                self._claim(pair, envelope)
            if not secrets.compare_digest(pair.client_nonce, envelope.client_nonce):
                raise PairingDenied
            fingerprint = hashlib.sha256(envelope.ciphertext.encode("ascii")).digest()
            if envelope.counter == pair.counter and secrets.compare_digest(fingerprint, pair.fingerprint):
                if pair.response is not None:
                    return pair.response
                if pair.task:
                    return await asyncio.shield(pair.task)
            if envelope.counter != pair.counter + 1 or (pair.task and not pair.task.done()):
                raise PairingDenied
            self._rate(pair)
            assert pair.cipher is not None
            message = pair.cipher.open("c2s", envelope.counter, envelope.ciphertext)
        except (ValueError, InvalidTag, UnicodeError):
            raise PairingDenied from None
        # Reserve before any business side effect. Disconnects never rerun this operation.
        pair.counter, pair.fingerprint, pair.response = envelope.counter, fingerprint, None
        pair.task = asyncio.create_task(self._execute(pair, message), name="phone-request")
        pair.task.add_done_callback(lambda task: None if task.cancelled() else task.exception())
        return await asyncio.shield(pair.task)

    def _rate(self, pair: Pair) -> None:
        now = self.clock()
        if now - pair.window_started >= 60:
            pair.window_started, pair.requests = now, 0
        pair.requests += 1
        if pair.requests > 180:
            raise PairingDenied

    async def _execute(self, pair: Pair, message: dict[str, JsonValue]) -> Reply:
        try:
            result = await self._result(pair, message)
            self.guard(pair)
            assert pair.cipher is not None
            try:
                ciphertext = pair.cipher.seal("s2c", pair.counter, result)
            except MessageTooLarge:
                # This specific failure happens before encryption, so the nonce is unused.
                ciphertext = pair.cipher.seal("s2c", pair.counter, {"error": "response_too_large", "message": "内容过长，请分段读取或导出已同步记录"})
            response: Reply = {"version": 1, "counter": pair.counter, "ciphertext": ciphertext}
            pair.response = response
            return response
        except BaseException:
            # An uncertain side effect or uncached ciphertext must never reuse this key.
            pair.valid = False
            raise PairingDenied from None

    async def _result(self, pair: Pair, message: dict[str, JsonValue]) -> dict[str, JsonValue]:
        self.guard(pair)
        try:
            command = COMMAND.validate_python(message)
            if isinstance(command, (Hello, Status)):
                return {"state": pair.state, "verification_code": pair.cipher.verification_code if pair.cipher else None}
            if pair.state != "approved":
                return {"error": "pending_approval", "message": "请在电脑确认此手机连接"}
            return await self.classrooms.dispatch(pair.owner, command, lambda: self.guard(pair))
        except ValidationError:
            return {"error": "invalid_request", "message": "手机请求格式无效，请更新小程序后重试"}
        except KeyError:
            return {"error": "not_found", "message": "未找到此连接的课堂或任务"}
        except AudioError as error:
            return {"error": error.code, "message": str(error)}
        except ValueError as error:
            return {"error": "invalid_state", "message": str(error)}

    async def revoke(self, pair_id: str) -> None:
        if retiring := self._retiring.get(pair_id):
            await asyncio.shield(retiring)
            return
        pair = self._pairs.pop(pair_id, None)
        if pair is None:
            return
        pair.valid, pair.secret = False, b""
        cleanup = asyncio.create_task(self._cleanup(pair), name="phone-cleanup")
        self._retiring[pair_id] = cleanup
        await asyncio.shield(cleanup)

    async def _cleanup(self, pair: Pair) -> None:
        if pair.task and not pair.task.done():
            pair.task.cancel()
            await asyncio.gather(pair.task, return_exceptions=True)
        await self.classrooms.close_owner(pair.owner)
        pair.cipher, pair.response = None, None
        self._retiring.pop(pair.id, None)

    async def expire(self) -> None:
        for pair in list(self._pairs.values()):
            if not pair.valid or self.clock() >= pair.deadline:
                await self.revoke(pair.id)

    async def close(self) -> None:
        for pair in list(self._pairs.values()):
            pair.valid = False
        for pair_id in list(self._pairs):
            await self.revoke(pair_id)
        if self._retiring:
            await asyncio.gather(*(asyncio.shield(task) for task in list(self._retiring.values())))
