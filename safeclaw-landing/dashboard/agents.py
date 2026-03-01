"""Agent management page."""

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


def HostedAgentsContent():
    """Agents page content for hosted users."""
    return (
        Card(
            H3("Agent Governance"),
            P("On the hosted service, agents are governed automatically when they "
              "connect using your API key. Each agent that calls the SafeClaw API "
              "is tracked and governed by your preferences.",
              cls=TextPresets.muted_sm),
            Divider(),
            H4("How it works"),
            Ul(
                Li("Your AI agent's plugin sends every tool call to SafeClaw before execution"),
                Li("SafeClaw validates it against your governance rules and preferences"),
                Li("Blocked actions are logged and the agent receives a clear explanation"),
                Li("All decisions are recorded in the audit trail"),
                cls="uk-list uk-list-disc",
                style="font-size:0.875rem; color:var(--muted-foreground, #888);",
            ),
            Divider(),
            P("To manage individual agents (kill switch, role assignment), "
              "enable ", Strong("self-hosted mode"), " in ",
              A("Preferences", href="/dashboard/prefs"),
              " and connect to your own SafeClaw service instance.",
              cls=TextPresets.muted_sm),
        ),
    )


def SelfHostedAgentsContent(service_url: str = ""):
    """Agents page content for self-hosted users."""
    return (
        Card(
            H3("Service Connection"),
            P("Connect to your self-hosted SafeClaw service to view and manage agents.",
              cls=TextPresets.muted_sm),
            Divider(),
            Form(
                Div(
                    LabelInput("Service URL", id="service_url",
                               value=service_url or "http://localhost:8420",
                               placeholder="http://localhost:8420"),
                    P("The URL of your self-hosted SafeClaw service.",
                      cls=TextPresets.muted_sm),
                    cls="space-y-1",
                ),
                Div(
                    LabelInput("Admin Password", id="admin_password", type="password",
                               placeholder="Leave empty if not set"),
                    P("Required if you set ", Code("SAFECLAW_ADMIN_PASSWORD"),
                      " on your service.",
                      cls=TextPresets.muted_sm),
                    cls="space-y-1",
                ),
                Button("Connect & Load Agents", cls=ButtonT.primary, type="submit"),
                hx_post="/dashboard/agents/load",
                hx_target="#agent-list",
                hx_swap="innerHTML",
                cls="space-y-6",
            ),
        ),
        Card(
            H3("Registered Agents"),
            P("Agents register themselves when they start a session. "
              "You can ", Strong("kill"), " an agent to immediately block all its actions, "
              "or ", Strong("revive"), " it to restore access.",
              cls=TextPresets.muted_sm),
            Divider(),
            Div(P("Connect to a service to see agents.", cls=TextPresets.muted_sm), id="agent-list"),
        ),
    )
