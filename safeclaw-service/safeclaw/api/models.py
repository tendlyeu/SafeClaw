"""API request/response Pydantic models."""

from pydantic import BaseModel


class ToolCallRequest(BaseModel):
    sessionId: str = ""
    userId: str = "default"
    toolName: str
    params: dict = {}
    sessionHistory: list[str] = []
    agentId: str = ""
    agentToken: str = ""


class MessageRequest(BaseModel):
    sessionId: str = ""
    userId: str = "default"
    to: str
    content: str
    agentId: str = ""
    agentToken: str = ""


class AgentStartRequest(BaseModel):
    sessionId: str = ""
    userId: str = "default"
    agentId: str = ""
    agentToken: str = ""


class ToolResultRequest(BaseModel):
    sessionId: str = ""
    toolName: str
    params: dict = {}
    result: str = ""
    success: bool = True
    agentId: str = ""
    agentToken: str = ""


class LlmIORequest(BaseModel):
    sessionId: str = ""
    content: str = ""
    agentId: str = ""
    agentToken: str = ""


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


class AgentRegisterRequest(BaseModel):
    agentId: str
    role: str = "developer"
    sessionId: str = ""
    parentId: str | None = None


class AgentRegisterResponse(BaseModel):
    agentId: str
    token: str
    role: str


class AgentKillRequest(BaseModel):
    agentId: str


class TempGrantRequest(BaseModel):
    agentId: str
    permission: str
    durationSeconds: int | None = None
    taskId: str | None = None


class TempGrantResponse(BaseModel):
    grantId: str
    expiresAt: str | None = None
