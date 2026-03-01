# Onboarding Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve the SaaS onboarding to collect Mistral API keys per-user, show proper plugin connection instructions, and add a `safeclaw connect` CLI command.

**Architecture:** The onboarding wizard expands from 2 to 3 steps (autonomy → Mistral key → connection instructions). Mistral keys are stored per-user in SQLite. The service resolves each user's key per-request, falling back to the global env var. A new CLI command writes the SafeClaw API key to `~/.safeclaw/config.json`.

**Tech Stack:** Python, FastHTML/MonsterUI, Typer CLI, SQLite, Mistral SDK

---

### Task 1: Add `mistral_api_key` column to User model

**Files:**
- Modify: `safeclaw-landing/db.py:10-20`

**Step 1: Add column to User dataclass**

In `safeclaw-landing/db.py`, add `mistral_api_key` field to the `User` class after `autonomy_level`:

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
```

The `transform=True` on line 34 handles the schema migration automatically.

**Step 2: Verify no errors**

Run: `cd safeclaw-landing && python -c "from db import users; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add safeclaw-landing/db.py
git commit -m "feat(landing): add mistral_api_key column to User model"
```

---

### Task 2: Add Mistral key step to onboarding wizard

**Files:**
- Modify: `safeclaw-landing/dashboard/onboard.py`

**Step 1: Add `OnboardStep2Mistral()` function**

This is the new Step 2. Add it between `OnboardStep1` and the existing `OnboardStep2` (which becomes Step 3). The function renders a text input for the Mistral API key with a "Skip for now" link:

```python
def OnboardStep2Mistral():
    """Step 2: Optional Mistral API key for LLM features."""
    return Div(
        H2("Enable LLM Features"),
        P("SafeClaw uses Mistral for security review, smart classification, "
          "and plain-English decision explanations.",
          cls=TextPresets.muted_sm),
        P("You can add this later from Preferences.",
          cls=TextPresets.muted_sm),
        Form(
            LabelInput(
                "Mistral API Key",
                id="mistral_api_key",
                type="password",
                placeholder="Enter your Mistral API key",
            ),
            DivLAligned(
                Button("Next", cls=ButtonT.primary, type="submit"),
                A("Skip for now", hx_post="/dashboard/onboard/step2",
                  hx_target="#onboard-content", hx_swap="innerHTML",
                  cls="uk-link-muted", style="margin-left:1rem;"),
            ),
            hx_post="/dashboard/onboard/step2",
            hx_target="#onboard-content",
            hx_swap="innerHTML",
            cls="space-y-4",
        ),
        id="onboard-content",
    )
```

**Step 2: Rename existing `OnboardStep2` to `OnboardStep3`**

Rename the function and update the docstring:

```python
def OnboardStep3(raw_key: str):
    """Step 3: Show generated API key + connection instructions."""
```

**Step 3: Update Step 3 instructions**

Replace the old `export SAFECLAW_API_KEY=...` instructions in `OnboardStep3` with proper config file instructions:

```python
def OnboardStep3(raw_key: str):
    """Step 3: Show generated API key + connection instructions."""
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
            P("2. Connect your plugin (choose one):"),
            P(Strong("Option A — CLI (recommended):")),
            Pre(Code(f"safeclaw connect {raw_key}")),
            P(Strong("Option B — Manual config file:")),
            Pre(Code(
                f'mkdir -p ~/.safeclaw && cat > ~/.safeclaw/config.json << \'EOF\'\n'
                f'{{\n'
                f'  "remote": {{\n'
                f'    "apiKey": "{raw_key}",\n'
                f'    "serviceUrl": "https://api.safeclaw.eu/api/v1"\n'
                f'  }}\n'
                f'}}\n'
                f'EOF'
            )),
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

**Step 4: Verify syntax**

Run: `cd safeclaw-landing && python -c "from dashboard.onboard import OnboardStep1, OnboardStep2Mistral, OnboardStep3; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add safeclaw-landing/dashboard/onboard.py
git commit -m "feat(landing): 3-step onboarding with Mistral key and config instructions"
```

---

### Task 3: Wire up onboarding routes for the new 3-step flow

**Files:**
- Modify: `safeclaw-landing/main.py:1436-1530`

**Step 1: Update imports**

Change line 1439 from:
```python
from dashboard.onboard import OnboardStep1, OnboardStep2
```
to:
```python
from dashboard.onboard import OnboardStep1, OnboardStep2Mistral, OnboardStep3
```

**Step 2: Modify `onboard_step1` route to go to Mistral step**

The current `/dashboard/onboard/step1` handler saves autonomy level AND generates the API key. Split this: Step 1 saves autonomy level only and returns the Mistral step. The API key generation moves to Step 2.

Replace the `onboard_step1` function (lines 1500-1522) with:

```python
@rt("/dashboard/onboard/step1")
def onboard_step1(req, sess, autonomy_level: str = "moderate"):
    user = req.scope.get("user")
    if autonomy_level not in _VALID_AUTONOMY_LEVELS:
        autonomy_level = "moderate"
    user.autonomy_level = autonomy_level
    users.update(user)
    return OnboardStep2Mistral()
```

**Step 3: Add new `/dashboard/onboard/step2` route**

This handles the Mistral key (optional) and then generates the SafeClaw API key:

```python
@rt("/dashboard/onboard/step2")
def onboard_step2(req, sess, mistral_api_key: str = ""):
    user = req.scope.get("user")
    if mistral_api_key.strip():
        user.mistral_api_key = mistral_api_key.strip()
        users.update(user)
    # Guard: don't create duplicate keys on re-submit
    existing = api_keys(where="user_id = ? AND label = ? AND is_active = 1",
                        where_args=[user.id, "Default"])
    if existing:
        return OnboardStep3("(key already generated — check your API Keys page)")
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
    return OnboardStep3(raw_key)
```

**Step 4: Update `OnboardStep2` → `OnboardStep3` references**

Any remaining references to `OnboardStep2` in main.py should now reference `OnboardStep3`. Search for `OnboardStep2` and replace.

**Step 5: Verify syntax**

Run: `cd safeclaw-landing && python -c "import main; print('OK')"`
Expected: `OK`

**Step 6: Commit**

```bash
git add safeclaw-landing/main.py
git commit -m "feat(landing): wire 3-step onboarding routes with Mistral key step"
```

---

### Task 4: Add Mistral key field to Preferences page

**Files:**
- Modify: `safeclaw-landing/dashboard/prefs.py:6-59`
- Modify: `safeclaw-landing/main.py:1606-1640` (prefs routes)

**Step 1: Add Mistral key input to PrefsForm**

In `safeclaw-landing/dashboard/prefs.py`, add a Mistral API Key section to the form. Add after the existing "Limits" section (before the Save button). The `PrefsForm` function needs a new `mistral_api_key` parameter:

```python
def PrefsForm(prefs: dict | None = None, mistral_api_key: str = ""):
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
            Option(
                "Autonomous",
                value="autonomous",
                selected=prefs.get("autonomy_level") == "autonomous",
            ),
            label="Autonomy Level",
            id="autonomy_level",
        ),
        H4("Confirmation Rules"),
        LabelCheckboxX(
            "Confirm before deleting files",
            id="confirm_before_delete",
            checked=prefs.get("confirm_before_delete", True),
        ),
        LabelCheckboxX(
            "Confirm before pushing code",
            id="confirm_before_push",
            checked=prefs.get("confirm_before_push", True),
        ),
        LabelCheckboxX(
            "Confirm before sending messages",
            id="confirm_before_send",
            checked=prefs.get("confirm_before_send", True),
        ),
        H4("Limits"),
        LabelInput(
            "Max files per commit",
            id="max_files_per_commit",
            type="number",
            value=str(prefs.get("max_files_per_commit", 10)),
            min="1",
            max="100",
        ),
        H4("LLM Integration"),
        P("SafeClaw uses Mistral for security review, smart classification, "
          "and plain-English decision explanations.",
          cls=TextPresets.muted_sm),
        LabelInput(
            "Mistral API Key",
            id="mistral_api_key",
            type="password",
            value=mistral_api_key,
            placeholder="Enter your Mistral API key",
        ),
        Button("Save Preferences", cls=ButtonT.primary, type="submit"),
        hx_post="/dashboard/prefs/save",
        hx_target="#prefs-status",
        hx_swap="innerHTML",
        cls="space-y-4",
    )
```

**Step 2: Update `PrefsContent` to accept `mistral_api_key`**

```python
def PrefsContent(prefs: dict | None = None, mistral_api_key: str = ""):
    """Full preferences page content."""
    return (
        Card(
            H3("Governance Preferences"),
            P(
                "These settings control how strictly SafeClaw governs your agent's actions.",
                cls=TextPresets.muted_sm,
            ),
            PrefsForm(prefs, mistral_api_key=mistral_api_key),
        ),
        Div(id="prefs-status"),
    )
```

**Step 3: Update prefs route to pass Mistral key**

In `safeclaw-landing/main.py`, update the `/dashboard/prefs` route (around line 1606) to pass the user's Mistral key to `PrefsContent`:

```python
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

    # Mask Mistral key for display: show last 4 chars only
    masked_key = ""
    if user.mistral_api_key:
        masked_key = "••••" + user.mistral_api_key[-4:]

    return (
        Title("Preferences — SafeClaw"),
        *MUITheme.blue.headers(),
        DashboardLayout("Preferences", *PrefsContent(prefs, mistral_api_key=masked_key), user=user, active="prefs"),
    )
```

**Step 4: Update save_prefs route to handle Mistral key**

In `safeclaw-landing/main.py`, update the `/dashboard/prefs/save` route (around line 1634) to accept and save the Mistral key:

Add `mistral_api_key: str = ""` parameter to the function signature. After the existing prefs save logic, save the Mistral key to the user if it was changed (i.e., not the masked value):

```python
@rt("/dashboard/prefs/save")
async def save_prefs(req, sess, autonomy_level: str = "moderate",
                     confirm_before_delete: bool = True, confirm_before_push: bool = True,
                     confirm_before_send: bool = True, max_files_per_commit: int = 10,
                     mistral_api_key: str = ""):
    user = req.scope.get("user")
    # Save Mistral key if changed (not the masked placeholder)
    if mistral_api_key and not mistral_api_key.startswith("••••"):
        user.mistral_api_key = mistral_api_key.strip()
        users.update(user)
    # ... rest of existing save logic unchanged ...
```

**Step 5: Verify syntax**

Run: `cd safeclaw-landing && python -c "from dashboard.prefs import PrefsForm, PrefsContent; print('OK')"`
Expected: `OK`

**Step 6: Commit**

```bash
git add safeclaw-landing/dashboard/prefs.py safeclaw-landing/main.py
git commit -m "feat(landing): add Mistral API key to preferences page"
```

---

### Task 5: Add dashboard nudge banner for missing Mistral key

**Files:**
- Modify: `safeclaw-landing/dashboard/overview.py:35-53`
- Modify: `safeclaw-landing/main.py:1395-1403`

**Step 1: Add `MistralNudge` component to overview**

In `safeclaw-landing/dashboard/overview.py`, add a new function and update `OverviewContent` to accept a flag:

```python
def MistralNudge():
    """Banner shown when user has no Mistral API key configured."""
    return Card(
        DivLAligned(
            UkIcon("alert-triangle", height=20),
            Div(
                P(Strong("LLM features disabled")),
                P("Add your Mistral API key in ",
                  A("Preferences", href="/dashboard/prefs"),
                  " to enable security review and smart classification.",
                  cls=TextPresets.muted_sm),
            ),
        ),
        cls="uk-alert-warning",
    )
```

**Step 2: Update `OverviewContent` to show nudge**

```python
def OverviewContent(user, key_count: int, has_mistral_key: bool = True):
    """Main overview page content."""
    content = [
        Grid(
            Card(
                DivLAligned(UkIcon("key", height=20), H4("API Keys")),
                P(f"{key_count} keys", cls=TextPresets.muted_sm),
                footer=A("Manage keys ->", href="/dashboard/keys"),
            ),
            Card(
                DivLAligned(UkIcon("bot", height=20), H4("Agents")),
                P("View on service", cls=TextPresets.muted_sm),
                footer=A("View agents ->", href="/dashboard/agents"),
            ),
            cols=2,
        ),
    ]
    if not has_mistral_key:
        content.append(MistralNudge())
    content.append(ServiceHealthCard())
    content.append(GettingStartedCard())
    return tuple(content)
```

**Step 3: Update dashboard route to pass flag**

In `safeclaw-landing/main.py`, update the `/dashboard` route:

```python
@rt("/dashboard")
def dashboard(req, sess):
    user = req.scope.get("user")
    key_count = len(api_keys(where="user_id = ? AND is_active = 1", where_args=[user.id]))
    return (
        Title("Dashboard — SafeClaw"),
        *MUITheme.blue.headers(),
        DashboardLayout("Overview",
                        *OverviewContent(user, key_count, has_mistral_key=bool(user.mistral_api_key)),
                        user=user, active="overview"),
    )
```

**Step 4: Update overview import if needed**

Make sure `MistralNudge` is importable (it's used internally by `OverviewContent`, so no import change needed in main.py).

**Step 5: Also update the GettingStartedCard instructions**

In `safeclaw-landing/dashboard/overview.py`, update `GettingStartedCard` to use the config file approach instead of `export`:

```python
def GettingStartedCard():
    """Setup instructions for new users."""
    return Card(
        H3("Getting Started"),
        Div(
            P("1. Create an API key in the ", A("Keys", href="/dashboard/keys"), " tab"),
            P("2. Install the OpenClaw plugin:"),
            Pre(Code("openclaw plugins install openclaw-safeclaw-plugin")),
            P("3. Connect your plugin:"),
            Pre(Code("safeclaw connect sc_your_key_here")),
            cls="space-y-2",
        ),
    )
```

**Step 6: Verify syntax**

Run: `cd safeclaw-landing && python -c "from dashboard.overview import OverviewContent, MistralNudge; print('OK')"`
Expected: `OK`

**Step 7: Commit**

```bash
git add safeclaw-landing/dashboard/overview.py safeclaw-landing/main.py
git commit -m "feat(landing): add Mistral key nudge banner and update getting started instructions"
```

---

### Task 6: Create `safeclaw connect` CLI command

**Files:**
- Create: `safeclaw-service/safeclaw/cli/connect_cmd.py`
- Modify: `safeclaw-service/safeclaw/cli/main.py:1-21`
- Test: `safeclaw-service/tests/test_connect_cmd.py`

**Step 1: Write the failing test**

Create `safeclaw-service/tests/test_connect_cmd.py`:

```python
"""Tests for the safeclaw connect CLI command."""

import json

from typer.testing import CliRunner

from safeclaw.cli.main import app

runner = CliRunner()


class TestConnectCommand:
    def test_connect_creates_config(self, tmp_path, monkeypatch):
        config_path = tmp_path / ".safeclaw" / "config.json"
        monkeypatch.setattr("safeclaw.cli.connect_cmd.get_config_path", lambda: config_path)

        result = runner.invoke(app, ["connect", "sc_test_key_12345"])
        assert result.exit_code == 0
        assert "Connected" in result.output

        config = json.loads(config_path.read_text())
        assert config["remote"]["apiKey"] == "sc_test_key_12345"
        assert "safeclaw.eu" in config["remote"]["serviceUrl"]

    def test_connect_custom_service_url(self, tmp_path, monkeypatch):
        config_path = tmp_path / ".safeclaw" / "config.json"
        monkeypatch.setattr("safeclaw.cli.connect_cmd.get_config_path", lambda: config_path)

        result = runner.invoke(app, [
            "connect", "sc_test_key_12345",
            "--service-url", "http://localhost:8420/api/v1",
        ])
        assert result.exit_code == 0

        config = json.loads(config_path.read_text())
        assert config["remote"]["serviceUrl"] == "http://localhost:8420/api/v1"

    def test_connect_merges_existing_config(self, tmp_path, monkeypatch):
        config_path = tmp_path / ".safeclaw" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(json.dumps({
            "enabled": True,
            "userId": "existing-user",
            "remote": {"serviceUrl": "http://old.example.com", "apiKey": "old_key"},
        }))
        monkeypatch.setattr("safeclaw.cli.connect_cmd.get_config_path", lambda: config_path)

        result = runner.invoke(app, ["connect", "sc_new_key_67890"])
        assert result.exit_code == 0

        config = json.loads(config_path.read_text())
        assert config["remote"]["apiKey"] == "sc_new_key_67890"
        assert config["userId"] == "existing-user"  # preserved
```

**Step 2: Run tests to verify they fail**

Run: `cd safeclaw-service && source .venv/bin/activate && python -m pytest tests/test_connect_cmd.py -v`
Expected: FAIL (module not found)

**Step 3: Write the implementation**

Create `safeclaw-service/safeclaw/cli/connect_cmd.py`:

```python
"""safeclaw connect — write API key to ~/.safeclaw/config.json."""

import json
from pathlib import Path

import typer


def get_config_path() -> Path:
    """Return the default config path. Extracted for testability."""
    return Path.home() / ".safeclaw" / "config.json"


def connect_cmd(
    api_key: str = typer.Argument(help="Your SafeClaw API key (starts with sc_)"),
    service_url: str = typer.Option(
        "https://api.safeclaw.eu/api/v1",
        help="SafeClaw service URL",
    ),
):
    """Connect your plugin to SafeClaw by saving your API key to ~/.safeclaw/config.json."""
    config_path = get_config_path()

    # Load existing config or start fresh
    config: dict = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass  # Start fresh

    # Set remote config
    if "remote" not in config or not isinstance(config["remote"], dict):
        config["remote"] = {}
    config["remote"]["apiKey"] = api_key
    config["remote"]["serviceUrl"] = service_url

    # Write config
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    typer.echo(f"Connected! Your API key has been saved to {config_path}")
```

**Step 4: Register in CLI main**

In `safeclaw-service/safeclaw/cli/main.py`, add the import and registration:

```python
from safeclaw.cli.connect_cmd import connect_cmd
```

And register after the existing commands:

```python
app.command("connect")(connect_cmd)
```

**Step 5: Run tests to verify they pass**

Run: `cd safeclaw-service && python -m pytest tests/test_connect_cmd.py -v`
Expected: 3 PASSED

**Step 6: Run all tests for regressions**

Run: `cd safeclaw-service && python -m pytest tests/ -v`
Expected: All pass

**Step 7: Commit**

```bash
git add safeclaw-service/safeclaw/cli/connect_cmd.py safeclaw-service/safeclaw/cli/main.py safeclaw-service/tests/test_connect_cmd.py
git commit -m "feat(cli): add safeclaw connect command to save API key to config"
```

---

### Task 7: Add `get_user_mistral_key()` to SQLiteAPIKeyManager

**Files:**
- Modify: `safeclaw-service/safeclaw/auth/api_key.py:83-121`
- Test: `safeclaw-service/tests/test_phase5.py`

**Step 1: Write the failing test**

Add to the existing `TestSQLiteAPIKeyManager` class in `safeclaw-service/tests/test_phase5.py`:

```python
def test_get_user_mistral_key(self, tmp_path):
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
    conn.execute(
        "CREATE TABLE users ("
        "  id INTEGER PRIMARY KEY,"
        "  mistral_api_key TEXT DEFAULT ''"
        ")"
    )
    conn.execute("INSERT INTO users (id, mistral_api_key) VALUES (?, ?)", (42, "mist_test_key"))
    conn.commit()
    conn.close()

    mgr = SQLiteAPIKeyManager(str(db_path))
    assert mgr.get_user_mistral_key("42") == "mist_test_key"
    assert mgr.get_user_mistral_key("999") is None

def test_get_user_mistral_key_empty(self, tmp_path):
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
    conn.execute(
        "CREATE TABLE users ("
        "  id INTEGER PRIMARY KEY,"
        "  mistral_api_key TEXT DEFAULT ''"
        ")"
    )
    conn.execute("INSERT INTO users (id, mistral_api_key) VALUES (?, ?)", (42, ""))
    conn.commit()
    conn.close()

    mgr = SQLiteAPIKeyManager(str(db_path))
    assert mgr.get_user_mistral_key("42") is None  # empty string = no key
```

**Step 2: Run tests to verify they fail**

Run: `cd safeclaw-service && python -m pytest tests/test_phase5.py::TestSQLiteAPIKeyManager::test_get_user_mistral_key -v`
Expected: FAIL (method not found)

**Step 3: Add `get_user_mistral_key()` method**

In `safeclaw-service/safeclaw/auth/api_key.py`, add to the `SQLiteAPIKeyManager` class after the `validate_key` method:

```python
def get_user_mistral_key(self, user_id: str) -> str | None:
    """Look up a user's Mistral API key from the shared DB. Returns None if not set."""
    row = self._conn.execute(
        "SELECT mistral_api_key FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None or not row[0]:
        return None
    return row[0]
```

**Step 4: Run tests to verify they pass**

Run: `cd safeclaw-service && python -m pytest tests/test_phase5.py::TestSQLiteAPIKeyManager -v`
Expected: All PASSED

**Step 5: Commit**

```bash
git add safeclaw-service/safeclaw/auth/api_key.py safeclaw-service/tests/test_phase5.py
git commit -m "feat(service): add get_user_mistral_key to SQLiteAPIKeyManager"
```

---

### Task 8: Per-user LLM client in the engine

**Files:**
- Modify: `safeclaw-service/safeclaw/auth/middleware.py:27-56`
- Modify: `safeclaw-service/safeclaw/engine/full_engine.py:69-164`
- Test: `safeclaw-service/tests/test_phase5.py`

**Step 1: Expose user_id on request state in middleware**

The middleware already sets `request.state.org_id` (which is the `user_id`). This is sufficient — no middleware change needed. The `org_id` from `validate_key()` is the `user_id` string.

**Step 2: Write failing test for per-user LLM client**

Add to `safeclaw-service/tests/test_phase5.py`:

```python
class TestPerUserLLMClient:
    def test_get_llm_client_for_user_returns_none_without_db(self):
        """Without a SQLite key manager, per-user lookup returns None."""
        from safeclaw.engine.full_engine import FullEngine
        from safeclaw.config import SafeClawConfig

        config = SafeClawConfig()
        engine = FullEngine(config)
        assert engine.get_llm_client_for_user("42") is None

    def test_get_llm_client_for_user_falls_back_to_global(self):
        """If user has no Mistral key, fall back to global client."""
        from safeclaw.engine.full_engine import FullEngine
        from safeclaw.config import SafeClawConfig

        config = SafeClawConfig()
        engine = FullEngine(config)
        engine.llm_client = MagicMock()  # Simulate global client
        # No api_key_manager set, so per-user returns global
        result = engine.get_llm_client_for_user("42")
        assert result is engine.llm_client
```

**Step 3: Run tests to verify they fail**

Run: `cd safeclaw-service && python -m pytest tests/test_phase5.py::TestPerUserLLMClient -v`
Expected: FAIL (method not found)

**Step 4: Add `get_llm_client_for_user()` method to FullEngine**

In `safeclaw-service/safeclaw/engine/full_engine.py`, add after the LLM initialization block (after line 164):

```python
# Per-user LLM client cache (keyed by Mistral API key)
self._user_llm_clients: dict[str, "SafeClawLLMClient"] = {}
```

Then add the method to the class:

```python
def get_llm_client_for_user(self, user_id: str) -> "SafeClawLLMClient | None":
    """Get LLM client for a specific user, falling back to global client.

    Looks up the user's Mistral key from the shared DB, caches clients by key.
    """
    from safeclaw.main import _api_key_manager

    if _api_key_manager is None or not hasattr(_api_key_manager, "get_user_mistral_key"):
        return self.llm_client  # Fall back to global

    user_key = _api_key_manager.get_user_mistral_key(user_id)
    if not user_key:
        return self.llm_client  # Fall back to global

    # Check cache
    if user_key in self._user_llm_clients:
        return self._user_llm_clients[user_key]

    # Create new client for this key
    from safeclaw.llm.client import SafeClawLLMClient
    try:
        from mistralai import Mistral
        mistral = Mistral(api_key=user_key)
        client = SafeClawLLMClient(
            mistral_client=mistral,
            model=self.config.mistral_model,
            model_large=self.config.mistral_model_large,
            timeout_ms=self.config.mistral_timeout_ms,
        )
        self._user_llm_clients[user_key] = client
        return client
    except Exception:
        logger.warning("Failed to create per-user Mistral client for user %s", user_id)
        return self.llm_client
```

**Step 5: Store api_key_manager reference on engine instead of importing from main**

The circular import from `safeclaw.main` is fragile. Better approach: pass the `api_key_manager` to the engine. In `safeclaw-service/safeclaw/engine/full_engine.py`, update `__init__`:

```python
def __init__(self, config: SafeClawConfig, api_key_manager=None):
    self.config = config
    self.api_key_manager = api_key_manager
    self.event_bus = EventBus()
    self._reload_lock = asyncio.Lock()
    self._init_components(config)
```

And update `get_llm_client_for_user` to use `self.api_key_manager` instead of importing from main:

```python
def get_llm_client_for_user(self, user_id: str) -> "SafeClawLLMClient | None":
    if self.api_key_manager is None or not hasattr(self.api_key_manager, "get_user_mistral_key"):
        return self.llm_client

    user_key = self.api_key_manager.get_user_mistral_key(user_id)
    if not user_key:
        return self.llm_client

    if user_key in self._user_llm_clients:
        return self._user_llm_clients[user_key]

    from safeclaw.llm.client import SafeClawLLMClient
    try:
        from mistralai import Mistral
        mistral = Mistral(api_key=user_key)
        client = SafeClawLLMClient(
            mistral_client=mistral,
            model=self.config.mistral_model,
            model_large=self.config.mistral_model_large,
            timeout_ms=self.config.mistral_timeout_ms,
        )
        self._user_llm_clients[user_key] = client
        return client
    except Exception:
        logger.warning("Failed to create per-user Mistral client for user %s", user_id)
        return self.llm_client
```

**Step 6: Pass api_key_manager in main.py**

In `safeclaw-service/safeclaw/main.py`, update the lifespan to pass the manager:

Change line 32 from:
```python
engine = FullEngine(_config)
```
to:
```python
engine = FullEngine(_config, api_key_manager=_api_key_manager)
```

**Step 7: Update test to match new API**

Update `TestPerUserLLMClient` tests to pass `api_key_manager=None` explicitly (already the default, so no change needed).

**Step 8: Run tests to verify they pass**

Run: `cd safeclaw-service && python -m pytest tests/test_phase5.py::TestPerUserLLMClient -v`
Expected: All PASSED

**Step 9: Run all tests for regressions**

Run: `cd safeclaw-service && python -m pytest tests/ -v`
Expected: All pass

**Step 10: Lint**

Run: `cd safeclaw-service && ruff check safeclaw/ tests/`
Expected: No errors

**Step 11: Commit**

```bash
git add safeclaw-service/safeclaw/engine/full_engine.py safeclaw-service/safeclaw/main.py safeclaw-service/tests/test_phase5.py
git commit -m "feat(service): per-user LLM client with Mistral key lookup from DB"
```

---

### Task 9: Update /docs page with new onboarding flow

**Files:**
- Modify: `safeclaw-landing/main.py` (docs section)

**Step 1: Find and update the SaaS Onboarding section**

The docs page has a section about SaaS onboarding. Update it to reflect the 3-step wizard and the `safeclaw connect` command. Also update the QuickStart SaaS section.

Find the existing onboarding docs section and update:
- Step 2 is now "Mistral API key (optional)"
- Step 3 is "API key + connection instructions"
- Add `safeclaw connect` as the recommended connection method

**Step 2: Verify syntax**

Run: `cd safeclaw-landing && python -c "import main; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add safeclaw-landing/main.py
git commit -m "docs(landing): update /docs page with 3-step onboarding and safeclaw connect"
```

---

## Verification

```bash
# Service tests
cd safeclaw-service
source .venv/bin/activate
python -m pytest tests/ -v
ruff check safeclaw/ tests/

# Landing site syntax check
cd ../safeclaw-landing
python -c "import main; print('OK')"
```
