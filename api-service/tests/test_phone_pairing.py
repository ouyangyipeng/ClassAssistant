import asyncio
from collections.abc import Callable
from typing import cast

import pytest
from pydantic import JsonValue

from classfox.phone_commands import PhoneClassrooms, PhoneCommand
from classfox.phone_crypto import PhoneCipher
from classfox.phone_pairing import Envelope, PairingDenied, Pairings


class FakeClassrooms:
    def __init__(self) -> None:
        self.calls = 0
        self.closed: list[str] = []
        self.waiting: asyncio.Event | None = None
        self.entered = asyncio.Event()

    async def dispatch(self, _owner: str, _command: PhoneCommand, guard: Callable[[], None]) -> dict[str, JsonValue]:
        guard()
        self.calls += 1
        self.entered.set()
        if self.waiting:
            await self.waiting.wait()
        guard()
        return {"created": True}

    async def close_owner(self, owner: str) -> None:
        self.closed.append(owner)


async def paired(manager: Pairings) -> tuple[PhoneCipher, str, str]:
    offer = await manager.offer("192.168.1.20", 40001)
    pair_id, secret = str(offer["id"]), str(offer["secret"])
    client_nonce = "12" * 32
    cipher = PhoneCipher(bytes.fromhex(secret), pair_id, bytes.fromhex(client_nonce))
    hello = envelope(cipher, client_nonce, 1, {"operation": "hello", "name": "合成测试手机"})
    result = await manager.receive(hello)
    assert cipher.open("s2c", 1, result["ciphertext"])["state"] == "pending"
    return cipher, pair_id, client_nonce


def envelope(cipher: PhoneCipher, client_nonce: str, counter: int, message: dict[str, JsonValue]) -> Envelope:
    return Envelope(version=1, id=cipher.pair_id, client_nonce=client_nonce, counter=counter, ciphertext=cipher.seal("c2s", counter, message))


async def test_requires_confirmation_and_retries_have_one_effect() -> None:
    rooms = FakeClassrooms()
    manager = Pairings(cast(PhoneClassrooms, rooms))
    cipher, pair_id, nonce = await paired(manager)
    command = envelope(cipher, nonce, 2, {"operation": "create", "course_name": "数学"})
    pending = await manager.receive(command)
    assert cipher.open("s2c", 2, pending["ciphertext"])["error"] == "pending_approval"
    assert rooms.calls == 0
    manager.approve(pair_id, nonce)
    # Approval cannot replace an already encrypted response with a new plaintext.
    assert await manager.receive(command) == pending
    command = envelope(cipher, nonce, 3, {"operation": "create", "course_name": "数学"})
    first, retry = await asyncio.gather(manager.receive(command), manager.receive(command))
    assert first == retry
    assert rooms.calls == 1
    with pytest.raises(PairingDenied):
        await manager.receive(envelope(cipher, nonce, 3, {"operation": "create", "course_name": "物理"}))
    with pytest.raises(PairingDenied):
        await manager.receive(envelope(cipher, nonce, 5, {"operation": "status"}))
    await manager.close()


async def test_revoke_cancels_inflight_and_cannot_be_revived() -> None:
    rooms = FakeClassrooms()
    rooms.waiting = asyncio.Event()
    manager = Pairings(cast(PhoneClassrooms, rooms))
    cipher, pair_id, nonce = await paired(manager)
    manager.approve(pair_id, nonce)
    command = envelope(cipher, nonce, 2, {"operation": "create", "course_name": "数学"})
    receiving = asyncio.create_task(manager.receive(command))
    await rooms.entered.wait()
    await asyncio.wait_for(manager.revoke(pair_id), 1)
    with pytest.raises((PairingDenied, asyncio.CancelledError)):
        await receiving
    with pytest.raises(PairingDenied):
        await manager.receive(command)
    with pytest.raises(PairingDenied):
        manager.approve(pair_id, nonce)
    assert rooms.closed == ["phone:" + pair_id]


async def test_expiry_is_monotonic_and_retires_without_phone_requests() -> None:
    now = [100.0]
    rooms = FakeClassrooms()
    manager = Pairings(cast(PhoneClassrooms, rooms), clock=lambda: now[0])
    cipher, pair_id, nonce = await paired(manager)
    now[0] += 121
    with pytest.raises(PairingDenied):
        manager.approve(pair_id, nonce)
    await manager.expire()
    assert manager.status() == []
    with pytest.raises(PairingDenied):
        await manager.receive(envelope(cipher, nonce, 2, {"operation": "status"}))
    assert rooms.closed == ["phone:" + pair_id]


async def test_unknown_invalid_or_second_client_cannot_claim_offer() -> None:
    rooms = FakeClassrooms()
    manager = Pairings(cast(PhoneClassrooms, rooms))
    cipher, pair_id, nonce = await paired(manager)
    with pytest.raises(PairingDenied):
        await manager.receive(envelope(cipher, "34" * 32, 1, {"operation": "hello", "name": "其他手机"}))
    with pytest.raises(PairingDenied):
        manager.approve(pair_id, "34" * 32)
    assert rooms.calls == 0
    await manager.close()


async def test_disconnect_does_not_cancel_or_repeat_reserved_side_effect() -> None:
    rooms = FakeClassrooms()
    rooms.waiting = asyncio.Event()
    manager = Pairings(cast(PhoneClassrooms, rooms))
    cipher, pair_id, nonce = await paired(manager)
    manager.approve(pair_id, nonce)
    command = envelope(cipher, nonce, 2, {"operation": "create", "course_name": "数学"})
    original = asyncio.create_task(manager.receive(command))
    await rooms.entered.wait()
    original.cancel()
    await asyncio.gather(original, return_exceptions=True)
    retry = asyncio.create_task(manager.receive(command))
    rooms.waiting.set()
    result = await retry
    assert result == await manager.receive(command)
    assert rooms.calls == 1
    await manager.close()


async def test_uncertain_response_retires_key_and_never_reexecutes(monkeypatch: pytest.MonkeyPatch) -> None:
    rooms = FakeClassrooms()
    manager = Pairings(cast(PhoneClassrooms, rooms))
    cipher, pair_id, nonce = await paired(manager)
    manager.approve(pair_id, nonce)
    command = envelope(cipher, nonce, 2, {"operation": "create", "course_name": "数学"})

    def fail_seal(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("Synthetic failure after the side effect")

    monkeypatch.setattr(PhoneCipher, "seal", fail_seal)
    with pytest.raises(PairingDenied):
        await manager.receive(command)
    with pytest.raises(PairingDenied):
        await manager.receive(command)
    assert rooms.calls == 1
    await manager.expire()
    assert rooms.closed == ["phone:" + pair_id]


async def test_cancelled_revoke_is_still_awaited_by_close(monkeypatch: pytest.MonkeyPatch) -> None:
    rooms = FakeClassrooms()
    manager = Pairings(cast(PhoneClassrooms, rooms))
    _, pair_id, nonce = await paired(manager)
    manager.approve(pair_id, nonce)
    entered, release = asyncio.Event(), asyncio.Event()

    async def cleanup(owner: str) -> None:
        entered.set()
        await release.wait()
        rooms.closed.append(owner)

    monkeypatch.setattr(rooms, "close_owner", cleanup)
    revoking = asyncio.create_task(manager.revoke(pair_id))
    await entered.wait()
    revoking.cancel()
    await asyncio.gather(revoking, return_exceptions=True)
    closing = asyncio.create_task(manager.close())
    await asyncio.sleep(0)
    assert not closing.done()
    release.set()
    await closing
    assert rooms.closed == ["phone:" + pair_id]


async def test_oversized_result_is_cached_error_without_losing_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    rooms = FakeClassrooms()
    manager = Pairings(cast(PhoneClassrooms, rooms))
    cipher, pair_id, nonce = await paired(manager)
    manager.approve(pair_id, nonce)

    async def too_large(_owner: str, _command: PhoneCommand, _guard: Callable[[], None]) -> dict[str, JsonValue]:
        rooms.calls += 1
        return {"text": "🦊" * 200000}

    monkeypatch.setattr(rooms, "dispatch", too_large)
    command = envelope(cipher, nonce, 2, {"operation": "create", "course_name": "课堂"})
    response = await manager.receive(command)
    assert cipher.open("s2c", 2, response["ciphertext"])["error"] == "response_too_large"
    assert await manager.receive(command) == response
    assert rooms.calls == 1
    response = await manager.receive(envelope(cipher, nonce, 3, {"operation": "status"}))
    assert cipher.open("s2c", 3, response["ciphertext"])["state"] == "approved"
    await manager.close()
