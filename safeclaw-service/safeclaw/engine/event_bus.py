"""In-process event bus for real-time SafeClaw events."""

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("safeclaw.events")

MAX_SUBSCRIBERS_PER_EVENT = 100
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
        self._lock = asyncio.Lock()

    def publish(self, event: SafeClawEvent) -> None:
        """Non-blocking publish to all subscribers. Drops if queue full."""
        # Iterate over a snapshot to avoid issues with concurrent modification
        snapshot = list(self._subscribers)
        dead = []
        for q in snapshot:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.debug("Event queue full, dropping event for subscriber")
            except Exception:
                dead.append(q)
        for q in dead:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass  # already removed by another coroutine

    def _add_subscriber(self) -> asyncio.Queue[SafeClawEvent]:
        """Eagerly validate and add a subscriber queue. Raises ValueError if at limit."""
        if len(self._subscribers) >= MAX_SUBSCRIBERS_PER_EVENT:
            raise ValueError(
                f"Max subscribers limit reached ({MAX_SUBSCRIBERS_PER_EVENT}). "
                "Cannot add more subscribers."
            )
        q: asyncio.Queue[SafeClawEvent] = asyncio.Queue(maxsize=MAX_QUEUED_EVENTS)
        self._subscribers.append(q)
        return q

    async def subscribe(self, keepalive_timeout: float | None = None):
        """Yield events as they arrive. Use as `async for event in bus.subscribe():`.

        Raises ValueError eagerly if the subscriber limit is reached.

        If keepalive_timeout is set, yields None when no event arrives within
        that many seconds (caller can use this to send keepalive pings).
        """
        q = self._add_subscriber()
        try:
            while True:
                if keepalive_timeout is not None:
                    try:
                        event = await asyncio.wait_for(q.get(), timeout=keepalive_timeout)
                    except asyncio.TimeoutError:
                        yield None
                        continue
                else:
                    event = await q.get()
                yield event
        finally:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass  # already removed
