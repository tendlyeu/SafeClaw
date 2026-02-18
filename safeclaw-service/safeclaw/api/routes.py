"""FastAPI route definitions for SafeClaw API."""

import logging

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from safeclaw.api.models import (
    AgentRegisterRequest,
    AgentRegisterResponse,
    AgentStartRequest,
    ContextResponse,
    DecisionResponse,
    LlmIORequest,
    MessageRequest,
    SessionEndRequest,
    TempGrantRequest,
    TempGrantResponse,
    ToolCallRequest,
    ToolResultRequest,
)
from safeclaw.engine.core import AgentStartEvent, LlmIOEvent, MessageEvent, ToolCallEvent, ToolResultEvent

logger = logging.getLogger("safeclaw.api")

router = APIRouter()


async def require_admin(request: Request):
    """Require admin auth for sensitive endpoints.

    When auth is disabled (local mode), scope is None and check passes
    intentionally — all users are treated as admin in local dev.
    """
    scope = getattr(request.state, 'api_key_scope', None)
    if scope is not None and 'admin' not in scope:
        raise HTTPException(status_code=403, detail="Admin access required")


def _get_engine():
    from safeclaw.main import get_engine
    return get_engine()


@router.post("/evaluate/tool-call", response_model=DecisionResponse)
async def evaluate_tool_call(request: ToolCallRequest) -> DecisionResponse:
    engine = _get_engine()
    event = ToolCallEvent(
        session_id=request.sessionId,
        user_id=request.userId,
        tool_name=request.toolName,
        params=request.params,
        session_history=request.sessionHistory,
        agent_id=request.agentId,
        agent_token=request.agentToken,
    )
    decision = await engine.evaluate_tool_call(event)
    return DecisionResponse(
        block=decision.block,
        reason=decision.reason,
        auditId=decision.audit_id,
    )


@router.post("/evaluate/message", response_model=DecisionResponse)
async def evaluate_message(request: MessageRequest) -> DecisionResponse:
    engine = _get_engine()
    event = MessageEvent(
        session_id=request.sessionId,
        user_id=request.userId,
        to=request.to,
        content=request.content,
        agent_id=request.agentId,
        agent_token=request.agentToken,
    )
    decision = await engine.evaluate_message(event)
    return DecisionResponse(
        block=decision.block,
        reason=decision.reason,
        auditId=decision.audit_id,
    )


@router.post("/context/build", response_model=ContextResponse)
async def build_context(request: AgentStartRequest) -> ContextResponse:
    engine = _get_engine()
    event = AgentStartEvent(
        session_id=request.sessionId,
        user_id=request.userId,
        agent_id=request.agentId,
        agent_token=request.agentToken,
    )
    result = await engine.build_context(event)
    return ContextResponse(prependContext=result.prepend_context)


@router.post("/session/end")
async def end_session(request: SessionEndRequest):
    """Clean up all per-session state when a session ends."""
    engine = _get_engine()
    engine.clear_session(request.sessionId)
    return {"ok": True, "sessionId": request.sessionId}


@router.post("/record/tool-result")
async def record_tool_result(request: ToolResultRequest):
    engine = _get_engine()
    event = ToolResultEvent(
        session_id=request.sessionId,
        tool_name=request.toolName,
        params=request.params,
        result=request.result,
        success=request.success,
        agent_id=request.agentId,
        agent_token=request.agentToken,
    )
    await engine.record_action_result(event)
    return {"ok": True}


@router.post("/log/llm-input")
async def log_llm_input(request: LlmIORequest):
    engine = _get_engine()
    event = LlmIOEvent(
        session_id=request.sessionId,
        direction="input",
        content=request.content,
        agent_id=request.agentId,
        agent_token=request.agentToken,
    )
    await engine.log_llm_io(event)
    return {"ok": True}


@router.post("/log/llm-output")
async def log_llm_output(request: LlmIORequest):
    engine = _get_engine()
    event = LlmIOEvent(
        session_id=request.sessionId,
        direction="output",
        content=request.content,
        agent_id=request.agentId,
        agent_token=request.agentToken,
    )
    await engine.log_llm_io(event)
    return {"ok": True}


@router.get("/audit", dependencies=[Depends(require_admin)])
async def query_audit(
    session_id: str | None = Query(None, alias="sessionId"),
    blocked: bool = False,
    limit: int = Query(20, ge=1, le=1000),
):
    engine = _get_engine()
    if session_id:
        records = engine.audit.get_session_records(session_id)[:limit]
    elif blocked:
        records = engine.audit.get_blocked_records(limit)
    else:
        records = engine.audit.get_recent_records(limit)
    return {"decisions": [r.model_dump() for r in records]}


@router.post("/reload", dependencies=[Depends(require_admin)])
async def reload_ontologies():
    """Hot-reload ontologies and reinitialize constraint checkers."""
    engine = _get_engine()
    engine.reload()
    return {"ok": True, "triples": len(engine.kg)}


@router.get("/audit/statistics", dependencies=[Depends(require_admin)])
async def audit_statistics(limit: int = Query(100, ge=1, le=1000)):
    """Get aggregate statistics from recent audit records."""
    from safeclaw.audit.reporter import AuditReporter
    engine = _get_engine()
    reporter = AuditReporter(engine.audit)
    records = engine.audit.get_recent_records(limit)
    return reporter.get_statistics(records)


@router.get("/audit/report/{session_id}", dependencies=[Depends(require_admin)])
async def audit_report(
    session_id: str,
    fmt: Literal["markdown", "json", "csv"] = Query("markdown", alias="format"),
):
    """Generate a session audit report in markdown, JSON, or CSV format."""
    from fastapi.responses import PlainTextResponse
    from safeclaw.audit.reporter import AuditReporter
    engine = _get_engine()
    reporter = AuditReporter(engine.audit)
    content = reporter.generate_session_report(session_id, format=fmt)
    content_type = "text/csv" if fmt == "csv" else "application/json" if fmt == "json" else "text/markdown"
    return PlainTextResponse(content, media_type=content_type)


@router.get("/audit/compliance", dependencies=[Depends(require_admin)])
async def compliance_report(limit: int = Query(100, ge=1, le=1000)):
    """Generate a compliance report from recent audit records."""
    from fastapi.responses import PlainTextResponse
    from safeclaw.audit.reporter import AuditReporter
    engine = _get_engine()
    reporter = AuditReporter(engine.audit)
    records = engine.audit.get_recent_records(limit)
    content = reporter.generate_compliance_report(records)
    return PlainTextResponse(content, media_type="text/markdown")


@router.get("/ontology/graph")
async def ontology_graph():
    """Get D3-compatible graph of the knowledge graph."""
    from safeclaw.engine.graph_builder import GraphBuilder
    engine = _get_engine()
    builder = GraphBuilder(engine.kg)
    return builder.build_graph()


@router.get("/ontology/search")
async def ontology_search(q: str = Query(..., max_length=200)):
    """Fuzzy search for ontology nodes by name or label."""
    from safeclaw.engine.graph_builder import GraphBuilder
    engine = _get_engine()
    builder = GraphBuilder(engine.kg)
    return {"results": builder.search_nodes(q)}


@router.post("/agents/register", response_model=AgentRegisterResponse, dependencies=[Depends(require_admin)])
async def register_agent(request: AgentRegisterRequest) -> AgentRegisterResponse:
    engine = _get_engine()
    token = engine.agent_registry.register_agent(
        agent_id=request.agentId,
        role=request.role,
        session_id=request.sessionId,
        parent_id=request.parentId,
    )
    return AgentRegisterResponse(agentId=request.agentId, token=token, role=request.role)


@router.post("/agents/{agent_id}/kill", dependencies=[Depends(require_admin)])
async def kill_agent(agent_id: str):
    engine = _get_engine()
    found = engine.agent_registry.kill_agent(agent_id)
    if not found:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"ok": True, "agentId": agent_id, "killed": True}


@router.post("/agents/{agent_id}/revive", dependencies=[Depends(require_admin)])
async def revive_agent(agent_id: str):
    engine = _get_engine()
    found = engine.agent_registry.revive_agent(agent_id)
    if not found:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"ok": True, "agentId": agent_id, "killed": False}


@router.get("/agents", dependencies=[Depends(require_admin)])
async def list_agents():
    engine = _get_engine()
    agents = engine.agent_registry.list_agents()
    return {"agents": [
        {"agentId": a.agent_id, "role": a.role, "parentId": a.parent_id, "killed": a.killed}
        for a in agents
    ]}


@router.post("/agents/{agent_id}/temp-grant", response_model=TempGrantResponse, dependencies=[Depends(require_admin)])
async def grant_temp_permission(agent_id: str, request: TempGrantRequest) -> TempGrantResponse:
    from datetime import datetime, timezone, timedelta

    engine = _get_engine()
    # Capture wall clock at grant time so the expiry is computed from the same
    # moment as the monotonic grant_time inside TempPermissionManager. This is
    # an approximation (millisecond-level drift) but avoids the racy
    # monotonic-to-wall-clock subtraction that could shift under NTP corrections
    # or system sleep. Ideally TempGrant would store wall_expires_at directly,
    # but that field lives in engine code shared with another fixer. (R3-34)
    wall_now = datetime.now(timezone.utc)
    grant_id = engine.temp_permissions.grant(
        agent_id=agent_id,
        permission=request.permission,
        duration_seconds=request.durationSeconds,
        task_id=request.taskId,
    )
    expires_at = None
    if request.durationSeconds is not None:
        expires_at = (wall_now + timedelta(seconds=request.durationSeconds)).isoformat()
    return TempGrantResponse(grantId=grant_id, expiresAt=expires_at)


@router.delete("/agents/{agent_id}/temp-grant/{grant_id}", dependencies=[Depends(require_admin)])
async def revoke_temp_permission(agent_id: str, grant_id: str):
    engine = _get_engine()
    grant = engine.temp_permissions.get_grant(grant_id)
    if grant is None or grant.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Grant not found for this agent")
    engine.temp_permissions.revoke(grant_id)
    return {"ok": True}


@router.post("/tasks/{task_id}/complete", dependencies=[Depends(require_admin)])
async def complete_task(task_id: str):
    engine = _get_engine()
    count = engine.temp_permissions.complete_task(task_id)
    return {"ok": True, "taskId": task_id, "grantsRevoked": count}
