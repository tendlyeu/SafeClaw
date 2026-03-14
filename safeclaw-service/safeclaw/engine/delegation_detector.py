"""Detect delegation bypass attempts in multi-agent sessions."""

import hashlib
import json
import logging
from collections import deque
from dataclasses import dataclass, field
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
    params_keys: dict = field(default_factory=dict)


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
        valid_modes = {"strict", "permissive", "disabled", "configurable"}
        if mode not in valid_modes:
            logger.warning(
                f"Invalid delegation detection mode '{mode}', defaulting to 'strict'"
            )
            mode = "strict"
        # "configurable" is the default from the config template; treat it as "strict"
        if mode == "configurable":
            mode = "strict"
        self.mode = mode
        self._blocks: deque[BlockRecord] = deque(maxlen=MAX_BLOCKS)

    def record_block(
        self,
        session_id: str,
        agent_id: str,
        tool_name: str,
        params_signature: str,
        params: dict | None = None,
    ) -> None:
        """Record that an action was blocked for an agent.

        Args:
            session_id: The session in which the block occurred.
            agent_id: The agent that was blocked.
            tool_name: The tool that was blocked.
            params_signature: SHA-256 signature of the full params dict.
            params: The original params dict (stored for subset matching to
                    prevent bypass by adding dummy keys).
        """
        self._prune_expired()
        self._blocks.append(
            BlockRecord(
                session_id=session_id,
                agent_id=agent_id,
                tool_name=tool_name,
                params_signature=params_signature,
                params_keys=params if params is not None else {},
                timestamp=monotonic(),
            )
        )

    @staticmethod
    def _is_param_subset(blocked_params: dict, new_params: dict) -> bool:
        """Check if all keys from blocked_params exist in new_params with the same values.

        This catches delegation bypass attempts where the delegating agent adds
        extra dummy keys to change the hash signature while preserving the
        semantically meaningful parameters.
        """
        if not blocked_params:
            return False
        for key, value in blocked_params.items():
            if key not in new_params:
                return False
            new_value = new_params[key]
            # Recursive check for nested dicts
            if isinstance(value, dict) and isinstance(new_value, dict):
                if not DelegationDetector._is_param_subset(value, new_value):
                    return False
            elif value != new_value:
                return False
        return True

    def check_delegation(
        self,
        session_id: str,
        agent_id: str,
        tool_name: str,
        params_signature: str,
        params: dict | None = None,
    ) -> DelegationResult:
        """Check if this action was previously blocked for a different agent.

        Detection works in two ways:
        1. Exact match: the params_signature matches exactly (identical params).
        2. Subset match: the blocked action's params are a subset of the new
           action's params (same values for overlapping keys), which catches
           bypass attempts that add dummy keys to change the hash.
        """
        if self.mode == "disabled":
            return DelegationResult(is_delegation=False)

        self._prune_expired()
        now = monotonic()

        for record in self._blocks:
            if (
                record.session_id == session_id
                and record.agent_id != agent_id
                and record.tool_name == tool_name
                and (now - record.timestamp) <= DETECTION_WINDOW
            ):
                # Exact signature match
                is_match = record.params_signature == params_signature
                # Subset match: blocked params are a subset of new params
                if (
                    not is_match
                    and params is not None
                    and record.params_keys
                    and self._is_param_subset(record.params_keys, params)
                ):
                    is_match = True

                if is_match:
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
