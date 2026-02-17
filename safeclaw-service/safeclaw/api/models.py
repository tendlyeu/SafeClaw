"""API request/response Pydantic models."""

from pydantic import BaseModel


class ToolCallRequest(BaseModel):
    sessionId: str = ""
    userId: str = "default"
    toolName: str
    params: dict = {}
    sessionHistory: list[str] = []


class MessageRequest(BaseModel):
    sessionId: str = ""
    userId: str = "default"
    to: str
    content: str


class AgentStartRequest(BaseModel):
    sessionId: str = ""
    userId: str = "default"


class ToolResultRequest(BaseModel):
    sessionId: str = ""
    toolName: str
    params: dict = {}
    result: str = ""
    success: bool = True


class LlmIORequest(BaseModel):
    sessionId: str = ""
    content: str = ""


class DecisionResponse(BaseModel):
    block: bool
    reason: str = ""
    auditId: str = ""


class ContextResponse(BaseModel):
    prependContext: str = ""


class AuditQueryParams(BaseModel):
    sessionId: str | None = None
    blocked: bool = False
    limit: int = 20
