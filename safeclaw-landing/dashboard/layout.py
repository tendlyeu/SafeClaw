"""Shared dashboard layout with sidebar navigation."""

from fasthtml.common import *
from monsterui.all import *


def DashboardNav(user, active="overview"):
    """Sidebar navigation for dashboard pages."""
    items = [
        ("overview", "Overview", "/dashboard", "layout-dashboard"),
        ("keys", "API Keys", "/dashboard/keys", "key"),
        ("agents", "Agents", "/dashboard/agents", "bot"),
        ("audit", "Audit Log", "/dashboard/audit", "scroll-text"),
        ("prefs", "Preferences", "/dashboard/prefs", "settings"),
    ]
    nav_items = []
    for key, label, href, icon in items:
        cls = "uk-active" if key == active else ""
        nav_items.append(
            Li(A(DivLAligned(UkIcon(icon, height=16), Span(label)), href=href), cls=cls)
        )
    return NavContainer(*nav_items, cls=NavT.default)


def DashboardLayout(title, *content, user=None, active="overview"):
    """Wrap dashboard content in the shared layout."""
    sidebar = Div(
        Div(
            DivLAligned(
                Img(src=user.avatar_url, style="width:32px;height:32px;border-radius:50%") if user else "",
                Div(
                    P(Strong(user.name if user else "User")),
                    P(user.github_login if user else "", cls=TextPresets.muted_sm),
                ),
            ),
            cls="space-y-2",
        ),
        Divider(),
        DashboardNav(user, active),
        Div(
            A(DivLAligned(UkIcon("log-out", height=16), Span("Sign out")), href="/logout"),
            cls="mt-6",
        ),
        cls="space-y-4",
        style="width:220px; min-width:220px; padding:24px; border-right:1px solid var(--border, #e5e7eb);",
    )
    main_content = Div(
        H2(title),
        *content,
        cls="space-y-6",
        style="flex:1; padding:24px; max-width:900px;",
    )
    return Div(sidebar, main_content, style="display:flex; min-height:100vh;")
