"""FastAPI route definitions for SafeClaw API."""

import logging
import secrets

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from safeclaw.api.models import (
    AgentRegisterRequest,
    AgentRegisterResponse,
    AgentStartRequest,
    ContextResponse,
    DecisionResponse,
    HeartbeatRequest,
    LlmIORequest,
    MessageRequest,
    PolicyCompileRequest,
    PolicyCompileResponse,
    PreferencesRequest,
    SessionEndRequest,
    TempGrantRequest,
    TempGrantResponse,
    ToolCallRequest,
    ToolResultRequest,
)
from safeclaw.engine.core import (
    AgentStartEvent,
    LlmIOEvent,
    MessageEvent,
    ToolCallEvent,
    ToolResultEvent,
)

logger = logging.getLogger("safeclaw.api")

router = APIRouter()


async def require_admin(request: Request):
    """Require admin auth for sensitive endpoints.

    Two-layer check:
    1. If API-key auth is active (scope is set), require "admin" in scope.
    2. If admin_password is configured, require X-Admin-Password header to match.
       If admin_password is NOT configured (empty string), allow access for
       backwards compatibility (local dev mode).
    """
    # Layer 1: API-key scope check (when middleware sets it)
    scope = getattr(request.state, "api_key_scope", None)
    if scope is not None and "admin" not in scope:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Layer 2: X-Admin-Password header check
    engine = _get_engine()
    configured_password = engine.config.admin_password
    if configured_password:  # only enforce when a password is actually set
        provided = request.headers.get("X-Admin-Password", "")
        if not provided or not secrets.compare_digest(provided, configured_password):
            raise HTTPException(status_code=403, detail="Admin access required")


def _get_engine():
    from safeclaw.main import get_engine

    return get_engine()  # raises SafeClawError("ENGINE_NOT_READY") if engine is None


def _verify_agent_token(engine, agent_id: str | None, agent_token: str | None):
    """Verify agent token if the agent is registered.

    If the agent is NOT registered, allow the request for backwards
    compatibility (unregistered agents are not subject to token auth here).
    If the agent IS registered and the token doesn't match, raise 403.
    """
    if not agent_id:
        return  # No agent context — allow
    record = engine.agent_registry.get_agent(agent_id)
    if record is None:
        return  # Agent not registered — backwards compat, allow
    if not agent_token or not engine.agent_registry.verify_token(agent_id, agent_token):
        raise HTTPException(status_code=403, detail="Invalid agent token")


@router.post("/evaluate/tool-call", response_model=DecisionResponse)
async def evaluate_tool_call(request: ToolCallRequest, req: Request) -> DecisionResponse:
    engine = _get_engine()
    # Use org_id from API key auth (numeric DB user ID) if available,
    # otherwise fall back to client-supplied userId
    user_id = getattr(req.state, "org_id", None) or request.userId
    event = ToolCallEvent(
        session_id=request.sessionId,
        user_id=user_id,
        tool_name=request.toolName,
        params=request.params,
        session_history=request.sessionHistory,
        agent_id=request.agentId,
        agent_token=request.agentToken,
        enforcement_mode=request.enforcementMode,
    )
    decision = await engine.evaluate_tool_call(event)
    return DecisionResponse(
        block=decision.block,
        reason=decision.reason,
        auditId=decision.audit_id,
    )


@router.post("/evaluate/message", response_model=DecisionResponse)
async def evaluate_message(request: MessageRequest, req: Request) -> DecisionResponse:
    engine = _get_engine()
    user_id = getattr(req.state, "org_id", None) or request.userId
    event = MessageEvent(
        session_id=request.sessionId,
        user_id=user_id,
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
    _verify_agent_token(engine, request.agentId, request.agentToken)
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
    await engine.clear_session(request.sessionId)
    return {"ok": True, "sessionId": request.sessionId}


@router.post("/record/tool-result")
async def record_tool_result(request: ToolResultRequest):
    engine = _get_engine()
    _verify_agent_token(engine, request.agentId, request.agentToken)
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
    await engine.reload()
    return {"ok": True, "triples": len(engine.kg)}


@router.get("/preferences/{user_id}", dependencies=[Depends(require_admin)])
async def get_preferences(user_id: str):
    """Get user preferences as JSON."""
    engine = _get_engine()
    prefs = engine.preference_checker.get_preferences(user_id)
    return {
        "autonomy_level": prefs.autonomy_level,
        "confirm_before_delete": prefs.confirm_before_delete,
        "confirm_before_push": prefs.confirm_before_push,
        "confirm_before_send": prefs.confirm_before_send,
        "max_files_per_commit": prefs.max_files_per_commit,
    }


@router.post("/preferences/{user_id}", dependencies=[Depends(require_admin)])
async def update_preferences(user_id: str, request: PreferencesRequest):
    """Update user preferences — writes Turtle file."""
    import re

    engine = _get_engine()
    safe_user_id = re.sub(r'[^a-zA-Z0-9_@.-]', '', user_id)

    users_dir = engine.config.data_dir / "ontologies" / "users"
    users_dir.mkdir(parents=True, exist_ok=True)
    ttl_path = users_dir / f"user-{safe_user_id}.ttl"

    su = "http://safeclaw.uku.ai/ontology/user#"

    turtle = f"""@prefix su: <{su}> .

su:user-{safe_user_id} a su:User ;
    su:hasPreference su:pref-{safe_user_id} .

su:pref-{safe_user_id} a su:UserPreferences ;
    su:autonomyLevel "{request.autonomy_level}" ;
    su:confirmBeforeDelete "{str(request.confirm_before_delete).lower()}"^^<http://www.w3.org/2001/XMLSchema#boolean> ;
    su:confirmBeforePush "{str(request.confirm_before_push).lower()}"^^<http://www.w3.org/2001/XMLSchema#boolean> ;
    su:confirmBeforeSend "{str(request.confirm_before_send).lower()}"^^<http://www.w3.org/2001/XMLSchema#boolean> ;
    su:maxFilesPerCommit "{request.max_files_per_commit}"^^<http://www.w3.org/2001/XMLSchema#integer> .
"""
    ttl_path.write_text(turtle)

    # Reload ontologies so the new preferences take effect
    await engine.reload()

    return {"ok": True, "userId": safe_user_id}


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
    content_type = (
        "text/csv" if fmt == "csv" else "application/json" if fmt == "json" else "text/markdown"
    )
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


@router.get("/ontology/graph", dependencies=[Depends(require_admin)])
async def ontology_graph():
    """Get D3-compatible graph of the knowledge graph."""
    from safeclaw.engine.graph_builder import GraphBuilder

    engine = _get_engine()
    builder = GraphBuilder(engine.kg)
    return builder.build_graph()


@router.get("/ontology/search", dependencies=[Depends(require_admin)])
async def ontology_search(q: str = Query(..., max_length=200)):
    """Fuzzy search for ontology nodes by name or label."""
    from safeclaw.engine.graph_builder import GraphBuilder

    engine = _get_engine()
    builder = GraphBuilder(engine.kg)
    return {"results": builder.search_nodes(q)}


@router.post(
    "/agents/register", response_model=AgentRegisterResponse, dependencies=[Depends(require_admin)]
)
async def register_agent(request: AgentRegisterRequest) -> AgentRegisterResponse:
    engine = _get_engine()
    try:
        token = engine.agent_registry.register_agent(
            agent_id=request.agentId,
            role=request.role,
            session_id=request.sessionId,
            parent_id=request.parentId,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
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
    return {
        "agents": [
            {"agentId": a.agent_id, "role": a.role, "parentId": a.parent_id, "killed": a.killed}
            for a in agents
        ]
    }


@router.post(
    "/agents/{agent_id}/temp-grant",
    response_model=TempGrantResponse,
    dependencies=[Depends(require_admin)],
)
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


@router.post("/heartbeat")
async def heartbeat(request: HeartbeatRequest):
    """Receive plugin heartbeat. No admin auth required -- plugins call this."""
    engine = _get_engine()
    if request.status == "shutdown":
        engine.heartbeat_monitor.remove(request.agentId)
        return {"ok": True, "action": "removed"}

    engine.heartbeat_monitor.record(request.agentId, request.configHash)

    # Piggyback: check for stale agents and config drift
    stale = engine.heartbeat_monitor.check_stale()
    drifted = engine.heartbeat_monitor.check_config_drift(
        request.agentId, request.configHash
    )

    return {"ok": True, "stale": stale, "configDrift": drifted}


# ── LLM Layer Routes ──


@router.post("/policies/compile", response_model=PolicyCompileResponse)
async def compile_policy(request: PolicyCompileRequest) -> PolicyCompileResponse:
    engine = _get_engine()
    if not hasattr(engine, "llm_client") or engine.llm_client is None:
        raise HTTPException(
            status_code=503, detail="LLM not configured (set SAFECLAW_MISTRAL_API_KEY)"
        )

    from safeclaw.llm.policy_compiler import PolicyCompiler

    compiler = PolicyCompiler(engine.llm_client, engine.kg)
    result = await compiler.compile(request.description)
    return PolicyCompileResponse(
        success=result.success,
        turtle=result.turtle,
        policyName=result.policy_name,
        policyType=result.policy_type,
        explanation=result.explanation,
        validationErrors=result.validation_errors,
    )


@router.get("/audit/{audit_id}/explain", dependencies=[Depends(require_admin)])
async def explain_decision(audit_id: str):
    engine = _get_engine()
    if not hasattr(engine, "explainer") or engine.explainer is None:
        raise HTTPException(
            status_code=503, detail="LLM not configured (set SAFECLAW_MISTRAL_API_KEY)"
        )

    # Try to find the audit record
    record = engine.audit.get_record_by_id(audit_id)
    if not record:
        raise HTTPException(status_code=404, detail="Audit record not found")

    explanation = await engine.explainer.explain(record)
    return {"auditId": audit_id, "explanation": explanation}


@router.get("/events", dependencies=[Depends(require_admin)])
async def event_stream():
    """SSE endpoint — streams real-time SafeClaw events."""
    from starlette.responses import StreamingResponse

    engine = _get_engine()

    async def generate():
        try:
            sub = engine.event_bus.subscribe(keepalive_timeout=15.0)
        except ValueError:
            yield "event: error\ndata: {\"error\": \"Max subscribers limit reached\"}\n\n"
            return
        try:
            async for event in sub:
                if event is None:
                    yield ":keepalive\n\n"
                else:
                    yield f"event: safeclaw\ndata: {event.to_json()}\n\n"
        finally:
            await sub.aclose()

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/llm/findings")
async def get_findings():
    # Findings are currently logged but not persisted to a queryable store.
    return {"findings": []}


@router.get("/llm/suggestions")
async def get_suggestions():
    import json

    engine = _get_engine()
    config = engine.config
    suggestions_file = config.data_dir / "llm" / "classification_suggestions.jsonl"

    if not suggestions_file.exists():
        return {"suggestions": []}

    suggestions = []
    for line in suggestions_file.read_text().strip().split("\n"):
        if line.strip():
            try:
                suggestions.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return {"suggestions": suggestions}
