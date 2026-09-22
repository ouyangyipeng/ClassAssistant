from pathlib import Path

from classfox.events import Event, EventBus
from classfox.models import SessionCreate
from classfox.runtime import Classroom
from classfox.settings import Preferences, SettingsStore
from classfox.storage import Store


async def test_retried_ingest_does_not_repeat_alerts_and_isolated_subscriber_receives_nothing(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite3")
    settings = SettingsStore(tmp_path / "prefs.json")
    settings.save(Preferences(keywords=["小王"]))
    events = EventBus()
    room = Classroom(store, settings, events)
    session = await room.start(SessionCreate(source="text"))
    local = events.subscribe("desktop")
    other = events.subscribe("unrelated-phone")
    room.ingest(session.id, "小王同学，请回答问题。", "source-1")
    room.ingest(session.id, "小王同学，请回答问题。", "source-1")
    assert local.queue.qsize() == 2
    assert (await local.queue.get()).type == "transcript"
    assert (await local.queue.get()).type == "alert"
    assert other.queue.empty()
    await room.close()
    store.close()


def test_slow_subscriber_is_told_to_resynchronize_instead_of_using_unbounded_memory() -> None:
    events = EventBus()
    subscriber = events.subscribe("desktop")
    for _ in range(129):
        events.publish("desktop", Event(type="transcript"))
    assert subscriber.queue.qsize() < 128
    assert subscriber.queue.get_nowait().type == "resync_required"
