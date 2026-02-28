"""Dashboard agents page — view and manage registered agents."""

from fasthtml.common import (
    Button,
    Div,
    Form,
    H2,
    P,
    RedirectResponse,
    Span,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
)

from starlette.responses import Response

import safeclaw.dashboard.components as _comp
from safeclaw.dashboard.components import AgentStatusBadge, Page


def register(rt, get_engine, csrf_field=None, verify_csrf=None):
    @rt("/agents")
    def agents_page(sess):
        engine = get_engine()
        agent_list = engine.agent_registry.list_agents()

        if not agent_list:
            empty = Div(
                P("No agents registered yet."),
                P("Agents will appear here once they connect to the service.", cls="text-sm"),
                cls="empty-state",
            )
            content = Div(H2("Registered Agents"), empty, cls="panel")
            return Page("Agents", content, active="agents")

        rows = []
        for agent in agent_list:
            # Truncate session ID for display
            session_display = agent.session_id[:8] if agent.session_id else "—"
            parent_display = (
                Span(agent.parent_id, cls="mono")
                if agent.parent_id
                else Span("—", cls="text-muted")
            )

            # Kill or Revive button depending on status
            csrf = csrf_field(sess) if csrf_field else ""
            if agent.killed:
                action_form = Form(
                    csrf,
                    Button("Revive", type="submit", cls="btn btn-primary btn-sm"),
                    method="post",
                    action=f"{_comp.MOUNT_PREFIX}/agents/{agent.agent_id}/revive",
                )
            else:
                action_form = Form(
                    csrf,
                    Button("Kill", type="submit", cls="btn btn-danger btn-sm"),
                    method="post",
                    action=f"{_comp.MOUNT_PREFIX}/agents/{agent.agent_id}/kill",
                )

            rows.append(
                Tr(
                    Td(Span(agent.agent_id, cls="mono")),
                    Td(agent.role),
                    Td(Span(session_display, cls="mono")),
                    Td(parent_display),
                    Td(AgentStatusBadge(agent.killed)),
                    Td(action_form),
                )
            )

        agent_table = Table(
            Thead(
                Tr(
                    Th("Agent ID"),
                    Th("Role"),
                    Th("Session"),
                    Th("Parent"),
                    Th("Status"),
                    Th("Actions"),
                )
            ),
            Tbody(*rows),
        )

        panel = Div(H2("Registered Agents"), agent_table, cls="panel")
        return Page("Agents", panel, active="agents")

    @rt("/agents/{agent_id}/kill", methods=["post"])
    def kill_agent(agent_id: str, sess, _csrf: str = ""):
        if verify_csrf and not verify_csrf(sess, _csrf):
            return Response("CSRF token invalid", status_code=403)
        engine = get_engine()
        engine.agent_registry.kill_agent(agent_id)
        return RedirectResponse(f"{_comp.MOUNT_PREFIX}/agents", status_code=303)

    @rt("/agents/{agent_id}/revive", methods=["post"])
    def revive_agent(agent_id: str, sess, _csrf: str = ""):
        if verify_csrf and not verify_csrf(sess, _csrf):
            return Response("CSRF token invalid", status_code=403)
        engine = get_engine()
        engine.agent_registry.revive_agent(agent_id)
        return RedirectResponse(f"{_comp.MOUNT_PREFIX}/agents", status_code=303)
