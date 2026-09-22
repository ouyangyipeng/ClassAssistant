import asyncio
from pathlib import Path

import pytest

from classfox.app import create_app
from classfox.assistant import Assistant
from classfox.assistant_context import TaskRequest
from classfox.config import RuntimeConfig
from classfox.phone_commands import CreateSession
from classfox.phone_gateway import PhoneGateway
from tests.test_audio_runtime import NoCredentials
from tests.test_phone_pairing import paired


async def test_gateway_close_during_expiry_waits_for_all_owner_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app(RuntimeConfig(data_dir=tmp_path, api_token="synthetic"), credentials=NoCredentials())
    entered, release = asyncio.Event(), asyncio.Event()
    started = 0

    async def pending(*_args: object) -> None:
        nonlocal started
        started += 1
        await asyncio.Event().wait()

    monkeypatch.setattr(Assistant, "_run", pending)
    async with app.router.lifespan_context(app):
        gateway: PhoneGateway = app.state.phone_gateway
        await gateway.start("127.0.0.1", allow_loopback=True)
        now = [100.0]
        gateway.pairings.clock = lambda: now[0]
        _, pair_id, nonce = await paired(gateway.pairings)
        gateway.pairings.approve(pair_id, nonce)
        owner = "phone:" + pair_id
        rooms = gateway.classrooms
        await rooms.dispatch(owner, CreateSession(operation="create", course_name="过期课堂"), lambda: None)
        session = rooms.store.list_sessions(owner_id=owner)[0]
        rooms.store.append_entry(session.id, "原文")
        jobs = [rooms.assistant.start(session.id, TaskRequest(kind=kind), owner_id=owner) for kind in ("rescue", "catchup")]
        await asyncio.sleep(0)
        assert started == 2
        original = rooms.close_owner

        async def delayed(owner_id: str) -> None:
            entered.set()
            await release.wait()
            await original(owner_id)

        monkeypatch.setattr(rooms, "close_owner", delayed)
        now[0] += 8 * 3600 + 1
        await asyncio.wait_for(entered.wait(), 2)
        closing = asyncio.create_task(gateway.close())
        await asyncio.sleep(0)
        assert not closing.done()
        release.set()
        await asyncio.wait_for(closing, 3)
        assert [rooms.assistant.get(job.id, owner_id=owner).status for job in jobs] == ["cancelled", "cancelled"]
        assert rooms.store.get_session(session.id).status == "stopped"
