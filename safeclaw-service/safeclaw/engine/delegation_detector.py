"""Detect delegation bypass attempts in multi-agent sessions."""

import hashlib
import json
import logging
from collections import deque
from dataclasses import dataclass
from time import monotonic

logger = logging.getLogger(__name__)

DETECTION_WINDOW = 300  # 5 minutes in seconds
MAX_BLOCKS = 10000


@dataclass
class BlockRecord:
    """Record of a blocked action."""

    session_id: str
    agent_id: str
    tool_name: str
    params_signature: str
    timestamp: float


@dataclass
class DelegationResult:
    """Result of a delegation check."""

    is_delegation: bool
    original_agent_id: str = ""
    reason: str = ""


class DelegationDetector:
    """Detects when an agent delegates a blocked action to another agent."""

    def __init__(self, mode: str = "strict"):
        """Initialize with detection mode.

        Args:
            mode: "strict", "permissive", or "disabled".
        """
        valid_modes = {"strict", "permissive", "disabled"}
        if mode not in valid_modes:
            logger.warning(
                f"Invalid delegation detection mode '{mode}', defaulting to 'strict'"
            )
            mode = "strict"
        self.mode = mode
        self._blocks: deque[BlockRecord] = deque(maxlen=MAX_BLOCKS)

    def record_block(
        self,
        session_id: str,
        agent_id: str,
        tool_name: str,
        params_signature: str,
    ) -> None:
        """Record that an action was blocked for an agent."""
        self._prune_expired()
        self._blocks.append(
            BlockRecord(
                session_id=session_id,
                agent_id=agent_id,
                tool_name=tool_name,
                params_signature=params_signature,
                timestamp=monotonic(),
            )
        )

    def check_delegation(
        self,
        session_id: str,
        agent_id: str,
        tool_name: str,
        params_signature: str,
    ) -> DelegationResult:
        """Check if this action was previously blocked for a different agent."""
        if self.mode == "disabled":
            return DelegationResult(is_delegation=False)

        self._prune_expired()
        now = monotonic()

        for record in self._blocks:
            if (
                record.session_id == session_id
                and record.agent_id != agent_id
                and record.tool_name == tool_name
                and record.params_signature == params_signature
                and (now - record.timestamp) <= DETECTION_WINDOW
            ):
                return DelegationResult(
                    is_delegation=True,
                    original_agent_id=record.agent_id,
                    reason=(
                        f"Agent {agent_id} attempting action that agent "
                        f"{record.agent_id} was blocked from"
                    ),
                )

        return DelegationResult(is_delegation=False)

    def clear_session(self, session_id: str) -> None:
        """Remove all block records for a given session."""
        self._blocks = deque(
            (r for r in self._blocks if r.session_id != session_id),
            maxlen=MAX_BLOCKS,
        )

    def _prune_expired(self) -> None:
        """Remove block records older than DETECTION_WINDOW."""
        cutoff = monotonic() - DETECTION_WINDOW
        while self._blocks and self._blocks[0].timestamp < cutoff:
            self._blocks.popleft()

    @staticmethod
    def make_signature(params: dict) -> str:
        """Create a deterministic signature from action parameters."""
        try:
            serialized = json.dumps(params, sort_keys=True, default=str)
        except (TypeError, ValueError):
            serialized = str(sorted(params.items()) if isinstance(params, dict) else str(params))
        return hashlib.sha256(serialized.encode()).hexdigest()
