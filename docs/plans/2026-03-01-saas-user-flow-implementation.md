# SaaS User Flow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable end-to-end SaaS user flow — GitHub OAuth signup, onboarding wizard, API key generation, and plugin connection to a shared SafeClaw service.

**Architecture:** Single-process deployment where the FastHTML landing app mounts the FastAPI service at `/api/v1`. Both share a SQLite database for users and API keys. The service's `APIKeyManager` is replaced with a `SQLiteAPIKeyManager` that reads from the shared DB. A two-step onboarding wizard guides first-time users through autonomy selection and API key setup.

**Tech Stack:** FastHTML, FastAPI (mounted as sub-app), fastlite/SQLite, MonsterUI, HTMX

---

### Task 1: Add onboarded and autonomy_level columns to User model

**Files:**
- Modify: `safeclaw-landing/db.py:9-18`

**Step 1: Update the User class**

In `safeclaw-landing/db.py`, add two fields to the `User` class:

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
```

The `transform=True` on `db.create(User, pk="id", transform=True)` will auto-migrate the schema.

**Step 2: Verify the migration works**

Run: `cd safeclaw-landing && python -c "from db import users; print([c for c in users.columns_dict])"`

Expected: dict includes `onboarded` and `autonomy_level` keys.

**Step 3: Commit**

```bash
git add safeclaw-landing/db.py
git commit -m "feat(landing): add onboarded and autonomy_level columns to User model"
```

---

### Task 2: Create the onboarding wizard page

**Files:**
- Create: `safeclaw-landing/dashboard/onboard.py`

**Step 1: Create the onboarding wizard component**

Create `safeclaw-landing/dashboard/onboard.py`:

```python
"""Onboarding wizard — shown to first-time users after GitHub OAuth."""

from monsterui.all import *


def OnboardStep1():
    """Step 1: Choose autonomy level."""
    levels = [
        ("cautious", "Cautious",
         "Confirms before any write, delete, or external action. "
         "Best for production environments."),
        ("moderate", "Moderate",
         "Confirms before deletes and irreversible actions. "
         "Allows reads and safe writes automatically."),
        ("autonomous", "Autonomous",
         "Minimal confirmations. Only blocks policy violations "
         "and critical-risk actions."),
    ]
    cards = []
    for value, label, desc in levels:
        checked = "checked" if value == "moderate" else ""
        cards.append(
            Label(
                Card(
                    DivLAligned(
                        Input(type="radio", name="autonomy_level", value=value,
                              cls="uk-radio", **({checked: True} if checked else {})),
                        H4(label),
                    ),
                    P(desc, cls=TextPresets.muted_sm),
                ),
                style="cursor:pointer; display:block;",
            )
        )
    return Div(
        H2("Welcome to SafeClaw"),
        P("Choose how much control SafeClaw should have over your AI agent's actions.",
          cls=TextPresets.muted_sm),
        Form(
            Div(*cards, cls="space-y-3"),
            Button("Next", cls=ButtonT.primary, type="submit"),
            hx_post="/dashboard/onboard/step1",
            hx_target="#onboard-content",
            hx_swap="innerHTML",
            cls="space-y-6",
        ),
        id="onboard-content",
    )


def OnboardStep2(raw_key: str):
    """Step 2: Show generated API key + install instructions."""
    return Div(
        H2("Your API Key"),
        P("Copy this key now — it won't be shown again.",
          cls=TextPresets.muted_sm),
        Card(
            Pre(Code(raw_key), style="word-break:break-all; font-size:1.1em;"),
            cls="uk-alert-success",
        ),
        H3("Connect your OpenClaw agent"),
        Div(
            P("1. Install the SafeClaw plugin:"),
            Pre(Code("openclaw plugins install openclaw-safeclaw-plugin")),
            P("2. Set your API key:"),
            Pre(Code(f"export SAFECLAW_API_KEY={raw_key}")),
            P("That's it — SafeClaw will govern your agent's actions automatically.",
              cls=TextPresets.muted_sm),
            cls="space-y-2",
        ),
        Form(
            Button("Go to Dashboard", cls=ButtonT.primary, type="submit"),
            action="/dashboard/onboard/done",
            method="post",
        ),
        id="onboard-content",
    )
```

**Step 2: Commit**

```bash
git add safeclaw-landing/dashboard/onboard.py
git commit -m "feat(landing): add onboarding wizard component"
```

---

### Task 3: Add onboarding routes and redirect logic

**Files:**
- Modify: `safeclaw-landing/main.py:1307-1329` (auth_callback)
- Modify: `safeclaw-landing/main.py:1346-1354` (dashboard route)
- Modify: `safeclaw-landing/main.py:1338-1344` (imports section)

**Step 1: Add the onboard route import and beforeware skip**

In `safeclaw-landing/main.py`, update the beforeware skip list to include `/dashboard/onboard`:

The `bware` skip list already covers `/dashboard` implicitly — no, it doesn't. The `user_auth_before` function checks `path.startswith("/dashboard")`, so `/dashboard/onboard` will be auth-protected. That's correct — onboard needs a logged-in user. No change to beforeware needed.

**Step 2: Update auth_callback to redirect first-time users**

In `safeclaw-landing/main.py`, change the `auth_callback` function. Replace:

```python
    sess["auth"] = user.id
    return RedirectResponse("/dashboard", status_code=303)
```

with:

```python
    sess["auth"] = user.id
    if not user.onboarded:
        return RedirectResponse("/dashboard/onboard", status_code=303)
    return RedirectResponse("/dashboard", status_code=303)
```

**Step 3: Add onboard routes**

Add these routes after the dashboard routes section in `main.py`. Add the import at the top of the dashboard routes section:

```python
from dashboard.onboard import OnboardStep1, OnboardStep2
```

Then add the routes:

```python
@rt("/dashboard/onboard")
def dashboard_onboard(req, sess):
    user = req.scope.get("user")
    if user.onboarded:
        return RedirectResponse("/dashboard", status_code=303)
    return (
        Title("Get Started — SafeClaw"),
        *MUITheme.blue.headers(),
        DashboardLayout("Get Started", OnboardStep1(), user=user, active="onboard"),
    )


@rt("/dashboard/onboard/step1")
def onboard_step1(req, sess, autonomy_level: str = "moderate"):
    user = req.scope.get("user")
    # Save autonomy level
    user.autonomy_level = autonomy_level
    users.update(user)
    # Generate default API key
    raw_key, key_id = generate_api_key()
    api_keys.insert(
        user_id=user.id,
        key_id=key_id,
        key_hash=hash_key(raw_key),
        label="Default",
        scope="full",
        created_at=datetime.now(timezone.utc).isoformat(),
        is_active=True,
    )
    return OnboardStep2(raw_key)


@rt("/dashboard/onboard/done")
def onboard_done(req, sess):
    user = req.scope.get("user")
    user.onboarded = True
    users.update(user)
    return RedirectResponse("/dashboard", status_code=303)
```

**Step 4: Verify the flow manually**

Start the landing app and test:
1. Login via GitHub (or simulate with a test user)
2. First login should redirect to `/dashboard/onboard`
3. Step 1: select autonomy level, click Next
4. Step 2: see API key and install instructions, click Done
5. Redirects to `/dashboard`
6. Subsequent logins should go directly to `/dashboard`

**Step 5: Commit**

```bash
git add safeclaw-landing/main.py
git commit -m "feat(landing): add onboarding wizard routes and first-login redirect"
```

---

### Task 4: Create SQLiteAPIKeyManager for the SafeClaw service

**Files:**
- Modify: `safeclaw-service/safeclaw/auth/api_key.py:21-81`
- Test: `safeclaw-service/tests/test_phase5.py` (existing API key tests)

**Step 1: Write the failing test**

Add to `safeclaw-service/tests/test_phase5.py`, in a new class after `TestAPIKeyManager`:

```python
class TestSQLiteAPIKeyManager:
    """Tests for SQLiteAPIKeyManager backed by a real SQLite file."""

    def test_validate_key_from_db(self, tmp_path):
        import hashlib
        import secrets
        import sqlite3

        from safeclaw.auth.api_key import SQLiteAPIKeyManager

        db_path = tmp_path / "safeclaw.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE api_keys ("
            "  id INTEGER PRIMARY KEY,"
            "  user_id INTEGER,"
            "  key_id TEXT,"
            "  key_hash TEXT,"
            "  label TEXT,"
            "  scope TEXT,"
            "  created_at TEXT,"
            "  is_active BOOLEAN"
            ")"
        )
        raw_key = "sc_" + secrets.token_urlsafe(32)
        key_id = raw_key[:12]
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        conn.execute(
            "INSERT INTO api_keys (user_id, key_id, key_hash, label, scope, created_at, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, key_id, key_hash, "test", "full", "2026-01-01", True),
        )
        conn.commit()
        conn.close()

        mgr = SQLiteAPIKeyManager(str(db_path))
        result = mgr.validate_key(raw_key)
        assert result is not None
        assert result.key_id == key_id
        assert result.scope == "full"

    def test_validate_revoked_key_returns_none(self, tmp_path):
        import hashlib
        import secrets
        import sqlite3

        from safeclaw.auth.api_key import SQLiteAPIKeyManager

        db_path = tmp_path / "safeclaw.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE api_keys ("
            "  id INTEGER PRIMARY KEY,"
            "  user_id INTEGER,"
            "  key_id TEXT,"
            "  key_hash TEXT,"
            "  label TEXT,"
            "  scope TEXT,"
            "  created_at TEXT,"
            "  is_active BOOLEAN"
            ")"
        )
        raw_key = "sc_" + secrets.token_urlsafe(32)
        key_id = raw_key[:12]
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        conn.execute(
            "INSERT INTO api_keys (user_id, key_id, key_hash, label, scope, created_at, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, key_id, key_hash, "test", "full", "2026-01-01", False),
        )
        conn.commit()
        conn.close()

        mgr = SQLiteAPIKeyManager(str(db_path))
        result = mgr.validate_key(raw_key)
        assert result is None

    def test_validate_wrong_key_returns_none(self, tmp_path):
        import sqlite3

        from safeclaw.auth.api_key import SQLiteAPIKeyManager

        db_path = tmp_path / "safeclaw.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE api_keys ("
            "  id INTEGER PRIMARY KEY,"
            "  user_id INTEGER,"
            "  key_id TEXT,"
            "  key_hash TEXT,"
            "  label TEXT,"
            "  scope TEXT,"
            "  created_at TEXT,"
            "  is_active BOOLEAN"
            ")"
        )
        conn.commit()
        conn.close()

        mgr = SQLiteAPIKeyManager(str(db_path))
        result = mgr.validate_key("sc_nonexistent12345678901234567890")
        assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `cd safeclaw-service && source .venv/bin/activate && python -m pytest tests/test_phase5.py::TestSQLiteAPIKeyManager -v`

Expected: FAIL with `ImportError: cannot import name 'SQLiteAPIKeyManager'`

**Step 3: Implement SQLiteAPIKeyManager**

Add to `safeclaw-service/safeclaw/auth/api_key.py`, after the existing `APIKeyManager` class:

```python
class SQLiteAPIKeyManager:
    """API key manager backed by a shared SQLite database.

    Reads from the same api_keys table that the landing site writes to.
    Used in SaaS mode when db_path is configured.
    """

    def __init__(self, db_path: str):
        self._db_path = db_path

    def _connect(self):
        import sqlite3
        return sqlite3.connect(self._db_path)

    def validate_key(self, raw_key: str) -> APIKey | None:
        """Validate an API key by looking it up in SQLite."""
        key_id = raw_key[:12]
        key_hash = APIKeyManager.hash_key(raw_key)

        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT key_id, key_hash, scope, created_at, is_active, user_id "
                "FROM api_keys WHERE key_id = ? AND is_active = 1",
                (key_id,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return None

        db_key_id, db_key_hash, scope, created_at, is_active, user_id = row
        if not hmac.compare_digest(key_hash, db_key_hash):
            return None

        return APIKey(
            key_id=db_key_id,
            key_hash=db_key_hash,
            org_id=str(user_id),
            scope=scope,
            created_at=created_at,
            is_active=bool(is_active),
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd safeclaw-service && source .venv/bin/activate && python -m pytest tests/test_phase5.py::TestSQLiteAPIKeyManager -v`

Expected: 3 passed

**Step 5: Run all tests to check for regressions**

Run: `cd safeclaw-service && python -m pytest tests/ -v`

Expected: All tests pass

**Step 6: Commit**

```bash
git add safeclaw-service/safeclaw/auth/api_key.py safeclaw-service/tests/test_phase5.py
git commit -m "feat(service): add SQLiteAPIKeyManager for shared DB key validation"
```

---

### Task 5: Wire SQLiteAPIKeyManager into the service

**Files:**
- Modify: `safeclaw-service/safeclaw/config.py` (add db_path setting)
- Modify: `safeclaw-service/safeclaw/main.py:57-58` (middleware setup)

**Step 1: Add db_path to SafeClawConfig**

Check the current config and add a `db_path` field. In `safeclaw-service/safeclaw/config.py`, add:

```python
    db_path: str = ""  # Path to shared SQLite DB (SaaS mode)
```

This maps to the `SAFECLAW_DB_PATH` env var.

**Step 2: Update middleware initialization in main.py**

In `safeclaw-service/safeclaw/main.py`, replace line 58:

```python
app.add_middleware(APIKeyAuthMiddleware, require_auth=_config.require_auth)
```

with:

```python
# Auth middleware — uses SQLite key manager when db_path is configured
_api_key_manager = None
if _config.require_auth and _config.db_path:
    from safeclaw.auth.api_key import SQLiteAPIKeyManager
    _api_key_manager = SQLiteAPIKeyManager(_config.db_path)
app.add_middleware(
    APIKeyAuthMiddleware,
    api_key_manager=_api_key_manager,
    require_auth=_config.require_auth,
)
```

**Step 3: Run all tests**

Run: `cd safeclaw-service && python -m pytest tests/ -v`

Expected: All tests pass (default `db_path=""` means no change to existing behavior)

**Step 4: Commit**

```bash
git add safeclaw-service/safeclaw/config.py safeclaw-service/safeclaw/main.py
git commit -m "feat(service): wire SQLiteAPIKeyManager into middleware when db_path is set"
```

---

### Task 6: Mount FastAPI service inside the landing app

**Files:**
- Modify: `safeclaw-landing/main.py:20-30` (app setup area)

**Step 1: Mount the FastAPI app**

At the end of `safeclaw-landing/main.py` (after all routes), add:

```python
# ── Mount SafeClaw Service ──
import os

if os.environ.get("SAFECLAW_MOUNT_SERVICE", "").lower() in ("1", "true", "yes"):
    import sys
    from pathlib import Path

    # Add safeclaw-service to Python path
    service_dir = Path(__file__).parent.parent / "safeclaw-service"
    sys.path.insert(0, str(service_dir))

    # Set required env vars for the service
    db_path = str(Path(__file__).parent / "data" / "safeclaw.db")
    os.environ.setdefault("SAFECLAW_DB_PATH", db_path)
    os.environ.setdefault("SAFECLAW_REQUIRE_AUTH", "true")

    from safeclaw.main import app as safeclaw_api
    app.mount("/api/v1", safeclaw_api)
```

This is opt-in via the `SAFECLAW_MOUNT_SERVICE=true` env var. When disabled (default), the landing site and service run separately as before.

**Step 2: Test locally**

Run: `cd safeclaw-landing && SAFECLAW_MOUNT_SERVICE=true python main.py`

Verify: `curl http://localhost:5001/api/v1/health` returns `{"status":"ok",...}`

**Step 3: Commit**

```bash
git add safeclaw-landing/main.py
git commit -m "feat(landing): optionally mount SafeClaw service at /api/v1"
```

---

### Task 7: Update QuickStart and docs

**Files:**
- Modify: `safeclaw-landing/main.py` (QuickStart component, ~line 249-270)
- Modify: `safeclaw-landing/main.py` (DocsPage, docs section)

**Step 1: Update QuickStart SaaS section**

In the QuickStart component, update the SaaS section to mention the sign-up step. Find the SaaS terminal section (~line 258) and update it to:

```python
            Div(
                Div(
                    Span("# ", cls="prompt"),
                    Span("Sign up at safeclaw.eu and get your API key", cls="comment"),
                ),
                Div(
                    Span("$ ", cls="prompt"),
                    Span("openclaw plugins install openclaw-safeclaw-plugin", cls="cmd"),
                ),
                Div(
                    Span("$ ", cls="prompt"),
                    Span("export SAFECLAW_API_KEY=sc_your_key_here", cls="cmd"),
                ),
                cls="quickstart-terminal",
            ),
```

**Step 2: Add SaaS onboarding section to /docs**

Add a new docs section after the Configuration Reference section (~section 18). Insert before the closing `cls="docs-content"`:

```python
                # ── 19. SaaS Onboarding ──
                DocsSection("saas", "SaaS Onboarding",
                    P("SafeClaw is available as a hosted service at ",
                      Code("safeclaw.eu"), ". No server setup required."),
                    H3("1. Create an account", cls="docs-h3"),
                    P("Click ", Strong("Get Started"), " on the landing page. "
                      "Sign in with your GitHub account."),
                    H3("2. Onboarding wizard", cls="docs-h3"),
                    P("First-time users are guided through a two-step wizard:"),
                    Ul(
                        Li(Strong("Autonomy level"), " — choose how much control SafeClaw has "
                           "(cautious, moderate, or autonomous)"),
                        Li(Strong("API key"), " — a key is generated automatically. "
                           "Copy it immediately; it is shown only once."),
                        cls="docs-list",
                    ),
                    H3("3. Connect your agent", cls="docs-h3"),
                    P("Install the plugin and set your key:"),
                    Div(
                        Pre(
                            "$ openclaw plugins install openclaw-safeclaw-plugin\n"
                            "$ export SAFECLAW_API_KEY=sc_your_key_here",
                            cls="docs-pre",
                        ),
                    ),
                    P("The plugin connects to ", Code("https://api.safeclaw.eu/api/v1"),
                      " by default. No URL configuration needed."),
                    H3("4. Manage from the dashboard", cls="docs-h3"),
                    P("After onboarding, the dashboard at ", Code("safeclaw.eu/dashboard"),
                      " lets you:"),
                    Ul(
                        Li("Create and revoke API keys"),
                        Li("Set preferences (confirm before delete, max files per commit)"),
                        Li("View connected agents"),
                        cls="docs-list",
                    ),
                ),
```

Also add the nav entry to `DocsToc()`:

```python
        ("saas", "SaaS Onboarding"),
```

**Step 3: Commit**

```bash
git add safeclaw-landing/main.py
git commit -m "docs(landing): update QuickStart and add SaaS Onboarding section to /docs"
```

---

### Task 8: Update dashboard health check default URL

**Files:**
- Modify: `safeclaw-landing/main.py:1357-1380` (health_check route)

**Step 1: Fix the hardcoded localhost default**

In the `health_check` route, change the default service URL to use the mounted service path when available:

```python
@rt("/dashboard/health-check")
async def health_check(req, sess):
    """HTMX partial: check service health."""
    import httpx
    import os
    try:
        if os.environ.get("SAFECLAW_MOUNT_SERVICE", "").lower() in ("1", "true", "yes"):
            # Service is mounted in the same process — use internal URL
            service_url = f"{req.url.scheme}://{req.url.netloc}/api/v1"
        else:
            service_url = sess.get("service_url", "http://localhost:8420")
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{service_url}/health")
```

The rest of the function stays the same.

**Step 2: Commit**

```bash
git add safeclaw-landing/main.py
git commit -m "fix(landing): use mounted service URL for health check in SaaS mode"
```

---

### Task 9: Lint and final verification

**Step 1: Lint the service**

Run: `cd safeclaw-service && source .venv/bin/activate && ruff check safeclaw/ tests/`

Fix any issues.

**Step 2: Run all service tests**

Run: `cd safeclaw-service && python -m pytest tests/ -v`

Expected: All tests pass.

**Step 3: Check landing app syntax**

Run: `cd safeclaw-landing && python -c "import ast; ast.parse(open('main.py').read()); print('OK')"`

Expected: `OK`

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: lint and verification fixes for SaaS user flow"
```
