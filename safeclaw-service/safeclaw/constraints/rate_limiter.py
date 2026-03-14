"""Rate limiter - tracks action counts per session within time windows."""

import time
from collections import OrderedDict
from dataclasses import dataclass

from safeclaw.constraints.action_classifier import ClassifiedAction

MAX_SESSIONS = 1000

# Default rate limits: (max_count, window_seconds)
DEFAULT_LIMITS: dict[str, tuple[int, int]] = {
    "HighRisk": (10, 3600),
    "CriticalRisk": (3, 3600),
}

# Hierarchy-wide rate limits: (max_count, window_seconds)
HIERARCHY_LIMITS: dict[str, tuple[int, int]] = {
    "HighRisk": (30, 3600),       # 30 per hierarchy per hour
    "CriticalRisk": (10, 3600),   # 10 per hierarchy per hour
}


@dataclass
class RateLimitResult:
    exceeded: bool
    reason: str = ""


@dataclass
class _ActionRecord:
    risk_level: str
    timestamp: float


class RateLimiter:
    """Tracks action rates per session and enforces per-risk-level limits."""

    def __init__(
        self,
        limits: dict[str, tuple[int, int]] | None = None,
        hierarchy_limits: dict[str, tuple[int, int]] | None = None,
    ):
        self._limits = limits or dict(DEFAULT_LIMITS)
        self._hierarchy_limits = hierarchy_limits or dict(HIERARCHY_LIMITS)
        self._sessions: OrderedDict[str, list[_ActionRecord]] = OrderedDict()
        self._agent_records: OrderedDict[str, list[_ActionRecord]] = OrderedDict()

    def check(self, action: ClassifiedAction, session_id: str) -> RateLimitResult:
        """Check if the action would exceed rate limits for this session."""
        limit_entry = self._limits.get(action.risk_level)
        if limit_entry is None:
            return RateLimitResult(exceeded=False)

        max_count, window_seconds = limit_entry
        now = time.monotonic()
        cutoff = now - window_seconds

        records = self._sessions.get(session_id, [])
        records = [r for r in records if r.timestamp >= cutoff]
        if session_id in self._sessions:
            self._sessions[session_id] = records
            self._sessions.move_to_end(session_id)  # Update LRU position
        count = sum(
            1
            for r in records
            if r.risk_level == action.risk_level
        )

        if count >= max_count:
            return RateLimitResult(
                exceeded=True,
                reason=(
                    f"Rate limit exceeded: {count}/{max_count} "
                    f"{action.risk_level} actions in the last "
                    f"{window_seconds // 60} minutes"
                ),
            )

        return RateLimitResult(exceeded=False)

    def record(self, action: ClassifiedAction, session_id: str, agent_id: str = "") -> None:
        """Record an action for rate limiting purposes."""
        if session_id not in self._sessions:
            self._sessions[session_id] = []
            # Evict oldest sessions to prevent memory leak
            while len(self._sessions) > MAX_SESSIONS:
                self._sessions.popitem(last=False)

        records = self._sessions[session_id]
        # Prune expired records to prevent unbounded growth
        max_window = max((w for _, w in self._limits.values()), default=3600)
        cutoff = time.monotonic() - max_window
        self._sessions[session_id] = [r for r in records if r.timestamp >= cutoff]

        self._sessions[session_id].append(
            _ActionRecord(risk_level=action.risk_level, timestamp=time.monotonic())
        )

        # Also track by agent_id for hierarchy rate limiting
        if agent_id:
            if agent_id not in self._agent_records:
                self._agent_records[agent_id] = []
                while len(self._agent_records) > MAX_SESSIONS:
                    self._agent_records.popitem(last=False)
            records = self._agent_records[agent_id]
            max_window = max((w for _, w in self._hierarchy_limits.values()), default=3600)
            cutoff = time.monotonic() - max_window
            self._agent_records[agent_id] = [r for r in records if r.timestamp >= cutoff]
            self._agent_records[agent_id].append(
                _ActionRecord(risk_level=action.risk_level, timestamp=time.monotonic())
            )

    def check_hierarchy(self, action: ClassifiedAction, hierarchy_agent_ids: set[str]) -> RateLimitResult:
        """Check combined rate across all agents in a hierarchy."""
        limit_entry = self._hierarchy_limits.get(action.risk_level)
        if limit_entry is None:
            return RateLimitResult(exceeded=False)

        max_count, window_seconds = limit_entry
        now = time.monotonic()
        cutoff = now - window_seconds

        count = 0
        for agent_id in hierarchy_agent_ids:
            records = self._agent_records.get(agent_id, [])
            count += sum(1 for r in records if r.risk_level == action.risk_level and r.timestamp >= cutoff)

        if count >= max_count:
            return RateLimitResult(
                exceeded=True,
                reason=(
                    f"Hierarchy rate limit exceeded: {count}/{max_count} "
                    f"{action.risk_level} actions across "
                    f"{len(hierarchy_agent_ids)} agents in the last "
                    f"{window_seconds // 60} minutes"
                ),
            )
        return RateLimitResult(exceeded=False)

    def clear_session(self, session_id: str) -> None:
        """Remove session data when session ends."""
        self._sessions.pop(session_id, None)

    def clear_agent(self, agent_id: str) -> None:
        """Remove agent rate-limit records."""
        self._agent_records.pop(agent_id, None)
