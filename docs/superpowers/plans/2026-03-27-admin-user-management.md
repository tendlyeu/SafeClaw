# Admin User Management — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-user admin capabilities to the SafeClaw landing dashboard — user list, user detail drill-down, combined audit view, and soft disable.

**Architecture:** Two new fields on the User model (`is_admin`, `is_disabled`), auth helpers that check env var + DB + first-user fallback, a new `dashboard/users.py` UI component file, and routes in `main.py`. The existing audit page gets an admin-only user filter. All admin routes are protected by a `require_admin` check.

**Tech Stack:** Python, FastHTML, MonsterUI, fastlite (SQLite), HTMX

---

## Task 1: #254 — Add `is_admin` and `is_disabled` fields to User model

**Files:**
- Modify: `safeclaw-landing/db.py`

- [ ] **Step 1: Add fields to User class**

In `safeclaw-landing/db.py`, add two fields to the `User` class after `audit_logging`:

```python
class User:
    id: int
    github_id: int
    github_login: str
    name: str
    avatar_url: str
    email: str
    created_at: str
    last_login: str
    onboarded: bool = False
    autonomy_level: str = "moderate"
    mistral_api_key: str = ""
    confirm_before_delete: bool = True
    confirm_before_push: bool = True
    confirm_before_send: bool = True
    max_files_per_commit: int = 10
    self_hosted: bool = False
    service_url: str = ""
    admin_password: str = ""
    audit_logging: bool = True
    is_admin: bool = False
    is_disabled: bool = False
```

No other changes needed — `db.create(User, pk="id", transform=True)` on line 77 handles the schema migration automatically.

- [ ] **Step 2: Verify the app starts without errors**

```bash
cd safeclaw-landing && python -c "from db import users; print('OK:', len(users()))"
```

Expected: `OK: <number>` (no migration errors)

- [ ] **Step 3: Commit**

```bash
git add safeclaw-landing/db.py
git commit -m "feat(#254): add is_admin and is_disabled fields to User model"
```

---

## Task 2: #255 — Add admin auth helpers and disabled user check

**Files:**
- Modify: `safeclaw-landing/auth.py`
- Modify: `safeclaw-landing/main.py`

- [ ] **Step 1: Add admin helpers to auth.py**

Replace the entire `safeclaw-landing/auth.py` with:

```python
"""GitHub OAuth authentication for safeclaw-landing."""

import hmac
import os

from fasthtml.common import *
from fasthtml.oauth import GitHubAppClient

from db import users

# GitHub OAuth config — set these env vars
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

# Only create client if credentials are configured
github_client = (
    GitHubAppClient(GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET)
    if GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET
    else None
)


def _get_env_admins() -> set[str]:
    """Parse SAFECLAW_ADMINS env var into a set of GitHub logins."""
    raw = os.environ.get("SAFECLAW_ADMINS", "")
    return {a.strip() for a in raw.split(",") if a.strip()}


def is_env_admin(user) -> bool:
    """Check if user is an admin via the SAFECLAW_ADMINS env var."""
    return user.github_login in _get_env_admins()


def is_user_admin(user) -> bool:
    """Check if user is an admin (env var or DB field)."""
    return bool(user.is_admin) or is_env_admin(user)


def require_admin(user):
    """Return a 403 Response if user is not an admin, else None."""
    if not is_user_admin(user):
        return Response("Admin access required.", status_code=403)
    return None


def sync_admin_on_login(user) -> None:
    """Sync env var admin status to DB on login. Apply first-user fallback."""
    changed = False
    # Env var admins always get is_admin=True in DB
    if is_env_admin(user) and not user.is_admin:
        user.is_admin = True
        changed = True
    # First-user fallback: if no admins exist, first user becomes admin
    if not user.is_admin:
        env_admins = _get_env_admins()
        if not env_admins:
            existing_admins = users(where="is_admin = 1")
            if not existing_admins:
                user.is_admin = True
                changed = True
    if changed:
        users.update(user)


def get_current_user(sess):
    """Get the currently logged-in user from session, or None."""
    user_id = sess.get("auth")
    if not user_id:
        return None
    try:
        return users[user_id]
    except Exception:
        return None


async def user_auth_before(req, sess):
    """Beforeware: protect /dashboard/* routes and verify CSRF on POST (#39)."""
    path = req.url.path
    if not path.startswith("/dashboard"):
        return  # Public routes — allow
    user = get_current_user(sess)
    if not user:
        return RedirectResponse("/login", status_code=303)

    # Disabled users cannot access the dashboard
    if user.is_disabled:
        from monsterui.all import Theme as MUITheme
        return (
            Title("Account Disabled — SafeClaw"),
            *MUITheme.blue.headers(mode='dark'),
            Div(
                Div(
                    H2("Account Disabled"),
                    P("Your account has been disabled by an administrator. "
                      "Contact your team admin to regain access."),
                    A("Back to home", href="/"),
                    cls="space-y-4",
                    style="max-width:400px; margin:100px auto; text-align:center; color:#e5e5e5;",
                ),
                style="background:#0a0a0a; min-height:100vh;",
            ),
        )

    req.scope["user"] = user

    # CSRF verification for all dashboard POST requests (#39)
    if req.method == "POST":
        form = await req.form()
        token = form.get("_csrf_token", "")
        expected = sess.get("_csrf_token", "")
        if not expected or not token or not hmac.compare_digest(expected, token):
            return Response("CSRF token missing or invalid.", status_code=403)
```

- [ ] **Step 2: Add `sync_admin_on_login` call to auth_callback in main.py**

In `safeclaw-landing/main.py`, find the `auth_callback` function (around line 1762). After `user = upsert_user(...)` and before `sess["auth"] = user.id`, add the sync call:

```python
@rt("/auth/callback")
def auth_callback(req, sess, code: str = "", state: str = ""):
    if not github_client or not code:
        return RedirectResponse("/", status_code=303)
    if state != sess.pop("oauth_state", ""):
        return RedirectResponse("/login", status_code=303)
    redir = redir_url(req, "/auth/callback")
    try:
        info = github_client.retr_info(code, redir)
    except Exception:
        return RedirectResponse("/login", status_code=303)
    github_id = info.get("id")
    if not github_id:
        return RedirectResponse("/login", status_code=303)
    user = upsert_user(
        github_id=github_id,
        github_login=info.get("login", ""),
        name=info.get("name", info.get("login", "")),
        avatar_url=info.get("avatar_url", ""),
        email=info.get("email", ""),
    )
    sync_admin_on_login(user)
    sess["auth"] = user.id
    if not user.onboarded:
        return RedirectResponse("/dashboard/onboard", status_code=303)
    return RedirectResponse("/dashboard", status_code=303)
```

Also add `sync_admin_on_login` to the import from auth at the top of the dashboard routes section. Find the existing import line `from auth import github_client, user_auth_before, get_current_user` and add `sync_admin_on_login, is_user_admin, is_env_admin, require_admin`:

```python
from auth import github_client, user_auth_before, get_current_user, sync_admin_on_login, is_user_admin, is_env_admin, require_admin
```

- [ ] **Step 3: Verify the app starts**

```bash
cd safeclaw-landing && python -c "from auth import is_user_admin, is_env_admin, require_admin, sync_admin_on_login; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add safeclaw-landing/auth.py safeclaw-landing/main.py
git commit -m "feat(#255): add admin auth helpers, disabled user check, env admin sync on login"
```

---

## Task 3: #256 — Add Users page with user list and management actions

**Files:**
- Create: `safeclaw-landing/dashboard/users.py`
- Modify: `safeclaw-landing/dashboard/layout.py`
- Modify: `safeclaw-landing/main.py`

- [ ] **Step 1: Update sidebar navigation for admins**

In `safeclaw-landing/dashboard/layout.py`, modify `DashboardNav` to accept an `is_admin` parameter and conditionally show the Users nav item:

```python
"""Shared dashboard layout with sidebar navigation."""

from fasthtml.common import *
from monsterui.all import *


def DashboardNav(user, active="overview", is_admin=False):
    """Sidebar navigation for dashboard pages."""
    items = [
        ("overview", "Overview", "/dashboard", "layout-dashboard"),
        ("keys", "API Keys", "/dashboard/keys", "key"),
        ("agents", "Agents", "/dashboard/agents", "bot"),
        ("audit", "Audit Log", "/dashboard/audit", "scroll-text"),
    ]
    if is_admin:
        items.append(("users", "Users", "/dashboard/users", "users"))
    items.append(("prefs", "Preferences", "/dashboard/prefs", "settings"))
    nav_items = []
    for key, label, href, icon in items:
        cls = "uk-active" if key == active else ""
        nav_items.append(
            Li(A(DivLAligned(UkIcon(icon, height=16), Span(label)), href=href), cls=cls)
        )
    return NavContainer(*nav_items, cls=NavT.default)


def DashboardLayout(title, *content, user=None, active="overview", is_admin=False):
    """Wrap dashboard content in the shared layout."""
    # Force dark theme consistently across sidebar and content
    dark_override = Style("""
        :root, html { color-scheme: dark !important; }
        html { background: #0a0a0a !important; color: #e5e5e5 !important; }
        body { background: #0a0a0a !important; color: #e5e5e5 !important; }
        .uk-card, .uk-card-default { background: #1a1a1a !important; border: 1px solid #2a2a2a !important; }
        .uk-table th { color: #e5e5e5 !important; }
        pre, code { background: #111 !important; }
        .uk-input, .uk-select, .uk-textarea { background: #1a1a1a !important; color: #e5e5e5 !important; border-color: #333 !important; }
        .uk-divider, hr { border-color: #2a2a2a !important; }
        a:not(.btn):not([class*="ButtonT"]) { color: #60a5fa !important; }
        h1, h2, h3, h4, h5, h6 { color: #f5f5f5 !important; }
    """)
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
        DashboardNav(user, active, is_admin=is_admin),
        Div(
            Form(
                Button(DivLAligned(UkIcon("log-out", height=16), Span("Sign out")),
                       type="submit", style="background:none;border:none;color:inherit;cursor:pointer;padding:0;"),
                action="/logout", method="post",
            ),
            cls="mt-6",
        ),
        cls="space-y-4",
        style="width:220px; min-width:220px; padding:24px; border-right:1px solid #2a2a2a;",
    )
    main_content = Div(
        H2(title),
        *content,
        cls="space-y-6",
        style="flex:1; padding:24px; max-width:900px;",
    )
    return Div(dark_override, sidebar, main_content, style="display:flex; min-height:100vh;")
```

- [ ] **Step 2: Update all existing DashboardLayout calls in main.py**

Every call to `DashboardLayout` in `main.py` needs to pass `is_admin=is_user_admin(user)`. There are calls in: `dashboard`, `dashboard_keys`, `dashboard_onboard`, `onboard_step1`, `dashboard_agents`, `dashboard_prefs`, `dashboard_audit`.

For each one, add `is_admin=is_user_admin(user)` to the `DashboardLayout(...)` call. For example, the `/dashboard` route becomes:

```python
@rt("/dashboard")
def dashboard(req, sess):
    user = req.scope.get("user")
    key_count = len(api_keys(where="user_id = ? AND is_active = 1", where_args=[user.id]))
    return (
        Title("Dashboard — SafeClaw"),
        *MUITheme.blue.headers(mode='dark'),
        DashboardLayout("Overview",
                        *OverviewContent(user, key_count, has_mistral_key=bool(user.mistral_api_key)),
                        user=user, active="overview", is_admin=is_user_admin(user)),
    )
```

Apply the same pattern to all other routes that call `DashboardLayout`.

- [ ] **Step 3: Create `dashboard/users.py` with user list components**

Create `safeclaw-landing/dashboard/users.py`:

```python
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

        # Format last login
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
```

- [ ] **Step 4: Add user list route and action routes to main.py**

Add these routes to `safeclaw-landing/main.py`, after the audit routes section (before the `# ── Mount SafeClaw Service ──` comment):

```python
# ── Admin: User Management Routes ──

from dashboard.users import UsersPageContent, UserTable
from auth import is_env_admin, _get_env_admins


@rt("/dashboard/users")
def dashboard_users(req, sess):
    user = req.scope.get("user")
    if err := require_admin(user):
        return err
    token = _generate_csrf_token(sess)
    all_users = users(order_by="id")
    env_admins = _get_env_admins()
    return (
        Title("Users — SafeClaw"),
        *MUITheme.blue.headers(mode='dark'),
        DashboardLayout("Users",
                        *UsersPageContent(all_users, user, env_admins, csrf_token=token),
                        user=user, active="users", is_admin=True),
    )


@rt("/dashboard/users/{user_id}/promote", methods=["POST"])
def promote_user(req, sess, user_id: int, _csrf_token: str = ""):
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return P("User not found.", style="color:#f87171;")
    target.is_admin = True
    users.update(target)
    token = _generate_csrf_token(sess)
    env_admins = _get_env_admins()
    return UserTable(users(order_by="id"), admin, env_admins, csrf_token=token)


@rt("/dashboard/users/{user_id}/demote", methods=["POST"])
def demote_user(req, sess, user_id: int, _csrf_token: str = ""):
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return P("User not found.", style="color:#f87171;")
    # Cannot demote self
    if target.id == admin.id:
        return P("Cannot demote yourself.", style="color:#f87171;")
    # Cannot demote env var admins
    if is_env_admin(target):
        return P("Cannot demote env var admins.", style="color:#f87171;")
    target.is_admin = False
    users.update(target)
    token = _generate_csrf_token(sess)
    env_admins = _get_env_admins()
    return UserTable(users(order_by="id"), admin, env_admins, csrf_token=token)


@rt("/dashboard/users/{user_id}/disable", methods=["POST"])
def disable_user(req, sess, user_id: int, _csrf_token: str = ""):
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return P("User not found.", style="color:#f87171;")
    if target.id == admin.id:
        return P("Cannot disable yourself.", style="color:#f87171;")
    target.is_disabled = True
    users.update(target)
    # Revoke all active API keys (#259)
    target_keys = api_keys(where="user_id = ? AND is_active = 1", where_args=[target.id])
    for k in target_keys:
        k.is_active = False
        api_keys.update(k)
    token = _generate_csrf_token(sess)
    env_admins = _get_env_admins()
    return UserTable(users(order_by="id"), admin, env_admins, csrf_token=token)


@rt("/dashboard/users/{user_id}/enable", methods=["POST"])
def enable_user(req, sess, user_id: int, _csrf_token: str = ""):
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return P("User not found.", style="color:#f87171;")
    target.is_disabled = False
    users.update(target)
    token = _generate_csrf_token(sess)
    env_admins = _get_env_admins()
    return UserTable(users(order_by="id"), admin, env_admins, csrf_token=token)
```

- [ ] **Step 5: Verify the app starts and routes are registered**

```bash
cd safeclaw-landing && python -c "
from db import users
from auth import is_user_admin, _get_env_admins
from dashboard.users import UsersPageContent, UserTable
print('All imports OK')
"
```

- [ ] **Step 6: Commit**

```bash
git add safeclaw-landing/dashboard/users.py safeclaw-landing/dashboard/layout.py safeclaw-landing/main.py
git commit -m "feat(#256): add Users page with user list, promote/demote/disable/enable actions"
```

---

## Task 4: #257 — Add user detail page with tabbed sub-views

**Files:**
- Modify: `safeclaw-landing/dashboard/users.py`
- Modify: `safeclaw-landing/main.py`

- [ ] **Step 1: Add user detail components to `dashboard/users.py`**

Append these functions to the end of `safeclaw-landing/dashboard/users.py`:

```python
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
```

- [ ] **Step 2: Add user detail routes to main.py**

Add these routes in `main.py` after the user list routes (inside the `# ── Admin: User Management Routes ──` section):

```python
from dashboard.users import UserDetailContent, UserPrefsTab, UserKeysTab, UserAuditTab


@rt("/dashboard/users/{user_id}")
def dashboard_user_detail(req, sess, user_id: int):
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return RedirectResponse("/dashboard/users", status_code=303)
    token = _generate_csrf_token(sess)
    env_admins = _get_env_admins()
    key_count = len(api_keys(where="user_id = ? AND is_active = 1", where_args=[target.id]))
    # Count decisions and blocks in last 30 days
    from datetime import timedelta
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    decision_count = len(audit_log(where="user_id = ? AND timestamp > ?",
                                   where_args=[target.id, thirty_days_ago]))
    block_count = len(audit_log(where="user_id = ? AND timestamp > ? AND decision = ?",
                                where_args=[target.id, thirty_days_ago, "blocked"]))
    return (
        Title(f"{target.name} — Users — SafeClaw"),
        *MUITheme.blue.headers(mode='dark'),
        DashboardLayout(f"User: {target.name}",
                        *UserDetailContent(target, admin, env_admins, key_count,
                                           decision_count, block_count, csrf_token=token),
                        user=admin, active="users", is_admin=True),
    )


@rt("/dashboard/users/{user_id}/tab/prefs")
def user_tab_prefs(req, sess, user_id: int):
    """HTMX partial: preferences tab."""
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return P("User not found.", style="color:#f87171;")
    token = _generate_csrf_token(sess)
    return UserPrefsTab(target, csrf_token=token)


@rt("/dashboard/users/{user_id}/tab/keys")
def user_tab_keys(req, sess, user_id: int):
    """HTMX partial: API keys tab."""
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return P("User not found.", style="color:#f87171;")
    token = _generate_csrf_token(sess)
    keys_list = api_keys(where="user_id = ?", where_args=[target.id], order_by="-id")
    return UserKeysTab(target, keys_list, csrf_token=token)


@rt("/dashboard/users/{user_id}/tab/audit")
def user_tab_audit(req, sess, user_id: int):
    """HTMX partial: audit log tab."""
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return P("User not found.", style="color:#f87171;")
    rows = audit_log(where="user_id = ?", where_args=[target.id], order_by="-id", limit=50)
    return UserAuditTab(rows)


@rt("/dashboard/users/{user_id}/prefs", methods=["POST"])
def save_user_prefs(req, sess, user_id: int,
                    autonomy_level: str = "moderate",
                    confirm_before_delete: str = "",
                    confirm_before_push: str = "",
                    confirm_before_send: str = "",
                    max_files_per_commit: int = 10,
                    audit_logging: str = "",
                    _csrf_token: str = ""):
    """Save preferences for a target user (admin only)."""
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return P("User not found.", style="color:#f87171;")
    if autonomy_level not in _VALID_AUTONOMY_LEVELS:
        return P("Invalid autonomy level.", style="color:#f87171;")
    if max_files_per_commit < 1 or max_files_per_commit > 100:
        return P("Max files per commit must be between 1 and 100.", style="color:#f87171;")
    target.autonomy_level = autonomy_level
    target.confirm_before_delete = confirm_before_delete == "on"
    target.confirm_before_push = confirm_before_push == "on"
    target.confirm_before_send = confirm_before_send == "on"
    target.max_files_per_commit = max_files_per_commit
    target.audit_logging = audit_logging == "on"
    users.update(target)
    return P("Preferences saved.", style="color:#4ade80;")


@rt("/dashboard/users/{user_id}/keys/{key_pk}/revoke", methods=["POST"])
def revoke_user_key(req, sess, user_id: int, key_pk: int, _csrf_token: str = ""):
    """Revoke another user's API key (admin only)."""
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
        key = api_keys[key_pk]
    except Exception:
        return P("Not found.", style="color:#f87171;")
    if key.user_id != target.id:
        return P("Key does not belong to this user.", style="color:#f87171;")
    key.is_active = False
    api_keys.update(key)
    token = _generate_csrf_token(sess)
    keys_list = api_keys(where="user_id = ?", where_args=[target.id], order_by="-id")
    return UserKeysTab(target, keys_list, csrf_token=token)
```

- [ ] **Step 3: Verify imports and app start**

```bash
cd safeclaw-landing && python -c "
from dashboard.users import UserDetailContent, UserPrefsTab, UserKeysTab, UserAuditTab
print('All imports OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add safeclaw-landing/dashboard/users.py safeclaw-landing/main.py
git commit -m "feat(#257): add user detail page with tabbed prefs/keys/audit sub-views"
```

---

## Task 5: #258 — Add admin user filter to audit log page

**Files:**
- Modify: `safeclaw-landing/dashboard/audit.py`
- Modify: `safeclaw-landing/main.py`

- [ ] **Step 1: Update `AuditFilters` and `AuditTable` for admin user filter**

Replace `safeclaw-landing/dashboard/audit.py` with:

```python
"""Audit log dashboard page."""

from fasthtml.common import *
from monsterui.all import *
from fasthtml.components import Select as RawSelect


def _decision_badge(decision: str):
    """Color-coded badge for allowed/blocked."""
    if decision == "blocked":
        return Label(decision, cls=LabelT.destructive)
    return Label(decision, cls=LabelT.secondary)


def _risk_badge(risk_level: str):
    """Color-coded badge for risk level."""
    colors = {
        "critical": LabelT.destructive,
        "high": LabelT.destructive,
        "medium": LabelT.primary,
    }
    return Label(risk_level, cls=colors.get(risk_level, LabelT.secondary))


def AuditTable(rows, show_user_column=False, disabled_logins=None):
    """Render audit log rows as a table."""
    if disabled_logins is None:
        disabled_logins = set()
    if not rows:
        return Card(
            DivCentered(
                UkIcon("file-search", height=32),
                H4("No audit log entries yet"),
                P("Governance decisions will appear here once SafeClaw evaluates tool calls.",
                  cls=TextPresets.muted_sm),
                P("Make sure audit logging is enabled in ",
                  A("Preferences", href="/dashboard/prefs"), ".",
                  cls=TextPresets.muted_sm),
                cls="space-y-2",
            ),
        )

    header = ["Time"]
    if show_user_column:
        header.append("User")
    header.extend(["Tool", "Decision", "Risk", "Reason", "Latency"])

    body = []
    for r in rows:
        ts = r.timestamp[:19].replace("T", " ") if r.timestamp else ""
        latency = f"{r.elapsed_ms:.0f}ms" if r.elapsed_ms else ""
        reason = (r.reason[:80] + "...") if r.reason and len(r.reason) > 80 else (r.reason or "")
        row_data = [ts]
        if show_user_column:
            login = getattr(r, "_github_login", "")
            style = "text-decoration:line-through;color:#888;" if login in disabled_logins else ""
            row_data.append(Span(login, style=style) if login else "—")
        row_data.extend([r.tool_name, _decision_badge(r.decision),
                         _risk_badge(r.risk_level), reason, latency])
        body.append(row_data)

    return Table(
        Thead(Tr(*[Th(h) for h in header])),
        Tbody(*[Tr(*[Td(c) for c in row]) for row in body]),
        cls=(TableT.hover, TableT.sm, TableT.striped),
    )


def AuditFilters(current_filter="all", session_id="", is_admin=False,
                 all_logins=None, current_user_filter=""):
    """Filter bar for the audit log."""
    admin_section = ""
    if is_admin and all_logins:
        options = [Option("All users", value="", selected=not current_user_filter)]
        for login in sorted(all_logins):
            options.append(Option(login, value=login, selected=current_user_filter == login))
        admin_section = Div(
            Div(
                FormLabel("User", _for="user_filter"),
                RawSelect(*options, name="user_filter", id="user_filter", cls="uk-select"),
                cls="space-y-2",
            ),
            style="border-left:1px solid #2a2a2a; padding-left:12px;",
        )

    return Form(
        DivLAligned(
            Div(
                FormLabel("Filter", _for="filter"),
                RawSelect(
                    Option("All decisions", value="all", selected=current_filter == "all"),
                    Option("Blocked only", value="blocked", selected=current_filter == "blocked"),
                    Option("Allowed only", value="allowed", selected=current_filter == "allowed"),
                    name="filter", id="filter", cls="uk-select",
                ),
                cls="space-y-2",
            ),
            LabelInput(
                "Session ID",
                id="session_id",
                value=session_id,
                placeholder="Optional",
            ),
            admin_section,
            Button("Apply", cls=ButtonT.primary, type="submit"),
            Span(Loading(cls=LoadingT.spinner), cls="htmx-indicator", id="audit-spinner"),
            cls="gap-4 items-end",
        ),
        hx_get="/dashboard/audit/results",
        hx_target="#audit-results",
        hx_swap="innerHTML",
        hx_indicator="#audit-spinner",
        cls="space-y-4",
    )


def AuditContent(rows, current_filter="all", session_id="",
                 is_admin=False, all_logins=None, current_user_filter="",
                 show_user_column=False, disabled_logins=None):
    """Full audit page content."""
    return (
        Card(
            H3("Governance Audit Log"),
            P("All governance decisions made by SafeClaw for your API keys. ",
              "Toggle logging in ",
              A("Preferences", href="/dashboard/prefs"), ".",
              cls=TextPresets.muted_sm),
            AuditFilters(current_filter, session_id, is_admin=is_admin,
                         all_logins=all_logins, current_user_filter=current_user_filter),
        ),
        Div(AuditTable(rows, show_user_column=show_user_column,
                        disabled_logins=disabled_logins), id="audit-results"),
    )
```

- [ ] **Step 2: Update audit routes in main.py**

Replace the two audit routes in `main.py`:

```python
@rt("/dashboard/audit")
def dashboard_audit(req, sess):
    user = req.scope.get("user")
    admin = is_user_admin(user)
    if admin:
        # Show all users' audit data by default
        rows = audit_log(order_by="-id", limit=50)
        # Attach github_login to each row for the user column
        user_map = {u.id: u for u in users()}
        for r in rows:
            u = user_map.get(r.user_id)
            r._github_login = u.github_login if u else ""
        all_logins = sorted({u.github_login for u in user_map.values()})
        disabled_logins = {u.github_login for u in user_map.values() if u.is_disabled}
    else:
        rows = audit_log(where="user_id = ?", where_args=[user.id], order_by="-id", limit=50)
        all_logins = None
        disabled_logins = None
    return (
        Title("Audit Log — SafeClaw"),
        *MUITheme.blue.headers(mode='dark'),
        DashboardLayout("Audit Log",
                        *AuditContent(rows, is_admin=admin, all_logins=all_logins,
                                      show_user_column=admin, disabled_logins=disabled_logins),
                        user=user, active="audit", is_admin=admin),
    )


@rt("/dashboard/audit/results")
def audit_results(req, sess, filter: str = "all", session_id: str = "",
                  user_filter: str = ""):
    """HTMX partial: filtered audit log results."""
    user = req.scope.get("user")
    admin = is_user_admin(user)

    conditions = []
    args = []

    if admin and user_filter:
        # Filter by specific user login
        target_users = users(where="github_login = ?", where_args=[user_filter])
        if target_users:
            conditions.append("user_id = ?")
            args.append(target_users[0].id)
    elif not admin:
        # Non-admins always see only their own data
        conditions.append("user_id = ?")
        args.append(user.id)

    if filter == "blocked":
        conditions.append("decision = ?")
        args.append("blocked")
    elif filter == "allowed":
        conditions.append("decision = ?")
        args.append("allowed")
    if session_id.strip():
        conditions.append("session_id = ?")
        args.append(session_id.strip())

    where = " AND ".join(conditions) if conditions else None
    rows = audit_log(where=where, where_args=args if args else None, order_by="-id", limit=50)

    show_user_col = admin and not user_filter
    disabled_logins = set()
    if show_user_col:
        user_map = {u.id: u for u in users()}
        for r in rows:
            u = user_map.get(r.user_id)
            r._github_login = u.github_login if u else ""
        disabled_logins = {u.github_login for u in user_map.values() if u.is_disabled}

    return AuditTable(rows, show_user_column=show_user_col, disabled_logins=disabled_logins)
```

- [ ] **Step 3: Verify app starts**

```bash
cd safeclaw-landing && python -c "from dashboard.audit import AuditContent, AuditTable, AuditFilters; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add safeclaw-landing/dashboard/audit.py safeclaw-landing/main.py
git commit -m "feat(#258): add admin user filter and user column to audit log page"
```

---

## Task 6: Verify all features work end-to-end

- [ ] **Step 1: Verify all imports and app startup**

```bash
cd safeclaw-landing && python -c "
from db import users, api_keys, audit_log
from auth import is_user_admin, is_env_admin, require_admin, sync_admin_on_login, _get_env_admins
from dashboard.users import UsersPageContent, UserTable, UserDetailContent, UserPrefsTab, UserKeysTab, UserAuditTab
from dashboard.audit import AuditContent, AuditTable, AuditFilters
from dashboard.layout import DashboardLayout, DashboardNav
print('All imports OK')
# Verify User model has new fields
u = users()
if u:
    print(f'First user is_admin={u[0].is_admin}, is_disabled={u[0].is_disabled}')
else:
    print('No users in DB (OK for fresh install)')
"
```

- [ ] **Step 2: Commit any final fixes if needed**

- [ ] **Step 3: Close all tickets**

```bash
gh issue close 254 --comment "Implemented: is_admin and is_disabled fields added to User model"
gh issue close 255 --comment "Implemented: admin auth helpers, disabled user check, env admin sync"
gh issue close 256 --comment "Implemented: Users page with list, promote/demote/disable/enable"
gh issue close 257 --comment "Implemented: User detail page with prefs/keys/audit tabs"
gh issue close 258 --comment "Implemented: Admin user filter and user column in audit log"
gh issue close 259 --comment "Implemented: API keys auto-revoked when user is disabled (in #256 disable handler)"
```

---

## Execution Order

Tasks 1 → 2 → 3 → 4 → 5 → 6 (strictly sequential — each builds on the previous).
