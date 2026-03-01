# Audit Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show all governance decisions in the user's safeclaw.eu dashboard, with a preference toggle to disable logging.

**Architecture:** The SafeClaw service writes decision summaries to an `audit_log` table in the shared SQLite DB after each evaluation. The landing site dashboard reads from this table. A per-user `audit_logging` column controls whether the service writes.

**Tech Stack:** Python, FastHTML, MonsterUI, SQLite (fastlite on landing, raw sqlite3 on service), HTMX

---

### Task 1: Add `audit_logging` column to landing User model

**Files:**
- Modify: `safeclaw-landing/db.py:10-29`

**Step 1: Add the field**

Add `audit_logging: bool = True` to the `User` class, after `admin_password`:

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
```

The `transform=True` on `db.create(User, ...)` at line 42 will auto-migrate the table.

**Step 2: Verify the landing app still starts**

Run: `cd safeclaw-landing && python -c "from db import users; print(users)"`
Expected: `<Table user (...)>` with `audit_logging` column

**Step 3: Commit**

```bash
git add safeclaw-landing/db.py
git commit -m "feat(landing): add audit_logging column to User model"
```

---

### Task 2: Add `audit_log` table to landing DB

**Files:**
- Modify: `safeclaw-landing/db.py`

**Step 1: Add the AuditLog class and table creation**

After the `APIKey` class and before `users = db.create(...)`, add:

```python
class AuditLog:
    id: int
    user_id: int
    timestamp: str
    session_id: str
    tool_name: str
    params_summary: str
    decision: str
    risk_level: str
    reason: str
    elapsed_ms: float
```

After `api_keys = db.create(...)`, add:

```python
audit_log = db.create(AuditLog, pk="id", transform=True)
```

**Step 2: Verify**

Run: `cd safeclaw-landing && python -c "from db import audit_log; print(audit_log)"`
Expected: `<Table audit_log (...)>`

**Step 3: Commit**

```bash
git add safeclaw-landing/db.py
git commit -m "feat(landing): add audit_log table"
```

---

### Task 3: Add audit_log table and write methods to SQLiteAPIKeyManager

**Files:**
- Modify: `safeclaw-service/safeclaw/auth/api_key.py:83-167`
- Test: `safeclaw-service/tests/test_api_key.py` (or inline test)

**Step 1: Write the failing test**

Create/append to `safeclaw-service/tests/test_audit_db.py`:

```python
"""Tests for audit DB logging in SQLiteAPIKeyManager."""

import sqlite3
import tempfile
import os
import pytest

from safeclaw.auth.api_key import SQLiteAPIKeyManager


@pytest.fixture
def db_with_user(tmp_path):
    """Create a writable SQLite DB with a user who has audit_logging enabled."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, mistral_api_key TEXT DEFAULT '', audit_logging INTEGER DEFAULT 1)")
    conn.execute("INSERT INTO users (id, audit_logging) VALUES (1, 1)")
    conn.execute("CREATE TABLE api_keys (id INTEGER PRIMARY KEY, user_id INTEGER, key_id TEXT, key_hash TEXT, label TEXT, scope TEXT, created_at TEXT, is_active BOOLEAN)")
    conn.execute("CREATE TABLE audit_log (id INTEGER PRIMARY KEY, user_id INTEGER, timestamp TEXT, session_id TEXT, tool_name TEXT, params_summary TEXT, decision TEXT, risk_level TEXT, reason TEXT, elapsed_ms REAL)")
    conn.commit()
    conn.close()
    return db_path


def test_is_audit_logging_enabled_returns_true(db_with_user):
    mgr = SQLiteAPIKeyManager(db_with_user)
    assert mgr.is_audit_logging_enabled("1") is True


def test_is_audit_logging_enabled_returns_false(db_with_user):
    conn = sqlite3.connect(db_with_user)
    conn.execute("UPDATE users SET audit_logging = 0 WHERE id = 1")
    conn.commit()
    conn.close()
    mgr = SQLiteAPIKeyManager(db_with_user)
    assert mgr.is_audit_logging_enabled("1") is False


def test_is_audit_logging_enabled_missing_user(db_with_user):
    mgr = SQLiteAPIKeyManager(db_with_user)
    assert mgr.is_audit_logging_enabled("999") is True  # default: enabled


def test_log_audit_decision_inserts_row(db_with_user):
    mgr = SQLiteAPIKeyManager(db_with_user)
    mgr.log_audit_decision(
        user_id="1",
        timestamp="2026-03-01T23:00:00Z",
        session_id="sess-1",
        tool_name="bash",
        params_summary='{"command": "rm -rf /"}',
        decision="blocked",
        risk_level="critical",
        reason="Dangerous command",
        elapsed_ms=12.5,
    )
    conn = sqlite3.connect(db_with_user)
    rows = conn.execute("SELECT * FROM audit_log WHERE user_id = 1").fetchall()
    assert len(rows) == 1
    assert rows[0][4] == "bash"  # tool_name
    assert rows[0][6] == "blocked"  # decision


def test_log_audit_decision_skips_when_disabled(db_with_user):
    conn = sqlite3.connect(db_with_user)
    conn.execute("UPDATE users SET audit_logging = 0 WHERE id = 1")
    conn.commit()
    conn.close()
    mgr = SQLiteAPIKeyManager(db_with_user)
    mgr.log_audit_decision(
        user_id="1",
        timestamp="2026-03-01T23:00:00Z",
        session_id="sess-1",
        tool_name="bash",
        params_summary="{}",
        decision="allowed",
        risk_level="safe",
        reason="passed",
        elapsed_ms=1.0,
    )
    conn = sqlite3.connect(db_with_user)
    rows = conn.execute("SELECT * FROM audit_log WHERE user_id = 1").fetchall()
    assert len(rows) == 0
```

**Step 2: Run test to verify it fails**

Run: `cd safeclaw-service && source .venv/bin/activate && python -m pytest tests/test_audit_db.py -v`
Expected: FAIL — `AttributeError: 'SQLiteAPIKeyManager' object has no attribute 'is_audit_logging_enabled'`

**Step 3: Implement the methods**

Add to `SQLiteAPIKeyManager` in `safeclaw-service/safeclaw/auth/api_key.py`:

1. In `__init__`, add the `audit_log` table creation (inside the existing try/except block):

```python
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS audit_log ("
            "  id INTEGER PRIMARY KEY,"
            "  user_id INTEGER,"
            "  timestamp TEXT,"
            "  session_id TEXT,"
            "  tool_name TEXT,"
            "  params_summary TEXT,"
            "  decision TEXT,"
            "  risk_level TEXT,"
            "  reason TEXT,"
            "  elapsed_ms REAL"
            ")"
        )
```

2. Add two new methods:

```python
    def is_audit_logging_enabled(self, user_id: str) -> bool:
        """Check if a user has audit logging enabled. Defaults to True."""
        import sqlite3
        try:
            row = self._conn.execute(
                "SELECT audit_logging FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return True  # Default: enabled
        if row is None:
            return True  # Unknown user: default enabled
        return bool(row[0])

    def log_audit_decision(self, user_id: str, timestamp: str, session_id: str,
                           tool_name: str, params_summary: str, decision: str,
                           risk_level: str, reason: str, elapsed_ms: float) -> None:
        """Insert an audit decision row if logging is enabled for this user."""
        import sqlite3
        if not self.is_audit_logging_enabled(user_id):
            return
        try:
            self._conn.execute(
                "INSERT INTO audit_log (user_id, timestamp, session_id, tool_name, "
                "params_summary, decision, risk_level, reason, elapsed_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (int(user_id), timestamp, session_id, tool_name,
                 params_summary[:500], decision, risk_level, reason, elapsed_ms),
            )
            self._conn.commit()
        except sqlite3.OperationalError:
            pass  # DB read-only or table missing — skip silently
```

**Step 4: Run tests to verify they pass**

Run: `cd safeclaw-service && source .venv/bin/activate && python -m pytest tests/test_audit_db.py -v`
Expected: All 5 tests PASS

**Step 5: Run all existing tests for regressions**

Run: `python -m pytest tests/ -v`
Expected: All 330+ tests PASS

**Step 6: Commit**

```bash
git add safeclaw-service/safeclaw/auth/api_key.py safeclaw-service/tests/test_audit_db.py
git commit -m "feat(service): add audit DB logging methods to SQLiteAPIKeyManager"
```

---

### Task 4: Wire audit DB logging into FullEngine

**Files:**
- Modify: `safeclaw-service/safeclaw/engine/full_engine.py:893-895` and `692-694`

**Step 1: Add the DB audit call after the existing JSONL audit call**

At line 895 (after `self.audit.log(record)` in the tool-call path), add:

```python
        # Write to shared DB for user dashboard (if enabled)
        if self.api_key_manager and hasattr(self.api_key_manager, 'log_audit_decision'):
            import json
            params_summary = json.dumps(event.params, default=str)[:500]
            self.api_key_manager.log_audit_decision(
                user_id=event.user_id,
                timestamp=record.timestamp,
                session_id=event.session_id,
                tool_name=event.tool_name,
                params_summary=params_summary,
                decision="blocked" if decision.block else "allowed",
                risk_level=action.risk_level,
                reason=decision.reason or "passed all checks",
                elapsed_ms=elapsed_ms,
            )
```

Similarly at line 694 (after `self.audit.log(record)` in the message path), add:

```python
        if self.api_key_manager and hasattr(self.api_key_manager, 'log_audit_decision'):
            import json
            self.api_key_manager.log_audit_decision(
                user_id=event.user_id,
                timestamp=record.timestamp,
                session_id=event.session_id,
                tool_name="message",
                params_summary=json.dumps({"to": event.to}, default=str)[:500],
                decision="blocked" if decision.block else "allowed",
                risk_level=risk_level,
                reason=decision.reason or "passed all checks",
                elapsed_ms=elapsed_ms,
            )
```

**Step 2: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS (existing tests use in-memory APIKeyManager without `log_audit_decision`, so the `hasattr` guard prevents errors)

**Step 3: Commit**

```bash
git add safeclaw-service/safeclaw/engine/full_engine.py
git commit -m "feat(service): wire audit DB logging into evaluation pipeline"
```

---

### Task 5: Add audit logging toggle to preferences page

**Files:**
- Modify: `safeclaw-landing/dashboard/prefs.py:12-204`
- Modify: `safeclaw-landing/main.py:1675-1724`

**Step 1: Add the checkbox to PrefsForm**

In `safeclaw-landing/dashboard/prefs.py`, add a new section after the "Limits" section (after line 105) and before the "LLM Integration" divider:

```python
        Divider(),

        # ── Audit Logging ──
        Div(
            H4("Audit Logging"),
            P("When enabled, SafeClaw logs every governance decision "
              "(allowed and blocked) to your dashboard for review.",
              cls=TextPresets.muted_sm),
            cls="space-y-1",
        ),

        _field_group(
            LabelCheckboxX(
                "Log governance decisions to dashboard",
                id="audit_logging",
                checked=prefs.get("audit_logging", True),
            ),
            P("Disable to stop recording decisions. Existing logs are preserved.",
              cls=TextPresets.muted_sm, style="padding-left:1.75rem;"),
        ),
```

**Step 2: Add `audit_logging` to the prefs dict in the route handler**

In `safeclaw-landing/main.py`, in the `dashboard_prefs` route (line 1678), add to the `prefs` dict:

```python
        "audit_logging": bool(user.audit_logging),
```

**Step 3: Handle `audit_logging` in the save route**

In `safeclaw-landing/main.py`, in `save_prefs` (line 1701):

Add `audit_logging: str = ""` to the function parameters.

Add to the body:
```python
    user.audit_logging = audit_logging == "on"
```

**Step 4: Commit**

```bash
git add safeclaw-landing/dashboard/prefs.py safeclaw-landing/main.py
git commit -m "feat(landing): add audit logging toggle to preferences page"
```

---

### Task 6: Create audit dashboard page

**Files:**
- Create: `safeclaw-landing/dashboard/audit.py`

**Step 1: Create the page component**

```python
"""Audit log dashboard page."""

from fasthtml.common import *
from monsterui.all import *


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


def AuditTable(rows):
    """Render audit log rows as a table."""
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

    header = ["Time", "Tool", "Decision", "Risk", "Reason", "Latency"]
    body = []
    for r in rows:
        # r is an AuditLog dataclass-like object from fastlite
        ts = r.timestamp[:19].replace("T", " ") if r.timestamp else ""
        latency = f"{r.elapsed_ms:.0f}ms" if r.elapsed_ms else ""
        reason = (r.reason[:80] + "...") if r.reason and len(r.reason) > 80 else (r.reason or "")
        body.append([ts, r.tool_name, _decision_badge(r.decision),
                      _risk_badge(r.risk_level), reason, latency])

    return Table(
        Thead(Tr(*[Th(h) for h in header])),
        Tbody(*[Tr(*[Td(c) for c in row]) for row in body]),
        cls=(TableT.hover, TableT.sm, TableT.striped),
    )


def AuditFilters(current_filter="all", session_id=""):
    """Filter bar for the audit log."""
    return Form(
        DivLAligned(
            LabelSelect(
                Option("All decisions", value="all", selected=current_filter == "all"),
                Option("Blocked only", value="blocked", selected=current_filter == "blocked"),
                Option("Allowed only", value="allowed", selected=current_filter == "allowed"),
                label="Filter",
                id="filter",
            ),
            LabelInput(
                "Session ID",
                id="session_id",
                value=session_id,
                placeholder="Optional",
            ),
            Button("Apply", cls=ButtonT.primary, type="submit"),
            cls="gap-4",
        ),
        hx_get="/dashboard/audit/results",
        hx_target="#audit-results",
        hx_swap="innerHTML",
        cls="space-y-4",
    )


def AuditContent(rows, current_filter="all", session_id=""):
    """Full audit page content."""
    return (
        Card(
            H3("Governance Audit Log"),
            P("All governance decisions made by SafeClaw for your API keys. ",
              "Toggle logging in ",
              A("Preferences", href="/dashboard/prefs"), ".",
              cls=TextPresets.muted_sm),
            AuditFilters(current_filter, session_id),
        ),
        Div(AuditTable(rows), id="audit-results"),
    )
```

**Step 2: Commit**

```bash
git add safeclaw-landing/dashboard/audit.py
git commit -m "feat(landing): create audit log dashboard page component"
```

---

### Task 7: Register audit dashboard routes

**Files:**
- Modify: `safeclaw-landing/main.py`
- Modify: `safeclaw-landing/dashboard/layout.py:9-14`

**Step 1: Add "Audit Log" to sidebar nav**

In `safeclaw-landing/dashboard/layout.py`, add to the `items` list (between "agents" and "prefs"):

```python
        ("audit", "Audit Log", "/dashboard/audit", "scroll-text"),
```

So the full list becomes:
```python
    items = [
        ("overview", "Overview", "/dashboard", "layout-dashboard"),
        ("keys", "API Keys", "/dashboard/keys", "key"),
        ("agents", "Agents", "/dashboard/agents", "bot"),
        ("audit", "Audit Log", "/dashboard/audit", "scroll-text"),
        ("prefs", "Preferences", "/dashboard/prefs", "settings"),
    ]
```

**Step 2: Add routes to main.py**

In `safeclaw-landing/main.py`, after the prefs routes and before `serve(port=5002)`, add:

```python
from dashboard.audit import AuditContent, AuditTable
from db import audit_log


@rt("/dashboard/audit")
def dashboard_audit(req, sess):
    user = req.scope.get("user")
    rows = audit_log(where="user_id = ?", where_args=[user.id], order_by="-id", limit=50)
    return (
        Title("Audit Log — SafeClaw"),
        *MUITheme.blue.headers(),
        DashboardLayout("Audit Log", *AuditContent(rows), user=user, active="audit"),
    )


@rt("/dashboard/audit/results")
def audit_results(req, sess, filter: str = "all", session_id: str = ""):
    """HTMX partial: filtered audit log results."""
    user = req.scope.get("user")
    conditions = ["user_id = ?"]
    args = [user.id]
    if filter == "blocked":
        conditions.append("decision = ?")
        args.append("blocked")
    elif filter == "allowed":
        conditions.append("decision = ?")
        args.append("allowed")
    if session_id.strip():
        conditions.append("session_id = ?")
        args.append(session_id.strip())
    where = " AND ".join(conditions)
    rows = audit_log(where=where, where_args=args, order_by="-id", limit=50)
    return AuditTable(rows)
```

**Step 3: Add the import at the top of the dashboard routes section**

Near line 1448, add `from db import audit_log` to the existing import, and add `from dashboard.audit import AuditContent, AuditTable`.

**Step 4: Commit**

```bash
git add safeclaw-landing/dashboard/layout.py safeclaw-landing/main.py
git commit -m "feat(landing): register audit dashboard routes and add nav item"
```

---

### Task 8: Add `audit_log` table creation to service SQLiteAPIKeyManager init

**Files:**
- Modify: `safeclaw-service/safeclaw/auth/api_key.py:97-119`

**Step 1: Add audit_log CREATE TABLE**

Inside the existing `try` block in `__init__` (around line 99-118), add after the `users` table creation:

```python
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS audit_log ("
                "  id INTEGER PRIMARY KEY,"
                "  user_id INTEGER,"
                "  timestamp TEXT,"
                "  session_id TEXT,"
                "  tool_name TEXT,"
                "  params_summary TEXT,"
                "  decision TEXT,"
                "  risk_level TEXT,"
                "  reason TEXT,"
                "  elapsed_ms REAL"
                ")"
            )
```

**Step 2: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add safeclaw-service/safeclaw/auth/api_key.py
git commit -m "feat(service): add audit_log table creation to SQLiteAPIKeyManager"
```

Note: This task can be merged with Task 3 if implemented together. Listed separately for clarity.

---

### Task 9: End-to-end verification

**Step 1: Run all service tests**

Run: `cd safeclaw-service && source .venv/bin/activate && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 2: Run linter**

Run: `ruff check safeclaw/ tests/`
Expected: No errors

**Step 3: Verify landing starts**

Run: `cd safeclaw-landing && python -c "from db import users, audit_log; print('users:', users); print('audit_log:', audit_log)"`
Expected: Both tables print correctly

**Step 4: Commit any remaining fixes**

**Step 5: Push**

```bash
git push
```
