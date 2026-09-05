"""WebSocket-ready event contracts without a connected stream."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class BotEvent:
    event_type: str
    payload: dict[str, Any]


class EventPublisher(Protocol):
    async def publish(self, event: BotEvent) -> None:
        """Publish a future real-time event."""
