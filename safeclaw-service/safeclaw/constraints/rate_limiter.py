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

    def __init__(self, limits: dict[str, tuple[int, int]] | None = None):
        self._limits = limits or dict(DEFAULT_LIMITS)
        self._sessions: OrderedDict[str, list[_ActionRecord]] = OrderedDict()

    def check(self, action: ClassifiedAction, session_id: str) -> RateLimitResult:
        """Check if the action would exceed rate limits for this session."""
        limit_entry = self._limits.get(action.risk_level)
        if limit_entry is None:
            return RateLimitResult(exceeded=False)

        max_count, window_seconds = limit_entry
        now = time.monotonic()
        cutoff = now - window_seconds

        records = self._sessions.get(session_id, [])
        count = sum(
            1
            for r in records
            if r.risk_level == action.risk_level and r.timestamp >= cutoff
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

    def record(self, action: ClassifiedAction, session_id: str) -> None:
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

    def clear_session(self, session_id: str) -> None:
        """Remove session data when session ends."""
        self._sessions.pop(session_id, None)
