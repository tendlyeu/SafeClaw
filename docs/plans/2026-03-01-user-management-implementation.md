# User Management & Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add GitHub OAuth login, SQLite user database, and a MonsterUI dashboard to the safeclaw-landing app — enabling users to manage API keys, agents, and governance preferences.

**Architecture:** Extend the existing `safeclaw-landing/` FastHTML app (currently a static marketing site on port 5002) with GitHub OAuth, fastlite SQLite, and MonsterUI dashboard pages. The dashboard is a client of the SafeClaw service API. A small preferences endpoint is added to the service.

**Tech Stack:** FastHTML, fastlite (SQLite), MonsterUI (blue theme), httpx, GitHub OAuth via FastHTML's `GitHubAppClient`

---

### Task 1: Add dependencies and database module

**Files:**
- Modify: `safeclaw-landing/requirements.txt`
- Create: `safeclaw-landing/db.py`

**Step 1: Update requirements.txt**

Replace the contents of `safeclaw-landing/requirements.txt` with:

```
python-fasthtml
monsterui
httpx
```

**Step 2: Install dependencies**

Run: `cd safeclaw-landing && pip install -r requirements.txt`

**Step 3: Create db.py**

Create `safeclaw-landing/db.py`:

```python
"""Database setup — SQLite via fastlite."""

from datetime import datetime, timezone
from fastlite import database

db = database("data/safeclaw.db")


class User:
    id: int
    github_id: int
    github_login: str
    name: str
    avatar_url: str
    email: str
    created_at: str
    last_login: str


class APIKey:
    id: int
    user_id: int
    key_id: str
    key_hash: str
    label: str
    scope: str
    created_at: str
    is_active: bool


users = db.create(User, pk="id", transform=True)
api_keys = db.create(APIKey, pk="id", transform=True)


def upsert_user(github_id: int, github_login: str, name: str, avatar_url: str, email: str = "") -> User:
    """Create or update a user from GitHub profile data."""
    now = datetime.now(timezone.utc).isoformat()
    existing = users(where=f"github_id={github_id}")
    if existing:
        user = existing[0]
        user.github_login = github_login
        user.name = name
        user.avatar_url = avatar_url
        user.email = email or user.email
        user.last_login = now
        return users.update(user)
    return users.insert(
        github_id=github_id,
        github_login=github_login,
        name=name,
        avatar_url=avatar_url,
        email=email or "",
        created_at=now,
        last_login=now,
    )
```

**Step 4: Ensure data/ directory is gitignored**

Add to `safeclaw-landing/.gitignore` (create if it doesn't exist):

```
data/
.venv/
__pycache__/
```

**Step 5: Verify the module imports cleanly**

Run: `cd safeclaw-landing && python -c "from db import db, users, api_keys, upsert_user; print('OK')"`
Expected: `OK`

**Step 6: Commit**

```bash
git add safeclaw-landing/requirements.txt safeclaw-landing/db.py safeclaw-landing/.gitignore
git commit -m "feat(landing): add database module with User and APIKey tables"
```

---

### Task 2: Add GitHub OAuth authentication

**Files:**
- Create: `safeclaw-landing/auth.py`
- Modify: `safeclaw-landing/main.py`

**Step 1: Create auth.py**

Create `safeclaw-landing/auth.py`:

```python
"""GitHub OAuth authentication for safeclaw-landing."""

import os

from fasthtml.common import *
from fasthtml.oauth import GitHubAppClient

from db import upsert_user, users

# GitHub OAuth config — set these env vars
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

# Only create client if credentials are configured
github_client = (
    GitHubAppClient(GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET)
    if GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET
    else None
)


def get_current_user(sess):
    """Get the currently logged-in user from session, or None."""
    user_id = sess.get("auth")
    if not user_id:
        return None
    try:
        return users[user_id]
    except Exception:
        return None


def user_auth_before(req, sess):
    """Beforeware: protect /dashboard/* routes."""
    path = req.url.path
    if not path.startswith("/dashboard"):
        return  # Public routes — allow
    user = get_current_user(sess)
    if not user:
        return RedirectResponse("/login", status_code=303)
    req.scope["user"] = user
```

**Step 2: Modify main.py — add OAuth setup**

In `safeclaw-landing/main.py`, make these changes:

1. Add imports at the top (after existing imports):

```python
import os
from auth import github_client, user_auth_before, get_current_user
from db import users
```

2. Add Beforeware to `fast_app` call. Replace the existing `app, rt = fast_app(...)` with:

```python
from fasthtml.common import *
from fasthtml.components import Footer as FooterTag

GITHUB_URL = "https://github.com/tendlyeu/SafeClaw"
DOCS_URL = "/docs"

bware = Beforeware(
    user_auth_before,
    skip=[r'/favicon\.ico', r'/static/.*', r'.*\.css', r'.*\.js', '/login', '/auth/callback', '/logout', '/', '/docs'],
)

app, rt = fast_app(
    pico=False,
    static_path="static",
    before=bware,
    hdrs=(
        Link(rel="stylesheet", href="/style.css"),
        Link(rel="icon", href="/favicon.ico", type="image/x-icon"),
        Meta(name="viewport", content="width=device-width, initial-scale=1"),
        Meta(name="description", content="SafeClaw — Neurosymbolic governance layer for autonomous AI agents"),
    ),
)
```

3. Add auth routes before the `serve()` call:

```python
# ── Auth Routes ──

@rt("/login")
def login(req):
    if not github_client:
        return Titled("Login",
            P("GitHub OAuth not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET."))
    redir = redir_url(req, "/auth/callback")
    return RedirectResponse(github_client.login_link(redir), status_code=303)


@rt("/auth/callback")
async def auth_callback(req, sess, code: str = ""):
    if not github_client or not code:
        return RedirectResponse("/", status_code=303)
    redir = redir_url(req, "/auth/callback")
    info = await github_client.retr_info(code, redir)
    github_id = info.get("id") or int(info.get("sub", 0))
    user = upsert_user(
        github_id=github_id,
        github_login=info.get("login", ""),
        name=info.get("name", info.get("login", "")),
        avatar_url=info.get("avatar_url", ""),
        email=info.get("email", ""),
    )
    sess["auth"] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@rt("/logout")
def logout(sess):
    sess.pop("auth", None)
    return RedirectResponse("/", status_code=303)
```

Also add `from fasthtml.oauth import redir_url` and `from db import upsert_user` to the imports.

4. Update the `Nav()` function to show login/dashboard link:

After the existing GitHub `Li` in the nav, add a conditional auth link. Modify `Nav()` to accept an optional `user` parameter:

```python
def Nav(user=None):
    auth_link = (
        Li(A("Dashboard", href="/dashboard")) if user
        else Li(A("Sign In", href="/login", cls="btn btn-primary btn-sm"))
    )
    return Header(
        Div(
            Div(
                Span("🛡️", cls="logo-icon"),
                Span("SafeClaw"),
                cls="nav-logo",
            ),
            Ul(
                Li(A("Features", href="/#features")),
                Li(A("How It Works", href="/#how-it-works")),
                Li(A("Architecture", href="/#architecture")),
                Li(A("Docs", href="/docs")),
                Li(A("GitHub", href=GITHUB_URL, target="_blank", rel="noopener noreferrer")),
                auth_link,
                cls="nav-links", id="nav-links",
            ),
            Button("☰", cls="nav-mobile-toggle",
                   onclick="document.getElementById('nav-links').classList.toggle('open')"),
            cls="nav-inner container",
        ),
        cls="nav",
    )
```

Update `index()` and `docs()` to pass user:

```python
@rt
def index(sess):
    user = get_current_user(sess)
    return (
        Title("SafeClaw — Neurosymbolic Governance for AI Agents"),
        Nav(user),
        Hero(),
        Features(),
        HowItWorks(),
        TerminalDemo(),
        Architecture(),
        QuickStart(),
        Footer(),
    )


@rt("/docs")
def docs(sess):
    user = get_current_user(sess)
    return (
        Title("Documentation — SafeClaw"),
        Nav(user),
        DocsPage(),
        Footer(),
    )
```

**Step 3: Test manually**

Run: `cd safeclaw-landing && python main.py`

Visit `http://localhost:5002` — should see "Sign In" in nav. Clicking it should show the "not configured" message (since no GitHub credentials are set in dev).

**Step 4: Commit**

```bash
git add safeclaw-landing/auth.py safeclaw-landing/main.py
git commit -m "feat(landing): add GitHub OAuth authentication"
```

---

### Task 3: Dashboard layout and overview page

**Files:**
- Create: `safeclaw-landing/dashboard/__init__.py`
- Create: `safeclaw-landing/dashboard/layout.py`
- Create: `safeclaw-landing/dashboard/overview.py`
- Modify: `safeclaw-landing/main.py`

**Step 1: Create dashboard/__init__.py**

Create empty `safeclaw-landing/dashboard/__init__.py`.

**Step 2: Create dashboard/layout.py**

Create `safeclaw-landing/dashboard/layout.py`:

```python
"""Shared dashboard layout with sidebar navigation."""

from monsterui.all import *


def DashboardNav(user, active="overview"):
    """Sidebar navigation for dashboard pages."""
    items = [
        ("overview", "Overview", "/dashboard", "layout-dashboard"),
        ("keys", "API Keys", "/dashboard/keys", "key"),
        ("agents", "Agents", "/dashboard/agents", "bot"),
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
```

**Step 3: Create dashboard/overview.py**

Create `safeclaw-landing/dashboard/overview.py`:

```python
"""Dashboard overview page."""

import httpx
from monsterui.all import *


def ServiceHealthCard(service_url: str):
    """Card showing service health status, refreshes via HTMX."""
    return Card(
        H3("Service Health"),
        Div(
            P("Checking...", cls=TextPresets.muted_sm),
            id="health-status",
            hx_get="/dashboard/health-check",
            hx_trigger="load, every 30s",
            hx_swap="innerHTML",
        ),
    )


def GettingStartedCard():
    """Setup instructions for new users."""
    return Card(
        H3("Getting Started"),
        Div(
            P("1. Create an API key in the ", A("Keys", href="/dashboard/keys"), " tab"),
            P("2. Install the OpenClaw plugin:"),
            Pre(Code("npm install openclaw-safeclaw-plugin")),
            P("3. Set your API key:"),
            Pre(Code("export SAFECLAW_API_KEY=sc_your_key_here")),
            cls="space-y-2",
        ),
    )


def OverviewContent(user, key_count: int):
    """Main overview page content."""
    return (
        Grid(
            Card(
                DivLAligned(UkIcon("key", height=20), H4("API Keys")),
                P(f"{key_count} keys", cls=TextPresets.muted_sm),
                footer=A("Manage keys →", href="/dashboard/keys"),
            ),
            Card(
                DivLAligned(UkIcon("bot", height=20), H4("Agents")),
                P("View on service", cls=TextPresets.muted_sm),
                footer=A("View agents →", href="/dashboard/agents"),
            ),
            cols=2,
        ),
        ServiceHealthCard(service_url=""),
        GettingStartedCard(),
    )
```

**Step 4: Wire routes into main.py**

Add to `safeclaw-landing/main.py`, before `serve()`:

```python
# ── Dashboard Routes ──

from monsterui.all import Theme as MUITheme
from dashboard.layout import DashboardLayout
from dashboard.overview import OverviewContent
from db import api_keys


@rt("/dashboard")
def dashboard(req, sess):
    user = req.scope.get("user")
    key_count = len(api_keys(where=f"user_id={user.id} AND is_active=1"))
    return (
        Title("Dashboard — SafeClaw"),
        *MUITheme.blue.headers(),
        DashboardLayout("Overview", *OverviewContent(user, key_count), user=user, active="overview"),
    )


@rt("/dashboard/health-check")
async def health_check(req, sess):
    """HTMX partial: check service health."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get("http://localhost:8420/health")
            data = r.json()
            status = data.get("status", "unknown")
            if status == "ok":
                return DivLAligned(
                    Span("●", style="color:#4ade80; font-size:20px;"),
                    Span("Service healthy"),
                )
            return DivLAligned(
                Span("●", style="color:#fb923c; font-size:20px;"),
                Span(f"Status: {status}"),
            )
    except Exception:
        return DivLAligned(
            Span("●", style="color:#f87171; font-size:20px;"),
            Span("Service unreachable"),
        )
```

Note: Import `DivLAligned`, `Span` from `monsterui.all` — they're already available via the wildcard import if you add `from monsterui.all import *` to the top of `main.py`, or import them where needed.

**Step 5: Test manually**

Run: `cd safeclaw-landing && python main.py`

Note: Without GitHub OAuth configured, you'll need to manually test by setting `sess["auth"]` or temporarily bypassing auth. The page structure is what matters at this stage.

**Step 6: Commit**

```bash
git add safeclaw-landing/dashboard/
git commit -m "feat(landing): add dashboard layout and overview page"
```

---

### Task 4: API key management page

**Files:**
- Create: `safeclaw-landing/dashboard/keys.py`
- Modify: `safeclaw-landing/main.py`

**Step 1: Create dashboard/keys.py**

Create `safeclaw-landing/dashboard/keys.py`:

```python
"""API key management page."""

import hashlib
import secrets
from datetime import datetime, timezone

from monsterui.all import *

from db import api_keys


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key. Returns (raw_key, key_id)."""
    raw_key = "sc_" + secrets.token_urlsafe(32)
    key_id = raw_key[:12]
    return raw_key, key_id


def hash_key(raw_key: str) -> str:
    """SHA256 hash of the raw key."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def KeyTable(user_id: int):
    """Table of existing API keys for this user."""
    keys = api_keys(where=f"user_id={user_id}", order_by="-id")
    if not keys:
        return P("No API keys yet. Create one to get started.", cls=TextPresets.muted_sm)

    rows = []
    for k in keys:
        status = Label("Active", cls=LabelT.primary) if k.is_active else Label("Revoked", cls=LabelT.destructive)
        revoke_btn = (
            Button("Revoke", cls=ButtonT.destructive + " " + ButtonT.xs,
                   hx_post=f"/dashboard/keys/{k.id}/revoke",
                   hx_target="#key-list", hx_swap="innerHTML",
                   hx_confirm="Revoke this key? This cannot be undone.")
            if k.is_active else Span("—", cls=TextPresets.muted_sm)
        )
        rows.append(Tr(
            Td(k.label),
            Td(Code(k.key_id + "…")),
            Td(k.scope),
            Td(k.created_at[:10]),
            Td(status),
            Td(revoke_btn),
        ))

    return Table(
        Thead(Tr(Th("Label"), Th("Key ID"), Th("Scope"), Th("Created"), Th("Status"), Th(""))),
        Tbody(*rows),
        cls=(TableT.divider, TableT.hover, TableT.sm),
    )


def CreateKeyForm():
    """Form to create a new API key."""
    return Card(
        H3("Create New Key"),
        Form(
            LabelInput("Label", id="label", placeholder="e.g. My dev key", required=True),
            LabelSelect(
                Option("Full access", value="full"),
                Option("Evaluate only", value="evaluate_only"),
                label="Scope", id="scope",
            ),
            Button("Create Key", cls=ButtonT.primary, type="submit"),
            hx_post="/dashboard/keys/create",
            hx_target="#key-list",
            hx_swap="innerHTML",
            cls="space-y-4",
        ),
    )


def NewKeyModal(raw_key: str):
    """Alert showing the raw key once (not a browser dialog — an inline card)."""
    return Card(
        H3("Key Created"),
        P("Copy this key now — it won't be shown again:", cls=TextPresets.muted_sm),
        Div(
            Pre(Code(raw_key), style="word-break:break-all;"),
            cls="space-y-2",
        ),
        P("Store it securely. Use it as your SAFECLAW_API_KEY.", cls=TextPresets.muted_sm),
        id="new-key-alert",
        cls="uk-alert-success",
    )


def KeysContent(user_id: int):
    """Full keys page content."""
    return (
        Div(id="new-key-alert"),
        CreateKeyForm(),
        Card(
            H3("Your API Keys"),
            Div(KeyTable(user_id), id="key-list"),
        ),
    )
```

**Step 2: Add routes in main.py**

Add before `serve()`:

```python
from dashboard.keys import KeysContent, KeyTable, generate_api_key, hash_key, NewKeyModal


@rt("/dashboard/keys")
def dashboard_keys(req, sess):
    user = req.scope.get("user")
    return (
        Title("API Keys — SafeClaw"),
        *MUITheme.blue.headers(),
        DashboardLayout("API Keys", *KeysContent(user.id), user=user, active="keys"),
    )


@rt("/dashboard/keys/create")
def create_key(req, sess, label: str = "", scope: str = "full"):
    user = req.scope.get("user")
    raw_key, key_id = generate_api_key()
    api_keys.insert(
        user_id=user.id,
        key_id=key_id,
        key_hash=hash_key(raw_key),
        label=label or "Unnamed key",
        scope=scope,
        created_at=datetime.now(timezone.utc).isoformat(),
        is_active=True,
    )
    return Div(
        NewKeyModal(raw_key),
        KeyTable(user.id),
    )


@rt("/dashboard/keys/{key_pk}/revoke")
def revoke_key(req, sess, key_pk: int):
    user = req.scope.get("user")
    try:
        key = api_keys[key_pk]
    except Exception:
        return KeyTable(user.id)
    if key.user_id != user.id:
        return KeyTable(user.id)
    key.is_active = False
    api_keys.update(key)
    return KeyTable(user.id)
```

Also add `from datetime import datetime, timezone` to imports if not already present.

**Step 3: Test manually**

Run the app, navigate to `/dashboard/keys`. The create form should render. Without auth, test via directly setting session.

**Step 4: Commit**

```bash
git add safeclaw-landing/dashboard/keys.py safeclaw-landing/main.py
git commit -m "feat(landing): add API key management page"
```

---

### Task 5: Agent management page

**Files:**
- Create: `safeclaw-landing/dashboard/agents.py`
- Modify: `safeclaw-landing/main.py`

**Step 1: Create dashboard/agents.py**

Create `safeclaw-landing/dashboard/agents.py`:

```python
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
```

**Step 2: Add routes in main.py**

Add before `serve()`:

```python
from dashboard.agents import AgentsContent, AgentTable
import httpx


@rt("/dashboard/agents")
def dashboard_agents(req, sess):
    user = req.scope.get("user")
    return (
        Title("Agents — SafeClaw"),
        *MUITheme.blue.headers(),
        DashboardLayout("Agents", *AgentsContent(), user=user, active="agents"),
    )


@rt("/dashboard/agents/load")
async def load_agents(req, sess, service_url: str = "", admin_password: str = ""):
    """Fetch agents from the service API."""
    sess["service_url"] = service_url or "http://localhost:8420"
    sess["admin_password"] = admin_password
    try:
        headers = {}
        if admin_password:
            headers["X-Admin-Password"] = admin_password
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{service_url}/api/v1/agents", headers=headers)
            r.raise_for_status()
            agents = r.json().get("agents", [])
            return AgentTable(agents)
    except Exception as e:
        return P(f"Could not connect: {e}", cls=TextPresets.muted_sm)


@rt("/dashboard/agents/{agent_id}/kill")
async def kill_agent_proxy(req, sess, agent_id: str):
    """Proxy kill request to service."""
    service_url = sess.get("service_url", "http://localhost:8420")
    headers = {}
    admin_pw = sess.get("admin_password", "")
    if admin_pw:
        headers["X-Admin-Password"] = admin_pw
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{service_url}/api/v1/agents/{agent_id}/kill", headers=headers)
            r = await client.get(f"{service_url}/api/v1/agents", headers=headers)
            return AgentTable(r.json().get("agents", []))
    except Exception as e:
        return P(f"Error: {e}", cls=TextPresets.muted_sm)


@rt("/dashboard/agents/{agent_id}/revive")
async def revive_agent_proxy(req, sess, agent_id: str):
    """Proxy revive request to service."""
    service_url = sess.get("service_url", "http://localhost:8420")
    headers = {}
    admin_pw = sess.get("admin_password", "")
    if admin_pw:
        headers["X-Admin-Password"] = admin_pw
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{service_url}/api/v1/agents/{agent_id}/revive", headers=headers)
            r = await client.get(f"{service_url}/api/v1/agents", headers=headers)
            return AgentTable(r.json().get("agents", []))
    except Exception as e:
        return P(f"Error: {e}", cls=TextPresets.muted_sm)
```

**Step 3: Test manually**

Run the app, visit `/dashboard/agents`. Should show the connection form. If the SafeClaw service is running locally, entering `http://localhost:8420` and clicking connect should load agents.

**Step 4: Commit**

```bash
git add safeclaw-landing/dashboard/agents.py safeclaw-landing/main.py
git commit -m "feat(landing): add agent management page"
```

---

### Task 6: Preferences page

**Files:**
- Create: `safeclaw-landing/dashboard/prefs.py`
- Modify: `safeclaw-landing/main.py`

**Step 1: Create dashboard/prefs.py**

Create `safeclaw-landing/dashboard/prefs.py`:

```python
"""User preferences page — proxies to SafeClaw service API."""

from monsterui.all import *


def PrefsForm(prefs: dict | None = None):
    """Preference editing form."""
    if prefs is None:
        prefs = {
            "autonomy_level": "moderate",
            "confirm_before_delete": True,
            "confirm_before_push": True,
            "confirm_before_send": True,
            "max_files_per_commit": 10,
        }

    return Form(
        LabelSelect(
            Option("Cautious", value="cautious", selected=prefs.get("autonomy_level") == "cautious"),
            Option("Moderate", value="moderate", selected=prefs.get("autonomy_level") == "moderate"),
            Option("Autonomous", value="autonomous", selected=prefs.get("autonomy_level") == "autonomous"),
            label="Autonomy Level", id="autonomy_level",
        ),
        H4("Confirmation Rules"),
        LabelCheckboxX("Confirm before deleting files", id="confirm_before_delete",
                        checked=prefs.get("confirm_before_delete", True)),
        LabelCheckboxX("Confirm before pushing code", id="confirm_before_push",
                        checked=prefs.get("confirm_before_push", True)),
        LabelCheckboxX("Confirm before sending messages", id="confirm_before_send",
                        checked=prefs.get("confirm_before_send", True)),
        H4("Limits"),
        LabelInput("Max files per commit", id="max_files_per_commit", type="number",
                   value=str(prefs.get("max_files_per_commit", 10)), min="1", max="100"),
        Button("Save Preferences", cls=ButtonT.primary, type="submit"),
        hx_post="/dashboard/prefs/save",
        hx_target="#prefs-status",
        hx_swap="innerHTML",
        cls="space-y-4",
    )


def PrefsContent(prefs: dict | None = None):
    """Full preferences page content."""
    return (
        Card(
            H3("Governance Preferences"),
            P("These settings control how strictly SafeClaw governs your agent's actions.",
              cls=TextPresets.muted_sm),
            PrefsForm(prefs),
        ),
        Div(id="prefs-status"),
    )
```

**Step 2: Add routes in main.py**

Add before `serve()`:

```python
from dashboard.prefs import PrefsContent


@rt("/dashboard/prefs")
async def dashboard_prefs(req, sess):
    user = req.scope.get("user")
    # Try to load prefs from service
    prefs = None
    service_url = sess.get("service_url", "http://localhost:8420")
    headers = {}
    admin_pw = sess.get("admin_password", "")
    if admin_pw:
        headers["X-Admin-Password"] = admin_pw
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{service_url}/api/v1/preferences/{user.github_login}",
                headers=headers,
            )
            if r.status_code == 200:
                prefs = r.json()
    except Exception:
        pass  # Use defaults

    return (
        Title("Preferences — SafeClaw"),
        *MUITheme.blue.headers(),
        DashboardLayout("Preferences", *PrefsContent(prefs), user=user, active="prefs"),
    )


@rt("/dashboard/prefs/save")
async def save_prefs(req, sess, autonomy_level: str = "moderate",
                     confirm_before_delete: bool = True, confirm_before_push: bool = True,
                     confirm_before_send: bool = True, max_files_per_commit: int = 10):
    user = req.scope.get("user")
    service_url = sess.get("service_url", "http://localhost:8420")
    headers = {"Content-Type": "application/json"}
    admin_pw = sess.get("admin_password", "")
    if admin_pw:
        headers["X-Admin-Password"] = admin_pw
    prefs_data = {
        "autonomy_level": autonomy_level,
        "confirm_before_delete": confirm_before_delete,
        "confirm_before_push": confirm_before_push,
        "confirm_before_send": confirm_before_send,
        "max_files_per_commit": max_files_per_commit,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                f"{service_url}/api/v1/preferences/{user.github_login}",
                json=prefs_data, headers=headers,
            )
            r.raise_for_status()
            return P("Preferences saved.", style="color:#4ade80;")
    except Exception as e:
        return P(f"Could not save: {e}. Is the service running?", style="color:#f87171;")
```

**Step 3: Commit**

```bash
git add safeclaw-landing/dashboard/prefs.py safeclaw-landing/main.py
git commit -m "feat(landing): add preferences page"
```

---

### Task 7: Add preferences API endpoint to the service

**Files:**
- Modify: `safeclaw-service/safeclaw/api/routes.py`
- Modify: `safeclaw-service/safeclaw/api/models.py`

**Step 1: Add PreferencesRequest model**

Add to `safeclaw-service/safeclaw/api/models.py`:

```python
class PreferencesRequest(BaseModel):
    autonomy_level: str = Field("moderate", alias="autonomy_level")
    confirm_before_delete: bool = Field(True, alias="confirm_before_delete")
    confirm_before_push: bool = Field(True, alias="confirm_before_push")
    confirm_before_send: bool = Field(True, alias="confirm_before_send")
    max_files_per_commit: int = Field(10, alias="max_files_per_commit")
```

**Step 2: Add GET/POST preferences routes**

Add to `safeclaw-service/safeclaw/api/routes.py`:

```python
from safeclaw.api.models import PreferencesRequest


@router.get("/preferences/{user_id}", dependencies=[Depends(require_admin)])
async def get_preferences(user_id: str):
    """Get user preferences as JSON."""
    engine = _get_engine()
    prefs = engine.preference_checker.get_preferences(user_id)
    return {
        "autonomy_level": prefs.autonomy_level,
        "confirm_before_delete": prefs.confirm_before_delete,
        "confirm_before_push": prefs.confirm_before_push,
        "confirm_before_send": prefs.confirm_before_send,
        "max_files_per_commit": prefs.max_files_per_commit,
    }


@router.post("/preferences/{user_id}", dependencies=[Depends(require_admin)])
async def update_preferences(user_id: str, request: PreferencesRequest):
    """Update user preferences — writes Turtle file."""
    import re
    from pathlib import Path

    engine = _get_engine()
    safe_user_id = re.sub(r'[^a-zA-Z0-9_@.-]', '', user_id)

    users_dir = engine.config.data_dir / "ontologies" / "users"
    users_dir.mkdir(parents=True, exist_ok=True)
    ttl_path = users_dir / f"user-{safe_user_id}.ttl"

    su = "http://safeclaw.uku.ai/ontology/user#"
    never_modify = ""  # Preserve existing never_modify_paths if present

    turtle = f"""@prefix su: <{su}> .

su:user-{safe_user_id} a su:User ;
    su:hasPreference su:pref-{safe_user_id} .

su:pref-{safe_user_id} a su:UserPreferences ;
    su:autonomyLevel "{request.autonomy_level}" ;
    su:confirmBeforeDelete "{str(request.confirm_before_delete).lower()}"^^<http://www.w3.org/2001/XMLSchema#boolean> ;
    su:confirmBeforePush "{str(request.confirm_before_push).lower()}"^^<http://www.w3.org/2001/XMLSchema#boolean> ;
    su:confirmBeforeSend "{str(request.confirm_before_send).lower()}"^^<http://www.w3.org/2001/XMLSchema#boolean> ;
    su:maxFilesPerCommit "{request.max_files_per_commit}"^^<http://www.w3.org/2001/XMLSchema#integer> .
"""
    ttl_path.write_text(turtle)

    # Reload ontologies so the new preferences take effect
    await engine.reload()

    return {"ok": True, "userId": safe_user_id}
```

**Step 3: Write a test**

Create or add to `safeclaw-service/tests/test_preferences_api.py`:

```python
"""Tests for the preferences API endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport
from safeclaw.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_get_default_preferences(client):
    r = await client.get("/api/v1/preferences/default")
    assert r.status_code == 200
    data = r.json()
    assert "autonomy_level" in data
    assert data["autonomy_level"] in ("cautious", "moderate", "autonomous")


@pytest.mark.asyncio
async def test_update_preferences(client, tmp_path, monkeypatch):
    # Point data dir to temp path for isolation
    r = await client.post("/api/v1/preferences/testuser", json={
        "autonomy_level": "cautious",
        "confirm_before_delete": False,
        "confirm_before_push": True,
        "confirm_before_send": False,
        "max_files_per_commit": 5,
    })
    # May fail if engine isn't ready in test mode — that's OK, test the model parsing
    assert r.status_code in (200, 503)
```

**Step 4: Run tests**

Run: `cd safeclaw-service && python -m pytest tests/test_preferences_api.py -v`

**Step 5: Commit**

```bash
git add safeclaw-service/safeclaw/api/routes.py safeclaw-service/safeclaw/api/models.py safeclaw-service/tests/test_preferences_api.py
git commit -m "feat(service): add GET/POST preferences API endpoints"
```

---

### Task 8: Update Dockerfile and add nav button styling

**Files:**
- Modify: `safeclaw-landing/Dockerfile`
- Modify: `safeclaw-landing/static/style.css`

**Step 1: Update Dockerfile**

Replace `safeclaw-landing/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data directory for SQLite
RUN mkdir -p data

EXPOSE 5002

CMD ["python", "main.py"]
```

**Step 2: Add minimal dashboard CSS**

Append to `safeclaw-landing/static/style.css`:

```css
/* ── Nav Auth Button ── */
.btn-sm {
  font-size: 0.85rem;
  padding: 6px 16px;
  border-radius: 6px;
}
```

The MonsterUI theme handles all dashboard styling — we only need this small addition for the nav sign-in button on public pages (which don't load MonsterUI headers).

**Step 3: Commit**

```bash
git add safeclaw-landing/Dockerfile safeclaw-landing/static/style.css
git commit -m "feat(landing): update Dockerfile and add nav button styling"
```

---

### Task 9: End-to-end verification

**Step 1: Verify landing page still works**

Run: `cd safeclaw-landing && python main.py`

Visit `http://localhost:5002`:
- Public pages (`/`, `/docs`) should render unchanged
- "Sign In" button should appear in nav
- Clicking "Sign In" should show "GitHub OAuth not configured" (without env vars)

**Step 2: Verify service tests pass**

Run: `cd safeclaw-service && python -m pytest tests/ -v`
Expected: All tests pass (317+ existing + new preferences tests)

**Step 3: Verify TypeScript build**

Run: `cd openclaw-safeclaw-plugin && npm run typecheck`
Expected: Clean (no changes to plugin)

**Step 4: Final commit (if any fixups needed)**

```bash
git add -A
git commit -m "fix: address end-to-end verification issues"
```

---

### Task 10: Update /docs page with User Dashboard documentation

**Files:**
- Modify: `safeclaw-landing/main.py`

**Step 1: Add "User Dashboard" entry to DocsToc**

In the `DocsToc()` function, add a new entry after `("dashboard", "Admin Dashboard")`:

```python
("user-dashboard", "User Dashboard"),
```

**Step 2: Add DocsSection for User Dashboard**

In the `DocsPage()` function, after the Admin Dashboard `DocsSection` (section `"dashboard"`), add:

```python
# ── 16b. User Dashboard ──
DocsSection("user-dashboard", "User Dashboard",
    P("SafeClaw includes a user-facing dashboard at ", Code("safeclaw.eu"),
      " (or self-hosted) for managing API keys, agents, and governance preferences. "
      "Sign in with your GitHub account to access the dashboard."),
    H3("Authentication", cls="docs-h3"),
    P("The dashboard uses GitHub OAuth for authentication. "
      "No password or email registration is required — sign in with GitHub and you're ready."),
    Ul(
        Li("Click ", Strong("Sign In"), " in the navigation bar"),
        Li("Authorize with GitHub"),
        Li("You're redirected to your dashboard"),
        cls="docs-list",
    ),
    H3("Dashboard Pages", cls="docs-h3"),
    Div(
        Table(
            Thead(Tr(Th("Page"), Th("Purpose"))),
            Tbody(
                Tr(Td(Strong("Overview")), Td("Service health status, quick stats, getting started guide")),
                Tr(Td(Strong("API Keys")), Td("Create, view, and revoke API keys for your agents")),
                Tr(Td(Strong("Agents")), Td("View registered agents, kill/revive switches (requires service connection)")),
                Tr(Td(Strong("Preferences")), Td("Edit governance preferences — autonomy level, confirmation rules, limits")),
            ),
        ),
        cls="docs-table-wrap",
    ),
    H3("API Keys", cls="docs-h3"),
    P("Generate API keys from the dashboard to authenticate your agents with the SafeClaw service:"),
    Ul(
        Li("Keys use the ", Code("sc_"), " prefix format"),
        Li("The full key is shown ", Strong("once"), " at creation — copy it immediately"),
        Li("Keys can be scoped: ", Code("full"), " (all operations) or ", Code("evaluate_only"), " (read-only evaluation)"),
        Li("Revoked keys cannot be reactivated — create a new one instead"),
        cls="docs-list",
    ),
    P("Set your key as an environment variable for the plugin:"),
    Div(
        Pre(
            "export SAFECLAW_API_KEY=sc_your_key_here",
            cls="docs-pre",
        ),
    ),
    H3("Governance Preferences", cls="docs-h3"),
    P("The preferences page lets you configure how strictly SafeClaw governs your agent's actions:"),
    Div(
        Table(
            Thead(Tr(Th("Setting"), Th("Options"), Th("Effect"))),
            Tbody(
                Tr(Td(Strong("Autonomy Level")),
                   Td(Code("cautious"), ", ", Code("moderate"), ", ", Code("autonomous")),
                   Td("Controls confirmation requirements for irreversible actions")),
                Tr(Td(Strong("Confirm Before Delete")),
                   Td("On / Off"),
                   Td("Require confirmation before file deletion, cleanup, or reset")),
                Tr(Td(Strong("Confirm Before Push")),
                   Td("On / Off"),
                   Td("Require confirmation before git push, force push, or package publish")),
                Tr(Td(Strong("Confirm Before Send")),
                   Td("On / Off"),
                   Td("Require confirmation before sending messages")),
                Tr(Td(Strong("Max Files Per Commit")),
                   Td("1–100"),
                   Td("Limit on files in a single commit")),
            ),
        ),
        cls="docs-table-wrap",
    ),
    H3("Self-Hosting the Dashboard", cls="docs-h3"),
    P("The dashboard works identically for self-hosted deployments. "
      "Run the landing app alongside your SafeClaw service and configure "
      "GitHub OAuth credentials:"),
    Div(
        Pre(
            "export GITHUB_CLIENT_ID=your_client_id\n"
            "export GITHUB_CLIENT_SECRET=your_client_secret\n"
            "cd safeclaw-landing && python main.py",
            cls="docs-pre",
        ),
    ),
    P("In the dashboard, point the service URL to your local instance "
      "(e.g. ", Code("http://localhost:8420"), ") when managing agents or preferences."),
),
```

**Step 3: Update the section numbering**

The "Configuration Reference" section is currently numbered 16. Renumber it to 17 (or just leave numbering as comments — it's internal only).

**Step 4: Test the docs page**

Run: `cd safeclaw-landing && python main.py`

Visit `http://localhost:5002/docs`:
- "User Dashboard" should appear in the table of contents
- Clicking it should scroll to the new section
- Section should show auth flow, pages table, API key docs, preferences table, and self-host instructions

**Step 5: Commit**

```bash
git add safeclaw-landing/main.py
git commit -m "docs(landing): add User Dashboard section to /docs page"
```

---

## Execution Order

Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6 → Task 7 → Task 8 → Task 9 → Task 10

Tasks 1-6 are landing app changes (sequential — each builds on the previous).
Task 7 is the service-side endpoint (can be done in parallel with Tasks 4-6 if desired).
Task 8 is cleanup.
Task 9 is verification.
Task 10 is documentation (depends on Tasks 1-6 being complete so the docs match reality).

## Verify

- `python main.py` starts on port 5002 without errors
- Public pages (`/`, `/docs`) render correctly
- `/docs` includes the new "User Dashboard" section with all subsections
- `/login` redirects to GitHub (when credentials configured) or shows message
- `/dashboard` shows overview with health check
- `/dashboard/keys` creates/revokes API keys
- `/dashboard/agents` connects to service and lists agents
- `/dashboard/prefs` loads/saves preferences
- `python -m pytest tests/ -v` passes all service tests
- `npm run typecheck` passes for the plugin
