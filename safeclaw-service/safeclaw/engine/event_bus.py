"""In-process event bus for real-time SafeClaw events."""

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("safeclaw.events")

MAX_SUBSCRIBERS = 50
MAX_QUEUED_EVENTS = 100


@dataclass
class SafeClawEvent:
    event_type: str  # "blocked", "security_finding", "allowed", etc.
    severity: str  # "info", "warning", "critical"
    title: str
    detail: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)


class EventBus:
    """Publish/subscribe event bus using asyncio.Queue — no external deps."""

    def __init__(self):
        self._subscribers: list[asyncio.Queue[SafeClawEvent]] = []

    def publish(self, event: SafeClawEvent) -> None:
        """Non-blocking publish to all subscribers. Drops if queue full."""
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.debug("Event queue full, dropping event for subscriber")
            except Exception:
                dead.append(q)
        for q in dead:
            self._subscribers.remove(q)

    async def subscribe(self):
        """Yield events as they arrive. Use as `async for event in bus.subscribe():`."""
        if len(self._subscribers) >= MAX_SUBSCRIBERS:
            logger.warning("Max subscribers reached (%d), rejecting", MAX_SUBSCRIBERS)
            return
        q: asyncio.Queue[SafeClawEvent] = asyncio.Queue(maxsize=MAX_QUEUED_EVENTS)
        self._subscribers.append(q)
        try:
            while True:
                event = await q.get()
                yield event
        finally:
            if q in self._subscribers:
                self._subscribers.remove(q)
