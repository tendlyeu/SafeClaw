"""Detect delegation bypass attempts in multi-agent sessions."""

import hashlib
import json
import logging
import shlex
from collections import deque
from dataclasses import dataclass, field
from time import monotonic

logger = logging.getLogger(__name__)

DETECTION_WINDOW = 300  # 5 minutes in seconds
MAX_BLOCKS = 10000

# Tool name alias map: maps known aliases to a canonical tool name.
# This prevents bypass via renaming (e.g., "bash" instead of "exec").
_TOOL_ALIASES: dict[str, str] = {
    "bash": "exec",
    "shell": "exec",
    "sh": "exec",
    "spawn": "exec",
    "write_file": "fs_write",
    "create_file": "fs_write",
    "file_write": "fs_write",
    "delete_file": "fs_delete",
    "remove_file": "fs_delete",
    "file_delete": "fs_delete",
}

# Parameter keys that contain shell commands whose flags should be normalized.
_COMMAND_PARAM_KEYS = {"command", "cmd", "shell_command", "script"}


def _normalize_tool_name(tool_name: str) -> str:
    """Normalize a tool name to its canonical form using the alias map."""
    return _TOOL_ALIASES.get(tool_name, tool_name)


def _normalize_command_value(value: str) -> str:
    """Normalize a shell command string for semantic comparison.

    Uses shlex.split to tokenize, then sorts flags (tokens starting with '-')
    while preserving the order of positional arguments and the base command.

    For example: "rm -r -f /"  and  "rm -rf /"  both normalize to "rm -f -r /".
    """
    try:
        tokens = shlex.split(value)
    except ValueError:
        # Malformed command string; fall back to whitespace normalization
        return " ".join(value.split())
    if not tokens:
        return value

    command = tokens[0]
    flags: list[str] = []
    positionals: list[str] = []

    for i, token in enumerate(tokens[1:], start=1):
        if token == "--":
            # Everything after "--" is positional
            positionals.append(token)
            positionals.extend(tokens[i + 1 :])
            break
        elif token.startswith("--"):
            flags.append(token)
        elif token.startswith("-") and len(token) > 1:
            # Expand combined short flags: "-rf" -> ["-f", "-r"]
            for char in token[1:]:
                flags.append(f"-{char}")
        else:
            positionals.append(token)

    flags.sort()
    return " ".join([command] + flags + positionals)


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
            logger.warning(f"Invalid delegation detection mode '{mode}', defaulting to 'strict'")
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
        normalized_name = _normalize_tool_name(tool_name)
        normalized_params = self._normalize_params(params) if params else {}
        normalized_sig = (
            self.make_signature(normalized_params) if normalized_params else params_signature
        )
        self._blocks.append(
            BlockRecord(
                session_id=session_id,
                agent_id=agent_id,
                tool_name=normalized_name,
                params_signature=normalized_sig,
                params_keys=normalized_params
                if normalized_params
                else (params if params is not None else {}),
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

    @staticmethod
    def _flatten_values(d: dict) -> set[str]:
        """Extract all leaf string values from a nested dict."""
        values: set[str] = set()
        for v in d.values():
            if isinstance(v, dict):
                values.update(DelegationDetector._flatten_values(v))
            elif isinstance(v, str):
                values.add(v)
        return values

    def check_delegation(
        self,
        session_id: str,
        agent_id: str,
        tool_name: str,
        params_signature: str,
        params: dict | None = None,
    ) -> DelegationResult:
        """Check if this action was previously blocked for a different agent.

        Detection works in three ways:
        1. Exact match: the normalized params_signature matches exactly.
        2. Subset match: the blocked action's params are a subset of the new
           action's params (same values for overlapping keys), which catches
           bypass attempts that add dummy keys to change the hash.
        3. Cross-session: blocks are checked across ALL sessions (not just
           the current one), preventing bypass by starting a new session.

        Tool names are normalized through an alias map to prevent bypass
        via tool name variants (e.g., "bash" vs "exec").

        Command parameters are normalized (flag expansion, sorting) to prevent
        bypass via semantically equivalent but syntactically different commands.
        """
        if self.mode == "disabled":
            return DelegationResult(is_delegation=False)

        self._prune_expired()
        now = monotonic()

        normalized_name = _normalize_tool_name(tool_name)
        normalized_params = self._normalize_params(params) if params else None
        normalized_sig = (
            self.make_signature(normalized_params) if normalized_params else params_signature
        )

        for record in self._blocks:
            if (
                record.agent_id != agent_id
                and record.tool_name == normalized_name
                and (now - record.timestamp) <= DETECTION_WINDOW
            ):
                # Exact normalized signature match
                is_match = record.params_signature == normalized_sig
                # Subset match: blocked params are a subset of new params
                check_params = normalized_params if normalized_params is not None else params
                if (
                    not is_match
                    and check_params is not None
                    and record.params_keys
                    and self._is_param_subset(record.params_keys, check_params)
                ):
                    is_match = True

                # Flattened value match: catches nesting bypass where blocked
                # params are wrapped under a different key structure
                if (
                    not is_match
                    and check_params is not None
                    and record.params_keys
                ):
                    blocked_vals = self._flatten_values(record.params_keys)
                    new_vals = self._flatten_values(check_params)
                    if blocked_vals and blocked_vals.issubset(new_vals):
                        is_match = True

                if is_match:
                    cross_session = record.session_id != session_id
                    reason_suffix = " (cross-session)" if cross_session else ""
                    return DelegationResult(
                        is_delegation=True,
                        original_agent_id=record.agent_id,
                        reason=(
                            f"Agent {agent_id} attempting action that agent "
                            f"{record.agent_id} was blocked from{reason_suffix}"
                        ),
                    )

        return DelegationResult(is_delegation=False)

    @staticmethod
    def _normalize_params(params: dict | None) -> dict | None:
        """Normalize command-like parameter values for semantic comparison.

        Iterates over known command parameter keys and normalizes their string
        values using _normalize_command_value (shlex tokenization, flag sorting).
        """
        if not params:
            return params
        normalized = dict(params)
        for key in _COMMAND_PARAM_KEYS:
            if key in normalized and isinstance(normalized[key], str):
                normalized[key] = _normalize_command_value(normalized[key])
        return normalized

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
