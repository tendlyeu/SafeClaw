"""FastAPI route definitions for SafeClaw API."""

import logging

from fastapi import APIRouter, Query

from safeclaw.api.models import (
    AgentStartRequest,
    ContextResponse,
    DecisionResponse,
    LlmIORequest,
    MessageRequest,
    ToolCallRequest,
    ToolResultRequest,
)
from safeclaw.engine.core import AgentStartEvent, LlmIOEvent, MessageEvent, ToolCallEvent, ToolResultEvent

logger = logging.getLogger("safeclaw.api")

router = APIRouter()


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
    )
    result = await engine.build_context(event)
    return ContextResponse(prependContext=result.prepend_context)


@router.post("/record/tool-result")
async def record_tool_result(request: ToolResultRequest):
    engine = _get_engine()
    event = ToolResultEvent(
        session_id=request.sessionId,
        tool_name=request.toolName,
        params=request.params,
        result=request.result,
        success=request.success,
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
    )
    await engine.log_llm_io(event)
    return {"ok": True}


@router.get("/audit")
async def query_audit(
    session_id: str | None = Query(None, alias="sessionId"),
    blocked: bool = False,
    limit: int = 20,
):
    engine = _get_engine()
    if session_id:
        records = engine.audit.get_session_records(session_id)
    elif blocked:
        records = engine.audit.get_blocked_records(limit)
    else:
        records = engine.audit.get_recent_records(limit)
    return {"decisions": [r.model_dump() for r in records]}


@router.post("/reload")
async def reload_ontologies():
    """Hot-reload ontologies and reinitialize constraint checkers."""
    engine = _get_engine()
    engine.reload()
    return {"ok": True, "triples": len(engine.kg)}


@router.get("/audit/statistics")
async def audit_statistics(limit: int = 100):
    """Get aggregate statistics from recent audit records."""
    from safeclaw.audit.reporter import AuditReporter
    engine = _get_engine()
    reporter = AuditReporter(engine.audit)
    records = engine.audit.get_recent_records(limit)
    return reporter.get_statistics(records)


@router.get("/audit/report/{session_id}")
async def audit_report(
    session_id: str,
    format: str = Query("markdown", alias="format"),
):
    """Generate a session audit report in markdown, JSON, or CSV format."""
    from fastapi.responses import PlainTextResponse
    from safeclaw.audit.reporter import AuditReporter
    engine = _get_engine()
    reporter = AuditReporter(engine.audit)
    content = reporter.generate_session_report(session_id, format=format)
    content_type = "text/csv" if format == "csv" else "application/json" if format == "json" else "text/markdown"
    return PlainTextResponse(content, media_type=content_type)


@router.get("/audit/compliance")
async def compliance_report(limit: int = 100):
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
async def ontology_search(q: str = Query(...)):
    """Fuzzy search for ontology nodes by name or label."""
    from safeclaw.engine.graph_builder import GraphBuilder
    engine = _get_engine()
    builder = GraphBuilder(engine.kg)
    return {"results": builder.search_nodes(q)}
