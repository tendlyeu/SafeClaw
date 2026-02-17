"""Detect delegation bypass attempts in multi-agent sessions."""

import hashlib
import json
from dataclasses import dataclass
from time import monotonic

DETECTION_WINDOW = 300  # 5 minutes in seconds


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

    def __init__(self, mode: str = "configurable"):
        """Initialize with detection mode.

        Args:
            mode: "strict", "permissive", or "disabled".
        """
        self.mode = mode
        self._blocks: list[BlockRecord] = []

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

    def _prune_expired(self) -> None:
        """Remove block records older than DETECTION_WINDOW."""
        cutoff = monotonic() - DETECTION_WINDOW
        self._blocks = [b for b in self._blocks if b.timestamp >= cutoff]

    @staticmethod
    def make_signature(params: dict) -> str:
        """Create a deterministic signature from action parameters."""
        serialized = json.dumps(params, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()
