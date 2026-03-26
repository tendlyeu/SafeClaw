# Phase 1: Critical & High Bug Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all critical and high-severity bugs to make the SafeClaw service secure and correct before adding features.

**Architecture:** Each bug fix is independent — no fix depends on another. Fixes follow TDD: validate the bug exists, write a failing test that demonstrates it, implement the minimal fix, verify the test passes.

**Tech Stack:** Python 3.11+, pytest, ruff, FastAPI, bcrypt, asyncio

**Validation Protocol:** Several bugs may have been fixed in prior commits (c5d6d54, 03b5518, cd1fe28). Every task starts with a **validation step** that reproduces the bug. If the bug cannot be reproduced, skip the fix and close the ticket with a comment referencing the commit that fixed it.

---

## Batch 1A — Security-Critical

### Task 1: #132 — Admin passwords stored plaintext

**Status from research:** CONFIRMED ACTIVE. No hashing anywhere — `config.py:31` stores raw string, `routes.py:106-109` and `dashboard/app.py:138` compare plaintext.

**Files:**
- Modify: `safeclaw-service/pyproject.toml`
- Modify: `safeclaw-service/safeclaw/config.py`
- Modify: `safeclaw-service/safeclaw/api/routes.py:106-109`
- Modify: `safeclaw-service/safeclaw/dashboard/app.py:138`
- Modify: `safeclaw-service/safeclaw/cli/init_cmd.py` (where config template writes admin_password)
- Test: `safeclaw-service/tests/test_admin_password_hashing.py`

- [ ] **Step 1: Validate bug exists**

```bash
cd safeclaw-service
grep -n "admin_password" safeclaw/config.py safeclaw/api/routes.py safeclaw/dashboard/app.py
```

Expected: Find `admin_password: str = ""` in config.py (no hashing), `secrets.compare_digest(provided, configured_password)` comparing plaintext in routes.py, `secrets.compare_digest(password, cfg.admin_password)` comparing plaintext in dashboard/app.py. If all comparisons use plaintext strings, bug is confirmed.

- [ ] **Step 2: Add bcrypt dependency**

In `safeclaw-service/pyproject.toml`, add to `[project.dependencies]`:

```toml
"bcrypt>=4.0",
```

Run:

```bash
cd safeclaw-service && pip install -e ".[dev]"
```

- [ ] **Step 3: Write failing test**

Create `safeclaw-service/tests/test_admin_password_hashing.py`:

```python
"""Tests for admin password hashing — verifies passwords are never stored or compared in plaintext."""
import bcrypt
import pytest

from safeclaw.config import SafeClawConfig


def _hash_password(plain: str) -> str:
    """Hash a password with bcrypt (mirrors the function we'll add to config.py)."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


class TestAdminPasswordHashing:
    def test_hash_password_returns_bcrypt_hash(self):
        hashed = _hash_password("testpass123")
        assert hashed.startswith("$2b$")

    def test_verify_correct_password(self):
        hashed = _hash_password("testpass123")
        assert _verify_password("testpass123", hashed) is True

    def test_verify_wrong_password(self):
        hashed = _hash_password("testpass123")
        assert _verify_password("wrongpass", hashed) is False

    def test_config_admin_password_field_accepts_hash(self):
        hashed = _hash_password("mypassword")
        cfg = SafeClawConfig(admin_password=hashed)
        assert cfg.admin_password == hashed
        # The config should store the hash, not the plaintext
        assert not cfg.admin_password == "mypassword"

    def test_verify_admin_password_function_exists(self):
        """Config should expose a verify_admin_password method."""
        cfg = SafeClawConfig(admin_password=_hash_password("testpass123"))
        assert hasattr(cfg, "verify_admin_password")
        assert cfg.verify_admin_password("testpass123") is True
        assert cfg.verify_admin_password("wrong") is False

    def test_plaintext_password_still_works_for_migration(self):
        """During migration, plaintext passwords should still verify via fallback."""
        cfg = SafeClawConfig(admin_password="plaintext_legacy")
        assert cfg.verify_admin_password("plaintext_legacy") is True
        assert cfg.verify_admin_password("wrong") is False
```

- [ ] **Step 4: Run test to verify it fails**

```bash
cd safeclaw-service && python -m pytest tests/test_admin_password_hashing.py -v
```

Expected: `test_verify_admin_password_function_exists` and `test_plaintext_password_still_works_for_migration` FAIL because `verify_admin_password` doesn't exist yet.

- [ ] **Step 5: Add verify_admin_password to SafeClawConfig**

In `safeclaw-service/safeclaw/config.py`, add import at top:

```python
import bcrypt
```

Add method to `SafeClawConfig` class:

```python
def verify_admin_password(self, candidate: str) -> bool:
    """Verify a candidate password against the stored admin_password.

    Supports both bcrypt hashes (preferred) and plaintext (legacy fallback).
    """
    if not self.admin_password:
        return False
    # If stored value is a bcrypt hash, verify against it
    if self.admin_password.startswith("$2b$"):
        return bcrypt.checkpw(candidate.encode(), self.admin_password.encode())
    # Legacy fallback: plaintext comparison (timing-safe)
    import secrets
    return secrets.compare_digest(self.admin_password, candidate)
```

- [ ] **Step 6: Update API routes to use verify_admin_password**

In `safeclaw-service/safeclaw/api/routes.py`, replace lines 106-109:

```python
# BEFORE:
configured_password = engine.config.admin_password
if configured_password:  # only enforce when a password is actually set
    provided = request.headers.get("X-Admin-Password", "")
    if not provided or not secrets.compare_digest(provided, configured_password):

# AFTER:
if engine.config.admin_password:
    provided = request.headers.get("X-Admin-Password", "")
    if not provided or not engine.config.verify_admin_password(provided):
```

- [ ] **Step 7: Update dashboard login to use verify_admin_password**

In `safeclaw-service/safeclaw/dashboard/app.py`, replace the plaintext comparison (around line 138):

```python
# BEFORE:
if secrets.compare_digest(password, cfg.admin_password):

# AFTER:
if cfg.verify_admin_password(password):
```

- [ ] **Step 8: Run all tests**

```bash
cd safeclaw-service && python -m pytest tests/test_admin_password_hashing.py tests/test_dashboard_app.py tests/test_phase3.py -v
```

Expected: ALL PASS.

- [ ] **Step 9: Commit**

```bash
cd safeclaw-service
git add pyproject.toml safeclaw/config.py safeclaw/api/routes.py safeclaw/dashboard/app.py tests/test_admin_password_hashing.py
git commit -m "fix(#132): hash admin passwords with bcrypt, add legacy plaintext fallback"
```

---

### Task 2: #133 — Config file world-readable permissions

**Status from research:** CONFIRMED ACTIVE. `dashboard/pages/settings.py:211` uses `Path.write_text()` (default 0644) instead of the safe `os.open(..., 0o600)` pattern used elsewhere.

**Files:**
- Modify: `safeclaw-service/safeclaw/dashboard/pages/settings.py:204-211`
- Test: `safeclaw-service/tests/test_dashboard_settings.py`

- [ ] **Step 1: Validate bug exists**

```bash
cd safeclaw-service
grep -n "write_text\|Path.*write" safeclaw/dashboard/pages/settings.py
```

Expected: Find `config_path.write_text(...)` without any `os.open` or `chmod` call. Confirm it does NOT use the `0o600` pattern from `config_template.py`.

- [ ] **Step 2: Write failing test**

Add to `safeclaw-service/tests/test_dashboard_settings.py`:

```python
import os
import stat


def test_settings_config_write_permissions(tmp_path, monkeypatch):
    """Config file written by settings page must be owner-only (0o600)."""
    config_path = tmp_path / "config.json"
    config_path.write_text('{"existing": true}')
    # Make it world-readable first to prove the fix changes permissions
    os.chmod(config_path, 0o644)

    # Simulate the settings write path
    from safeclaw.dashboard.pages.settings import _write_config_safe
    _write_config_safe(config_path, {"mistral_api_key": "test-key"})

    perms = stat.S_IMODE(os.stat(config_path).st_mode)
    assert perms == 0o600, f"Config file permissions are {oct(perms)}, expected 0o600"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd safeclaw-service && python -m pytest tests/test_dashboard_settings.py::test_settings_config_write_permissions -v
```

Expected: FAIL — `_write_config_safe` doesn't exist yet.

- [ ] **Step 4: Extract safe write helper and use it in settings**

In `safeclaw-service/safeclaw/dashboard/pages/settings.py`, add helper:

```python
import json
import os


def _write_config_safe(config_path: Path, data: dict) -> None:
    """Write config JSON with owner-only permissions (0o600)."""
    content = json.dumps(data, indent=2)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(config_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content.encode())
    finally:
        os.close(fd)
```

Then replace the existing `config_path.write_text(...)` call (around line 211) with:

```python
_write_config_safe(config_path, cfg_data)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd safeclaw-service && python -m pytest tests/test_dashboard_settings.py -v
```

Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
cd safeclaw-service
git add safeclaw/dashboard/pages/settings.py tests/test_dashboard_settings.py
git commit -m "fix(#133): write config files with 0o600 permissions in dashboard settings"
```

---

### Task 3: #130 — LLM kill_switch auto-executes without confirmation

**Status from research:** APPEARS FIXED. Current code only logs and publishes events, never calls `kill_agent()`. But no test verifies this.

**Files:**
- Read: `safeclaw-service/safeclaw/llm/security_reviewer.py:74-125`
- Test: `safeclaw-service/tests/test_llm_security_reviewer.py`

- [ ] **Step 1: Validate bug — check if kill_agent is ever called**

```bash
cd safeclaw-service
grep -n "kill_agent\|registry.kill\|agent_registry.kill" safeclaw/llm/security_reviewer.py
```

Expected: NO matches. If no matches found, the auto-execute path has been removed. Bug is fixed.

- [ ] **Step 2: If bug is fixed, add regression test and close ticket**

Add to `safeclaw-service/tests/test_llm_security_reviewer.py`:

```python
def test_kill_switch_recommendation_does_not_auto_execute(self):
    """Regression test for #130: kill_switch must never auto-execute."""
    import ast
    import inspect
    from safeclaw.llm.security_reviewer import SecurityReviewer

    source = inspect.getsource(SecurityReviewer)
    tree = ast.parse(source)
    # Search for any call to kill_agent in the class
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "kill_agent":
                pytest.fail(
                    "SecurityReviewer must never call kill_agent() directly. "
                    "Kill switch requires human confirmation via the API."
                )
```

- [ ] **Step 3: Run the regression test**

```bash
cd safeclaw-service && python -m pytest tests/test_llm_security_reviewer.py -v -k "kill_switch"
```

Expected: PASS.

- [ ] **Step 4: Commit and close ticket**

```bash
cd safeclaw-service
git add tests/test_llm_security_reviewer.py
git commit -m "test(#130): add regression test confirming kill_switch never auto-executes"
```

Then close the GitHub issue:

```bash
gh issue close 130 --comment "Bug was fixed in a prior commit. Added regression test to prevent re-introduction."
```

---

### Task 4: #131 — Session lock creation race condition

**Status from research:** APPEARS FIXED. Meta-lock guards creation. Edge case remains: eviction can invalidate held lock references.

**Files:**
- Read: `safeclaw-service/safeclaw/engine/full_engine.py:341-361`
- Test: `safeclaw-service/tests/test_session_lock.py`

- [ ] **Step 1: Validate — check if meta-lock guards session lock creation**

```bash
cd safeclaw-service
grep -n "_meta_lock\|_get_session_lock\|_evict_unlocked" safeclaw/engine/full_engine.py
```

Expected: Find `async with self._meta_lock:` wrapping the lock creation in `_get_session_lock`. If present, the primary race condition is fixed.

- [ ] **Step 2: Check the eviction edge case**

Read `_evict_unlocked_session_locks` to determine if it can evict a lock that has waiters (coroutines waiting to acquire it but not yet holding it). The `locked()` check only detects if the lock is currently held, not if coroutines are waiting.

```bash
cd safeclaw-service
python -c "
import asyncio
lock = asyncio.Lock()
# locked() returns False even if something is waiting
print('locked:', lock.locked())  # False
"
```

- [ ] **Step 3: If primary race is fixed but eviction edge case exists, write targeted test**

Create `safeclaw-service/tests/test_session_lock.py`:

```python
"""Tests for session lock management — validates no race conditions."""
import asyncio

import pytest

from safeclaw.config import SafeClawConfig
from safeclaw.engine.full_engine import FullEngine


@pytest.fixture
def engine():
    cfg = SafeClawConfig(run_reasoner_on_startup=False)
    return FullEngine(cfg)


@pytest.mark.asyncio
async def test_concurrent_get_session_lock_returns_same_lock(engine):
    """Two concurrent calls for the same session must get the same lock object."""
    locks = await asyncio.gather(
        engine._get_session_lock("session-1"),
        engine._get_session_lock("session-1"),
    )
    assert locks[0] is locks[1], "Concurrent calls returned different lock objects"


@pytest.mark.asyncio
async def test_eviction_does_not_remove_in_use_lock(engine):
    """A lock currently acquired must not be evicted."""
    engine._max_session_locks = 1  # Force eviction after 1 lock

    lock1 = await engine._get_session_lock("session-1")
    async with lock1:
        # While lock1 is held, request a second lock — should trigger eviction
        lock2 = await engine._get_session_lock("session-2")
        # lock1 must not have been evicted
        assert "session-1" in engine._session_locks, "In-use lock was evicted"
    assert lock2 is not None
```

- [ ] **Step 4: Run tests**

```bash
cd safeclaw-service && python -m pytest tests/test_session_lock.py -v
```

Expected: PASS if eviction correctly skips locked locks. If eviction DOES remove in-use locks, the test will fail and we need to fix `_evict_unlocked_session_locks`.

- [ ] **Step 5: If tests pass, commit and close. If eviction test fails, fix the eviction logic.**

If the eviction edge case is confirmed, fix `_evict_unlocked_session_locks` in `full_engine.py` to also skip locks with `_waiters` (internal attribute) or use a reference count pattern. Then re-run tests.

```bash
cd safeclaw-service
git add tests/test_session_lock.py safeclaw/engine/full_engine.py
git commit -m "fix(#131): add session lock tests, fix eviction of in-use locks"
```

---

### Task 5: #128 — "Requires confirmation" indistinguishable from "blocked"

**Status from research:** CONFIRMED ACTIVE. Both confirmations and hard blocks return `block=True`. No distinct decision type.

**Files:**
- Modify: `safeclaw-service/safeclaw/api/models.py:94-100`
- Modify: `safeclaw-service/safeclaw/api/routes.py:155-162`
- Test: `safeclaw-service/tests/test_confirmation_flow.py`

- [ ] **Step 1: Validate bug exists**

```bash
cd safeclaw-service
python -c "
from safeclaw.api.models import DecisionResponse
# Both hard block and confirmation use block=True
hard_block = DecisionResponse(block=True, reason='Denied', confirmationRequired=False)
needs_confirm = DecisionResponse(block=True, reason='Confirm?', confirmationRequired=True)
# A naive client checking only 'block' treats both identically
print('Hard block.block:', hard_block.block)
print('Needs confirm.block:', needs_confirm.block)
print('Same block value:', hard_block.block == needs_confirm.block)
"
```

Expected: `Same block value: True` — confirming the ambiguity.

- [ ] **Step 2: Write failing test**

Create `safeclaw-service/tests/test_confirmation_flow.py`:

```python
"""Tests for confirmation vs blocked distinction in DecisionResponse."""
from safeclaw.api.models import DecisionResponse


def test_decision_response_has_decision_field():
    """DecisionResponse must have a 'decision' field with distinct values."""
    blocked = DecisionResponse(block=True, reason="Denied by policy")
    needs_confirm = DecisionResponse(
        block=True, reason="Confirm before delete?", confirmationRequired=True
    )
    allowed = DecisionResponse(block=False)

    assert hasattr(blocked, "decision"), "DecisionResponse missing 'decision' field"
    assert blocked.decision == "blocked"
    assert needs_confirm.decision == "needs_confirmation"
    assert allowed.decision == "allowed"


def test_decision_response_json_includes_decision():
    """The JSON serialization must include the decision field."""
    resp = DecisionResponse(
        block=True, reason="Confirm?", confirmationRequired=True
    )
    data = resp.model_dump(by_alias=True)
    assert "decision" in data
    assert data["decision"] == "needs_confirmation"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd safeclaw-service && python -m pytest tests/test_confirmation_flow.py -v
```

Expected: FAIL — `decision` field doesn't exist.

- [ ] **Step 4: Add computed decision field to DecisionResponse**

In `safeclaw-service/safeclaw/api/models.py`, modify `DecisionResponse`:

```python
class DecisionResponse(BaseModel):
    block: bool
    reason: str = ""
    auditId: str = ""
    confirmationRequired: bool = False
    constraintStep: str = ""
    riskLevel: str = ""

    @computed_field
    @property
    def decision(self) -> str:
        """Unambiguous decision type: 'allowed', 'blocked', or 'needs_confirmation'."""
        if not self.block:
            return "allowed"
        if self.confirmationRequired:
            return "needs_confirmation"
        return "blocked"
```

Add the import at the top of the file:

```python
from pydantic import BaseModel, computed_field
```

- [ ] **Step 5: Run tests**

```bash
cd safeclaw-service && python -m pytest tests/test_confirmation_flow.py tests/test_phase2.py tests/test_phase6.py -v
```

Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
cd safeclaw-service
git add safeclaw/api/models.py tests/test_confirmation_flow.py
git commit -m "fix(#128): add computed 'decision' field to DecisionResponse (allowed/blocked/needs_confirmation)"
```

---

### Task 6: #129 — CSRF token regenerated on every POST

**Status from research:** APPEARS FIXED. `get_csrf_token` checks `if "csrf_token" not in sess` before generating.

**Files:**
- Read: `safeclaw-service/safeclaw/dashboard/app.py:28-43`
- Test: `safeclaw-service/tests/test_csrf_stability.py`

- [ ] **Step 1: Validate bug — check if token persists across requests**

```bash
cd safeclaw-service
grep -n "csrf_token" safeclaw/dashboard/app.py
```

Expected: Find `if "csrf_token" not in sess:` guard — meaning the token is generated once and reused. If this guard exists, the bug is fixed.

- [ ] **Step 2: If bug is fixed, add regression test and close ticket**

Create `safeclaw-service/tests/test_csrf_stability.py`:

```python
"""Regression test for #129: CSRF token must persist within a session."""
from safeclaw.dashboard.app import get_csrf_token


def test_csrf_token_stable_within_session():
    """get_csrf_token must return the same token for the same session."""
    session = {}
    token1 = get_csrf_token(session)
    token2 = get_csrf_token(session)
    assert token1 == token2, "CSRF token changed between calls within same session"


def test_csrf_token_different_across_sessions():
    """Different sessions must get different tokens."""
    session1 = {}
    session2 = {}
    token1 = get_csrf_token(session1)
    token2 = get_csrf_token(session2)
    assert token1 != token2, "Different sessions got the same CSRF token"
```

- [ ] **Step 3: Run regression test**

```bash
cd safeclaw-service && python -m pytest tests/test_csrf_stability.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit and close ticket**

```bash
cd safeclaw-service
git add tests/test_csrf_stability.py
git commit -m "test(#129): add regression test confirming CSRF token stability within sessions"
```

```bash
gh issue close 129 --comment "Bug was fixed in a prior commit. Added regression test to prevent re-introduction."
```

---

## Batch 1B — High Bugs

### Task 7: #139 — SHA-256 password hashing insufficient

**Status from research:** CONFIRMED ACTIVE. `auth/api_key.py:39-42` uses `hashlib.sha256` for API key hashing.

**Files:**
- Modify: `safeclaw-service/safeclaw/auth/api_key.py:39-42`
- Test: `safeclaw-service/tests/test_api_key_hashing.py`

- [ ] **Step 1: Validate bug exists**

```bash
cd safeclaw-service
grep -n "sha256\|hashlib" safeclaw/auth/api_key.py
```

Expected: Find `hashlib.sha256(raw_key.encode()).hexdigest()` — confirming SHA-256 is used.

- [ ] **Step 2: Write failing test**

Create `safeclaw-service/tests/test_api_key_hashing.py`:

```python
"""Tests for API key hashing — must use bcrypt, not SHA-256."""
import hashlib

from safeclaw.auth.api_key import APIKeyManager


def test_hash_key_is_not_sha256():
    """API key hash must NOT be a raw SHA-256 hex digest."""
    raw_key = "test-api-key-12345"
    hashed = APIKeyManager.hash_key(raw_key)
    sha256_hex = hashlib.sha256(raw_key.encode()).hexdigest()
    assert hashed != sha256_hex, "API key is still hashed with plain SHA-256"


def test_hash_key_uses_bcrypt():
    """API key hash must be a bcrypt hash."""
    raw_key = "test-api-key-12345"
    hashed = APIKeyManager.hash_key(raw_key)
    assert hashed.startswith("$2b$"), f"Expected bcrypt hash, got: {hashed[:20]}..."


def test_hash_key_different_each_time():
    """bcrypt with random salt should produce different hashes for same input."""
    raw_key = "test-api-key-12345"
    hash1 = APIKeyManager.hash_key(raw_key)
    hash2 = APIKeyManager.hash_key(raw_key)
    assert hash1 != hash2, "Same input produced same hash — salt not being used"


def test_verify_key_matches():
    """Verification must succeed for correct key."""
    raw_key = "test-api-key-12345"
    hashed = APIKeyManager.hash_key(raw_key)
    assert APIKeyManager.verify_key(raw_key, hashed) is True


def test_verify_key_rejects_wrong_key():
    """Verification must fail for wrong key."""
    hashed = APIKeyManager.hash_key("correct-key")
    assert APIKeyManager.verify_key("wrong-key", hashed) is False
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd safeclaw-service && python -m pytest tests/test_api_key_hashing.py -v
```

Expected: `test_hash_key_is_not_sha256` and `test_hash_key_uses_bcrypt` FAIL.

- [ ] **Step 4: Replace SHA-256 with bcrypt in APIKeyManager**

In `safeclaw-service/safeclaw/auth/api_key.py`, replace:

```python
# BEFORE (lines 39-42):
@staticmethod
def hash_key(raw_key: str) -> str:
    """Hash an API key for storage."""
    return hashlib.sha256(raw_key.encode()).hexdigest()

# AFTER:
@staticmethod
def hash_key(raw_key: str) -> str:
    """Hash an API key for storage using bcrypt."""
    import bcrypt
    return bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()

@staticmethod
def verify_key(raw_key: str, hashed: str) -> bool:
    """Verify an API key against its bcrypt hash."""
    import bcrypt
    if hashed.startswith("$2b$"):
        return bcrypt.checkpw(raw_key.encode(), hashed.encode())
    # Legacy fallback: SHA-256 hex digest comparison for migration
    import hashlib
    return hashlib.sha256(raw_key.encode()).hexdigest() == hashed
```

- [ ] **Step 5: Update all callers that compare hashes directly**

Search for places that call `hash_key` and compare the result:

```bash
cd safeclaw-service
grep -rn "hash_key\|== .*hash" safeclaw/auth/api_key.py
```

In `APIKeyManager.validate_key` and `SQLiteAPIKeyManager.validate_key`, replace direct hash comparison with `verify_key`:

```python
# BEFORE:
if stored_hash == self.hash_key(raw_key):

# AFTER:
if self.verify_key(raw_key, stored_hash):
```

- [ ] **Step 6: Run all API key tests**

```bash
cd safeclaw-service && python -m pytest tests/test_api_key_hashing.py tests/test_phase5.py -v
```

Expected: ALL PASS.

- [ ] **Step 7: Commit**

```bash
cd safeclaw-service
git add safeclaw/auth/api_key.py tests/test_api_key_hashing.py
git commit -m "fix(#139): replace SHA-256 with bcrypt for API key hashing, add legacy fallback"
```

---

### Task 8: #136 — evaluate_tool_call doesn't sanitize input at engine level

**Status from research:** CONFIRMED ACTIVE. API routes sanitize, but `FullEngine.evaluate_tool_call()` does not. Direct engine callers bypass sanitization.

**Files:**
- Modify: `safeclaw-service/safeclaw/engine/full_engine.py:363-367`
- Test: `safeclaw-service/tests/test_engine_sanitization.py`

- [ ] **Step 1: Validate bug exists**

```bash
cd safeclaw-service
grep -n "sanitize\|_sanitize" safeclaw/engine/full_engine.py
```

Expected: NO sanitization in `evaluate_tool_call` or `_evaluate_tool_call_locked`. The sanitization only lives in `api/routes.py`.

- [ ] **Step 2: Write failing test**

Create `safeclaw-service/tests/test_engine_sanitization.py`:

```python
"""Tests for engine-level input sanitization."""
import pytest

from safeclaw.config import SafeClawConfig
from safeclaw.engine.core import ToolCallEvent
from safeclaw.engine.full_engine import FullEngine


@pytest.fixture
def engine():
    cfg = SafeClawConfig(run_reasoner_on_startup=False)
    return FullEngine(cfg)


@pytest.mark.asyncio
async def test_tool_call_params_are_sanitized(engine):
    """Engine must sanitize params even when called directly (not via API)."""
    event = ToolCallEvent(
        session_id="test-session",
        user_id="test-user",
        tool_name="write_file",
        params={"path": "/tmp/test.txt", "content": "normal <script>alert('xss')</script>"},
    )
    decision = await engine.evaluate_tool_call(event)
    # The params on the event should have been sanitized
    # (script tags stripped or escaped)
    assert "<script>" not in str(event.params.get("content", ""))


@pytest.mark.asyncio
async def test_tool_name_is_sanitized(engine):
    """Tool name with control characters must be sanitized."""
    event = ToolCallEvent(
        session_id="test-session",
        user_id="test-user",
        tool_name="write_file\x00\x01",
        params={},
    )
    decision = await engine.evaluate_tool_call(event)
    assert "\x00" not in event.tool_name
    assert "\x01" not in event.tool_name
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd safeclaw-service && python -m pytest tests/test_engine_sanitization.py -v
```

Expected: FAIL — no sanitization happening at engine level.

- [ ] **Step 4: Add sanitization to evaluate_tool_call**

In `safeclaw-service/safeclaw/engine/full_engine.py`, import the sanitization helpers from routes:

```python
from safeclaw.api.routes import _sanitize_params, _sanitize_string
```

Then modify `evaluate_tool_call` (around line 363):

```python
async def evaluate_tool_call(self, event: ToolCallEvent) -> Decision:
    """Run the full constraint checking pipeline."""
    # Sanitize inputs at the engine boundary (#136)
    event.tool_name = _sanitize_string(event.tool_name)
    event.params = _sanitize_params(event.params) if event.params else {}
    lock = await self._get_session_lock(event.session_id)
    async with lock:
        return await self._evaluate_tool_call_locked(event)
```

Note: If importing from `api.routes` creates a circular import, extract `_sanitize_params` and `_sanitize_string` into a shared `safeclaw/utils/sanitize.py` module and import from there in both files.

- [ ] **Step 5: Run tests**

```bash
cd safeclaw-service && python -m pytest tests/test_engine_sanitization.py tests/test_engine.py tests/test_api.py -v
```

Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
cd safeclaw-service
git add safeclaw/engine/full_engine.py tests/test_engine_sanitization.py
git commit -m "fix(#136): sanitize tool call inputs at engine level, not just API layer"
```

---

### Task 9: #135 — _sanitize_params doesn't recurse nested

**Status from research:** APPEARS FIXED. Current code at `routes.py:67-80` recurses into dicts and lists. Missing recursion depth limit.

**Files:**
- Read: `safeclaw-service/safeclaw/api/routes.py:52-80`
- Test: `safeclaw-service/tests/test_sanitize_recursion.py`

- [ ] **Step 1: Validate bug — check if recursion exists**

```bash
cd safeclaw-service
grep -A 20 "def _sanitize_params" safeclaw/api/routes.py
```

Expected: Find `isinstance(v, dict): sanitized[key] = _sanitize_params(v)` and `isinstance(v, list): sanitized[key] = _sanitize_list(v)`. If both exist, the primary bug is fixed.

- [ ] **Step 2: If fixed, add regression test + depth limit test**

Create `safeclaw-service/tests/test_sanitize_recursion.py`:

```python
"""Regression test for #135: sanitization must recurse and handle depth."""
from safeclaw.api.routes import _sanitize_params


def test_sanitize_recurses_nested_dicts():
    """Nested dict values must be sanitized."""
    params = {"outer": {"inner": "hello <script>alert(1)</script>"}}
    result = _sanitize_params(params)
    assert "<script>" not in result["outer"]["inner"]


def test_sanitize_recurses_nested_lists():
    """List values containing dicts must be sanitized."""
    params = {"items": [{"val": "<script>bad</script>"}]}
    result = _sanitize_params(params)
    assert "<script>" not in result["items"][0]["val"]


def test_sanitize_handles_deeply_nested_without_crash():
    """Deeply nested input must not cause RecursionError."""
    # Build 200-level deep nesting
    params: dict = {"value": "clean"}
    for _ in range(200):
        params = {"nested": params}
    # Should not raise RecursionError
    result = _sanitize_params(params)
    assert result is not None
```

- [ ] **Step 3: Run tests**

```bash
cd safeclaw-service && python -m pytest tests/test_sanitize_recursion.py -v
```

Expected: First two PASS (regression confirmed), third may FAIL if deeply nested input hits Python's recursion limit.

- [ ] **Step 4: If depth test fails, add recursion depth limit**

In `safeclaw-service/safeclaw/api/routes.py`, modify `_sanitize_params` to accept and enforce a depth parameter:

```python
_MAX_SANITIZE_DEPTH = 32


def _sanitize_params(params: dict, _depth: int = 0) -> dict:
    """Recursively sanitize string values in params dict (handles arbitrary nesting)."""
    if _depth > _MAX_SANITIZE_DEPTH:
        return {}  # Truncate excessively nested input
    sanitized = {}
    for k, v in params.items():
        key = _sanitize_string(str(k))
        if isinstance(v, str):
            sanitized[key] = _sanitize_string(v)
        elif isinstance(v, dict):
            sanitized[key] = _sanitize_params(v, _depth + 1)
        elif isinstance(v, list):
            sanitized[key] = _sanitize_list(v, _depth + 1)
        else:
            sanitized[key] = v
    return sanitized
```

Apply the same `_depth` parameter to `_sanitize_list`.

- [ ] **Step 5: Run tests again**

```bash
cd safeclaw-service && python -m pytest tests/test_sanitize_recursion.py tests/test_api.py -v
```

Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
cd safeclaw-service
git add safeclaw/api/routes.py tests/test_sanitize_recursion.py
git commit -m "fix(#135): add recursion depth limit to _sanitize_params, add regression tests"
```

---

### Task 10: #140 — Delegation detection trivially bypassed

**Status from research:** CONFIRMED ACTIVE. Detection requires exact tool_name match and same session_id. Bypassed by tool aliasing, new sessions, or semantically equivalent params.

**Files:**
- Modify: `safeclaw-service/safeclaw/engine/delegation_detector.py:110-160`
- Test: `safeclaw-service/tests/test_delegation_bypass.py`

- [ ] **Step 1: Validate bypass vectors**

```bash
cd safeclaw-service
grep -n "tool_name ==" safeclaw/engine/delegation_detector.py
```

Expected: Find exact string comparison like `record.tool_name == tool_name` — confirming no tool name normalization.

- [ ] **Step 2: Write failing tests for each bypass vector**

Create `safeclaw-service/tests/test_delegation_bypass.py`:

```python
"""Tests for delegation detection bypass vectors (#140)."""
import pytest

from safeclaw.engine.delegation_detector import DelegationDetector


@pytest.fixture
def detector():
    return DelegationDetector()


def test_tool_alias_bypass(detector):
    """Blocking 'exec' must also catch child using 'bash' or 'shell'."""
    detector.record_block(
        agent_id="parent",
        session_id="s1",
        tool_name="exec",
        params={"command": "rm -rf /"},
    )
    # Child uses 'bash' instead of 'exec' — same effect
    result = detector.check_delegation(
        parent_id="parent",
        child_id="child",
        session_id="s1",
        tool_name="bash",
        params={"command": "rm -rf /"},
    )
    assert result.is_delegation, "Tool alias 'bash' should be detected as delegation of blocked 'exec'"


def test_cross_session_bypass(detector):
    """Block recorded in session s1 must be checked when child uses session s2."""
    detector.record_block(
        agent_id="parent",
        session_id="s1",
        tool_name="exec",
        params={"command": "rm -rf /"},
    )
    result = detector.check_delegation(
        parent_id="parent",
        child_id="child",
        session_id="s2",  # Different session
        tool_name="exec",
        params={"command": "rm -rf /"},
    )
    assert result.is_delegation, "Cross-session delegation should be detected"


def test_param_variation_bypass(detector):
    """Semantically equivalent command with different formatting must be caught."""
    detector.record_block(
        agent_id="parent",
        session_id="s1",
        tool_name="exec",
        params={"command": "rm -rf /"},
    )
    result = detector.check_delegation(
        parent_id="parent",
        child_id="child",
        session_id="s1",
        tool_name="exec",
        params={"command": "rm -r -f /"},  # Same effect, different format
    )
    assert result.is_delegation, "Semantically equivalent command should be detected"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd safeclaw-service && python -m pytest tests/test_delegation_bypass.py -v
```

Expected: All three FAIL — detection doesn't handle aliases, cross-session, or param variations.

- [ ] **Step 4: Add tool name normalization**

In `safeclaw-service/safeclaw/engine/delegation_detector.py`, add a tool alias map and normalize before comparison:

```python
# Tool name aliases — tools that can achieve the same effect
_TOOL_ALIASES: dict[str, str] = {
    "bash": "exec",
    "shell": "exec",
    "sh": "exec",
    "spawn": "exec",
    "write_file": "fs_write",
    "create_file": "fs_write",
    "file_write": "fs_write",
    "delete_file": "fs_delete",
    "remove_file": "fs_delete",
    "file_delete": "fs_delete",
}


def _normalize_tool_name(tool_name: str) -> str:
    """Normalize tool name to canonical form for comparison."""
    return _TOOL_ALIASES.get(tool_name, tool_name)
```

Use `_normalize_tool_name` in both `record_block` and `check_delegation`.

- [ ] **Step 5: Add cross-session detection**

Modify `check_delegation` to search blocks by `parent_id` across ALL sessions, not just the current one:

```python
# BEFORE:
for record in self._blocks:
    if record.session_id == session_id and record.tool_name == tool_name:

# AFTER:
normalized_name = _normalize_tool_name(tool_name)
for record in self._blocks:
    if record.agent_id == parent_id and _normalize_tool_name(record.tool_name) == normalized_name:
```

- [ ] **Step 6: Add command normalization for param variation**

Add a helper that normalizes shell commands before hashing:

```python
import shlex

def _normalize_command(cmd: str) -> str:
    """Normalize a shell command for comparison (sort flags, collapse whitespace)."""
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return cmd.strip()
    if not parts:
        return cmd.strip()
    binary = parts[0]
    flags = sorted(p for p in parts[1:] if p.startswith("-"))
    args = [p for p in parts[1:] if not p.startswith("-")]
    return " ".join([binary] + flags + args)
```

Use this in `_compute_params_signature` for command-type params.

- [ ] **Step 7: Run all delegation tests**

```bash
cd safeclaw-service && python -m pytest tests/test_delegation_bypass.py tests/test_multi_agent_governance.py -v
```

Expected: ALL PASS.

- [ ] **Step 8: Commit**

```bash
cd safeclaw-service
git add safeclaw/engine/delegation_detector.py tests/test_delegation_bypass.py
git commit -m "fix(#140): harden delegation detection — tool aliases, cross-session, command normalization"
```

---

### Task 11: #138 — Governance state in-memory only

**Status from research:** CONFIRMED ACTIVE. Docstring in `full_engine.py:86-98` explicitly acknowledges the problem. All state in `OrderedDict`s.

This is the largest fix in Phase 1. The approach is to add a **state persistence layer** using SQLite (already a dependency for the landing site), with write-behind for performance.

**Files:**
- Create: `safeclaw-service/safeclaw/engine/state_store.py`
- Modify: `safeclaw-service/safeclaw/engine/full_engine.py:83-173`
- Modify: `safeclaw-service/safeclaw/engine/agent_registry.py`
- Test: `safeclaw-service/tests/test_state_persistence.py`

- [ ] **Step 1: Validate bug exists**

```bash
cd safeclaw-service
grep -n "OrderedDict\|dict\[str" safeclaw/engine/agent_registry.py safeclaw/engine/session_tracker.py safeclaw/constraints/rate_limiter.py safeclaw/engine/temp_permissions.py
```

Expected: Find `OrderedDict()` or `dict()` for agent records, session state, rate limits, temp permissions — all in-memory with no persistence.

- [ ] **Step 2: Write failing test**

Create `safeclaw-service/tests/test_state_persistence.py`:

```python
"""Tests for governance state persistence across restarts (#138)."""
import pytest

from safeclaw.config import SafeClawConfig
from safeclaw.engine.state_store import StateStore


@pytest.fixture
def state_store(tmp_path):
    db_path = tmp_path / "state.db"
    return StateStore(db_path)


def test_agent_kill_persists(state_store):
    """A killed agent must remain killed after store is reopened."""
    state_store.save_agent_kill("agent-1", reason="security violation")
    state_store.close()

    # Reopen
    store2 = StateStore(state_store.db_path)
    assert store2.is_agent_killed("agent-1") is True
    store2.close()


def test_agent_revive_persists(state_store):
    """Reviving an agent must persist."""
    state_store.save_agent_kill("agent-1", reason="test")
    state_store.revive_agent("agent-1")
    state_store.close()

    store2 = StateStore(state_store.db_path)
    assert store2.is_agent_killed("agent-1") is False
    store2.close()


def test_rate_limit_counter_persists(state_store):
    """Rate limit counters must survive restart."""
    state_store.increment_rate_counter("agent-1", "exec", window_key="2026-03-26T10")
    state_store.increment_rate_counter("agent-1", "exec", window_key="2026-03-26T10")
    state_store.close()

    store2 = StateStore(state_store.db_path)
    count = store2.get_rate_counter("agent-1", "exec", window_key="2026-03-26T10")
    assert count == 2
    store2.close()


def test_temp_permission_persists(state_store):
    """Unexpired temp permissions must survive restart."""
    import time
    state_store.save_temp_permission(
        agent_id="agent-1",
        action_class="FileWrite",
        expires_at=time.time() + 3600,
    )
    state_store.close()

    store2 = StateStore(state_store.db_path)
    perms = store2.get_active_temp_permissions("agent-1")
    assert len(perms) == 1
    assert perms[0]["action_class"] == "FileWrite"
    store2.close()
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd safeclaw-service && python -m pytest tests/test_state_persistence.py -v
```

Expected: FAIL — `StateStore` doesn't exist.

- [ ] **Step 4: Implement StateStore**

Create `safeclaw-service/safeclaw/engine/state_store.py`:

```python
"""Persistent governance state store backed by SQLite.

Stores agent kill states, rate limit counters, and temp permissions
so they survive service restarts. Uses WAL mode for concurrent reads.
"""
import sqlite3
import time
from pathlib import Path


class StateStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._create_tables()

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS agent_kills (
                agent_id TEXT PRIMARY KEY,
                reason TEXT NOT NULL,
                killed_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rate_counters (
                agent_id TEXT NOT NULL,
                action TEXT NOT NULL,
                window_key TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (agent_id, action, window_key)
            );
            CREATE TABLE IF NOT EXISTS temp_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                action_class TEXT NOT NULL,
                expires_at REAL NOT NULL
            );
        """)
        self._conn.commit()

    def save_agent_kill(self, agent_id: str, reason: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO agent_kills (agent_id, reason, killed_at) VALUES (?, ?, ?)",
            (agent_id, reason, time.time()),
        )
        self._conn.commit()

    def revive_agent(self, agent_id: str) -> None:
        self._conn.execute("DELETE FROM agent_kills WHERE agent_id = ?", (agent_id,))
        self._conn.commit()

    def is_agent_killed(self, agent_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM agent_kills WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        return row is not None

    def increment_rate_counter(self, agent_id: str, action: str, window_key: str) -> int:
        self._conn.execute(
            """INSERT INTO rate_counters (agent_id, action, window_key, count)
               VALUES (?, ?, ?, 1)
               ON CONFLICT (agent_id, action, window_key)
               DO UPDATE SET count = count + 1""",
            (agent_id, action, window_key),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT count FROM rate_counters WHERE agent_id=? AND action=? AND window_key=?",
            (agent_id, action, window_key),
        ).fetchone()
        return row[0] if row else 0

    def get_rate_counter(self, agent_id: str, action: str, window_key: str) -> int:
        row = self._conn.execute(
            "SELECT count FROM rate_counters WHERE agent_id=? AND action=? AND window_key=?",
            (agent_id, action, window_key),
        ).fetchone()
        return row[0] if row else 0

    def save_temp_permission(self, agent_id: str, action_class: str, expires_at: float) -> None:
        self._conn.execute(
            "INSERT INTO temp_permissions (agent_id, action_class, expires_at) VALUES (?, ?, ?)",
            (agent_id, action_class, expires_at),
        )
        self._conn.commit()

    def get_active_temp_permissions(self, agent_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT action_class, expires_at FROM temp_permissions WHERE agent_id=? AND expires_at > ?",
            (agent_id, time.time()),
        ).fetchall()
        return [{"action_class": r[0], "expires_at": r[1]} for r in rows]

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 5: Run tests**

```bash
cd safeclaw-service && python -m pytest tests/test_state_persistence.py -v
```

Expected: ALL PASS.

- [ ] **Step 6: Wire StateStore into FullEngine**

In `safeclaw-service/safeclaw/engine/full_engine.py`, in `__init__`:

```python
from safeclaw.engine.state_store import StateStore

# After other initialization:
state_db = self.config.data_dir / "governance_state.db"
self._state_store = StateStore(state_db)
```

Then in `AgentRegistry`, use `_state_store.is_agent_killed()` as the source of truth for kill state, with the in-memory cache as a fast path.

This is a large wiring task — the key principle is: **in-memory state remains the fast path for reads, StateStore is the write-through persistence layer for kill state, rate limits, and temp permissions.**

- [ ] **Step 7: Run full test suite**

```bash
cd safeclaw-service && python -m pytest tests/ -v --timeout=60
```

Expected: ALL PASS. No regressions.

- [ ] **Step 8: Commit**

```bash
cd safeclaw-service
git add safeclaw/engine/state_store.py safeclaw/engine/full_engine.py tests/test_state_persistence.py
git commit -m "fix(#138): add SQLite-backed StateStore for governance state persistence across restarts"
```

---

### Task 12: #134 — Audit hash chain resets on restart

**Status from research:** APPEARS FIXED. `_load_last_hash` reads the last hash from the most recent audit log file on startup.

**Files:**
- Read: `safeclaw-service/safeclaw/audit/logger.py:55-89`
- Test: `safeclaw-service/tests/test_audit_hash_chain.py`

- [ ] **Step 1: Validate bug — check if hash chain loads on restart**

```bash
cd safeclaw-service
grep -n "_load_last_hash\|_prev_hash" safeclaw/audit/logger.py
```

Expected: Find `self._prev_hash = self._load_last_hash()` in constructor. If present, the restart-reset bug is fixed.

- [ ] **Step 2: If fixed, add regression test and close**

Create `safeclaw-service/tests/test_audit_hash_chain.py`:

```python
"""Regression test for #134: audit hash chain must persist across restarts."""
import json
from pathlib import Path

from safeclaw.audit.logger import AuditLogger


def test_hash_chain_continues_after_restart(tmp_path):
    """Second AuditLogger instance must continue the hash chain from the first."""
    audit_dir = tmp_path / "audit"

    logger1 = AuditLogger(audit_dir=audit_dir)
    logger1.log_decision(
        session_id="s1",
        tool_name="exec",
        decision_block=True,
        reason="test",
    )
    last_hash_before = logger1._prev_hash
    del logger1  # Simulate restart

    logger2 = AuditLogger(audit_dir=audit_dir)
    assert logger2._prev_hash is not None, "Hash chain lost on restart"
    assert logger2._prev_hash == last_hash_before, "Hash chain did not continue"
```

- [ ] **Step 3: Run test**

```bash
cd safeclaw-service && python -m pytest tests/test_audit_hash_chain.py -v
```

Expected: PASS if fixed, FAIL if `_load_last_hash` doesn't work correctly.

- [ ] **Step 4: If test passes, commit and close. If fails, fix _load_last_hash.**

```bash
cd safeclaw-service
git add tests/test_audit_hash_chain.py
git commit -m "test(#134): add regression test for audit hash chain persistence across restarts"
```

```bash
gh issue close 134 --comment "Hash chain persistence was fixed in a prior commit via _load_last_hash(). Added regression test."
```

---

### Task 13: #143 — graph_builder cache uses id() which can be reused

**Status from research:** PARTIALLY MITIGATED. Generation counter added, but stale `_kg_generations` entries aren't cleaned up when KG is GC'd without explicit `invalidate_cache`.

**Files:**
- Modify: `safeclaw-service/safeclaw/engine/graph_builder.py:7-32`
- Test: `safeclaw-service/tests/test_graph_builder_cache.py`

- [ ] **Step 1: Validate the edge case**

```bash
cd safeclaw-service
grep -n "_kg_generations\|invalidate_cache\|_get_generation" safeclaw/engine/graph_builder.py
```

Expected: Find `_kg_generations` dict that is never cleaned up on GC. If `invalidate_cache` is the only cleanup path, the stale entry bug exists when KGs are simply dropped.

- [ ] **Step 2: Write test for the edge case**

Create `safeclaw-service/tests/test_graph_builder_cache.py`:

```python
"""Tests for graph_builder cache — verifies no stale cache hits after KG replacement."""
from safeclaw.engine.graph_builder import GraphBuilder, _kg_generations
from safeclaw.engine.knowledge_graph import KnowledgeGraph


def test_new_kg_gets_fresh_generation_even_if_same_id():
    """If a new KG gets the same id() as a freed one, it must get a fresh generation."""
    kg1 = KnowledgeGraph()
    builder1 = GraphBuilder(kg1)
    gen1 = builder1._generation

    # Explicitly invalidate and drop
    builder1.invalidate_cache()
    old_id = id(kg1)
    del kg1

    # Create new KG — may or may not get the same id()
    kg2 = KnowledgeGraph()
    builder2 = GraphBuilder(kg2)
    gen2 = builder2._generation

    # Regardless of id() reuse, generations must differ
    assert gen2 != gen1, "New KG reused stale generation number"
```

- [ ] **Step 3: Run test**

```bash
cd safeclaw-service && python -m pytest tests/test_graph_builder_cache.py -v
```

Expected: May PASS or FAIL depending on whether Python reuses the id.

- [ ] **Step 4: If test fails, fix _get_generation to use weakrefs**

In `safeclaw-service/safeclaw/engine/graph_builder.py`, use `weakref.finalize` to auto-clean stale entries:

```python
import weakref

def _get_generation(kg: KnowledgeGraph) -> int:
    kg_id = id(kg)
    if kg_id not in _kg_generations:
        _kg_generations[kg_id] = next(_generation_counter)
        # Auto-cleanup when the KG is garbage collected
        weakref.finalize(kg, _kg_generations.pop, kg_id, None)
    return _kg_generations[kg_id]
```

This ensures that when a `KnowledgeGraph` is garbage collected, its entry is removed from `_kg_generations`, so a new object with the same `id()` gets a fresh generation.

- [ ] **Step 5: Run tests**

```bash
cd safeclaw-service && python -m pytest tests/test_graph_builder_cache.py tests/test_engine.py -v
```

Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
cd safeclaw-service
git add safeclaw/engine/graph_builder.py tests/test_graph_builder_cache.py
git commit -m "fix(#143): use weakref.finalize to clean stale graph_builder cache entries"
```

---

### Task 14: #142 — _glob_match breaks on Python 3.11

**Status from research:** Code has version-specific handling but edge cases may exist with empty segments from `pattern.split("**")`.

**Files:**
- Read: `safeclaw-service/safeclaw/engine/roles.py:20-56`
- Test: `safeclaw-service/tests/test_glob_match.py`

- [ ] **Step 1: Validate — test edge cases**

```bash
cd safeclaw-service
python -c "
from safeclaw.engine.roles import _glob_match
# Test cases that might break:
print('basic:', _glob_match('/tmp/foo.py', '/tmp/*.py'))
print('double star:', _glob_match('/a/b/c/d.py', '/a/**/d.py'))
print('empty segment:', _glob_match('/a/b', '**'))
print('trailing star:', _glob_match('/a/b/c', '/a/**'))
"
```

Expected: Check if any return incorrect results. If all correct, bug may be fixed.

- [ ] **Step 2: Write comprehensive tests**

Create `safeclaw-service/tests/test_glob_match.py`:

```python
"""Tests for _glob_match across Python versions (#142)."""
import pytest

from safeclaw.engine.roles import _glob_match


@pytest.mark.parametrize("path,pattern,expected", [
    ("/tmp/foo.py", "/tmp/*.py", True),
    ("/tmp/foo.txt", "/tmp/*.py", False),
    ("/a/b/c/d.py", "/a/**/d.py", True),
    ("/a/d.py", "/a/**/d.py", True),
    ("/a/b/c", "/a/**", True),
    ("/a", "/a/**", False),  # ** matches one or more segments
    ("/a/b/c", "**", True),
    ("/tmp/foo", "/tmp/foo", True),
    ("/tmp/foo", "/tmp/bar", False),
    ("/a/b/c.py", "**/*.py", True),
    ("", "**", False),  # Empty path
    ("/a/b", "/a/b/**", False),  # No trailing path after **
])
def test_glob_match(path, pattern, expected):
    result = _glob_match(path, pattern)
    assert result == expected, f"_glob_match({path!r}, {pattern!r}) = {result}, expected {expected}"
```

- [ ] **Step 3: Run tests**

```bash
cd safeclaw-service && python -m pytest tests/test_glob_match.py -v
```

Expected: Identify which patterns fail. Fix any failures in `_glob_match`.

- [ ] **Step 4: Fix any failing patterns**

If edge cases fail, fix the regex construction in `_glob_match`. The most common issue is empty segments from `split("**")` producing invalid regex fragments. Add an early check:

```python
# In _glob_match, after segments = pattern.split("**"):
segments = [s for s in segments if s]  # Remove empty segments
if not segments:
    # Pattern is just "**" — matches everything
    return bool(path)
```

- [ ] **Step 5: Run all role-related tests**

```bash
cd safeclaw-service && python -m pytest tests/test_glob_match.py tests/test_multi_agent_governance.py -v
```

Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
cd safeclaw-service
git add safeclaw/engine/roles.py tests/test_glob_match.py
git commit -m "fix(#142): harden _glob_match for Python 3.11+ edge cases"
```

---

### Task 15: #141 — HeartbeatMonitor config drift fires continuously

**Status from research:** The `stale_notified` flag prevents repeated event bus publishes, but `check_stale()` is called on every heartbeat from every agent (O(n) scan).

**Files:**
- Read: `safeclaw-service/safeclaw/engine/heartbeat_monitor.py:58-77`
- Test: `safeclaw-service/tests/test_heartbeat_monitor.py`

- [ ] **Step 1: Validate — measure the actual issue**

```bash
cd safeclaw-service
grep -n "check_stale\|stale_notified\|config_drift" safeclaw/engine/heartbeat_monitor.py safeclaw/api/routes.py
```

Expected: Find `check_stale()` called from both heartbeat endpoint and dashboard page.

Read the GitHub issue body for #141 to understand if the reported issue is about the event bus firing or config drift specifically:

```bash
gh issue view 141 --json body --jq .body | head -30
```

- [ ] **Step 2: Based on validation, write targeted test**

If the issue is about config drift detection firing continuously (not heartbeat staleness), write a test for that specific behavior:

```python
"""Test for #141: config drift detection must fire once, not continuously."""
from safeclaw.engine.heartbeat_monitor import HeartbeatMonitor


def test_config_drift_fires_only_once():
    """Config drift event must fire once per drift, not on every check."""
    from unittest.mock import MagicMock
    event_bus = MagicMock()
    monitor = HeartbeatMonitor(event_bus)

    # Agent sends heartbeat with hash "abc"
    monitor.record("agent-1", config_hash="abc")
    # Agent sends heartbeat with DIFFERENT hash — drift detected
    monitor.record("agent-1", config_hash="xyz")

    # Check how many drift events were published
    drift_calls = [
        c for c in event_bus.publish.call_args_list
        if "config_drift" in str(c)
    ]
    assert len(drift_calls) <= 1, f"Config drift event fired {len(drift_calls)} times, expected at most 1"
```

- [ ] **Step 3: Run test, fix if needed**

```bash
cd safeclaw-service && python -m pytest tests/test_heartbeat_monitor.py -v
```

If the test fails, add a `drift_notified` flag similar to `stale_notified`:

```python
# In record():
if config_hash and config_hash != self._agents[agent_id].get("config_hash"):
    if not self._agents[agent_id].get("drift_notified"):
        self._event_bus.publish(...)
        self._agents[agent_id]["drift_notified"] = True
    self._agents[agent_id]["config_hash"] = config_hash
```

- [ ] **Step 4: Commit**

```bash
cd safeclaw-service
git add safeclaw/engine/heartbeat_monitor.py tests/test_heartbeat_monitor.py
git commit -m "fix(#141): prevent HeartbeatMonitor config drift from firing continuously"
```

---

### Task 16: #137 — Dead engine modes (hybrid/cached)

**Status from research:** Both files deprecated with warnings, `CachedEngine.evaluate_tool_call` always returns `Decision(block=False)` — zero governance.

**Files:**
- Delete: `safeclaw-service/safeclaw/engine/cached_engine.py`
- Delete: `safeclaw-service/safeclaw/engine/hybrid_engine.py`
- Modify: `safeclaw-service/tests/test_coverage.py` (remove CachedEngine tests)
- Modify: `safeclaw-service/tests/test_phase5.py` (remove HybridEngine tests)

- [ ] **Step 1: Validate — confirm the files are unused**

```bash
cd safeclaw-service
grep -rn "CachedEngine\|HybridEngine\|cached_engine\|hybrid_engine" safeclaw/ --include="*.py" | grep -v "test_" | grep -v "__pycache__"
```

Expected: Only find the definition files themselves and possibly imports that are never used. No production code should instantiate these.

- [ ] **Step 2: Remove the dead engine files**

```bash
cd safeclaw-service
rm safeclaw/engine/cached_engine.py safeclaw/engine/hybrid_engine.py
```

- [ ] **Step 3: Remove references from __init__.py if any**

```bash
grep -n "CachedEngine\|HybridEngine" safeclaw/engine/__init__.py
```

If found, remove the imports.

- [ ] **Step 4: Remove dead tests**

In `tests/test_coverage.py`, remove the `CachedEngine` test class.
In `tests/test_phase5.py`, remove the `TestHybridEngine` class.

- [ ] **Step 5: Run full test suite to verify no regressions**

```bash
cd safeclaw-service && python -m pytest tests/ -v --timeout=60
```

Expected: ALL PASS (minus the removed tests).

- [ ] **Step 6: Commit**

```bash
cd safeclaw-service
git add -A safeclaw/engine/ tests/
git commit -m "fix(#137): remove dead CachedEngine and HybridEngine — always use FullEngine"
```

---

## Post-Phase 1 Checklist

After all tasks are complete:

- [ ] **Run full test suite**: `cd safeclaw-service && python -m pytest tests/ -v`
- [ ] **Run linter**: `cd safeclaw-service && ruff check safeclaw/ tests/`
- [ ] **Run formatter check**: `cd safeclaw-service && ruff format --check safeclaw/ tests/`
- [ ] **Close superseded/fixed tickets**: #129, #130, #134 (if confirmed fixed) with comments referencing regression tests
- [ ] **Verify all 16 tickets have commits**: `git log --oneline | head -20`
