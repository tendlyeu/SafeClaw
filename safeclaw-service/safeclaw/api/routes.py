"""FastAPI route definitions for SafeClaw API."""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from safeclaw.utils.sanitize import sanitize_string as _sanitize_string
from safeclaw.utils.sanitize import sanitize_params as _sanitize_params

from safeclaw.api.models import (
    AgentRegisterRequest,
    AgentRegisterResponse,
    AgentStartRequest,
    ContextResponse,
    DecisionResponse,
    HandshakeRequest,
    HandshakeResponse,
    HeartbeatRequest,
    LlmIORequest,
    MessageRequest,
    PolicyCompileRequest,
    PolicyCompileResponse,
    PreferencesRequest,
    SandboxPolicyValidationRequest,
    SandboxPolicyValidationResponse,
    SessionEndRequest,
    InboundMessageRequest,
    InboundMessageResponse,
    SessionStartRequest,
    SessionStartResponse,
    SubagentEndedRequest,
    SubagentEndedResponse,
    SubagentSpawnRequest,
    SubagentSpawnResponse,
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
    if scope is not None:
        # Use exact match or set membership (not substring) to avoid
        # false positives like "administrator" or "notadmin"
        scope_set = {s.strip() for s in scope.split(",")} if isinstance(scope, str) else set()
        if "admin" not in scope_set:
            raise HTTPException(status_code=403, detail="Admin access required")

    # Layer 2: X-Admin-Password header check
    engine = _get_engine()
    if engine.config.admin_password:  # only enforce when a password is actually set
        provided = request.headers.get("X-Admin-Password", "")
        if not engine.config.verify_admin_password(provided):
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
    _verify_agent_token(engine, request.agentId, request.agentToken)
    # Use org_id from API key auth (numeric DB user ID) if available,
    # otherwise fall back to client-supplied userId, then "default"
    user_id = getattr(req.state, "org_id", None) or request.userId or "default"
    # Sanitize params to strip control characters that could be used for
    # prompt injection when params are later included in LLM prompts
    sanitized_params = _sanitize_params(request.params)
    event = ToolCallEvent(
        session_id=request.sessionId,
        user_id=user_id,
        tool_name=request.toolName,
        params=sanitized_params,
        session_history=request.sessionHistory,
        agent_id=request.agentId,
        agent_token=request.agentToken,
    )
    decision = await engine.evaluate_tool_call(event)
    audit_id = decision.audit_id
    if request.dryRun:
        audit_id = ""
    return DecisionResponse(
        block=decision.block,
        reason=decision.reason,
        auditId=audit_id,
        confirmationRequired=decision.requires_confirmation,
        constraintStep=decision.constraint_step,
        riskLevel=getattr(decision, "_risk_level", ""),
    )


@router.post("/evaluate/message", response_model=DecisionResponse)
async def evaluate_message(request: MessageRequest, req: Request) -> DecisionResponse:
    engine = _get_engine()
    _verify_agent_token(engine, request.agentId, request.agentToken)
    user_id = getattr(req.state, "org_id", None) or request.userId or "default"
    # Sanitize message content to strip control characters
    sanitized_content = _sanitize_string(request.content)
    event = MessageEvent(
        session_id=request.sessionId,
        user_id=user_id,
        to=request.to,
        content=sanitized_content,
        agent_id=request.agentId,
        agent_token=request.agentToken,
    )
    decision = await engine.evaluate_message(event)
    return DecisionResponse(
        block=decision.block,
        reason=decision.reason,
        auditId=decision.audit_id,
        confirmationRequired=decision.requires_confirmation,
        constraintStep=decision.constraint_step,
    )


@router.post("/evaluate/inbound-message", response_model=InboundMessageResponse)
async def evaluate_inbound_message(request: InboundMessageRequest, req: Request) -> InboundMessageResponse:
    """Evaluate inbound messages for prompt injection risk.

    Assesses risk based on:
    - Channel trust level (from channel ontology)
    - Content analysis for prompt injection patterns
    - Sender metadata
    """
    import re

    engine = _get_engine()
    _verify_agent_token(engine, request.userId, getattr(request, "agentToken", None))
    sanitized_content = _sanitize_string(request.content)
    flags: list[str] = []
    warnings: list[str] = []

    # Channel trust mapping — derived from the channel ontology
    channel_trust: dict[str, str] = {
        "direct_message": "high",
        "dm": "high",
        "group_message": "medium",
        "group": "medium",
        "public_channel": "low",
        "public": "low",
        "webhook": "untrusted",
        "webhook_message": "untrusted",
        "api": "untrusted",
    }
    channel_key = request.channel.lower().replace("-", "_").replace(" ", "_")
    trust_level = channel_trust.get(channel_key, "low")

    # Start with risk based on channel trust
    risk_level = "low"
    if trust_level == "untrusted":
        risk_level = "medium"
        flags.append("untrusted_channel")
    elif trust_level == "low":
        risk_level = "low"
        flags.append("low_trust_channel")

    # Prompt injection detection patterns
    injection_patterns = [
        (re.compile(
            r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
        ), "prompt_injection_ignore_instructions"),
        (re.compile(
            r"(?i)you\s+are\s+now\s+(a|an|in)\s+",
        ), "prompt_injection_role_override"),
        (re.compile(
            r"(?i)system\s*prompt\s*[:=]",
        ), "prompt_injection_system_prompt"),
        (re.compile(
            r"(?i)(do\s+not|don'?t)\s+follow\s+(your|the)\s+(rules|guidelines|instructions)",
        ), "prompt_injection_rule_override"),
        (re.compile(
            r"(?i)\[/?INST\]|\[/?SYS\]|<\|im_start\|>|<\|im_end\|>",
        ), "prompt_injection_special_tokens"),
        (re.compile(
            r"(?i)pretend\s+(you\s+)?(are|to\s+be)\s+",
        ), "prompt_injection_pretend"),
    ]

    for pattern, flag in injection_patterns:
        if pattern.search(sanitized_content):
            flags.append(flag)

    # Escalate risk level based on detected flags
    injection_flags = [f for f in flags if f.startswith("prompt_injection_")]
    if len(injection_flags) >= 2:
        risk_level = "critical"
        warnings.append(
            f"Multiple prompt injection patterns detected: {', '.join(injection_flags)}"
        )
    elif len(injection_flags) == 1:
        if trust_level in ("untrusted", "low"):
            risk_level = "high"
        else:
            risk_level = "medium"
        warnings.append(
            f"Prompt injection pattern detected: {injection_flags[0]}"
        )

    # Empty sender from untrusted channel is suspicious
    if not request.sender and trust_level == "untrusted":
        flags.append("anonymous_untrusted_sender")
        if risk_level == "low":
            risk_level = "medium"

    return InboundMessageResponse(
        riskLevel=risk_level,
        flags=flags,
        warnings=warnings,
    )


@router.post(
    "/evaluate/sandbox-policy",
    response_model=SandboxPolicyValidationResponse,
    dependencies=[Depends(require_admin)],
)
async def evaluate_sandbox_policy(
    request: SandboxPolicyValidationRequest,
) -> SandboxPolicyValidationResponse:
    """Validate a sandbox policy configuration.

    Checks that the policy dict contains the required sections
    (toolPolicy, filesystemPolicy) and validates mount point
    configurations. Full SHACL graph-based validation is performed
    when the policy is mapped to RDF triples.
    """
    violations: list[dict] = []
    policy = request.policy

    if not policy.get("toolPolicy"):
        violations.append({
            "field": "toolPolicy",
            "message": "Sandbox must define a tool policy",
        })
    if not policy.get("filesystemPolicy"):
        violations.append({
            "field": "filesystemPolicy",
            "message": "Sandbox must define filesystem boundaries",
        })

    # Validate mount points if present
    fs_policy = policy.get("filesystemPolicy", {})
    mounts = fs_policy.get("mounts", [])
    if isinstance(mounts, list):
        for i, mount in enumerate(mounts):
            if not isinstance(mount, dict):
                continue
            if not mount.get("path"):
                violations.append({
                    "field": f"filesystemPolicy.mounts[{i}].path",
                    "message": "Mount point must specify a path",
                })
            mode = mount.get("mode", "")
            if mode not in ("read-only", "read-write"):
                violations.append({
                    "field": f"filesystemPolicy.mounts[{i}].mode",
                    "message": "Mount mode must be read-only or read-write",
                })

    # Validate denied tools have names
    tool_policy = policy.get("toolPolicy", {})
    denied = tool_policy.get("denied", [])
    if isinstance(denied, list):
        for i, tool in enumerate(denied):
            if isinstance(tool, dict) and not tool.get("name"):
                violations.append({
                    "field": f"toolPolicy.denied[{i}].name",
                    "message": "Denied tool must specify a name",
                })

    return SandboxPolicyValidationResponse(
        conformant=len(violations) == 0,
        violations=violations,
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


@router.post("/session/start", response_model=SessionStartResponse)
async def start_session(request: SessionStartRequest, req: Request) -> SessionStartResponse:
    """Initialize session-scoped governance state.

    Pre-loads user preferences, initializes rate limit bucket, and logs
    session start to audit.
    """
    engine = _get_engine()
    _verify_agent_token(engine, request.agentId, request.agentToken)
    user_id = getattr(req.state, "org_id", None) or request.userId or "default"
    owner_id = request.agentId or user_id

    # Initialize session tracker state with the owner
    engine.session_tracker._get_or_create(request.sessionId, owner_id=owner_id)

    # Pre-load user preferences into cache by querying them
    if request.userId:
        engine.preference_checker.get_preferences(request.userId)

    # Initialize rate limiter session bucket (creates entry if missing)
    engine.rate_limiter._sessions.setdefault(request.sessionId, [])

    logger.info(
        "Session %s started: user=%s agent=%s",
        request.sessionId,
        user_id,
        request.agentId,
    )
    return SessionStartResponse(acknowledged=True)


@router.post("/session/end")
async def end_session(request: SessionEndRequest, req: Request):
    """Clean up all per-session state when a session ends.

    Verifies session ownership before clearing: only the org/agent that
    created the session (or unowned sessions) can be cleared.
    """
    engine = _get_engine()
    org_id = getattr(req.state, "org_id", None)

    # Ownership check: if the caller has an org_id, verify they own the session
    if org_id:
        if not engine.session_tracker.verify_session_owner(request.sessionId, org_id):
            raise HTTPException(
                status_code=403,
                detail="Session owned by a different user/agent",
            )

    logger.info("Session %s cleared by org_id=%s", request.sessionId, org_id)
    await engine.clear_session(request.sessionId)
    return {"ok": True, "sessionId": request.sessionId}


@router.post("/record/tool-result")
async def record_tool_result(request: ToolResultRequest, req: Request):
    engine = _get_engine()
    _verify_agent_token(engine, request.agentId, request.agentToken)
    user_id = getattr(req.state, "org_id", None) or request.userId or "default"
    # Sanitize params: strip control characters from string values that could be
    # used for prompt injection when session history is injected into LLM context
    sanitized_params = _sanitize_params(request.params)
    sanitized_result = _sanitize_string(request.result)
    event = ToolResultEvent(
        session_id=request.sessionId,
        tool_name=request.toolName,
        params=sanitized_params,
        result=sanitized_result,
        success=request.success,
        user_id=user_id,
        agent_id=request.agentId,
        agent_token=request.agentToken,
    )
    await engine.record_action_result(event)
    return {"ok": True}


@router.post("/evaluate/subagent-spawn", response_model=SubagentSpawnResponse)
async def evaluate_subagent_spawn(request: SubagentSpawnRequest, req: Request) -> SubagentSpawnResponse:
    """Evaluate whether a subagent spawn should be allowed.

    Checks for delegation bypass: if the parent agent has recent blocks and the
    child's proposed tools overlap with those blocked actions, this is flagged as
    a delegation bypass attempt.
    """
    engine = _get_engine()
    _verify_agent_token(engine, request.agentId, request.agentToken)

    parent_id = request.parentAgentId
    if not parent_id:
        return SubagentSpawnResponse(allowed=True)

    # Check if parent agent is killed
    parent_record = engine.agent_registry.get_agent(parent_id)
    if parent_record is not None and parent_record.killed:
        return SubagentSpawnResponse(
            allowed=False,
            block=True,
            reason=f"Parent agent {parent_id} is killed; cannot spawn subagents",
        )

    # Check delegation bypass: if child's proposed tools overlap with parent's
    # recently blocked actions, flag it as a potential delegation bypass.
    # We check the detector's block records directly rather than using
    # check_delegation(), because at spawn time we only know the tool names
    # the child will have access to -- not the specific params it will use.
    child_tools = request.childConfig.get("tools", [])
    if child_tools and isinstance(child_tools, list):
        from safeclaw.engine.delegation_detector import _normalize_tool_name
        from time import monotonic

        detector = engine.delegation_detector
        if detector.mode != "disabled":
            now = monotonic()
            child_tool_set = {
                _normalize_tool_name(t) for t in child_tools if isinstance(t, str)
            }
            for record in detector._blocks:
                if (
                    record.agent_id == parent_id
                    and record.tool_name in child_tool_set
                    and (now - record.timestamp) <= 300  # DETECTION_WINDOW
                ):
                    return SubagentSpawnResponse(
                        allowed=False,
                        block=True,
                        reason=(
                            f"Delegation bypass detected: parent {parent_id} was "
                            f"blocked from '{record.tool_name}' and is attempting "
                            f"to spawn a child with access to the same tool"
                        ),
                    )

    logger.info(
        "Subagent spawn allowed: parent=%s session=%s reason=%s",
        parent_id,
        request.sessionId,
        request.reason,
    )
    return SubagentSpawnResponse(allowed=True)


@router.post("/record/subagent-ended", response_model=SubagentEndedResponse)
async def record_subagent_ended(request: SubagentEndedRequest, req: Request) -> SubagentEndedResponse:
    """Record subagent completion for audit trail."""
    engine = _get_engine()
    _verify_agent_token(engine, request.agentId, request.agentToken)
    logger.info(
        "Subagent ended: parent=%s child=%s success=%s session=%s",
        request.parentAgentId,
        request.childAgentId,
        request.success,
        request.sessionId,
    )
    # Record in session tracker if session exists
    if request.sessionId:
        engine.session_tracker.record_outcome(
            session_id=request.sessionId,
            action_class="SubagentEnded",
            tool_name="__subagent__",
            success=request.success,
            params={
                "parentAgentId": request.parentAgentId,
                "childAgentId": request.childAgentId,
            },
        )
    return SubagentEndedResponse(ok=True)


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
        "autonomyLevel": prefs.autonomy_level,
        "confirmBeforeDelete": prefs.confirm_before_delete,
        "confirmBeforePush": prefs.confirm_before_push,
        "confirmBeforeSend": prefs.confirm_before_send,
        "maxFilesPerCommit": prefs.max_files_per_commit,
    }


@router.post("/preferences/{user_id}", dependencies=[Depends(require_admin)])
async def update_preferences(user_id: str, request: PreferencesRequest):
    """Update user preferences — writes Turtle file."""
    import re

    engine = _get_engine()
    safe_user_id = re.sub(r"[^a-zA-Z0-9_@.-]", "", user_id)

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
    found, new_token = engine.agent_registry.revive_agent(agent_id)
    if not found:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"ok": True, "agentId": agent_id, "killed": False, "newToken": new_token}


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
    drifted = engine.heartbeat_monitor.check_config_drift(request.agentId, request.configHash)

    return {"ok": True, "stale": stale, "configDrift": drifted}


@router.post("/handshake", response_model=HandshakeResponse)
async def handshake(req: HandshakeRequest, request: Request):
    """Validate API key and log a connection event to the audit dashboard."""
    org_id = getattr(request.state, "org_id", None)
    scope = getattr(request.state, "api_key_scope", "full")
    engine = _get_engine()

    # Log to audit dashboard
    key_mgr = getattr(engine, "api_key_manager", None)
    if key_mgr and hasattr(key_mgr, "log_audit_decision") and org_id:
        from datetime import datetime, timezone

        key_mgr.log_audit_decision(
            user_id=org_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id="",
            tool_name="__handshake__",
            params_summary=f"plugin_version={req.pluginVersion}",
            decision="allowed",
            risk_level="none",
            reason="Plugin connected successfully",
            elapsed_ms=0.0,
        )

    engine_ready = getattr(engine, "is_ready", lambda: True)()
    version = getattr(engine, "version", "unknown")

    return HandshakeResponse(
        ok=True,
        orgId=org_id or "",
        scope=scope,
        engineReady=engine_ready,
        serviceVersion=version,
        message="Handshake successful",
    )


# ── LLM Layer Routes ──


@router.post(
    "/policies/compile", response_model=PolicyCompileResponse, dependencies=[Depends(require_admin)]
)
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
            yield 'event: error\ndata: {"error": "Max subscribers limit reached"}\n\n'
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


@router.get("/llm/findings", dependencies=[Depends(require_admin)])
async def get_findings():
    # Findings are currently logged but not persisted to a queryable store.
    return {"findings": []}


@router.get("/llm/suggestions", dependencies=[Depends(require_admin)])
async def get_suggestions(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    import json

    engine = _get_engine()
    config = engine.config
    suggestions_file = config.data_dir / "llm" / "classification_suggestions.jsonl"

    if not suggestions_file.exists():
        return {"suggestions": [], "total": 0}

    # Stream the file line-by-line instead of reading the entire file into memory.
    # Use a deque with maxlen to keep only the tail (most recent entries).
    suggestions = []
    total = 0
    with open(suggestions_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            if total <= offset:
                continue
            if len(suggestions) >= limit:
                # Keep counting total but stop collecting
                continue
            try:
                suggestions.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return {"suggestions": suggestions, "total": total}
