"""Dashboard agents page — view and manage registered agents."""

import time

from fasthtml.common import (
    Button,
    Details,
    Div,
    Form,
    H2,
    H3,
    Input,
    P,
    RedirectResponse,
    Small,
    Span,
    Strong,
    Summary,
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


def _relative_time(age_seconds: float) -> str:
    """Format a duration in seconds as a human-readable relative time."""
    if age_seconds < 60:
        return f"{age_seconds:.0f}s ago"
    elif age_seconds < 3600:
        return f"{age_seconds / 60:.0f}m ago"
    else:
        return f"{age_seconds / 3600:.0f}h ago"


def _grant_expiry_display(grant) -> str:
    """Format grant expiry as relative time or task ID."""
    if grant.task_id and grant.expires_at is None:
        return f"task: {grant.task_id}"
    elif grant.expires_at is not None:
        remaining = grant.expires_at - time.monotonic()
        if remaining <= 0:
            return "expired"
        return (
            _relative_time(-remaining)
            if remaining < 0
            else f"in {_relative_time(remaining).replace(' ago', '')}"
        )
    return "no expiry"


def _grant_expiry_cell(grant) -> str:
    """Format grant expiry for display in the grants table."""
    parts = []
    if grant.expires_at is not None:
        remaining = grant.expires_at - time.monotonic()
        if remaining <= 0:
            parts.append("expired")
        elif remaining < 60:
            parts.append(f"{remaining:.0f}s remaining")
        elif remaining < 3600:
            parts.append(f"{remaining / 60:.0f}m remaining")
        else:
            parts.append(f"{remaining / 3600:.0f}h remaining")
    if grant.task_id:
        parts.append(f"task: {grant.task_id}")
    return ", ".join(parts) if parts else "no expiry"


def register(rt, get_engine, csrf_field=None, verify_csrf=None, get_csrf_token=None):
    @rt("/agents")
    def agents_page(sess):
        engine = get_engine()
        agent_list = engine.agent_registry.list_agents()
        token = get_csrf_token(sess) if get_csrf_token else ""

        if not agent_list:
            empty = Div(
                P("No agents registered yet."),
                P("Agents will appear here once they connect to the service.", cls="text-sm"),
                cls="empty-state",
            )
            content = Div(H2("Registered Agents"), empty, cls="panel")
            return Page("Agents", content, active="agents", csrf_token=token)

        csrf = csrf_field(sess) if csrf_field else ""

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

            # ── Heartbeat status ──
            hb = engine.heartbeat_monitor._agents.get(agent.agent_id)
            if hb:
                age = time.monotonic() - hb["last_seen"]
                last_seen_parts = [Span(_relative_time(age))]
                if age > 90:
                    last_seen_parts.append(Span(" "))
                    last_seen_parts.append(Span("stale", cls="badge stale-badge"))
                last_seen_cell = Span(*last_seen_parts)

                if hb["config_hash"] != hb["first_hash"]:
                    config_cell = Span("drift", cls="badge drift-warning")
                else:
                    config_cell = Span("ok", cls="text-muted")
            else:
                last_seen_cell = Span("—", cls="text-muted")
                config_cell = Span("—", cls="text-muted")

            # ── Role with details button ──
            role_cell = Div(
                Span(agent.role),
                Span(" "),
                Button(
                    "Details",
                    cls="btn btn-sm",
                    hx_get=f"{_comp.MOUNT_PREFIX}/agents/role/{agent.role}",
                    hx_target=f"#role-detail-{agent.agent_id}",
                    hx_swap="innerHTML",
                ),
                Div(id=f"role-detail-{agent.agent_id}", cls="mt-1"),
            )

            # ── Temporary permissions detail row ──
            grants = engine.temp_permissions.list_grants(agent.agent_id)

            grant_rows = []
            for grant in grants:
                revoke_form = Form(
                    csrf,
                    Button("Revoke", type="submit", cls="btn btn-danger btn-sm"),
                    method="post",
                    action=f"{_comp.MOUNT_PREFIX}/agents/{agent.agent_id}/revoke-grant/{grant.id}",
                )
                grant_rows.append(
                    Tr(
                        Td(Span(grant.permission, cls="mono")),
                        Td(_grant_expiry_cell(grant)),
                        Td(revoke_form),
                    )
                )

            if grant_rows:
                grants_table = Table(
                    Thead(Tr(Th("Permission"), Th("Expires"), Th("Action"))),
                    Tbody(*grant_rows),
                )
            else:
                grants_table = P("No active grants.", cls="text-muted text-sm")

            grant_form = Details(
                Summary("Grant new permission"),
                Form(
                    csrf,
                    Div(
                        Small("Permission name", cls="text-muted"),
                        Input(
                            type="text",
                            name="permission",
                            placeholder="e.g. WriteFile",
                            required=True,
                        ),
                        style="margin-bottom: 0.5rem;",
                    ),
                    Div(
                        Small("Duration (seconds)", cls="text-muted"),
                        Input(type="number", name="duration", placeholder="Optional"),
                        style="margin-bottom: 0.5rem;",
                    ),
                    Div(
                        Small("Task ID", cls="text-muted"),
                        Input(type="text", name="task_id", placeholder="Optional"),
                        style="margin-bottom: 0.5rem;",
                    ),
                    Button("Grant", type="submit", cls="btn btn-primary btn-sm"),
                    method="post",
                    action=f"{_comp.MOUNT_PREFIX}/agents/{agent.agent_id}/temp-grant",
                ),
                cls="mt-1",
            )

            detail_content = Div(
                H3("Temporary Permissions", cls="text-sm mb-1"),
                grants_table,
                grant_form,
                style="padding: 0.75rem 1rem; background: rgba(255,255,255,0.02);",
            )

            # Main agent row
            rows.append(
                Tr(
                    Td(Span(agent.agent_id, cls="mono")),
                    Td(role_cell),
                    Td(Span(session_display, cls="mono")),
                    Td(parent_display),
                    Td(AgentStatusBadge(agent.killed)),
                    Td(last_seen_cell),
                    Td(config_cell),
                    Td(action_form),
                )
            )
            # Detail/expansion row for temp permissions
            rows.append(
                Tr(
                    Td(detail_content, colspan="8"),
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
                    Th("Last Seen"),
                    Th("Config"),
                    Th("Actions"),
                )
            ),
            Tbody(*rows),
        )

        panel = Div(H2("Registered Agents"), agent_table, cls="panel")
        return Page("Agents", panel, active="agents", csrf_token=token)

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
        engine.agent_registry.revive_agent(agent_id)  # new token discarded in dashboard
        return RedirectResponse(f"{_comp.MOUNT_PREFIX}/agents", status_code=303)

    @rt("/agents/{agent_id}/temp-grant", methods=["post"])
    def grant_temp_permission(
        agent_id: str,
        permission: str,
        duration: str = "",
        task_id: str = "",
        sess=None,
        _csrf: str = "",
    ):
        if verify_csrf and not verify_csrf(sess, _csrf):
            return Response("CSRF token invalid", status_code=403)
        engine = get_engine()
        dur = float(duration) if duration else None
        tid = task_id if task_id else None
        engine.temp_permissions.grant(agent_id, permission, duration_seconds=dur, task_id=tid)
        return RedirectResponse(f"{_comp.MOUNT_PREFIX}/agents", status_code=303)

    @rt("/agents/{agent_id}/revoke-grant/{grant_id}", methods=["post"])
    def revoke_grant(agent_id: str, grant_id: str, sess=None, _csrf: str = ""):
        if verify_csrf and not verify_csrf(sess, _csrf):
            return Response("CSRF token invalid", status_code=403)
        engine = get_engine()
        engine.temp_permissions.revoke(grant_id)
        return RedirectResponse(f"{_comp.MOUNT_PREFIX}/agents", status_code=303)

    @rt("/agents/role/{role_name}")
    def role_details(role_name: str):
        engine = get_engine()
        role = engine.role_manager.get_role(role_name)

        if role is None:
            return Div(
                P(f"Role '{role_name}' not found.", cls="text-muted text-sm"),
            )

        allowed = (
            ", ".join(sorted(role.allowed_action_classes))
            if role.allowed_action_classes
            else "all (no restrictions)"
        )
        denied = (
            ", ".join(sorted(role.denied_action_classes)) if role.denied_action_classes else "none"
        )

        resource_allow = role.resource_patterns.get("allow", [])
        resource_deny = role.resource_patterns.get("deny", [])

        allow_display = ", ".join(resource_allow) if resource_allow else "none"
        deny_display = ", ".join(resource_deny) if resource_deny else "none"

        return Div(
            Div(
                Div(
                    Strong("Enforcement: "),
                    Span(role.enforcement_mode, cls="mono"),
                    cls="text-sm",
                ),
                Div(
                    Strong("Autonomy: "),
                    Span(role.autonomy_level, cls="mono"),
                    cls="text-sm",
                ),
                Div(
                    Strong("Allowed actions: "),
                    Span(allowed, cls="mono text-sm"),
                    cls="text-sm mt-1",
                ),
                Div(
                    Strong("Denied actions: "),
                    Span(denied, cls="mono text-sm"),
                    cls="text-sm",
                ),
                Div(
                    Strong("Resource allow: "),
                    Span(allow_display, cls="mono text-sm"),
                    cls="text-sm mt-1",
                ),
                Div(
                    Strong("Resource deny: "),
                    Span(deny_display, cls="mono text-sm"),
                    cls="text-sm",
                ),
                style="padding: 0.5rem; background: rgba(255,255,255,0.03); border-radius: 6px; border: 1px solid var(--border);",
            )
        )
