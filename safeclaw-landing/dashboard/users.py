"""Admin user management pages."""

from fasthtml.common import *
from monsterui.all import *


def _role_badges(user, env_admins: set[str]):
    """Return role badge(s) for a user row."""
    badges = []
    if user.is_admin:
        badges.append(Label("Admin", cls=LabelT.primary))
        if user.github_login in env_admins:
            badges.append(Label("env", cls=LabelT.secondary))
    else:
        badges.append(Span("User", cls=TextPresets.muted_sm))
    return Span(*badges, style="display:flex;gap:4px;align-items:center;")


def _status_badge(user):
    """Return status badge for a user."""
    if user.is_disabled:
        return Label("Disabled", cls=LabelT.destructive)
    return Label("Active", cls=LabelT.primary)


def _initials(name: str) -> str:
    """Get initials from a name."""
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper() if name else "??"


def UserStatsBar(total: int, admin_count: int, disabled_count: int):
    """Stats bar at the top of the users page."""
    return Grid(
        Card(
            P("Total Users", cls=TextPresets.muted_sm),
            H3(str(total)),
        ),
        Card(
            P("Admins", cls=TextPresets.muted_sm),
            H3(str(admin_count)),
        ),
        Card(
            P("Disabled", cls=TextPresets.muted_sm),
            H3(str(disabled_count)),
        ),
        cols=3,
    )


def UserTable(all_users, current_user, env_admins: set[str], csrf_token=""):
    """Table of all users with management actions."""
    if not all_users:
        return P("No users registered.", cls=TextPresets.muted_sm)

    rows = []
    for u in all_users:
        is_self = u.id == current_user.id
        is_env = u.github_login in env_admins
        row_style = "opacity:0.5;" if u.is_disabled else ""

        # Build action buttons
        actions = [
            A("View →", href=f"/dashboard/users/{u.id}",
              style="color:#60a5fa;font-size:0.8rem;text-decoration:none;"),
        ]
        if not is_self:
            if u.is_admin and not is_env:
                actions.append(
                    Form(
                        Input(type="hidden", name="_csrf_token", value=csrf_token),
                        Button("Demote", cls=ButtonT.primary + " " + ButtonT.xs, type="submit"),
                        hx_post=f"/dashboard/users/{u.id}/demote",
                        hx_target="#user-list", hx_swap="innerHTML",
                        style="display:inline;",
                    )
                )
            elif not u.is_admin:
                actions.append(
                    Form(
                        Input(type="hidden", name="_csrf_token", value=csrf_token),
                        Button("Promote", cls=ButtonT.primary + " " + ButtonT.xs, type="submit"),
                        hx_post=f"/dashboard/users/{u.id}/promote",
                        hx_target="#user-list", hx_swap="innerHTML",
                        style="display:inline;",
                    )
                )
            if u.is_disabled:
                actions.append(
                    Form(
                        Input(type="hidden", name="_csrf_token", value=csrf_token),
                        Button("Enable", cls=ButtonT.primary + " " + ButtonT.xs, type="submit"),
                        hx_post=f"/dashboard/users/{u.id}/enable",
                        hx_target="#user-list", hx_swap="innerHTML",
                        style="display:inline;",
                    )
                )
            else:
                actions.append(
                    Form(
                        Input(type="hidden", name="_csrf_token", value=csrf_token),
                        Button("Disable", cls=ButtonT.destructive + " " + ButtonT.xs, type="submit"),
                        hx_post=f"/dashboard/users/{u.id}/disable",
                        hx_target="#user-list", hx_swap="innerHTML",
                        hx_confirm="Disable this user? Their API keys will be revoked.",
                        style="display:inline;",
                    )
                )

        last_login = u.last_login[:10] if u.last_login else "—"

        rows.append(Tr(
            Td(
                DivLAligned(
                    Img(src=u.avatar_url, style="width:28px;height:28px;border-radius:50%;") if u.avatar_url else Span(_initials(u.name)),
                    Div(
                        Span(Strong(u.name)),
                        Br(),
                        Span(u.github_login, cls=TextPresets.muted_sm),
                    ),
                ),
            ),
            Td(_role_badges(u, env_admins)),
            Td(_status_badge(u)),
            Td(last_login),
            Td(DivLAligned(*actions, cls="gap-2")),
            style=row_style,
        ))

    return Table(
        Thead(Tr(Th("User"), Th("Role"), Th("Status"), Th("Last Login"), Th("Actions"))),
        Tbody(*rows),
        cls=(TableT.divider, TableT.hover, TableT.sm),
    )


def UsersPageContent(all_users, current_user, env_admins: set[str], csrf_token=""):
    """Full users page content."""
    total = len(all_users)
    admin_count = sum(1 for u in all_users if u.is_admin or u.github_login in env_admins)
    disabled_count = sum(1 for u in all_users if u.is_disabled)
    return (
        UserStatsBar(total, admin_count, disabled_count),
        Card(
            H3("All Users"),
            P("Manage SafeClaw users, roles, and access.", cls=TextPresets.muted_sm),
            Divider(),
            Div(UserTable(all_users, current_user, env_admins, csrf_token), id="user-list"),
        ),
    )
