"""API request/response Pydantic models."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator


MAX_PARAMS_DEPTH = 5
MAX_PARAMS_SIZE = 100_000  # bytes


def _check_depth(obj: Any, current: int = 0) -> int:
    """Return the max nesting depth of a dict/list structure."""
    if current > MAX_PARAMS_DEPTH:
        return current
    if isinstance(obj, dict):
        if not obj:
            return current
        return max(_check_depth(v, current + 1) for v in obj.values())
    if isinstance(obj, list):
        if not obj:
            return current
        return max(_check_depth(v, current + 1) for v in obj)
    return current


def _validate_params(v: dict) -> dict:
    """Reject params dicts that are too deeply nested or too large."""
    if _check_depth(v) > MAX_PARAMS_DEPTH:
        raise ValueError(f"params nesting exceeds max depth of {MAX_PARAMS_DEPTH}")
    if len(str(v).encode("utf-8")) > MAX_PARAMS_SIZE:
        raise ValueError(f"params serialized size exceeds {MAX_PARAMS_SIZE} bytes")
    return v


class ToolCallRequest(BaseModel):
    sessionId: str = ""
    userId: str = "default"
    toolName: str
    params: dict = {}
    sessionHistory: list[str] = []
    agentId: str | None = None
    agentToken: str = ""

    @field_validator("params")
    @classmethod
    def check_params(cls, v: dict) -> dict:
        return _validate_params(v)


class MessageRequest(BaseModel):
    sessionId: str = ""
    userId: str = "default"
    to: str
    content: str = Field(..., max_length=1_000_000)
    agentId: str | None = None
    agentToken: str = ""


class AgentStartRequest(BaseModel):
    sessionId: str = ""
    userId: str = "default"
    agentId: str = ""
    agentToken: str = ""


class ToolResultRequest(BaseModel):
    sessionId: str = ""
    userId: str = ""
    toolName: str
    params: dict = {}
    result: str = ""
    success: bool = True
    agentId: str = ""
    agentToken: str = ""

    @field_validator("params")
    @classmethod
    def check_params(cls, v: dict) -> dict:
        return _validate_params(v)


class LlmIORequest(BaseModel):
    sessionId: str = ""
    content: str = Field("", max_length=1_000_000)
    agentId: str = ""
    agentToken: str = ""


class SessionEndRequest(BaseModel):
    sessionId: str


class DecisionResponse(BaseModel):
    block: bool
    reason: str = ""
    auditId: str = ""
    confirmationRequired: bool = False
    constraintStep: str = ""
    riskLevel: str = ""

    @computed_field
    @property
    def decision(self) -> str:
        """Disambiguate block+confirmationRequired into a single decision string.

        Returns 'allowed', 'needs_confirmation', or 'blocked'.
        """
        if not self.block:
            return "allowed"
        if self.confirmationRequired:
            return "needs_confirmation"
        return "blocked"


class ContextResponse(BaseModel):
    prependContext: str = ""


class AgentRegisterRequest(BaseModel):
    agentId: str
    role: str = "developer"
    sessionId: str = ""
    parentId: str | None = None


class AgentRegisterResponse(BaseModel):
    agentId: str
    token: str
    role: str


class TempGrantRequest(BaseModel):
    permission: str
    durationSeconds: int | None = None
    taskId: str | None = None

    @model_validator(mode='after')
    def check_scope(self):
        if self.durationSeconds is None and self.taskId is None:
            raise ValueError("Either durationSeconds or taskId must be provided")
        return self


class TempGrantResponse(BaseModel):
    grantId: str
    expiresAt: str | None = None


class PolicyCompileRequest(BaseModel):
    description: str


class PolicyCompileResponse(BaseModel):
    success: bool
    turtle: str = ""
    policyName: str = ""
    policyType: str = ""
    explanation: str = ""
    validationErrors: list[str] = []


class HeartbeatRequest(BaseModel):
    agentId: str = ""
    configHash: str = ""
    status: str = "alive"  # "alive" or "shutdown"


class HandshakeRequest(BaseModel):
    pluginVersion: str = ""
    configHash: str = ""


class HandshakeResponse(BaseModel):
    ok: bool
    orgId: str = ""
    scope: str = ""
    engineReady: bool = False
    serviceVersion: str = ""
    message: str = ""


class PolicyApplyRequest(BaseModel):
    turtle: str


class PreferencesRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    autonomy_level: Literal["cautious", "moderate", "autonomous", "supervised", "full"] = Field(
        "moderate", alias="autonomyLevel"
    )
    confirm_before_delete: bool = Field(True, alias="confirmBeforeDelete")
    confirm_before_push: bool = Field(True, alias="confirmBeforePush")
    confirm_before_send: bool = Field(True, alias="confirmBeforeSend")
    max_files_per_commit: int = Field(10, ge=1, le=100, alias="maxFilesPerCommit")
