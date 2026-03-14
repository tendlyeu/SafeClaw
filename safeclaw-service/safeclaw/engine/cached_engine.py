"""Cached engine for hybrid local mode - lightweight, no full reasoner.

.. deprecated::
    CachedEngine is deprecated and non-functional. Use FullEngine instead.
    This class always returns ``Decision(block=False)`` for all checks and
    provides no real governance. It exists only for backwards compatibility.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from safeclaw.engine.core import (
    AgentStartEvent,
    ContextResult,
    Decision,
    LlmIOEvent,
    MessageEvent,
    SafeClawEngine,
    ToolCallEvent,
    ToolResultEvent,
)

if TYPE_CHECKING:
    from safeclaw.engine.agent_registry import AgentRegistry


class CachedEngine(SafeClawEngine):
    """Lightweight engine for hybrid local cache mode.

    .. deprecated::
        CachedEngine is deprecated and non-functional. Use FullEngine instead.
        This class always returns ``Decision(block=False)`` for all checks
        and provides no real governance.
    """

    def __init__(
        self,
        cached_shapes: dict | None = None,
        cached_preferences: dict | None = None,
        agent_registry: AgentRegistry | None = None,
    ):
        warnings.warn(
            "CachedEngine is deprecated and non-functional. Use FullEngine.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.shapes = cached_shapes or {}
        self.preferences = cached_preferences or {}
        self._agent_registry = agent_registry

    async def evaluate_tool_call(self, event: ToolCallEvent) -> Decision:
        # Check kill switch if agent registry is available
        if self._agent_registry and hasattr(event, "agent_id") and event.agent_id:
            if self._agent_registry.is_killed(event.agent_id):
                return Decision(block=True, reason="Agent is killed")

        # Fast pattern matching only - no full reasoner
        # In hybrid mode, this returns Decision(block=False) and the
        # remote service handles complex checks
        return Decision(block=False)

    async def evaluate_message(self, event: MessageEvent) -> Decision:
        return Decision(block=False)

    async def build_context(self, event: AgentStartEvent) -> ContextResult:
        return ContextResult()

    async def record_action_result(self, event: ToolResultEvent) -> None:
        pass

    async def log_llm_io(self, event: LlmIOEvent) -> None:
        pass
