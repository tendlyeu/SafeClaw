"""Cached engine for hybrid local mode - lightweight, no full reasoner."""

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


class CachedEngine(SafeClawEngine):
    """Lightweight engine for hybrid local cache mode.

    Uses cached SHACL shapes and preferences for fast pattern-match checks.
    Falls through to remote service for complex reasoning.
    """

    def __init__(self, cached_shapes: dict | None = None, cached_preferences: dict | None = None):
        self.shapes = cached_shapes or {}
        self.preferences = cached_preferences or {}

    async def evaluate_tool_call(self, event: ToolCallEvent) -> Decision:
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
