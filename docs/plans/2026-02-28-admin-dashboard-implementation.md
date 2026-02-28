# Admin Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a 4-page admin dashboard (Home, Audit, Agents, Settings) inside the safeclaw-service, mounted at `/admin/`.

**Architecture:** FastHTML app mounted as an ASGI sub-application inside the existing FastAPI service. Direct Python access to the `FullEngine` instance via `get_engine()`. Session-based password auth via `SAFECLAW_ADMIN_PASSWORD` env var. MonsterUI slate theme in dark mode for styling.

**Tech Stack:** FastHTML, MonsterUI (slate dark theme), HTMX, python-fasthtml, existing FastAPI service

**Design doc:** `docs/plans/2026-02-28-admin-dashboard-design.md`

---

### Task 1: Add dependencies and config field

**Files:**
- Modify: `safeclaw-service/pyproject.toml`
- Modify: `safeclaw-service/safeclaw/config.py`

**Step 1: Add python-fasthtml and monsterui to dependencies**

In `pyproject.toml`, add to the `dependencies` list:

```toml
dependencies = [
    # ... existing deps ...
    "python-fasthtml>=0.12.0",
    "monsterui>=0.12.0",
]
```

**Step 2: Add admin_password config field**

In `safeclaw/config.py`, add this field to `SafeClawConfig`:

```python
# Admin dashboard
admin_password: str = ""
```

Place it after the `log_level` field, before the LLM section.

**Step 3: Install the new dependencies**

Run: `cd safeclaw-service && pip install -e ".[dev]"`
Expected: Installs successfully, python-fasthtml and monsterui available

**Step 4: Verify import works**

Run: `cd safeclaw-service && python -c "from fasthtml.common import *; from monsterui.all import *; print('OK')"`
Expected: `OK`

**Step 5: Run existing tests to confirm nothing broke**

Run: `cd safeclaw-service && python -m pytest tests/ -x -q`
Expected: All tests pass (270+)

**Step 6: Commit**

```bash
cd safeclaw-service
git add pyproject.toml safeclaw/config.py
git commit -m "feat(dashboard): add FastHTML + MonsterUI deps and admin_password config"
```

---

### Task 2: Dashboard app skeleton with auth

**Files:**
- Create: `safeclaw-service/safeclaw/dashboard/__init__.py`
- Create: `safeclaw-service/safeclaw/dashboard/app.py`
- Create: `safeclaw-service/safeclaw/dashboard/components.py`
- Create: `safeclaw-service/safeclaw/dashboard/pages/__init__.py`
- Test: `safeclaw-service/tests/test_dashboard_app.py`

**Step 1: Write the failing tests**

Create `tests/test_dashboard_app.py`:

```python
"""Tests for the admin dashboard app."""

import pytest
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient

from safeclaw.config import SafeClawConfig
from safeclaw.dashboard.app import create_dashboard


@pytest.fixture
def mock_engine():
    """Create a mock FullEngine for dashboard tests."""
    engine = MagicMock()
    engine.config = SafeClawConfig(admin_password="testpass123")
    engine.audit = MagicMock()
    engine.audit.get_recent_records.return_value = []
    engine.audit.get_blocked_records.return_value = []
    engine.agent_registry = MagicMock()
    engine.agent_registry.list_agents.return_value = []
    engine.session_tracker = MagicMock()
    engine.session_tracker._sessions = {}
    engine.kg = MagicMock()
    engine.kg.__len__ = MagicMock(return_value=42)
    engine.llm_client = None
    engine.security_reviewer = None
    engine.classification_observer = None
    engine.explainer = None
    return engine


@pytest.fixture
def dashboard_client(mock_engine):
    """Create a test client for the dashboard."""
    def get_engine():
        return mock_engine
    app = create_dashboard(get_engine)
    return TestClient(app)


def test_login_page_shown_when_not_authenticated(dashboard_client):
    """Unauthenticated users are redirected to login."""
    resp = dashboard_client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


def test_login_page_renders(dashboard_client):
    """Login page renders a password form."""
    resp = dashboard_client.get("/login")
    assert resp.status_code == 200
    assert "password" in resp.text.lower()


def test_login_with_correct_password(dashboard_client):
    """Correct password sets session and redirects to home."""
    resp = dashboard_client.post(
        "/login",
        data={"password": "testpass123"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_login_with_wrong_password(dashboard_client):
    """Wrong password stays on login page."""
    resp = dashboard_client.post(
        "/login",
        data={"password": "wrong"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


def test_no_password_configured_allows_access(mock_engine):
    """When admin_password is empty, dashboard is accessible without auth."""
    mock_engine.config = SafeClawConfig(admin_password="")
    def get_engine():
        return mock_engine
    app = create_dashboard(get_engine)
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200


def test_logout_clears_session(dashboard_client):
    """Logout clears the session and redirects to login."""
    # Login first
    dashboard_client.post(
        "/login",
        data={"password": "testpass123"},
        follow_redirects=False,
    )
    resp = dashboard_client.get("/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]
```

**Step 2: Run tests to verify they fail**

Run: `cd safeclaw-service && python -m pytest tests/test_dashboard_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'safeclaw.dashboard'`

**Step 3: Create the dashboard package**

Create `safeclaw/dashboard/__init__.py`:

```python
"""SafeClaw admin dashboard — FastHTML app mounted inside the FastAPI service."""
```

Create `safeclaw/dashboard/pages/__init__.py`:

```python
"""Dashboard page modules."""
```

**Step 4: Write shared components**

Create `safeclaw/dashboard/components.py`:

```python
"""Shared UI components for the admin dashboard."""

from fasthtml.common import *


# ── Color palette (matching safeclaw.eu landing page) ──
COLORS = {
    "bg": "#0a0a0a",
    "surface": "#1a1a1a",
    "border": "#2a2a2a",
    "text": "#e5e5e5",
    "muted": "#888888",
    "green": "#4ade80",
    "red": "#f87171",
    "blue": "#60a5fa",
    "purple": "#a78bfa",
    "orange": "#fb923c",
}


def DashboardCSS():
    """Inline CSS for the dashboard (avoids needing a static file mount)."""
    return Style("""
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

        :root {
            --bg: #0a0a0a; --surface: #1a1a1a; --border: #2a2a2a;
            --text: #e5e5e5; --muted: #888888;
            --green: #4ade80; --red: #f87171; --blue: #60a5fa;
            --purple: #a78bfa; --orange: #fb923c;
            --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
        }
        *, *::before, *::after { box-sizing: border-box; }
        body { background: var(--bg); color: var(--text); font-family: var(--font-sans);
               line-height: 1.6; margin: 0; -webkit-font-smoothing: antialiased; }
        a { color: var(--blue); text-decoration: none; }
        a:hover { opacity: 0.8; }

        .dashboard-nav {
            position: sticky; top: 0; z-index: 100;
            background: rgba(10,10,10,0.9); backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border); padding: 0 24px;
        }
        .dashboard-nav-inner {
            max-width: 1200px; margin: 0 auto; display: flex;
            align-items: center; justify-content: space-between; height: 56px;
        }
        .dashboard-nav-logo { font-weight: 700; font-size: 1.1rem; }
        .dashboard-nav-links { display: flex; gap: 24px; list-style: none; margin: 0; padding: 0; }
        .dashboard-nav-links a { color: var(--muted); font-size: 0.9rem; font-weight: 500; }
        .dashboard-nav-links a:hover, .dashboard-nav-links a.active { color: var(--text); }
        .dashboard-nav-right a { color: var(--muted); font-size: 0.85rem; }

        .dashboard-container { max-width: 1200px; margin: 0 auto; padding: 24px; }

        .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .stat-card {
            background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
            padding: 20px; border-left: 3px solid var(--blue);
        }
        .stat-card h3 { font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin: 0 0 8px 0; }
        .stat-card .stat-value { font-size: 1.8rem; font-weight: 700; margin: 0; }
        .stat-card.green { border-left-color: var(--green); }
        .stat-card.red { border-left-color: var(--red); }
        .stat-card.purple { border-left-color: var(--purple); }
        .stat-card.orange { border-left-color: var(--orange); }

        .panel {
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 8px; padding: 20px; margin-bottom: 24px;
        }
        .panel h2 { font-size: 1.1rem; margin: 0 0 16px 0; }

        table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
        th { text-align: left; color: var(--muted); font-weight: 500; padding: 8px 12px;
             border-bottom: 1px solid var(--border); font-size: 0.75rem; text-transform: uppercase; }
        td { padding: 10px 12px; border-bottom: 1px solid var(--border); }
        tr:hover { background: rgba(255,255,255,0.02); }

        .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
        .badge-allowed { background: rgba(74,222,128,0.15); color: var(--green); }
        .badge-blocked { background: rgba(248,113,113,0.15); color: var(--red); }
        .badge-active { background: rgba(74,222,128,0.15); color: var(--green); }
        .badge-killed { background: rgba(248,113,113,0.15); color: var(--red); }
        .badge-risk-low { color: var(--green); }
        .badge-risk-medium { color: var(--orange); }
        .badge-risk-high { color: var(--red); }
        .badge-risk-critical { color: var(--red); font-weight: 700; }

        .btn {
            display: inline-block; padding: 8px 16px; border-radius: 6px;
            font-size: 0.85rem; font-weight: 500; cursor: pointer; border: none;
            transition: opacity 0.2s;
        }
        .btn:hover { opacity: 0.85; }
        .btn-primary { background: var(--blue); color: #0a0a0a; }
        .btn-danger { background: var(--red); color: #0a0a0a; }
        .btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
        .btn-sm { padding: 4px 10px; font-size: 0.8rem; }

        input, textarea, select {
            background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
            color: var(--text); padding: 8px 12px; font-size: 0.9rem; width: 100%;
            font-family: var(--font-sans);
        }
        input:focus, textarea:focus, select:focus { outline: none; border-color: var(--blue); }

        .form-group { margin-bottom: 16px; }
        .form-group label { display: block; font-size: 0.85rem; color: var(--muted); margin-bottom: 4px; }

        .login-container {
            display: flex; justify-content: center; align-items: center;
            min-height: 100vh; padding: 24px;
        }
        .login-card {
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 12px; padding: 40px; max-width: 400px; width: 100%; text-align: center;
        }
        .login-card h1 { font-size: 1.4rem; margin-bottom: 8px; }
        .login-card p { color: var(--muted); font-size: 0.9rem; margin-bottom: 24px; }

        .mono { font-family: var(--font-mono); font-size: 0.85rem; }
        .text-muted { color: var(--muted); }
        .text-green { color: var(--green); }
        .text-red { color: var(--red); }
        .text-sm { font-size: 0.85rem; }
        .mt-16 { margin-top: 16px; }

        .detail-row { display: none; }
        .detail-row.open { display: table-row; }
        .detail-content { background: var(--bg); padding: 16px; border-radius: 6px; font-size: 0.85rem; }

        .empty-state { text-align: center; padding: 40px; color: var(--muted); }

        .config-grid { display: grid; grid-template-columns: 200px 1fr; gap: 8px 16px; font-size: 0.85rem; }
        .config-key { color: var(--muted); font-family: var(--font-mono); }
        .config-val { font-family: var(--font-mono); word-break: break-all; }

        .flash-error { background: rgba(248,113,113,0.15); color: var(--red); padding: 8px 16px; border-radius: 6px; margin-bottom: 16px; font-size: 0.85rem; }
        .flash-success { background: rgba(74,222,128,0.15); color: var(--green); padding: 8px 16px; border-radius: 6px; margin-bottom: 16px; font-size: 0.85rem; }
    """)


def NavBar(active: str = "home"):
    """Dashboard navigation bar."""
    links = [
        ("Home", "/", "home"),
        ("Audit", "/audit", "audit"),
        ("Agents", "/agents", "agents"),
        ("Settings", "/settings", "settings"),
    ]
    return Nav(
        Div(
            Span("🛡️ SafeClaw Admin", cls="dashboard-nav-logo"),
            Ul(
                *[Li(A(label, href=href, cls="active" if key == active else ""))
                  for label, href, key in links],
                cls="dashboard-nav-links",
            ),
            Div(A("Logout", href="/logout"), cls="dashboard-nav-right"),
            cls="dashboard-nav-inner",
        ),
        cls="dashboard-nav",
    )


def Page(title: str, *content, active: str = "home"):
    """Full dashboard page wrapper."""
    return (
        Title(f"SafeClaw Admin — {title}"),
        DashboardCSS(),
        NavBar(active=active),
        Main(Div(*content, cls="dashboard-container")),
    )


def StatCard(label: str, value, color: str = ""):
    """A stat card for the dashboard grid."""
    return Div(
        H3(label),
        P(str(value), cls="stat-value"),
        cls=f"stat-card {color}",
    )


def DecisionBadge(decision: str):
    """Render an allowed/blocked badge."""
    cls = "badge-allowed" if decision == "allowed" else "badge-blocked"
    return Span(decision.upper(), cls=f"badge {cls}")


def RiskBadge(risk_level: str):
    """Render a risk level indicator."""
    level = risk_level.lower().replace("risk", "").strip()
    cls_map = {"low": "badge-risk-low", "medium": "badge-risk-medium",
               "high": "badge-risk-high", "critical": "badge-risk-critical"}
    return Span(risk_level, cls=cls_map.get(level, ""))


def AgentStatusBadge(killed: bool):
    """Render an active/killed badge."""
    if killed:
        return Span("KILLED", cls="badge badge-killed")
    return Span("ACTIVE", cls="badge badge-active")
```

**Step 5: Write the dashboard app factory**

Create `safeclaw/dashboard/app.py`:

```python
"""FastHTML admin dashboard — mounted inside the FastAPI service at /admin."""

from functools import lru_cache
from fasthtml.common import *

from safeclaw.dashboard.components import DashboardCSS, Page


def create_dashboard(get_engine_fn):
    """Create the FastHTML dashboard app.

    Args:
        get_engine_fn: callable that returns the FullEngine instance.
    """

    def _engine():
        return get_engine_fn()

    def _config():
        return _engine().config

    def auth_before(req, sess):
        """Beforeware: require login unless admin_password is empty."""
        password = _config().admin_password
        if not password:
            # Dev mode — no auth required
            return
        auth = sess.get("admin_auth")
        if not auth:
            return RedirectResponse("/login", status_code=303)

    bware = Beforeware(auth_before, skip=[r"/login", r"/favicon\.ico", r".*\.css", r".*\.js"])

    app, rt = fast_app(
        pico=False,
        before=bware,
        secret_key="safeclaw-admin-session-key",
        hdrs=(Meta(name="viewport", content="width=device-width, initial-scale=1"),),
    )

    # Store engine accessor on app for use by page modules
    app._get_engine = _engine

    @rt("/login")
    def login(req, sess):
        error = req.query_params.get("error", "")
        return (
            Title("SafeClaw Admin — Login"),
            DashboardCSS(),
            Div(
                Div(
                    H1("🛡️ SafeClaw"),
                    P("Admin Dashboard"),
                    Div(P("Invalid password", cls="flash-error") if error else ""),
                    Form(
                        Div(
                            Label("Password", fr="password"),
                            Input(type="password", name="password", id="password",
                                  placeholder="Enter admin password", autofocus=True),
                            cls="form-group",
                        ),
                        Button("Sign In", type="submit", cls="btn btn-primary",
                               style="width:100%; margin-top:8px;"),
                        method="post",
                    ),
                    cls="login-card",
                ),
                cls="login-container",
            ),
        )

    @rt("/login", methods=["POST"])
    def login_post(password: str, sess):
        expected = _config().admin_password
        if not expected or password == expected:
            sess["admin_auth"] = True
            return RedirectResponse("/", status_code=303)
        return RedirectResponse("/login?error=1", status_code=303)

    @rt("/logout")
    def logout(sess):
        sess.pop("admin_auth", None)
        return RedirectResponse("/login", status_code=303)

    # Import and register page routes
    from safeclaw.dashboard.pages import home, audit, agents, settings
    home.register(rt, _engine)
    audit.register(rt, _engine)
    agents.register(rt, _engine)
    settings.register(rt, _engine)

    return app
```

**Step 6: Create stub page modules**

Create `safeclaw/dashboard/pages/home.py`:

```python
"""Home / System Health page."""

from safeclaw.dashboard.components import Page


def register(rt, get_engine):
    @rt("/")
    def index():
        engine = get_engine()
        return Page("Home", P("Dashboard home — coming soon"), active="home")
```

Create `safeclaw/dashboard/pages/audit.py`:

```python
"""Audit log viewer page."""

from safeclaw.dashboard.components import Page


def register(rt, get_engine):
    @rt("/audit")
    def audit_page():
        engine = get_engine()
        return Page("Audit Log", P("Audit log — coming soon"), active="audit")
```

Create `safeclaw/dashboard/pages/agents.py`:

```python
"""Agent management page."""

from safeclaw.dashboard.components import Page


def register(rt, get_engine):
    @rt("/agents")
    def agents_page():
        engine = get_engine()
        return Page("Agents", P("Agent management — coming soon"), active="agents")
```

Create `safeclaw/dashboard/pages/settings.py`:

```python
"""Settings page."""

from safeclaw.dashboard.components import Page


def register(rt, get_engine):
    @rt("/settings")
    def settings_page():
        engine = get_engine()
        return Page("Settings", P("Settings — coming soon"), active="settings")
```

**Step 7: Run tests to verify they pass**

Run: `cd safeclaw-service && python -m pytest tests/test_dashboard_app.py -v`
Expected: All 6 tests pass

**Step 8: Run full test suite**

Run: `cd safeclaw-service && python -m pytest tests/ -x -q`
Expected: All tests pass

**Step 9: Commit**

```bash
cd safeclaw-service
git add safeclaw/dashboard/ tests/test_dashboard_app.py
git commit -m "feat(dashboard): app skeleton with auth, nav, and stub pages"
```

---

### Task 3: Mount dashboard in FastAPI and add home page

**Files:**
- Modify: `safeclaw-service/safeclaw/main.py`
- Modify: `safeclaw-service/safeclaw/dashboard/pages/home.py`
- Test: `safeclaw-service/tests/test_dashboard_app.py` (add tests)

**Step 1: Write the failing test for home page content**

Add to `tests/test_dashboard_app.py`:

```python
def test_home_page_shows_stats(mock_engine):
    """Home page shows system health stats."""
    mock_engine.config = SafeClawConfig(admin_password="")
    def get_engine():
        return mock_engine
    app = create_dashboard(get_engine)
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Engine" in resp.text
    assert "Decisions" in resp.text
```

**Step 2: Run test to verify it fails**

Run: `cd safeclaw-service && python -m pytest tests/test_dashboard_app.py::test_home_page_shows_stats -v`
Expected: FAIL (stub page doesn't contain those strings)

**Step 3: Implement the home page**

Replace `safeclaw/dashboard/pages/home.py`:

```python
"""Home / System Health page."""

from fasthtml.common import *

from safeclaw.audit.reporter import AuditReporter
from safeclaw.dashboard.components import (
    DecisionBadge,
    Page,
    RiskBadge,
    StatCard,
)


def register(rt, get_engine):

    @rt("/")
    def index():
        engine = get_engine()

        # Gather stats
        recent = engine.audit.get_recent_records(limit=50)
        reporter = AuditReporter(engine.audit)
        stats = reporter.get_statistics(recent)

        agents = engine.agent_registry.list_agents()
        active_sessions = len(getattr(engine.session_tracker, "_sessions", {}))
        triples = len(engine.kg)
        llm_status = "Configured" if engine.llm_client else "Not configured"

        return Page(
            "Home",
            # Status cards
            Div(
                StatCard("Engine Status", "Running", "green"),
                StatCard("LLM Status", llm_status, "purple" if engine.llm_client else ""),
                StatCard("Ontology Triples", f"{triples:,}", ""),
                StatCard("Active Sessions", active_sessions, ""),
                cls="stat-grid",
            ),
            # Quick stats
            Div(
                StatCard("Total Decisions", stats.get("total", 0), ""),
                StatCard("Allowed", stats.get("allowed", 0), "green"),
                StatCard("Blocked", stats.get("blocked", 0), "red"),
                StatCard("Block Rate", f"{stats.get('block_rate', 0)}%", "orange"),
                cls="stat-grid",
            ),
            # Recent activity
            Div(
                H2("Recent Activity"),
                _recent_table(recent[:10]) if recent else P("No decisions recorded yet.", cls="empty-state"),
                cls="panel",
            ),
            active="home",
        )

    def _recent_table(records):
        return Table(
            Thead(Tr(
                Th("Time"), Th("Session"), Th("Tool"), Th("Action"),
                Th("Risk"), Th("Decision"), Th("Latency"),
            )),
            Tbody(*[
                Tr(
                    Td(r.timestamp[:19], cls="mono text-sm"),
                    Td(r.session_id[:8] + "…" if len(r.session_id) > 8 else r.session_id, cls="mono text-sm"),
                    Td(r.action.tool_name),
                    Td(r.action.ontology_class, cls="text-sm"),
                    Td(RiskBadge(r.action.risk_level)),
                    Td(DecisionBadge(r.decision)),
                    Td(f"{r.justification.elapsed_ms:.0f}ms", cls="mono text-sm text-muted"),
                )
                for r in records
            ]),
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd safeclaw-service && python -m pytest tests/test_dashboard_app.py -v`
Expected: All tests pass

**Step 5: Mount the dashboard in main.py**

Add to the bottom of `safeclaw/main.py`, before any serve() call:

```python
# Admin dashboard (FastHTML sub-app)
from safeclaw.dashboard.app import create_dashboard

app.mount("/admin", create_dashboard(get_engine))
```

**Step 6: Run full test suite**

Run: `cd safeclaw-service && python -m pytest tests/ -x -q`
Expected: All tests pass

**Step 7: Commit**

```bash
cd safeclaw-service
git add safeclaw/main.py safeclaw/dashboard/pages/home.py tests/test_dashboard_app.py
git commit -m "feat(dashboard): home page with stats and recent activity table"
```

---

### Task 4: Audit log page

**Files:**
- Modify: `safeclaw-service/safeclaw/dashboard/pages/audit.py`
- Test: `safeclaw-service/tests/test_dashboard_audit.py`

**Step 1: Write the failing tests**

Create `tests/test_dashboard_audit.py`:

```python
"""Tests for audit log dashboard page."""

import pytest
from unittest.mock import MagicMock
from starlette.testclient import TestClient

from safeclaw.config import SafeClawConfig
from safeclaw.audit.models import (
    ActionDetail,
    ConstraintCheck,
    DecisionRecord,
    Justification,
)
from safeclaw.dashboard.app import create_dashboard


def _make_record(decision="allowed", tool="read", risk="LowRisk", session_id="sess-1"):
    return DecisionRecord(
        session_id=session_id,
        user_id="testuser",
        action=ActionDetail(
            tool_name=tool,
            params={"file_path": "/src/main.py"},
            ontology_class="ReadFile",
            risk_level=risk,
            is_reversible=True,
            affects_scope="Workspace",
        ),
        decision=decision,
        justification=Justification(
            constraints_checked=[
                ConstraintCheck(
                    constraint_uri="shacl:validation",
                    constraint_type="SHACL",
                    result="satisfied",
                    reason="All shapes conform",
                ),
            ],
            elapsed_ms=1.5,
        ),
    )


@pytest.fixture
def audit_client():
    engine = MagicMock()
    engine.config = SafeClawConfig(admin_password="")
    engine.audit.get_recent_records.return_value = [
        _make_record("allowed"),
        _make_record("blocked", "exec", "CriticalRisk"),
    ]
    engine.audit.get_blocked_records.return_value = [
        _make_record("blocked", "exec", "CriticalRisk"),
    ]
    engine.audit.get_session_records.return_value = []
    engine.agent_registry = MagicMock()
    engine.agent_registry.list_agents.return_value = []
    engine.session_tracker = MagicMock()
    engine.session_tracker._sessions = {}
    engine.kg = MagicMock()
    engine.kg.__len__ = MagicMock(return_value=42)
    engine.llm_client = None
    engine.security_reviewer = None
    engine.classification_observer = None
    engine.explainer = None

    def get_engine():
        return engine

    app = create_dashboard(get_engine)
    return TestClient(app), engine


def test_audit_page_renders(audit_client):
    """Audit page renders with decision records."""
    client, _ = audit_client
    resp = client.get("/audit")
    assert resp.status_code == 200
    assert "ReadFile" in resp.text
    assert "ALLOWED" in resp.text
    assert "BLOCKED" in resp.text


def test_audit_filter_blocked(audit_client):
    """Audit page can filter to blocked only."""
    client, engine = audit_client
    resp = client.get("/audit?filter=blocked")
    assert resp.status_code == 200
    engine.audit.get_blocked_records.assert_called()
```

**Step 2: Run tests to verify they fail**

Run: `cd safeclaw-service && python -m pytest tests/test_dashboard_audit.py -v`
Expected: FAIL

**Step 3: Implement the audit page**

Replace `safeclaw/dashboard/pages/audit.py`:

```python
"""Audit log viewer page."""

from fasthtml.common import *

from safeclaw.dashboard.components import DecisionBadge, Page, RiskBadge


def register(rt, get_engine):

    @rt("/audit")
    def audit_page(filter: str = "", session_id: str = "", limit: int = 50):
        engine = get_engine()

        if filter == "blocked":
            records = engine.audit.get_blocked_records(limit=limit)
        elif session_id:
            records = engine.audit.get_session_records(session_id)
        else:
            records = engine.audit.get_recent_records(limit=limit)

        return Page(
            "Audit Log",
            # Filters
            Div(
                Form(
                    Div(
                        Label("Filter:", fr="filter"),
                        Select(
                            Option("All decisions", value="", selected=filter == ""),
                            Option("Blocked only", value="blocked", selected=filter == "blocked"),
                            name="filter", id="filter",
                            style="width: auto; display: inline-block; min-width: 160px;",
                        ),
                        Label("Session:", fr="session_id", style="margin-left: 16px;"),
                        Input(name="session_id", id="session_id", value=session_id,
                              placeholder="session-id...", style="width: 200px; display: inline-block;"),
                        Button("Apply", type="submit", cls="btn btn-outline btn-sm",
                               style="margin-left: 8px;"),
                        style="display: flex; align-items: center; gap: 8px;",
                    ),
                    method="get", action="/audit",
                ),
                cls="panel",
            ),
            # Results
            Div(
                H2(f"Decisions ({len(records)})"),
                _audit_table(records) if records else P("No records found.", cls="empty-state"),
                cls="panel",
            ),
            active="audit",
        )

    @rt("/audit/detail/{audit_id}")
    def audit_detail(audit_id: str):
        """HTMX partial: show detail for a specific audit record."""
        engine = get_engine()
        # Search recent records for the matching ID
        records = engine.audit.get_recent_records(limit=200)
        record = next((r for r in records if r.id == audit_id), None)
        if not record:
            return Div(P("Record not found.", cls="text-muted"), id=f"detail-{audit_id}")

        checks = record.justification.constraints_checked
        prefs = record.justification.preferences_applied
        return Div(
            Div(
                H3("Justification"),
                P(f"Latency: {record.justification.elapsed_ms:.1f}ms", cls="text-sm text-muted"),
                H4("Constraints Checked") if checks else "",
                Table(
                    Thead(Tr(Th("Type"), Th("Result"), Th("Reason"))),
                    Tbody(*[
                        Tr(
                            Td(c.constraint_type),
                            Td(Span(c.result, cls=f"text-green" if c.result == "satisfied" else "text-red")),
                            Td(c.reason, cls="text-sm"),
                        )
                        for c in checks
                    ]),
                ) if checks else "",
                H4("Preferences Applied") if prefs else "",
                Ul(*[Li(f"{p.preference_uri}: {p.effect}") for p in prefs]) if prefs else "",
                cls="detail-content",
            ),
            id=f"detail-{audit_id}",
        )

    def _audit_table(records):
        rows = []
        for r in records:
            rows.append(Tr(
                Td(r.timestamp[:19], cls="mono text-sm"),
                Td(r.session_id[:8] + "…" if len(r.session_id) > 8 else r.session_id, cls="mono text-sm"),
                Td(r.action.tool_name),
                Td(r.action.ontology_class, cls="text-sm"),
                Td(RiskBadge(r.action.risk_level)),
                Td(DecisionBadge(r.decision)),
                Td(f"{r.justification.elapsed_ms:.0f}ms", cls="mono text-sm text-muted"),
                Td(Button("Details", cls="btn btn-outline btn-sm",
                          hx_get=f"/audit/detail/{r.id}",
                          hx_target=f"#detail-{r.id}",
                          hx_swap="innerHTML")),
            ))
            rows.append(Tr(Td(Div(id=f"detail-{r.id}"), colspan="8"), cls="detail-row open"))
        return Table(
            Thead(Tr(
                Th("Time"), Th("Session"), Th("Tool"), Th("Action"),
                Th("Risk"), Th("Decision"), Th("Latency"), Th(""),
            )),
            Tbody(*rows),
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd safeclaw-service && python -m pytest tests/test_dashboard_audit.py -v`
Expected: All tests pass

**Step 5: Run full test suite**

Run: `cd safeclaw-service && python -m pytest tests/ -x -q`
Expected: All tests pass

**Step 6: Commit**

```bash
cd safeclaw-service
git add safeclaw/dashboard/pages/audit.py tests/test_dashboard_audit.py
git commit -m "feat(dashboard): audit log page with filters and detail expansion"
```

---

### Task 5: Agents page

**Files:**
- Modify: `safeclaw-service/safeclaw/dashboard/pages/agents.py`
- Test: `safeclaw-service/tests/test_dashboard_agents.py`

**Step 1: Write the failing tests**

Create `tests/test_dashboard_agents.py`:

```python
"""Tests for agents dashboard page."""

import pytest
from unittest.mock import MagicMock
from starlette.testclient import TestClient
from time import monotonic

from safeclaw.config import SafeClawConfig
from safeclaw.engine.agent_registry import AgentRecord
from safeclaw.dashboard.app import create_dashboard


def _make_agent(agent_id="agent-1", role="developer", killed=False):
    return AgentRecord(
        agent_id=agent_id,
        role=role,
        parent_id=None,
        session_id="sess-1",
        token_hash="fake",
        created_at=monotonic(),
        killed=killed,
    )


@pytest.fixture
def agents_client():
    engine = MagicMock()
    engine.config = SafeClawConfig(admin_password="")
    engine.audit = MagicMock()
    engine.audit.get_recent_records.return_value = []
    engine.agent_registry = MagicMock()
    engine.agent_registry.list_agents.return_value = [
        _make_agent("agent-1", "developer"),
        _make_agent("agent-2", "researcher", killed=True),
    ]
    engine.session_tracker = MagicMock()
    engine.session_tracker._sessions = {}
    engine.kg = MagicMock()
    engine.kg.__len__ = MagicMock(return_value=42)
    engine.llm_client = None
    engine.security_reviewer = None
    engine.classification_observer = None
    engine.explainer = None
    engine.temp_permissions = MagicMock()
    engine.temp_permissions.list_grants.return_value = []

    def get_engine():
        return engine

    app = create_dashboard(get_engine)
    return TestClient(app), engine


def test_agents_page_renders(agents_client):
    """Agents page shows registered agents."""
    client, _ = agents_client
    resp = client.get("/agents")
    assert resp.status_code == 200
    assert "agent-1" in resp.text
    assert "agent-2" in resp.text
    assert "developer" in resp.text


def test_agents_page_shows_status(agents_client):
    """Agents page shows active/killed status badges."""
    client, _ = agents_client
    resp = client.get("/agents")
    assert "ACTIVE" in resp.text
    assert "KILLED" in resp.text


def test_kill_agent(agents_client):
    """POST to kill endpoint kills an agent."""
    client, engine = agents_client
    engine.agent_registry.kill_agent.return_value = True
    resp = client.post("/agents/agent-1/kill", follow_redirects=False)
    assert resp.status_code in (200, 303)
    engine.agent_registry.kill_agent.assert_called_with("agent-1")


def test_revive_agent(agents_client):
    """POST to revive endpoint revives an agent."""
    client, engine = agents_client
    engine.agent_registry.revive_agent.return_value = True
    resp = client.post("/agents/agent-2/revive", follow_redirects=False)
    assert resp.status_code in (200, 303)
    engine.agent_registry.revive_agent.assert_called_with("agent-2")
```

**Step 2: Run tests to verify they fail**

Run: `cd safeclaw-service && python -m pytest tests/test_dashboard_agents.py -v`
Expected: FAIL

**Step 3: Implement the agents page**

Replace `safeclaw/dashboard/pages/agents.py`:

```python
"""Agent management page."""

from fasthtml.common import *

from safeclaw.dashboard.components import AgentStatusBadge, Page


def register(rt, get_engine):

    @rt("/agents")
    def agents_page():
        engine = get_engine()
        agents = engine.agent_registry.list_agents()

        return Page(
            "Agents",
            Div(
                H2("Registered Agents"),
                _agents_table(agents) if agents else Div(
                    P("No agents registered yet."),
                    P("Agents are registered when they connect to SafeClaw via the plugin.", cls="text-sm text-muted"),
                    cls="empty-state",
                ),
                cls="panel",
            ),
            active="agents",
        )

    @rt("/agents/{agent_id}/kill", methods=["POST"])
    def kill_agent(agent_id: str):
        engine = get_engine()
        engine.agent_registry.kill_agent(agent_id)
        return RedirectResponse("/agents", status_code=303)

    @rt("/agents/{agent_id}/revive", methods=["POST"])
    def revive_agent(agent_id: str):
        engine = get_engine()
        engine.agent_registry.revive_agent(agent_id)
        return RedirectResponse("/agents", status_code=303)

    @rt("/agents/{agent_id}/grant", methods=["POST"])
    def grant_permission(agent_id: str, permission: str, duration: int = 300):
        engine = get_engine()
        engine.temp_permissions.grant(
            agent_id=agent_id,
            permission=permission,
            duration_seconds=duration,
        )
        return RedirectResponse("/agents", status_code=303)

    def _agents_table(agents):
        return Table(
            Thead(Tr(
                Th("Agent ID"), Th("Role"), Th("Session"), Th("Parent"),
                Th("Status"), Th("Actions"),
            )),
            Tbody(*[
                Tr(
                    Td(a.agent_id, cls="mono"),
                    Td(a.role),
                    Td(a.session_id[:8] + "…" if len(a.session_id) > 8 else a.session_id, cls="mono text-sm"),
                    Td(a.parent_id or "—", cls="mono text-sm text-muted"),
                    Td(AgentStatusBadge(a.killed)),
                    Td(
                        Form(
                            Button(
                                "Revive" if a.killed else "Kill",
                                type="submit",
                                cls=f"btn btn-sm {'btn-primary' if a.killed else 'btn-danger'}",
                            ),
                            method="post",
                            action=f"/agents/{a.agent_id}/{'revive' if a.killed else 'kill'}",
                            style="display: inline;",
                        ),
                    ),
                )
                for a in agents
            ]),
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd safeclaw-service && python -m pytest tests/test_dashboard_agents.py -v`
Expected: All tests pass

**Step 5: Run full test suite**

Run: `cd safeclaw-service && python -m pytest tests/ -x -q`
Expected: All tests pass

**Step 6: Commit**

```bash
cd safeclaw-service
git add safeclaw/dashboard/pages/agents.py tests/test_dashboard_agents.py
git commit -m "feat(dashboard): agents page with kill/revive controls"
```

---

### Task 6: Settings page

**Files:**
- Modify: `safeclaw-service/safeclaw/dashboard/pages/settings.py`
- Test: `safeclaw-service/tests/test_dashboard_settings.py`

**Step 1: Write the failing tests**

Create `tests/test_dashboard_settings.py`:

```python
"""Tests for settings dashboard page."""

import pytest
from unittest.mock import MagicMock
from starlette.testclient import TestClient

from safeclaw.config import SafeClawConfig
from safeclaw.dashboard.app import create_dashboard


@pytest.fixture
def settings_client():
    engine = MagicMock()
    engine.config = SafeClawConfig(admin_password="", mistral_api_key="sk-test-123")
    engine.audit = MagicMock()
    engine.audit.get_recent_records.return_value = []
    engine.agent_registry = MagicMock()
    engine.agent_registry.list_agents.return_value = []
    engine.session_tracker = MagicMock()
    engine.session_tracker._sessions = {}
    engine.kg = MagicMock()
    engine.kg.__len__ = MagicMock(return_value=42)
    engine.llm_client = MagicMock()
    engine.security_reviewer = MagicMock()
    engine.classification_observer = MagicMock()
    engine.explainer = MagicMock()

    def get_engine():
        return engine

    app = create_dashboard(get_engine)
    return TestClient(app), engine


def test_settings_page_renders(settings_client):
    """Settings page shows configuration."""
    client, _ = settings_client
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert "Mistral API Key" in resp.text or "API Key" in resp.text


def test_settings_shows_llm_status(settings_client):
    """Settings page shows LLM feature status."""
    client, _ = settings_client
    resp = client.get("/settings")
    assert "Security Reviewer" in resp.text


def test_settings_shows_config_values(settings_client):
    """Settings page shows current config values."""
    client, _ = settings_client
    resp = client.get("/settings")
    assert "8420" in resp.text  # port


def test_reload_ontologies(settings_client):
    """Reload button triggers engine reload."""
    client, engine = settings_client
    resp = client.post("/settings/reload", follow_redirects=False)
    assert resp.status_code in (200, 303)
    engine.reload.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `cd safeclaw-service && python -m pytest tests/test_dashboard_settings.py -v`
Expected: FAIL

**Step 3: Implement the settings page**

Replace `safeclaw/dashboard/pages/settings.py`:

```python
"""Settings page."""

import json
import os
from pathlib import Path

from fasthtml.common import *

from safeclaw.dashboard.components import Page, StatCard


def register(rt, get_engine):

    @rt("/settings")
    def settings_page(sess):
        engine = get_engine()
        config = engine.config
        flash = sess.pop("settings_flash", None)

        return Page(
            "Settings",
            Div(P(flash, cls="flash-success") if flash else ""),
            # API Key section
            Div(
                H2("Mistral API Key"),
                _api_key_section(config),
                cls="panel",
            ),
            # LLM feature status
            Div(
                H2("LLM Features"),
                _llm_status(engine),
                cls="panel",
            ),
            # Ontology reload
            Div(
                H2("Ontology Management"),
                P(f"Loaded triples: {len(engine.kg):,}", cls="text-sm"),
                Form(
                    Button("Reload Ontologies", type="submit", cls="btn btn-outline"),
                    method="post", action="/settings/reload",
                ),
                cls="panel mt-16",
            ),
            # Current config
            Div(
                H2("Current Configuration"),
                _config_display(config),
                cls="panel",
            ),
            active="settings",
        )

    @rt("/settings/reload", methods=["POST"])
    def reload_ontologies(sess):
        engine = get_engine()
        engine.reload()
        sess["settings_flash"] = "Ontologies reloaded successfully."
        return RedirectResponse("/settings", status_code=303)

    @rt("/settings/api-key", methods=["POST"])
    def set_api_key(api_key: str, sess):
        """Set the Mistral API key at runtime via env var."""
        if api_key:
            os.environ["SAFECLAW_MISTRAL_API_KEY"] = api_key
            sess["settings_flash"] = "API key updated. Restart the service to apply."
        return RedirectResponse("/settings", status_code=303)

    def _api_key_section(config):
        has_key = bool(config.mistral_api_key)
        if has_key:
            masked = config.mistral_api_key[:4] + "…" + config.mistral_api_key[-4:]
            status = Span("Configured", cls="text-green")
        else:
            masked = "Not set"
            status = Span("Not configured", cls="text-red")

        return Div(
            P("Status: ", status, cls="text-sm"),
            P(f"Current: ", Span(masked, cls="mono"), cls="text-sm text-muted"),
            Form(
                Div(
                    Label("New API Key", fr="api_key"),
                    Input(type="password", name="api_key", id="api_key",
                          placeholder="sk-..."),
                    cls="form-group",
                ),
                Button("Update Key", type="submit", cls="btn btn-primary btn-sm"),
                P("Note: Changes take effect after service restart.", cls="text-sm text-muted"),
                method="post", action="/settings/api-key",
            ),
        )

    def _llm_status(engine):
        features = [
            ("Security Reviewer", engine.security_reviewer is not None),
            ("Classification Observer", engine.classification_observer is not None),
            ("Decision Explainer", engine.explainer is not None),
            ("LLM Client", engine.llm_client is not None),
        ]
        return Table(
            Thead(Tr(Th("Feature"), Th("Status"))),
            Tbody(*[
                Tr(
                    Td(name),
                    Td(Span("Active", cls="text-green") if active else Span("Inactive", cls="text-muted")),
                )
                for name, active in features
            ]),
        )

    def _config_display(config):
        fields = [
            ("host", config.host),
            ("port", str(config.port)),
            ("data_dir", str(config.data_dir)),
            ("ontology_dir", str(config.get_ontology_dir())),
            ("audit_dir", str(config.get_audit_dir())),
            ("require_auth", str(config.require_auth)),
            ("run_reasoner_on_startup", str(config.run_reasoner_on_startup)),
            ("mistral_model", config.mistral_model),
            ("mistral_model_large", config.mistral_model_large),
            ("mistral_timeout_ms", str(config.mistral_timeout_ms)),
            ("llm_security_review_enabled", str(config.llm_security_review_enabled)),
            ("llm_classification_observe", str(config.llm_classification_observe)),
            ("log_level", config.log_level),
        ]
        return Div(
            *[Div(
                Span(key, cls="config-key"),
                Span(val, cls="config-val"),
            ) for key, val in fields],
            cls="config-grid",
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd safeclaw-service && python -m pytest tests/test_dashboard_settings.py -v`
Expected: All tests pass

**Step 5: Run full test suite**

Run: `cd safeclaw-service && python -m pytest tests/ -x -q`
Expected: All tests pass

**Step 6: Commit**

```bash
cd safeclaw-service
git add safeclaw/dashboard/pages/settings.py tests/test_dashboard_settings.py
git commit -m "feat(dashboard): settings page with API key management and config view"
```

---

### Task 7: Final verification and lint

**Files:**
- All dashboard files

**Step 1: Run ruff check**

Run: `cd safeclaw-service && ruff check safeclaw/dashboard/ tests/test_dashboard*.py`
Expected: No errors. If errors found, fix them.

**Step 2: Run ruff format**

Run: `cd safeclaw-service && ruff format safeclaw/dashboard/ tests/test_dashboard*.py`
Expected: All files formatted

**Step 3: Run full test suite**

Run: `cd safeclaw-service && python -m pytest tests/ -v`
Expected: All tests pass (270+ existing + new dashboard tests)

**Step 4: Quick manual smoke test**

Run: `cd safeclaw-service && python -c "
from safeclaw.main import app
from starlette.testclient import TestClient
c = TestClient(app)
r = c.get('/admin/', follow_redirects=False)
print(f'Status: {r.status_code}')
print('Dashboard mount working' if r.status_code in (200, 303) else 'FAILED')
"`
Expected: `Status: 303` (redirect to login, since no password = dev mode would be 200 but default config has no engine yet)

**Step 5: Commit if any fixes were needed**

```bash
cd safeclaw-service
git add -A
git commit -m "chore(dashboard): lint and format fixes"
```

---
