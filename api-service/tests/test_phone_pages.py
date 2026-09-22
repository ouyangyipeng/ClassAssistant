from typing import cast

import pytest

from classfox.phone_commands import PhoneClassrooms
from classfox.phone_pairing import Pairings
from tests.test_phone_commands import rooms
from tests.test_phone_pairing import envelope, paired

__all__ = ["rooms"]


@pytest.mark.parametrize("character", ["课", "🦊", "\x01"])
async def test_maximum_unicode_pages_remain_readable_through_encrypted_channel(rooms: PhoneClassrooms, character: str) -> None:
    manager = Pairings(rooms)
    cipher, pair_id, nonce = await paired(manager)
    manager.approve(pair_id, nonce)
    session = rooms.store.create_session("手机大文本", owner_id="phone:" + pair_id)
    for index in range(25):
        rooms.store.append_entry(session.id, character * 8000, source_id=str(index))
    for _ in range(2):
        rooms.store.save_summary(session.id, "合成笔记", character * 64000)
    after_id, seen, counter = 0, 0, 1
    while True:
        counter += 1
        response = await manager.receive(envelope(cipher, nonce, counter, {"operation": "entries", "session_id": session.id, "after_id": after_id}))
        result = cipher.open("s2c", counter, response["ciphertext"])
        entries = cast(list[dict[str, object]], result["entries"])
        if not entries:
            break
        seen += len(entries)
        after_id = cast(int, entries[-1]["id"])
    assert seen == 25
    for offset in range(3):
        counter += 1
        response = await manager.receive(envelope(cipher, nonce, counter, {"operation": "notes", "session_id": session.id, "offset": offset}))
        result = cipher.open("s2c", counter, response["ciphertext"])
        assert len(cast(list[object], result["notes"])) == (1 if offset < 2 else 0)
    assert manager.status()[0]["state"] == "approved"
    await manager.close()
