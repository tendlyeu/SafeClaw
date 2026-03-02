"""Heartbeat monitor for detecting plugin tampering."""

import logging
import time
from collections import OrderedDict

from safeclaw.engine.event_bus import EventBus, SafeClawEvent

logger = logging.getLogger("safeclaw.heartbeat")

MAX_AGENTS = 1000


class HeartbeatMonitor:
    """Tracks agent heartbeats and detects staleness or config drift."""

    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        # {agent_id: {"last_seen": monotonic, "config_hash": str, "first_hash": str}}
        self._agents: OrderedDict[str, dict] = OrderedDict()

    def record(self, agent_id: str, config_hash: str) -> None:
        """Record a heartbeat from an agent."""
        now = time.monotonic()
        if agent_id not in self._agents:
            self._agents[agent_id] = {
                "last_seen": now,
                "config_hash": config_hash,
                "first_hash": config_hash,
            }
            # LRU eviction: pop oldest entry when over capacity
            while len(self._agents) > MAX_AGENTS:
                self._agents.popitem(last=False)
        else:
            self._agents.move_to_end(agent_id)
            self._agents[agent_id]["last_seen"] = now
            self._agents[agent_id]["config_hash"] = config_hash

    def check_stale(self, threshold: float = 90.0) -> list[str]:
        """Return agent IDs that haven't sent a heartbeat within threshold seconds."""
        now = time.monotonic()
        stale = []
        for agent_id, info in self._agents.items():
            if now - info["last_seen"] > threshold:
                stale.append(agent_id)
                self._event_bus.publish(
                    SafeClawEvent(
                        event_type="heartbeat_lost",
                        severity="critical",
                        title=f"Agent {agent_id} heartbeat lost",
                        detail=f"No heartbeat for {int(now - info['last_seen'])}s "
                        f"(threshold: {int(threshold)}s). "
                        "Plugin may have been disabled or uninstalled.",
                    )
                )
        return stale

    def check_config_drift(self, agent_id: str, current_hash: str) -> bool:
        """Check if an agent's config hash has changed from its first-seen value."""
        info = self._agents.get(agent_id)
        if info is None:
            return False
        if info["first_hash"] != current_hash:
            self._event_bus.publish(
                SafeClawEvent(
                    event_type="config_drift",
                    severity="critical",
                    title=f"Agent {agent_id} config hash changed",
                    detail="Plugin configuration was modified since registration. "
                    "Possible tampering detected.",
                )
            )
            return True
        return False

    def remove(self, agent_id: str) -> None:
        """Remove an agent (intentional shutdown)."""
        self._agents.pop(agent_id, None)
