import asyncio
from dataclasses import dataclass, field

from pydantic import BaseModel, Field


class Event(BaseModel):
    type: str
    session_id: str | None = None
    data: dict[str, object] = Field(default_factory=dict)


@dataclass(eq=False)
class Subscription:
    owner_id: str
    queue: asyncio.Queue[Event] = field(default_factory=lambda: asyncio.Queue(maxsize=128))


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[Subscription] = set()

    def subscribe(self, owner_id: str) -> Subscription:
        subscription = Subscription(owner_id)
        self._subscribers.add(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        self._subscribers.discard(subscription)

    def publish(self, owner_id: str, event: Event) -> None:
        for subscription in self._subscribers:
            if subscription.owner_id != owner_id:
                continue
            if subscription.queue.full():
                # Transcripts remain durable; a slow client must reload its snapshot.
                while not subscription.queue.empty():
                    subscription.queue.get_nowait()
                subscription.queue.put_nowait(Event(type="resync_required", session_id=event.session_id))
            subscription.queue.put_nowait(event)
