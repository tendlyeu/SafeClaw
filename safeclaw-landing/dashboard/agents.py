"""Agent management page — proxies to SafeClaw service API."""

from fasthtml.common import *
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
        P("This page connects to a running SafeClaw service instance to show "
          "agents that have registered with it. This is for advanced users "
          "who self-host the SafeClaw engine.",
          cls=TextPresets.muted_sm),
        P("If you're using the hosted service at ", Code("safeclaw.eu"),
          ", agents are managed automatically — you don't need to configure anything here.",
          cls=TextPresets.muted_sm),
        Form(
            LabelInput("Service URL", id="service_url", value="http://localhost:8420",
                       placeholder="http://localhost:8420"),
            P("The URL of your self-hosted SafeClaw service.",
              cls=TextPresets.muted_sm, style="margin-top:-0.5rem;"),
            LabelInput("Admin Password", id="admin_password", type="password",
                       placeholder="Leave empty if not set"),
            P("Required if you set ", Code("SAFECLAW_ADMIN_PASSWORD"),
              " on your service.",
              cls=TextPresets.muted_sm, style="margin-top:-0.5rem;"),
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
            P("Agents register themselves when they start a session with the SafeClaw service. "
              "You can ", Strong("kill"), " an agent to immediately block all its actions, "
              "or ", Strong("revive"), " it to restore access.",
              cls=TextPresets.muted_sm),
            Div(P("Connect to a service to see agents.", cls=TextPresets.muted_sm), id="agent-list"),
        ),
    )
