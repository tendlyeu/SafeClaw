"""SafeClawEngine - abstract base class for all engine implementations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolCallEvent:
    session_id: str
    user_id: str
    tool_name: str
    params: dict
    session_history: list[str] = field(default_factory=list)
    agent_id: str | None = None
    agent_token: str = ""


@dataclass
class MessageEvent:
    session_id: str
    user_id: str
    to: str
    content: str
    agent_id: str | None = None
    agent_token: str = ""


@dataclass
class AgentStartEvent:
    session_id: str
    user_id: str
    agent_id: str | None = None
    agent_token: str = ""


@dataclass
class ToolResultEvent:
    session_id: str
    tool_name: str
    params: dict
    result: str
    success: bool
    user_id: str = "default"
    agent_id: str | None = None
    agent_token: str = ""


@dataclass
class LlmIOEvent:
    session_id: str
    direction: str  # "input" or "output"
    content: str
    agent_id: str | None = None
    agent_token: str = ""


@dataclass
class Decision:
    block: bool
    reason: str = ""
    audit_id: str = ""
    requires_confirmation: bool = False
    constraint_step: str = ""


@dataclass
class ContextResult:
    prepend_context: str = ""


class SafeClawEngine(ABC):
    """Core engine interface. All constraint logic goes behind this interface."""

    @abstractmethod
    async def evaluate_tool_call(self, event: ToolCallEvent) -> Decision: ...

    @abstractmethod
    async def evaluate_message(self, event: MessageEvent) -> Decision: ...

    @abstractmethod
    async def build_context(self, event: AgentStartEvent) -> ContextResult: ...

    @abstractmethod
    async def record_action_result(self, event: ToolResultEvent) -> None: ...

    @abstractmethod
    async def log_llm_io(self, event: LlmIOEvent) -> None: ...
