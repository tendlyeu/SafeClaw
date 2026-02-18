"""Audit data models - DecisionRecord and related types."""

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class ActionDetail(BaseModel):
    tool_name: str
    params: dict
    ontology_class: str
    risk_level: str
    is_reversible: bool
    affects_scope: str


class ConstraintCheck(BaseModel):
    constraint_uri: str
    constraint_type: str
    result: str  # "satisfied" | "violated" | "not_applicable"
    reason: str


class PreferenceApplied(BaseModel):
    preference_uri: str
    value: str
    effect: str


class Justification(BaseModel):
    constraints_checked: list[ConstraintCheck] = []
    preferences_applied: list[PreferenceApplied] = []
    elapsed_ms: float = 0.0


class DecisionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    session_id: str
    user_id: str
    agent_id: str = ""
    action: ActionDetail
    decision: str  # "allowed" | "blocked"
    justification: Justification
    session_action_history: list[str] = []
