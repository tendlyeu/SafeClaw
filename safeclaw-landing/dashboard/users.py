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


def UserDetailHeader(target, current_user, env_admins: set[str], csrf_token=""):
    """Header card with user info and action buttons."""
    is_self = target.id == current_user.id
    is_env = target.github_login in env_admins

    actions = []
    if not is_self:
        if target.is_admin and not is_env:
            actions.append(
                Form(
                    Input(type="hidden", name="_csrf_token", value=csrf_token),
                    Button("Demote", cls=ButtonT.primary, type="submit"),
                    hx_post=f"/dashboard/users/{target.id}/demote",
                    hx_target="#user-detail-header", hx_swap="innerHTML",
                    style="display:inline;",
                )
            )
        elif not target.is_admin:
            actions.append(
                Form(
                    Input(type="hidden", name="_csrf_token", value=csrf_token),
                    Button("Promote to Admin", cls=ButtonT.primary, type="submit"),
                    hx_post=f"/dashboard/users/{target.id}/promote",
                    hx_target="#user-detail-header", hx_swap="innerHTML",
                    style="display:inline;",
                )
            )
        if target.is_disabled:
            actions.append(
                Form(
                    Input(type="hidden", name="_csrf_token", value=csrf_token),
                    Button("Enable User", cls=ButtonT.primary, type="submit"),
                    hx_post=f"/dashboard/users/{target.id}/enable",
                    hx_target="#user-detail-header", hx_swap="innerHTML",
                    style="display:inline;",
                )
            )
        else:
            actions.append(
                Form(
                    Input(type="hidden", name="_csrf_token", value=csrf_token),
                    Button("Disable User", cls=ButtonT.destructive, type="submit"),
                    hx_post=f"/dashboard/users/{target.id}/disable",
                    hx_target="#user-detail-header", hx_swap="innerHTML",
                    hx_confirm="Disable this user? Their API keys will be revoked.",
                    style="display:inline;",
                )
            )

    joined = target.created_at[:10] if target.created_at else "—"
    last_login = target.last_login[:10] if target.last_login else "—"

    return Card(
        DivLAligned(
            Img(src=target.avatar_url, style="width:48px;height:48px;border-radius:50%;") if target.avatar_url else "",
            Div(
                H3(target.name),
                P(f"{target.github_login} · Joined {joined} · Last login {last_login}",
                  cls=TextPresets.muted_sm),
            ),
            style="flex:1;",
        ),
        DivLAligned(*actions, cls="gap-2") if actions else "",
    )


def UserDetailTabs(target_id: int, active_tab="prefs"):
    """Tab navigation for user detail sub-views."""
    tabs = [
        ("prefs", "Preferences", f"/dashboard/users/{target_id}/tab/prefs"),
        ("keys", "API Keys", f"/dashboard/users/{target_id}/tab/keys"),
        ("audit", "Audit Log", f"/dashboard/users/{target_id}/tab/audit"),
    ]
    items = []
    for key, label, url in tabs:
        cls = "uk-active" if key == active_tab else ""
        items.append(
            Li(A(label, hx_get=url, hx_target="#user-tab-content", hx_swap="innerHTML",
                 hx_push_url="false", style="cursor:pointer;"), cls=cls)
        )
    return Ul(*items, cls="uk-tab")


def UserPrefsTab(target, csrf_token=""):
    """Editable preferences form for a target user."""
    return Form(
        Input(type="hidden", name="_csrf_token", value=csrf_token),
        Grid(
            Div(
                FormLabel("Autonomy Level"),
                Select(
                    Option("Cautious", value="cautious", selected=target.autonomy_level == "cautious"),
                    Option("Moderate", value="moderate", selected=target.autonomy_level == "moderate"),
                    Option("Autonomous", value="autonomous", selected=target.autonomy_level == "autonomous"),
                    name="autonomy_level", cls="uk-select",
                ),
                cls="space-y-1",
            ),
            Div(
                FormLabel("Max Files per Commit"),
                Input(type="number", name="max_files_per_commit",
                      value=str(target.max_files_per_commit), min="1", max="100",
                      cls="uk-input"),
                cls="space-y-1",
            ),
            cols=2,
        ),
        Divider(),
        Div(
            H4("Confirmations"),
            LabelCheckboxX("Before delete", id="confirm_before_delete",
                           name="confirm_before_delete",
                           checked=bool(target.confirm_before_delete)),
            LabelCheckboxX("Before push", id="confirm_before_push",
                           name="confirm_before_push",
                           checked=bool(target.confirm_before_push)),
            LabelCheckboxX("Before send", id="confirm_before_send",
                           name="confirm_before_send",
                           checked=bool(target.confirm_before_send)),
            cls="space-y-2",
        ),
        Divider(),
        LabelCheckboxX("Audit logging", id="audit_logging",
                       name="audit_logging",
                       checked=bool(target.audit_logging)),
        Divider(),
        Button("Save Changes", cls=ButtonT.primary, type="submit"),
        Div(id="user-prefs-status"),
        hx_post=f"/dashboard/users/{target.id}/prefs",
        hx_target="#user-prefs-status",
        hx_swap="innerHTML",
        cls="space-y-4",
    )


def UserKeysTab(target, keys_list, csrf_token=""):
    """API keys table for a target user (admin view — revoke only, no create)."""
    if not keys_list:
        return P("No API keys.", cls=TextPresets.muted_sm)

    rows = []
    for k in keys_list:
        status = Label("Active", cls=LabelT.primary) if k.is_active else Label("Revoked", cls=LabelT.destructive)
        revoke_btn = (
            Form(
                Input(type="hidden", name="_csrf_token", value=csrf_token),
                Button("Revoke", cls=ButtonT.destructive + " " + ButtonT.xs, type="submit"),
                hx_post=f"/dashboard/users/{target.id}/keys/{k.id}/revoke",
                hx_target="#user-tab-content", hx_swap="innerHTML",
                hx_confirm="Revoke this key?",
                style="display:inline;",
            )
            if k.is_active else Span("—", cls=TextPresets.muted_sm)
        )
        rows.append(Tr(
            Td(k.label),
            Td(Code(k.key_id + "…")),
            Td(k.scope),
            Td(k.created_at[:10] if k.created_at else "—"),
            Td(status),
            Td(revoke_btn),
        ))

    return Table(
        Thead(Tr(Th("Label"), Th("Key ID"), Th("Scope"), Th("Created"), Th("Status"), Th(""))),
        Tbody(*rows),
        cls=(TableT.divider, TableT.hover, TableT.sm),
    )


def UserAuditTab(audit_rows):
    """Audit log entries for a target user."""
    from dashboard.audit import AuditTable
    return AuditTable(audit_rows)


def UserDetailContent(target, current_user, env_admins, key_count, decision_count, block_count, csrf_token=""):
    """Full user detail page content."""
    return (
        A("← All Users", href="/dashboard/users",
          style="font-size:0.85rem;"),
        Div(UserDetailHeader(target, current_user, env_admins, csrf_token), id="user-detail-header"),
        Grid(
            Card(P("API Keys", cls=TextPresets.muted_sm), H4(str(key_count))),
            Card(P("Decisions (30d)", cls=TextPresets.muted_sm), H4(str(decision_count))),
            Card(P("Blocked (30d)", cls=TextPresets.muted_sm), H4(str(block_count))),
            cols=3,
        ),
        Card(
            UserDetailTabs(target.id, active_tab="prefs"),
            Div(UserPrefsTab(target, csrf_token), id="user-tab-content"),
        ),
    )
