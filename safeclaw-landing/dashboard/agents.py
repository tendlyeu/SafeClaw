"""Agent management page — proxies to SafeClaw service API."""

from monsterui.all import *


def AgentTable(agents: list[dict]):
    """Table of registered agents."""
    if not agents:
        return P("No agents registered on the connected service.", cls=TextPresets.muted_sm)

    rows = []
    for a in agents:
        status = Label("Killed", cls=LabelT.destructive) if a.get("killed") else Label("Active", cls=LabelT.primary)
        action_btn = (
            Button("Revive", cls=ButtonT.primary + " " + ButtonT.xs,
                   hx_post=f"/dashboard/agents/{a['agentId']}/revive",
                   hx_target="#agent-list", hx_swap="innerHTML")
            if a.get("killed") else
            Button("Kill", cls=ButtonT.destructive + " " + ButtonT.xs,
                   hx_post=f"/dashboard/agents/{a['agentId']}/kill",
                   hx_target="#agent-list", hx_swap="innerHTML",
                   hx_confirm="Kill this agent?")
        )
        rows.append(Tr(
            Td(Code(a["agentId"])),
            Td(a.get("role", "—")),
            Td(a.get("parentId", "—") or "—"),
            Td(status),
            Td(action_btn),
        ))

    return Table(
        Thead(Tr(Th("Agent ID"), Th("Role"), Th("Parent"), Th("Status"), Th(""))),
        Tbody(*rows),
        cls=(TableT.divider, TableT.hover, TableT.sm),
    )


def ServiceConfigCard():
    """Card for configuring service connection."""
    return Card(
        H3("Service Connection"),
        P("Configure the SafeClaw service URL and admin password to manage agents.", cls=TextPresets.muted_sm),
        Form(
            LabelInput("Service URL", id="service_url", value="http://localhost:8420",
                       placeholder="http://localhost:8420"),
            LabelInput("Admin Password", id="admin_password", type="password",
                       placeholder="Leave empty if not set"),
            Button("Connect & Load Agents", cls=ButtonT.primary, type="submit"),
            hx_post="/dashboard/agents/load",
            hx_target="#agent-list",
            hx_swap="innerHTML",
            cls="space-y-4",
        ),
    )


def AgentsContent():
    """Full agents page content."""
    return (
        ServiceConfigCard(),
        Card(
            H3("Registered Agents"),
            Div(P("Connect to a service to see agents.", cls=TextPresets.muted_sm), id="agent-list"),
        ),
    )
