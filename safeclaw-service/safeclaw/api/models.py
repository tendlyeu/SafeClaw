"""API request/response Pydantic models."""

import sys
from typing import Any

from pydantic import BaseModel, field_validator


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
    if sys.getsizeof(str(v)) > MAX_PARAMS_SIZE:
        raise ValueError(f"params serialized size exceeds {MAX_PARAMS_SIZE} bytes")
    return v


class ToolCallRequest(BaseModel):
    sessionId: str = ""
    userId: str = "default"
    toolName: str
    params: dict = {}
    sessionHistory: list[str] = []
    agentId: str = ""
    agentToken: str = ""

    @field_validator("params")
    @classmethod
    def check_params(cls, v: dict) -> dict:
        return _validate_params(v)


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

    @field_validator("params")
    @classmethod
    def check_params(cls, v: dict) -> dict:
        return _validate_params(v)


class LlmIORequest(BaseModel):
    sessionId: str = ""
    content: str = ""
    agentId: str = ""
    agentToken: str = ""


class SessionEndRequest(BaseModel):
    sessionId: str


class DecisionResponse(BaseModel):
    block: bool
    reason: str = ""
    auditId: str = ""


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


class PolicyApplyRequest(BaseModel):
    turtle: str
