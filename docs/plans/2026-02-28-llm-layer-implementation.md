# LLM Layer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a passive LLM observer layer (Mistral) to SafeClaw that compiles NL→policy, reviews security semantically, observes classification fallbacks, and explains decisions — without ever touching the critical enforcement path.

**Architecture:** Four capabilities (client, security reviewer, classification observer, decision explainer, policy compiler) built as `safeclaw/llm/` module. All LLM calls are fire-and-forget (`asyncio.create_task`) or on-demand (CLI/API). The symbolic engine remains the sole enforcer. If no API key is set, zero behavior change.

**Tech Stack:** `mistralai` Python SDK, existing SafeClaw config/engine/audit infrastructure.

**Design doc:** `docs/plans/2026-02-28-llm-layer-design.md`

---

## Task 1: Add `mistralai` dependency and LLM config fields

**Files:**
- Modify: `safeclaw-service/pyproject.toml`
- Modify: `safeclaw-service/safeclaw/config.py`
- Test: `safeclaw-service/tests/test_config.py`

**Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_llm_config_defaults():
    """LLM config fields exist with correct defaults."""
    from safeclaw.config import SafeClawConfig
    config = SafeClawConfig()
    assert config.mistral_api_key == ""
    assert config.mistral_model == "mistral-small-latest"
    assert config.mistral_model_large == "mistral-large-latest"
    assert config.mistral_timeout_ms == 3000
    assert config.llm_security_review_enabled is True
    assert config.llm_classification_observe is True


def test_llm_disabled_without_api_key():
    """LLM is considered disabled when no API key is set."""
    from safeclaw.config import SafeClawConfig
    config = SafeClawConfig()
    assert config.mistral_api_key == ""
    # Presence of empty string means disabled
```

**Step 2: Run test to verify it fails**

Run: `cd safeclaw-service && python -m pytest tests/test_config.py::test_llm_config_defaults -v`
Expected: FAIL — `SafeClawConfig` has no attribute `mistral_api_key`

**Step 3: Add dependency to pyproject.toml**

In `safeclaw-service/pyproject.toml`, add `"mistralai>=1.0.0"` to the `dependencies` list (after `"rich>=13.0"`).

**Step 4: Add config fields to SafeClawConfig**

In `safeclaw-service/safeclaw/config.py`, add these fields to `SafeClawConfig` after `log_level`:

```python
    # LLM layer (passive observer — all features gated on mistral_api_key)
    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-latest"
    mistral_model_large: str = "mistral-large-latest"
    mistral_timeout_ms: int = 3000
    llm_security_review_enabled: bool = True
    llm_classification_observe: bool = True
```

**Step 5: Run test to verify it passes**

Run: `cd safeclaw-service && python -m pytest tests/test_config.py -v`
Expected: ALL PASS

**Step 6: Install the new dependency**

Run: `cd safeclaw-service && pip install -e ".[dev]"`

**Step 7: Run full test suite to verify no regressions**

Run: `cd safeclaw-service && python -m pytest tests/ -v`
Expected: ALL PASS (233+ tests)

**Step 8: Commit**

```bash
git add safeclaw-service/pyproject.toml safeclaw-service/safeclaw/config.py safeclaw-service/tests/test_config.py
git commit -m "feat: add mistralai dependency and LLM config fields"
```

---

## Task 2: Create `safeclaw/llm/client.py` — Mistral client wrapper

**Files:**
- Create: `safeclaw-service/safeclaw/llm/__init__.py`
- Create: `safeclaw-service/safeclaw/llm/client.py`
- Create: `safeclaw-service/tests/test_llm_client.py`

**Step 1: Write the failing test**

Create `safeclaw-service/tests/test_llm_client.py`:

```python
"""Tests for the Mistral client wrapper."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from safeclaw.config import SafeClawConfig


def test_create_client_returns_wrapper():
    """create_client returns a SafeClawLLMClient with correct config."""
    from safeclaw.llm.client import create_client

    config = SafeClawConfig(mistral_api_key="test-key-123")
    client = create_client(config)
    assert client is not None
    assert client.model == "mistral-small-latest"
    assert client.model_large == "mistral-large-latest"
    assert client.timeout_ms == 3000


def test_create_client_no_key_returns_none():
    """create_client returns None when no API key is configured."""
    from safeclaw.llm.client import create_client

    config = SafeClawConfig(mistral_api_key="")
    client = create_client(config)
    assert client is None


@pytest.mark.asyncio
async def test_chat_returns_content():
    """chat() calls Mistral and returns the text content."""
    from safeclaw.llm.client import SafeClawLLMClient

    mock_mistral = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hello from Mistral"
    mock_mistral.chat.complete_async = AsyncMock(return_value=mock_response)

    client = SafeClawLLMClient(
        mistral_client=mock_mistral,
        model="mistral-small-latest",
        model_large="mistral-large-latest",
        timeout_ms=3000,
    )
    result = await client.chat(
        messages=[{"role": "user", "content": "Hi"}],
    )
    assert result == "Hello from Mistral"
    mock_mistral.chat.complete_async.assert_called_once()


@pytest.mark.asyncio
async def test_chat_timeout_returns_none():
    """chat() returns None on timeout."""
    from safeclaw.llm.client import SafeClawLLMClient

    mock_mistral = MagicMock()
    mock_mistral.chat.complete_async = AsyncMock(side_effect=Exception("timeout"))

    client = SafeClawLLMClient(
        mistral_client=mock_mistral,
        model="mistral-small-latest",
        model_large="mistral-large-latest",
        timeout_ms=3000,
    )
    result = await client.chat(
        messages=[{"role": "user", "content": "Hi"}],
    )
    assert result is None


@pytest.mark.asyncio
async def test_chat_json_parses_response():
    """chat_json() parses JSON from LLM response."""
    from safeclaw.llm.client import SafeClawLLMClient

    mock_mistral = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"suspicious": false}'
    mock_mistral.chat.complete_async = AsyncMock(return_value=mock_response)

    client = SafeClawLLMClient(
        mistral_client=mock_mistral,
        model="mistral-small-latest",
        model_large="mistral-large-latest",
        timeout_ms=3000,
    )
    result = await client.chat_json(
        messages=[{"role": "user", "content": "review this"}],
    )
    assert result == {"suspicious": False}


@pytest.mark.asyncio
async def test_chat_json_invalid_json_returns_none():
    """chat_json() returns None when LLM response is not valid JSON."""
    from safeclaw.llm.client import SafeClawLLMClient

    mock_mistral = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "not json at all"
    mock_mistral.chat.complete_async = AsyncMock(return_value=mock_response)

    client = SafeClawLLMClient(
        mistral_client=mock_mistral,
        model="mistral-small-latest",
        model_large="mistral-large-latest",
        timeout_ms=3000,
    )
    result = await client.chat_json(
        messages=[{"role": "user", "content": "review this"}],
    )
    assert result is None
```

**Step 2: Run test to verify it fails**

Run: `cd safeclaw-service && python -m pytest tests/test_llm_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'safeclaw.llm'`

**Step 3: Create the `__init__.py`**

Create `safeclaw-service/safeclaw/llm/__init__.py`:

```python
"""SafeClaw LLM layer — passive observer and advisor."""
```

**Step 4: Implement `client.py`**

Create `safeclaw-service/safeclaw/llm/client.py`:

```python
"""Mistral client wrapper with timeout, error handling, and graceful degradation."""

import asyncio
import json
import logging

from safeclaw.config import SafeClawConfig

logger = logging.getLogger("safeclaw.llm")


class SafeClawLLMClient:
    """Thin wrapper around the Mistral SDK with timeout and error handling."""

    def __init__(self, mistral_client, model: str, model_large: str, timeout_ms: int):
        self._client = mistral_client
        self.model = model
        self.model_large = model_large
        self.timeout_ms = timeout_ms

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> str | None:
        """Send a chat completion request. Returns content string or None on failure."""
        try:
            response = await asyncio.wait_for(
                self._client.chat.complete_async(
                    model=model or self.model,
                    messages=messages,
                    temperature=temperature,
                ),
                timeout=self.timeout_ms / 1000,
            )
            return response.choices[0].message.content
        except asyncio.TimeoutError:
            logger.warning("LLM request timed out after %dms", self.timeout_ms)
            return None
        except Exception:
            logger.warning("LLM request failed", exc_info=True)
            return None

    async def chat_json(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> dict | None:
        """Send a chat request and parse the response as JSON. Returns dict or None."""
        content = await self.chat(messages, model=model, temperature=temperature)
        if content is None:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning("LLM response was not valid JSON: %s", content[:200])
            return None


def create_client(config: SafeClawConfig) -> SafeClawLLMClient | None:
    """Create a SafeClawLLMClient from config. Returns None if no API key."""
    if not config.mistral_api_key:
        return None

    try:
        from mistralai import Mistral

        mistral = Mistral(api_key=config.mistral_api_key)
        return SafeClawLLMClient(
            mistral_client=mistral,
            model=config.mistral_model,
            model_large=config.mistral_model_large,
            timeout_ms=config.mistral_timeout_ms,
        )
    except Exception:
        logger.warning("Failed to initialize Mistral client", exc_info=True)
        return None
```

**Step 5: Run tests to verify they pass**

Run: `cd safeclaw-service && python -m pytest tests/test_llm_client.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add safeclaw-service/safeclaw/llm/ safeclaw-service/tests/test_llm_client.py
git commit -m "feat: add Mistral client wrapper with timeout and graceful degradation"
```

---

## Task 3: Create `safeclaw/llm/prompts.py` — All prompt templates

**Files:**
- Create: `safeclaw-service/safeclaw/llm/prompts.py`
- Create: `safeclaw-service/tests/test_llm_prompts.py`

**Step 1: Write the failing test**

Create `safeclaw-service/tests/test_llm_prompts.py`:

```python
"""Tests for LLM prompt templates."""

from safeclaw.llm.prompts import (
    SECURITY_REVIEW_SYSTEM,
    CLASSIFICATION_OBSERVER_SYSTEM,
    DECISION_EXPLAINER_SYSTEM,
    POLICY_COMPILER_SYSTEM,
    build_security_review_user_prompt,
    build_classification_observer_user_prompt,
    build_explainer_user_prompt,
)


def test_security_review_system_prompt_exists():
    assert "security reviewer" in SECURITY_REVIEW_SYSTEM.lower()
    assert "evasion" in SECURITY_REVIEW_SYSTEM.lower()


def test_build_security_review_user_prompt():
    prompt = build_security_review_user_prompt(
        tool_name="exec",
        params={"command": "echo cm0gLXJmIC8= | base64 -d | sh"},
        ontology_class="ExecuteCommand",
        risk_level="MediumRisk",
        symbolic_decision="allowed",
        session_history=["ReadFile", "WriteFile"],
        constraints_checked=[{"type": "SHACL", "result": "satisfied"}],
    )
    assert "exec" in prompt
    assert "base64" in prompt
    assert "allowed" in prompt


def test_build_classification_observer_user_prompt():
    prompt = build_classification_observer_user_prompt(
        tool_name="custom_tool",
        params={"arg": "value"},
        symbolic_class="Action",
        risk_level="MediumRisk",
    )
    assert "custom_tool" in prompt
    assert "Action" in prompt


def test_build_explainer_user_prompt():
    prompt = build_explainer_user_prompt(
        tool_name="exec",
        params={"command": "git push --force"},
        ontology_class="ForcePush",
        risk_level="CriticalRisk",
        decision="blocked",
        reason="Force push can destroy shared history",
        constraints_checked=[{"type": "Policy", "result": "violated", "reason": "No force push"}],
    )
    assert "ForcePush" in prompt
    assert "blocked" in prompt


def test_policy_compiler_system_prompt_exists():
    assert "turtle" in POLICY_COMPILER_SYSTEM.lower() or "Turtle" in POLICY_COMPILER_SYSTEM
```

**Step 2: Run test to verify it fails**

Run: `cd safeclaw-service && python -m pytest tests/test_llm_prompts.py -v`
Expected: FAIL — `ModuleNotFoundError` or `ImportError`

**Step 3: Implement prompts.py**

Create `safeclaw-service/safeclaw/llm/prompts.py`:

```python
"""All LLM prompt templates for SafeClaw's passive observer layer."""

import json

# ── Security Reviewer ──

SECURITY_REVIEW_SYSTEM = """\
You are a security reviewer for SafeClaw, an AI agent governance system.

You analyze tool calls that ALREADY passed symbolic constraint checks (SHACL, \
policy rules, regex patterns). Your job is to find what those rigid checks missed:

- Base64/hex-encoded payloads hiding destructive commands
- Multi-step evasion: individually safe actions that chain into something dangerous
- URL-based payload delivery (curl | sh, wget | python)
- Flag reordering or aliases that bypass regex patterns
- Environment variable manipulation to change tool behavior
- File write + execute sequences (script injection)

You are deliberately paranoid. If something looks safe, say so explicitly. \
If something looks suspicious, explain exactly why and how confident you are.

Respond with ONLY a JSON object (no markdown fences):
{
  "suspicious": true/false,
  "severity": "low" | "medium" | "high" | "critical",
  "category": "obfuscation" | "evasion" | "multi_step" | "novel_risk" | "none",
  "description": "what you found or why it's safe",
  "recommended_action": "log" | "escalate_confirmation" | "kill_switch",
  "confidence": 0.0-1.0
}

If the action is safe, use: {"suspicious": false, "severity": "low", \
"category": "none", "description": "...", "recommended_action": "log", \
"confidence": 1.0}"""


def build_security_review_user_prompt(
    tool_name: str,
    params: dict,
    ontology_class: str,
    risk_level: str,
    symbolic_decision: str,
    session_history: list[str],
    constraints_checked: list[dict],
) -> str:
    return json.dumps(
        {
            "tool_name": tool_name,
            "params": params,
            "symbolic_classification": {
                "ontology_class": ontology_class,
                "risk_level": risk_level,
            },
            "symbolic_decision": symbolic_decision,
            "recent_session_actions": session_history[-5:],
            "constraints_checked": constraints_checked,
        },
        indent=2,
    )


# ── Classification Observer ──

CLASSIFICATION_OBSERVER_SYSTEM = """\
You are a classification advisor for SafeClaw, an AI agent governance system.

The symbolic classifier failed to match this tool call to a specific action class \
and fell back to the generic defaults ("Action", "MediumRisk").

Your job: suggest a better classification. SafeClaw's action classes are:
ReadFile, WriteFile, EditFile, DeleteFile, ListFiles, SearchFiles,
GitCommit, GitPush, ForcePush, GitResetHard,
WebFetch, WebSearch, BrowserAction, NetworkRequest,
ExecuteCommand, SendMessage, PackagePublish, DockerCleanup.

Risk levels: CriticalRisk, HighRisk, MediumRisk, LowRisk.
Scopes: LocalOnly, SharedState, ExternalWorld.
Reversibility: true (can be undone) or false (permanent).

Respond with ONLY a JSON object (no markdown fences):
{
  "suggested_class": "ActionClassName",
  "suggested_risk": "RiskLevel",
  "is_reversible": true/false,
  "affects_scope": "Scope",
  "reasoning": "why this classification"
}"""


def build_classification_observer_user_prompt(
    tool_name: str,
    params: dict,
    symbolic_class: str,
    risk_level: str,
) -> str:
    # Sanitize params: truncate long values, mask potential secrets
    safe_params = {}
    for k, v in params.items():
        sv = str(v)
        if any(secret in k.lower() for secret in ("key", "token", "password", "secret")):
            safe_params[k] = "***REDACTED***"
        elif len(sv) > 200:
            safe_params[k] = sv[:200] + "..."
        else:
            safe_params[k] = v

    return json.dumps(
        {
            "tool_name": tool_name,
            "params": safe_params,
            "current_classification": {
                "ontology_class": symbolic_class,
                "risk_level": risk_level,
            },
        },
        indent=2,
    )


# ── Decision Explainer ──

DECISION_EXPLAINER_SYSTEM = """\
You explain SafeClaw governance decisions in plain English.

Be concise: 2-3 sentences maximum. Include:
1. What was attempted (tool name and purpose)
2. Whether it was allowed or blocked, and why
3. Which specific policy or constraint applied

Use simple language. Avoid jargon. Write as if explaining to a developer \
who doesn't know SafeClaw internals."""


def build_explainer_user_prompt(
    tool_name: str,
    params: dict,
    ontology_class: str,
    risk_level: str,
    decision: str,
    reason: str,
    constraints_checked: list[dict],
) -> str:
    return json.dumps(
        {
            "tool_name": tool_name,
            "params": {k: str(v)[:100] for k, v in params.items()},
            "classification": {
                "ontology_class": ontology_class,
                "risk_level": risk_level,
            },
            "decision": decision,
            "reason": reason,
            "constraints_checked": constraints_checked,
        },
        indent=2,
    )


# ── Policy Compiler ──

POLICY_COMPILER_SYSTEM = """\
You generate SafeClaw governance policies in Turtle (TTL) format.

SafeClaw uses these namespace prefixes:
@prefix sp: <http://safeclaw.uku.ai/ontology/policy#> .
@prefix sc: <http://safeclaw.uku.ai/ontology/agent#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

Policy types (all subclass of sp:Constraint):
- sp:Prohibition — MUST NOT (forbidden actions)
- sp:Obligation — MUST (required preconditions)
- sp:Permission — MAY (explicitly allowed)

Constraint subtypes (can be combined with policy type):
- sp:PathConstraint — uses sp:forbiddenPathPattern (regex string)
- sp:CommandConstraint — uses sp:forbiddenCommandPattern (regex string)
- sp:TemporalConstraint — uses sp:notBefore / sp:notAfter (xsd:dateTime)
- sp:DependencyConstraint — uses sp:requiresBefore (reference to sc:ActionClass)

Every policy MUST have:
- sp:reason "..." (human-readable explanation)
- rdfs:label "..." (short name)

Action classes you can reference (sc: prefix):
ReadFile, WriteFile, EditFile, DeleteFile, ListFiles, SearchFiles,
GitCommit, GitPush, ForcePush, GitResetHard,
WebFetch, WebSearch, BrowserAction, NetworkRequest,
ExecuteCommand, SendMessage, PackagePublish, DockerCleanup, RunTests.

Examples:

# Prohibit accessing .env files
sp:NoEnvFiles a sp:Prohibition, sp:PathConstraint ;
    sp:forbiddenPathPattern ".*\\\\.env.*" ;
    sp:reason "Environment files may contain secrets" ;
    rdfs:label "No .env file access" .

# Require tests before pushing
sp:TestBeforePush a sp:Obligation, sp:DependencyConstraint ;
    sp:appliesTo sc:GitPush ;
    sp:requiresBefore sc:RunTests ;
    sp:reason "All pushes must pass tests first" ;
    rdfs:label "Test before push" .

# Prohibit force push
sp:NoForcePush a sp:Prohibition, sp:CommandConstraint ;
    sp:forbiddenCommandPattern "git push.*--force" ;
    sp:reason "Force push can destroy shared history" ;
    sp:appliesTo sc:ForcePush ;
    rdfs:label "No force push" .

Generate ONLY the Turtle block. No explanation, no markdown fences. \
Use a CamelCase name for the policy (sp:YourPolicyName). \
Always include sp:reason and rdfs:label."""
```

**Step 4: Run tests to verify they pass**

Run: `cd safeclaw-service && python -m pytest tests/test_llm_prompts.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add safeclaw-service/safeclaw/llm/prompts.py safeclaw-service/tests/test_llm_prompts.py
git commit -m "feat: add LLM prompt templates for all four capabilities"
```

---

## Task 4: Create `safeclaw/llm/security_reviewer.py` — Semantic Security Reviewer

**Files:**
- Create: `safeclaw-service/safeclaw/llm/security_reviewer.py`
- Create: `safeclaw-service/tests/test_llm_security_reviewer.py`

**Step 1: Write the failing test**

Create `safeclaw-service/tests/test_llm_security_reviewer.py`:

```python
"""Tests for the Semantic Security Reviewer."""

import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

from safeclaw.constraints.action_classifier import ClassifiedAction


@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    client.chat_json = AsyncMock()
    return client


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.agent_registry = MagicMock()
    engine.temp_permissions = MagicMock()
    return engine


@pytest.mark.asyncio
async def test_review_clean_action(mock_llm_client, mock_engine):
    """Clean actions should return None (no finding)."""
    from safeclaw.llm.security_reviewer import SecurityReviewer, ReviewEvent

    mock_llm_client.chat_json.return_value = {
        "suspicious": False,
        "severity": "low",
        "category": "none",
        "description": "Simple read operation, no risk",
        "recommended_action": "log",
        "confidence": 1.0,
    }

    reviewer = SecurityReviewer(mock_llm_client, mock_engine)
    event = ReviewEvent(
        tool_name="read",
        params={"file_path": "/src/main.py"},
        classified_action=ClassifiedAction(
            ontology_class="ReadFile",
            risk_level="LowRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="read",
            params={"file_path": "/src/main.py"},
        ),
        symbolic_decision="allowed",
        session_history=[],
        constraints_checked=[],
    )

    finding = await reviewer.review(event)
    assert finding is None


@pytest.mark.asyncio
async def test_review_obfuscated_command(mock_llm_client, mock_engine):
    """Obfuscated base64 command should produce a finding."""
    from safeclaw.llm.security_reviewer import SecurityReviewer, ReviewEvent, SecurityFinding

    mock_llm_client.chat_json.return_value = {
        "suspicious": True,
        "severity": "high",
        "category": "obfuscation",
        "description": "Base64-encoded destructive command detected",
        "recommended_action": "escalate_confirmation",
        "confidence": 0.95,
    }

    reviewer = SecurityReviewer(mock_llm_client, mock_engine)
    event = ReviewEvent(
        tool_name="exec",
        params={"command": "echo cm0gLXJmIC8= | base64 -d | sh"},
        classified_action=ClassifiedAction(
            ontology_class="ExecuteCommand",
            risk_level="MediumRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="exec",
            params={"command": "echo cm0gLXJmIC8= | base64 -d | sh"},
        ),
        symbolic_decision="allowed",
        session_history=["ReadFile"],
        constraints_checked=[{"type": "SHACL", "result": "satisfied"}],
    )

    finding = await reviewer.review(event)
    assert finding is not None
    assert finding.severity == "high"
    assert finding.category == "obfuscation"


@pytest.mark.asyncio
async def test_review_llm_timeout_returns_none(mock_llm_client, mock_engine):
    """If LLM times out, review returns None (graceful degradation)."""
    from safeclaw.llm.security_reviewer import SecurityReviewer, ReviewEvent

    mock_llm_client.chat_json.return_value = None  # timeout

    reviewer = SecurityReviewer(mock_llm_client, mock_engine)
    event = ReviewEvent(
        tool_name="exec",
        params={"command": "ls"},
        classified_action=ClassifiedAction(
            ontology_class="ExecuteCommand",
            risk_level="LowRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="exec",
            params={"command": "ls"},
        ),
        symbolic_decision="allowed",
        session_history=[],
        constraints_checked=[],
    )

    finding = await reviewer.review(event)
    assert finding is None


@pytest.mark.asyncio
async def test_review_invalid_json_returns_none(mock_llm_client, mock_engine):
    """If LLM returns invalid structure, review returns None."""
    from safeclaw.llm.security_reviewer import SecurityReviewer, ReviewEvent

    mock_llm_client.chat_json.return_value = {"unexpected": "format"}

    reviewer = SecurityReviewer(mock_llm_client, mock_engine)
    event = ReviewEvent(
        tool_name="exec",
        params={"command": "ls"},
        classified_action=ClassifiedAction(
            ontology_class="ExecuteCommand",
            risk_level="LowRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="exec",
            params={"command": "ls"},
        ),
        symbolic_decision="allowed",
        session_history=[],
        constraints_checked=[],
    )

    finding = await reviewer.review(event)
    assert finding is None
```

**Step 2: Run test to verify it fails**

Run: `cd safeclaw-service && python -m pytest tests/test_llm_security_reviewer.py -v`
Expected: FAIL — `ImportError`

**Step 3: Implement security_reviewer.py**

Create `safeclaw-service/safeclaw/llm/security_reviewer.py`:

```python
"""Semantic Security Reviewer — catches what rigid symbolic rules miss."""

import logging
from dataclasses import dataclass

from safeclaw.constraints.action_classifier import ClassifiedAction
from safeclaw.llm.prompts import SECURITY_REVIEW_SYSTEM, build_security_review_user_prompt

logger = logging.getLogger("safeclaw.llm.security")


@dataclass
class ReviewEvent:
    tool_name: str
    params: dict
    classified_action: ClassifiedAction
    symbolic_decision: str  # "allowed" | "blocked"
    session_history: list[str]
    constraints_checked: list[dict]


@dataclass
class SecurityFinding:
    severity: str  # "low" | "medium" | "high" | "critical"
    category: str  # "obfuscation" | "evasion" | "multi_step" | "novel_risk"
    description: str
    recommended_action: str  # "log" | "escalate_confirmation" | "kill_switch"
    confidence: float  # 0.0-1.0


VALID_SEVERITIES = {"low", "medium", "high", "critical"}
VALID_CATEGORIES = {"obfuscation", "evasion", "multi_step", "novel_risk", "none"}
VALID_ACTIONS = {"log", "escalate_confirmation", "kill_switch"}


class SecurityReviewer:
    """Async security reviewer that runs in parallel with the symbolic engine."""

    def __init__(self, client, engine_ref=None):
        self.client = client
        self.engine = engine_ref

    async def review(self, event: ReviewEvent) -> SecurityFinding | None:
        """Review a tool call for evasion/obfuscation. Returns finding or None."""
        user_prompt = build_security_review_user_prompt(
            tool_name=event.tool_name,
            params=event.params,
            ontology_class=event.classified_action.ontology_class,
            risk_level=event.classified_action.risk_level,
            symbolic_decision=event.symbolic_decision,
            session_history=event.session_history,
            constraints_checked=event.constraints_checked,
        )

        result = await self.client.chat_json(
            messages=[
                {"role": "system", "content": SECURITY_REVIEW_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
        )

        if result is None:
            return None

        return self._parse_finding(result)

    def _parse_finding(self, data: dict) -> SecurityFinding | None:
        """Parse LLM JSON response into a SecurityFinding. Returns None on invalid data."""
        try:
            suspicious = data.get("suspicious", False)
            if not suspicious:
                return None

            severity = data.get("severity", "low")
            category = data.get("category", "novel_risk")
            description = data.get("description", "No description")
            action = data.get("recommended_action", "log")
            confidence = float(data.get("confidence", 0.5))

            # Validate fields
            if severity not in VALID_SEVERITIES:
                severity = "low"
            if category not in VALID_CATEGORIES:
                category = "novel_risk"
            if action not in VALID_ACTIONS:
                action = "log"
            confidence = max(0.0, min(1.0, confidence))

            return SecurityFinding(
                severity=severity,
                category=category,
                description=description,
                recommended_action=action,
                confidence=confidence,
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("Failed to parse security review response", exc_info=True)
            return None
```

**Step 4: Run tests to verify they pass**

Run: `cd safeclaw-service && python -m pytest tests/test_llm_security_reviewer.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add safeclaw-service/safeclaw/llm/security_reviewer.py safeclaw-service/tests/test_llm_security_reviewer.py
git commit -m "feat: add Semantic Security Reviewer (passive red-team LLM step)"
```

---

## Task 5: Create `safeclaw/llm/classification_observer.py`

**Files:**
- Create: `safeclaw-service/safeclaw/llm/classification_observer.py`
- Create: `safeclaw-service/tests/test_llm_classification_observer.py`

**Step 1: Write the failing test**

Create `safeclaw-service/tests/test_llm_classification_observer.py`:

```python
"""Tests for the Classification Observer."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from safeclaw.constraints.action_classifier import ClassifiedAction


@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    client.chat_json = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_observe_default_classification(mock_llm_client, tmp_path):
    """Observer fires and returns suggestion when classifier used defaults."""
    from safeclaw.llm.classification_observer import ClassificationObserver

    mock_llm_client.chat_json.return_value = {
        "suggested_class": "NetworkRequest",
        "suggested_risk": "HighRisk",
        "is_reversible": True,
        "affects_scope": "ExternalWorld",
        "reasoning": "This tool makes HTTP requests to external services",
    }

    suggestions_file = tmp_path / "suggestions.jsonl"
    observer = ClassificationObserver(mock_llm_client, suggestions_file)

    action = ClassifiedAction(
        ontology_class="Action",
        risk_level="MediumRisk",
        is_reversible=True,
        affects_scope="LocalOnly",
        tool_name="http_client",
        params={"url": "https://api.example.com"},
    )

    suggestion = await observer.observe("http_client", {"url": "https://api.example.com"}, action)
    assert suggestion is not None
    assert suggestion.suggested_class == "NetworkRequest"
    assert suggestion.suggested_risk == "HighRisk"


@pytest.mark.asyncio
async def test_observe_skips_non_default(mock_llm_client, tmp_path):
    """Observer does NOT fire when classifier returned a specific class."""
    from safeclaw.llm.classification_observer import ClassificationObserver

    suggestions_file = tmp_path / "suggestions.jsonl"
    observer = ClassificationObserver(mock_llm_client, suggestions_file)

    action = ClassifiedAction(
        ontology_class="ReadFile",  # NOT "Action" — specific class
        risk_level="LowRisk",
        is_reversible=True,
        affects_scope="LocalOnly",
        tool_name="read",
        params={"file_path": "/src/main.py"},
    )

    suggestion = await observer.observe("read", {"file_path": "/src/main.py"}, action)
    assert suggestion is None
    mock_llm_client.chat_json.assert_not_called()


@pytest.mark.asyncio
async def test_observe_writes_to_suggestions_file(mock_llm_client, tmp_path):
    """Suggestions are appended to the JSONL file."""
    from safeclaw.llm.classification_observer import ClassificationObserver

    mock_llm_client.chat_json.return_value = {
        "suggested_class": "WebFetch",
        "suggested_risk": "MediumRisk",
        "is_reversible": True,
        "affects_scope": "ExternalWorld",
        "reasoning": "Fetches content from URLs",
    }

    suggestions_file = tmp_path / "suggestions.jsonl"
    observer = ClassificationObserver(mock_llm_client, suggestions_file)

    action = ClassifiedAction(
        ontology_class="Action",
        risk_level="MediumRisk",
        is_reversible=True,
        affects_scope="LocalOnly",
        tool_name="fetch",
        params={"url": "https://example.com"},
    )

    await observer.observe("fetch", {"url": "https://example.com"}, action)

    assert suggestions_file.exists()
    lines = suggestions_file.read_text().strip().split("\n")
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["suggested_class"] == "WebFetch"
    assert data["tool_name"] == "fetch"


@pytest.mark.asyncio
async def test_observe_llm_timeout_returns_none(mock_llm_client, tmp_path):
    """If LLM times out, observer returns None gracefully."""
    from safeclaw.llm.classification_observer import ClassificationObserver

    mock_llm_client.chat_json.return_value = None

    suggestions_file = tmp_path / "suggestions.jsonl"
    observer = ClassificationObserver(mock_llm_client, suggestions_file)

    action = ClassifiedAction(
        ontology_class="Action",
        risk_level="MediumRisk",
        is_reversible=True,
        affects_scope="LocalOnly",
        tool_name="unknown",
        params={},
    )

    suggestion = await observer.observe("unknown", {}, action)
    assert suggestion is None
```

**Step 2: Run test to verify it fails**

Run: `cd safeclaw-service && python -m pytest tests/test_llm_classification_observer.py -v`
Expected: FAIL — `ImportError`

**Step 3: Implement classification_observer.py**

Create `safeclaw-service/safeclaw/llm/classification_observer.py`:

```python
"""Classification Observer — suggests better classifications when regex falls back to defaults."""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from safeclaw.constraints.action_classifier import ClassifiedAction
from safeclaw.llm.prompts import (
    CLASSIFICATION_OBSERVER_SYSTEM,
    build_classification_observer_user_prompt,
)

logger = logging.getLogger("safeclaw.llm.observer")

# The default class name that ActionClassifier uses when no pattern matches
DEFAULT_ONTOLOGY_CLASS = "Action"


@dataclass
class ClassificationSuggestion:
    tool_name: str
    params_summary: str
    symbolic_class: str
    suggested_class: str
    suggested_risk: str
    reasoning: str
    timestamp: str


class ClassificationObserver:
    """Watches for classifier defaults and suggests better classifications."""

    def __init__(self, client, suggestions_file: Path):
        self.client = client
        self.suggestions_file = suggestions_file

    async def observe(
        self,
        tool_name: str,
        params: dict,
        symbolic_result: ClassifiedAction,
    ) -> ClassificationSuggestion | None:
        """If the classifier used defaults, ask the LLM for a better classification."""
        if symbolic_result.ontology_class != DEFAULT_ONTOLOGY_CLASS:
            return None

        user_prompt = build_classification_observer_user_prompt(
            tool_name=tool_name,
            params=params,
            symbolic_class=symbolic_result.ontology_class,
            risk_level=symbolic_result.risk_level,
        )

        result = await self.client.chat_json(
            messages=[
                {"role": "system", "content": CLASSIFICATION_OBSERVER_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
        )

        if result is None:
            return None

        return self._parse_and_save(result, tool_name, params, symbolic_result)

    def _parse_and_save(
        self,
        data: dict,
        tool_name: str,
        params: dict,
        symbolic_result: ClassifiedAction,
    ) -> ClassificationSuggestion | None:
        try:
            # Sanitize params summary
            summary = ", ".join(f"{k}={str(v)[:50]}" for k, v in list(params.items())[:5])

            suggestion = ClassificationSuggestion(
                tool_name=tool_name,
                params_summary=summary,
                symbolic_class=symbolic_result.ontology_class,
                suggested_class=data.get("suggested_class", "Action"),
                suggested_risk=data.get("suggested_risk", "MediumRisk"),
                reasoning=data.get("reasoning", ""),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

            # Append to JSONL file
            self.suggestions_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.suggestions_file, "a") as f:
                f.write(json.dumps(asdict(suggestion)) + "\n")

            logger.info(
                "Classification suggestion: %s → %s (%s)",
                tool_name,
                suggestion.suggested_class,
                suggestion.suggested_risk,
            )
            return suggestion

        except (KeyError, TypeError, ValueError):
            logger.warning("Failed to parse classification suggestion", exc_info=True)
            return None
```

**Step 4: Run tests to verify they pass**

Run: `cd safeclaw-service && python -m pytest tests/test_llm_classification_observer.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add safeclaw-service/safeclaw/llm/classification_observer.py safeclaw-service/tests/test_llm_classification_observer.py
git commit -m "feat: add Classification Observer (async learning loop for classifier)"
```

---

## Task 6: Create `safeclaw/llm/explainer.py` — Decision Explainer

**Files:**
- Create: `safeclaw-service/safeclaw/llm/explainer.py`
- Create: `safeclaw-service/tests/test_llm_explainer.py`

**Step 1: Write the failing test**

Create `safeclaw-service/tests/test_llm_explainer.py`:

```python
"""Tests for the Decision Explainer."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from safeclaw.audit.models import (
    ActionDetail,
    ConstraintCheck,
    DecisionRecord,
    Justification,
)


@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    client.chat = AsyncMock()
    return client


@pytest.fixture
def sample_record():
    return DecisionRecord(
        session_id="test-session",
        user_id="test-user",
        agent_id="",
        action=ActionDetail(
            tool_name="exec",
            params={"command": "git push --force"},
            ontology_class="ForcePush",
            risk_level="CriticalRisk",
            is_reversible=False,
            affects_scope="SharedState",
        ),
        decision="blocked",
        justification=Justification(
            constraints_checked=[
                ConstraintCheck(
                    constraint_uri="sp:NoForcePush",
                    constraint_type="Policy",
                    result="violated",
                    reason="Force push can destroy shared history",
                )
            ],
            elapsed_ms=12.5,
        ),
    )


@pytest.mark.asyncio
async def test_explain_returns_llm_text(mock_llm_client, sample_record):
    """explain() returns the LLM's plain-English explanation."""
    from safeclaw.llm.explainer import DecisionExplainer

    mock_llm_client.chat.return_value = (
        "The agent tried to force-push to git. SafeClaw blocked this because "
        "force pushing can overwrite shared history. The NoForcePush policy was violated."
    )

    explainer = DecisionExplainer(mock_llm_client)
    result = await explainer.explain(sample_record)
    assert "force" in result.lower()
    assert len(result) > 20


@pytest.mark.asyncio
async def test_explain_fallback_on_timeout(mock_llm_client, sample_record):
    """If LLM times out, explain() returns the raw reason from the record."""
    from safeclaw.llm.explainer import DecisionExplainer

    mock_llm_client.chat.return_value = None

    explainer = DecisionExplainer(mock_llm_client)
    result = await explainer.explain(sample_record)
    assert "Force push" in result  # Falls back to constraint reason


@pytest.mark.asyncio
async def test_explain_session_summarizes(mock_llm_client, sample_record):
    """explain_session() summarizes multiple records."""
    from safeclaw.llm.explainer import DecisionExplainer

    mock_llm_client.chat.return_value = "In this session, 1 action was blocked."

    explainer = DecisionExplainer(mock_llm_client)
    result = await explainer.explain_session([sample_record])
    assert "blocked" in result.lower()
```

**Step 2: Run test to verify it fails**

Run: `cd safeclaw-service && python -m pytest tests/test_llm_explainer.py -v`
Expected: FAIL — `ImportError`

**Step 3: Implement explainer.py**

Create `safeclaw-service/safeclaw/llm/explainer.py`:

```python
"""Decision Explainer — turns machine-readable DecisionRecords into plain English."""

import logging

from safeclaw.audit.models import DecisionRecord
from safeclaw.llm.prompts import DECISION_EXPLAINER_SYSTEM, build_explainer_user_prompt

logger = logging.getLogger("safeclaw.llm.explainer")


class DecisionExplainer:
    """Generates human-readable explanations of governance decisions."""

    def __init__(self, client):
        self.client = client

    async def explain(self, record: DecisionRecord) -> str:
        """Generate a 2-3 sentence explanation of a single decision."""
        user_prompt = build_explainer_user_prompt(
            tool_name=record.action.tool_name,
            params=record.action.params,
            ontology_class=record.action.ontology_class,
            risk_level=record.action.risk_level,
            decision=record.decision,
            reason=self._extract_reason(record),
            constraints_checked=[
                {"type": c.constraint_type, "result": c.result, "reason": c.reason}
                for c in record.justification.constraints_checked
            ],
        )

        result = await self.client.chat(
            messages=[
                {"role": "system", "content": DECISION_EXPLAINER_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
        )

        if result is None:
            return self._fallback_explanation(record)

        return result

    async def explain_session(self, records: list[DecisionRecord]) -> str:
        """Summarize all decisions in a session."""
        if not records:
            return "No decisions to explain."

        summary_parts = []
        for r in records:
            reason = self._extract_reason(r)
            summary_parts.append(
                f"- {r.action.tool_name} ({r.action.ontology_class}): "
                f"{r.decision} — {reason}"
            )

        user_prompt = (
            "Summarize these governance decisions from one session:\n\n"
            + "\n".join(summary_parts)
        )

        result = await self.client.chat(
            messages=[
                {"role": "system", "content": DECISION_EXPLAINER_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
        )

        if result is None:
            return self._fallback_session_summary(records)

        return result

    def _extract_reason(self, record: DecisionRecord) -> str:
        """Get the first violated constraint reason, or a default."""
        for check in record.justification.constraints_checked:
            if check.result == "violated":
                return check.reason
        for pref in record.justification.preferences_applied:
            return pref.effect
        return record.decision

    def _fallback_explanation(self, record: DecisionRecord) -> str:
        """Fallback when LLM is unavailable."""
        reason = self._extract_reason(record)
        return (
            f"Tool '{record.action.tool_name}' was {record.decision}. "
            f"Classification: {record.action.ontology_class} ({record.action.risk_level}). "
            f"Reason: {reason}"
        )

    def _fallback_session_summary(self, records: list[DecisionRecord]) -> str:
        allowed = sum(1 for r in records if r.decision == "allowed")
        blocked = sum(1 for r in records if r.decision == "blocked")
        return f"Session summary: {allowed} allowed, {blocked} blocked out of {len(records)} total decisions."
```

**Step 4: Run tests to verify they pass**

Run: `cd safeclaw-service && python -m pytest tests/test_llm_explainer.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add safeclaw-service/safeclaw/llm/explainer.py safeclaw-service/tests/test_llm_explainer.py
git commit -m "feat: add Decision Explainer (human-readable governance explanations)"
```

---

## Task 7: Create `safeclaw/llm/policy_compiler.py` — NL→Policy Compiler

**Files:**
- Create: `safeclaw-service/safeclaw/llm/policy_compiler.py`
- Create: `safeclaw-service/tests/test_llm_policy_compiler.py`

**Step 1: Write the failing test**

Create `safeclaw-service/tests/test_llm_policy_compiler.py`:

```python
"""Tests for the NL → Policy Compiler."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from safeclaw.engine.knowledge_graph import KnowledgeGraph


@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    client.chat = AsyncMock()
    return client


@pytest.fixture
def kg():
    kg = KnowledgeGraph()
    ontology_dir = Path(__file__).parent.parent / "safeclaw" / "ontologies"
    kg.load_directory(ontology_dir)
    return kg


VALID_TURTLE = '''\
sp:NoProdDeploy a sp:Prohibition, sp:CommandConstraint ;
    sp:forbiddenCommandPattern "deploy.*production" ;
    sp:reason "Deploying to production is forbidden without approval" ;
    rdfs:label "No production deploy" .
'''


@pytest.mark.asyncio
async def test_compile_valid_policy(mock_llm_client, kg):
    """compile() returns success with valid generated Turtle."""
    from safeclaw.llm.policy_compiler import PolicyCompiler

    mock_llm_client.chat.return_value = VALID_TURTLE

    compiler = PolicyCompiler(mock_llm_client, kg)
    result = await compiler.compile("Never deploy to production without approval")

    assert result.success is True
    assert "NoProdDeploy" in result.turtle
    assert result.policy_name == "NoProdDeploy"
    assert len(result.validation_errors) == 0


@pytest.mark.asyncio
async def test_compile_invalid_turtle_syntax(mock_llm_client, kg):
    """compile() returns failure on invalid Turtle syntax."""
    from safeclaw.llm.policy_compiler import PolicyCompiler

    mock_llm_client.chat.return_value = "this is not valid turtle at all {"

    compiler = PolicyCompiler(mock_llm_client, kg)
    result = await compiler.compile("Some policy")

    assert result.success is False
    assert len(result.validation_errors) > 0


@pytest.mark.asyncio
async def test_compile_missing_reason(mock_llm_client, kg):
    """compile() flags policies without sp:reason."""
    from safeclaw.llm.policy_compiler import PolicyCompiler

    no_reason_turtle = '''\
sp:BadPolicy a sp:Prohibition, sp:CommandConstraint ;
    sp:forbiddenCommandPattern "bad" ;
    rdfs:label "Bad policy" .
'''
    mock_llm_client.chat.return_value = no_reason_turtle

    compiler = PolicyCompiler(mock_llm_client, kg)
    result = await compiler.compile("Block bad things")

    assert result.success is False
    assert any("reason" in e.lower() for e in result.validation_errors)


@pytest.mark.asyncio
async def test_compile_llm_timeout(mock_llm_client, kg):
    """compile() returns failure on LLM timeout."""
    from safeclaw.llm.policy_compiler import PolicyCompiler

    mock_llm_client.chat.return_value = None

    compiler = PolicyCompiler(mock_llm_client, kg)
    result = await compiler.compile("Some policy")

    assert result.success is False
    assert any("llm" in e.lower() or "timeout" in e.lower() for e in result.validation_errors)
```

**Step 2: Run test to verify it fails**

Run: `cd safeclaw-service && python -m pytest tests/test_llm_policy_compiler.py -v`
Expected: FAIL — `ImportError`

**Step 3: Implement policy_compiler.py**

Create `safeclaw-service/safeclaw/llm/policy_compiler.py`:

```python
"""NL → Policy Compiler — turns natural language into validated Turtle policies."""

import logging
import re
from dataclasses import dataclass, field

from rdflib import Graph, Namespace

from safeclaw.engine.knowledge_graph import KnowledgeGraph, SP
from safeclaw.llm.prompts import POLICY_COMPILER_SYSTEM

logger = logging.getLogger("safeclaw.llm.compiler")

# Prefixes needed to parse generated Turtle
TURTLE_PREFIXES = """\
@prefix sp: <http://safeclaw.uku.ai/ontology/policy#> .
@prefix sc: <http://safeclaw.uku.ai/ontology/agent#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
"""


@dataclass
class CompileResult:
    success: bool
    turtle: str = ""
    policy_name: str = ""
    policy_type: str = ""
    validation_errors: list[str] = field(default_factory=list)
    explanation: str = ""


class PolicyCompiler:
    """Compiles natural language policy descriptions into validated Turtle."""

    def __init__(self, client, kg: KnowledgeGraph):
        self.client = client
        self.kg = kg

    async def compile(self, natural_language: str) -> CompileResult:
        """Convert a natural language policy to Turtle. Returns CompileResult."""
        raw_turtle = await self.client.chat(
            messages=[
                {"role": "system", "content": POLICY_COMPILER_SYSTEM},
                {"role": "user", "content": natural_language},
            ],
            model=self.client.model_large,
            temperature=0.0,
        )

        if raw_turtle is None:
            return CompileResult(
                success=False,
                validation_errors=["LLM request failed or timed out"],
            )

        # Strip markdown fences if present
        turtle = self._strip_fences(raw_turtle)

        # Validate
        errors = self._validate(turtle)
        if errors:
            return CompileResult(
                success=False,
                turtle=turtle,
                validation_errors=errors,
            )

        # Extract policy name and type
        name = self._extract_policy_name(turtle)
        ptype = self._extract_policy_type(turtle)

        return CompileResult(
            success=True,
            turtle=turtle,
            policy_name=name,
            policy_type=ptype,
            explanation=f"Generated {ptype} policy '{name}' from: {natural_language}",
        )

    def _strip_fences(self, text: str) -> str:
        """Remove markdown code fences if present."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```turtle or ```)
            lines = lines[1:]
            # Remove last line if it's ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return text.strip()

    def _validate(self, turtle: str) -> list[str]:
        """Validate the generated Turtle. Returns list of error strings."""
        errors = []

        # 1. Syntax check: parse with RDFLib
        full_turtle = TURTLE_PREFIXES + "\n" + turtle
        g = Graph()
        try:
            g.parse(data=full_turtle, format="turtle")
        except Exception as e:
            errors.append(f"Turtle syntax error: {e}")
            return errors  # Can't proceed with invalid syntax

        # 2. Check that sp:reason is present
        sp = Namespace("http://safeclaw.uku.ai/ontology/policy#")
        reasons = list(g.triples((None, sp.reason, None)))
        if not reasons:
            errors.append("Policy must include sp:reason property")

        # 3. Check namespace usage — all subjects should use sp: or sc:
        valid_ns = {
            "http://safeclaw.uku.ai/ontology/policy#",
            "http://safeclaw.uku.ai/ontology/agent#",
        }
        for s, _, _ in g:
            s_str = str(s)
            if s_str.startswith("http://") and not any(s_str.startswith(ns) for ns in valid_ns):
                errors.append(f"Unknown namespace in subject: {s_str}")

        return errors

    def _extract_policy_name(self, turtle: str) -> str:
        """Extract the policy name (sp:Name) from the Turtle block."""
        match = re.search(r"sp:(\w+)\s+a\s+", turtle)
        return match.group(1) if match else "UnknownPolicy"

    def _extract_policy_type(self, turtle: str) -> str:
        """Extract the policy type (Prohibition/Obligation/Permission)."""
        if "sp:Prohibition" in turtle:
            return "prohibition"
        elif "sp:Obligation" in turtle:
            return "obligation"
        elif "sp:Permission" in turtle:
            return "permission"
        return "unknown"
```

**Step 4: Run tests to verify they pass**

Run: `cd safeclaw-service && python -m pytest tests/test_llm_policy_compiler.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add safeclaw-service/safeclaw/llm/policy_compiler.py safeclaw-service/tests/test_llm_policy_compiler.py
git commit -m "feat: add NL→Policy Compiler with Turtle validation"
```

---

## Task 8: Integrate LLM layer into FullEngine

**Files:**
- Modify: `safeclaw-service/safeclaw/engine/full_engine.py`
- Create: `safeclaw-service/tests/test_llm_integration.py`

**Step 1: Write the failing test**

Create `safeclaw-service/tests/test_llm_integration.py`:

```python
"""Integration tests for LLM layer in FullEngine."""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from safeclaw.config import SafeClawConfig
from safeclaw.engine.core import ToolCallEvent
from safeclaw.engine.full_engine import FullEngine


@pytest.fixture
def engine_no_llm(tmp_path):
    """Engine without LLM (no API key)."""
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
        run_reasoner_on_startup=False,
        mistral_api_key="",
    )
    return FullEngine(config)


@pytest.mark.asyncio
async def test_engine_works_without_llm(engine_no_llm):
    """Engine works exactly as before when no API key is set."""
    event = ToolCallEvent(
        session_id="test",
        user_id="test",
        tool_name="read",
        params={"file_path": "/src/main.py"},
    )
    decision = await engine_no_llm.evaluate_tool_call(event)
    assert decision.block is False
    assert engine_no_llm.llm_client is None
    assert engine_no_llm.security_reviewer is None


@pytest.mark.asyncio
async def test_engine_initializes_llm_with_api_key(tmp_path):
    """Engine initializes LLM components when API key is provided."""
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
        run_reasoner_on_startup=False,
        mistral_api_key="test-key-for-init",
    )

    with patch("safeclaw.llm.client.Mistral"):
        engine = FullEngine(config)

    assert engine.llm_client is not None
    assert engine.security_reviewer is not None
    assert engine.classification_observer is not None
    assert engine.explainer is not None


@pytest.mark.asyncio
async def test_security_review_fires_after_allow(tmp_path):
    """Security review task is created after a tool call is allowed."""
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
        run_reasoner_on_startup=False,
        mistral_api_key="test-key",
    )

    with patch("safeclaw.llm.client.Mistral"):
        engine = FullEngine(config)

    # Mock the security reviewer to track if it's called
    engine.security_reviewer.review = AsyncMock(return_value=None)

    event = ToolCallEvent(
        session_id="test",
        user_id="test",
        tool_name="read",
        params={"file_path": "/src/main.py"},
    )
    decision = await engine.evaluate_tool_call(event)
    assert decision.block is False

    # Give background tasks a moment to fire
    await asyncio.sleep(0.1)

    engine.security_reviewer.review.assert_called_once()


@pytest.mark.asyncio
async def test_symbolic_decision_not_delayed_by_llm(engine_no_llm):
    """Verify symbolic pipeline returns immediately regardless of LLM."""
    import time

    event = ToolCallEvent(
        session_id="test",
        user_id="test",
        tool_name="read",
        params={"file_path": "/src/main.py"},
    )

    start = time.monotonic()
    decision = await engine_no_llm.evaluate_tool_call(event)
    elapsed_ms = (time.monotonic() - start) * 1000

    assert decision.block is False
    assert elapsed_ms < 500  # Symbolic pipeline should be fast
```

**Step 2: Run test to verify it fails**

Run: `cd safeclaw-service && python -m pytest tests/test_llm_integration.py::test_engine_works_without_llm -v`
Expected: FAIL — `FullEngine` has no attribute `llm_client`

**Step 3: Modify `full_engine.py` — add LLM initialization**

At the end of `_init_components()` (after line 114 `self.audit = AuditLogger(audit_dir)`), add:

```python
        # LLM layer (passive observer — gated on API key)
        self.llm_client = None
        self.security_reviewer = None
        self.classification_observer = None
        self.explainer = None

        if config.mistral_api_key:
            from safeclaw.llm.client import create_client
            from safeclaw.llm.security_reviewer import SecurityReviewer
            from safeclaw.llm.classification_observer import ClassificationObserver
            from safeclaw.llm.explainer import DecisionExplainer

            self.llm_client = create_client(config)
            if self.llm_client:
                suggestions_path = config.data_dir / "llm" / "classification_suggestions.jsonl"
                self.security_reviewer = SecurityReviewer(self.llm_client, self)
                self.classification_observer = ClassificationObserver(
                    self.llm_client, suggestions_path
                )
                self.explainer = DecisionExplainer(self.llm_client)
                logger.info("LLM layer initialized (security review, observer, explainer)")
```

**Step 4: Modify `_evaluate_tool_call_locked()` — fire LLM tasks after decision**

In `_evaluate_tool_call_locked()`, just before `return decision` on the success path (line 360), add fire-and-forget LLM tasks:

Replace lines 356-360:
```python
        # 10. All checks passed - record for rate limiting (only allowed actions)
        self.rate_limiter.record(action, event.session_id, agent_id=event.agent_id)
        decision = Decision(block=False)
        self._log_decision(event, action, decision, checks, prefs_applied, start)
        return decision
```

With:
```python
        # 10. All checks passed - record for rate limiting (only allowed actions)
        self.rate_limiter.record(action, event.session_id, agent_id=event.agent_id)
        decision = Decision(block=False)
        self._log_decision(event, action, decision, checks, prefs_applied, start)

        # Fire-and-forget LLM tasks (non-blocking, passive observer)
        self._fire_llm_tasks(event, action, decision, checks)

        return decision
```

Add the new method to `FullEngine` (before `_record_violation_and_log`):

```python
    def _fire_llm_tasks(
        self,
        event: ToolCallEvent,
        action,
        decision: Decision,
        checks: list[ConstraintCheck],
    ) -> None:
        """Launch background LLM review tasks. Non-blocking, fire-and-forget."""
        if self.security_reviewer and self.config.llm_security_review_enabled:
            from safeclaw.llm.security_reviewer import ReviewEvent

            review_event = ReviewEvent(
                tool_name=event.tool_name,
                params=event.params,
                classified_action=action,
                symbolic_decision="allowed" if not decision.block else "blocked",
                session_history=event.session_history,
                constraints_checked=[
                    {"type": c.constraint_type, "result": c.result, "reason": c.reason}
                    for c in checks
                ],
            )
            asyncio.create_task(self._run_security_review(review_event))

        if (
            self.classification_observer
            and self.config.llm_classification_observe
            and action.ontology_class == "Action"
        ):
            asyncio.create_task(
                self._run_classification_observer(event.tool_name, event.params, action)
            )

    async def _run_security_review(self, review_event) -> None:
        """Background task: run security review and handle findings."""
        try:
            finding = await self.security_reviewer.review(review_event)
            if finding:
                logger.warning(
                    "Security finding [%s/%s]: %s",
                    finding.severity,
                    finding.category,
                    finding.description,
                )
                # Escalation handling
                if finding.severity == "critical" and review_event.classified_action.tool_name:
                    # Could trigger kill switch here in the future
                    logger.critical("CRITICAL security finding — manual review required")
        except Exception:
            logger.debug("Security review background task failed", exc_info=True)

    async def _run_classification_observer(self, tool_name, params, action) -> None:
        """Background task: observe classification and suggest improvements."""
        try:
            await self.classification_observer.observe(tool_name, params, action)
        except Exception:
            logger.debug("Classification observer background task failed", exc_info=True)
```

**Step 5: Run integration tests**

Run: `cd safeclaw-service && python -m pytest tests/test_llm_integration.py -v`
Expected: ALL PASS

**Step 6: Run full test suite to verify no regressions**

Run: `cd safeclaw-service && python -m pytest tests/ -v`
Expected: ALL PASS (233+ tests plus new ones)

**Step 7: Commit**

```bash
git add safeclaw-service/safeclaw/engine/full_engine.py safeclaw-service/tests/test_llm_integration.py
git commit -m "feat: integrate LLM layer into FullEngine (fire-and-forget after symbolic decision)"
```

---

## Task 9: Add API routes for LLM features

**Files:**
- Modify: `safeclaw-service/safeclaw/api/routes.py`
- Modify: `safeclaw-service/safeclaw/api/models.py`
- Create: `safeclaw-service/tests/test_llm_api.py`

**Step 1: Write the failing test**

Create `safeclaw-service/tests/test_llm_api.py`:

```python
"""Tests for LLM-related API routes."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.testclient import TestClient

from safeclaw.config import SafeClawConfig
from safeclaw.engine.full_engine import FullEngine


@pytest.fixture
def client(tmp_path):
    import safeclaw.main as main_module

    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
        run_reasoner_on_startup=False,
    )
    main_module.engine = FullEngine(config)
    client = TestClient(main_module.app)
    yield client
    main_module.engine = None


def test_policy_compile_no_llm(client):
    """POST /policies/compile returns 503 when LLM is not configured."""
    resp = client.post(
        "/api/v1/policies/compile",
        json={"description": "Never delete production files"},
    )
    assert resp.status_code == 503


def test_audit_explain_no_llm(client):
    """GET /audit/{id}/explain returns 503 when LLM is not configured."""
    resp = client.get("/api/v1/audit/fake-id/explain")
    assert resp.status_code == 503


def test_llm_findings_empty(client):
    """GET /llm/findings returns empty list when no findings exist."""
    resp = client.get("/api/v1/llm/findings")
    assert resp.status_code == 200
    assert resp.json()["findings"] == []


def test_llm_suggestions_empty(client):
    """GET /llm/suggestions returns empty list when no suggestions exist."""
    resp = client.get("/api/v1/llm/suggestions")
    assert resp.status_code == 200
    assert resp.json()["suggestions"] == []
```

**Step 2: Run test to verify it fails**

Run: `cd safeclaw-service && python -m pytest tests/test_llm_api.py -v`
Expected: FAIL — routes don't exist yet

**Step 3: Add API models**

In `safeclaw-service/safeclaw/api/models.py`, add at the end:

```python
class PolicyCompileRequest(BaseModel):
    description: str


class PolicyCompileResponse(BaseModel):
    success: bool
    turtle: str = ""
    policyName: str = ""
    policyType: str = ""
    explanation: str = ""
    validationErrors: list[str] = []


class PolicyApplyRequest(BaseModel):
    turtle: str
```

**Step 4: Add API routes**

In `safeclaw-service/safeclaw/api/routes.py`, add the import at the top (with other model imports):

```python
from safeclaw.api.models import PolicyCompileRequest, PolicyCompileResponse, PolicyApplyRequest
```

Add these routes at the end of the file (before any closing code):

```python
# ── LLM Layer Routes ──


@router.post("/policies/compile", response_model=PolicyCompileResponse)
async def compile_policy(request: PolicyCompileRequest) -> PolicyCompileResponse:
    engine = _get_engine()
    if not hasattr(engine, "llm_client") or engine.llm_client is None:
        raise HTTPException(status_code=503, detail="LLM not configured (set SAFECLAW_MISTRAL_API_KEY)")

    from safeclaw.llm.policy_compiler import PolicyCompiler

    compiler = PolicyCompiler(engine.llm_client, engine.kg)
    result = await compiler.compile(request.description)
    return PolicyCompileResponse(
        success=result.success,
        turtle=result.turtle,
        policyName=result.policy_name,
        policyType=result.policy_type,
        explanation=result.explanation,
        validationErrors=result.validation_errors,
    )


@router.post("/policies/apply")
async def apply_policy(request: PolicyApplyRequest, _=Depends(require_admin)):
    engine = _get_engine()
    from safeclaw.config import SafeClawConfig

    config = SafeClawConfig()
    policy_file = config.get_ontology_dir() / "safeclaw-policy.ttl"

    if not policy_file.exists():
        raise HTTPException(status_code=404, detail="Policy file not found")

    with open(policy_file, "a") as f:
        f.write(f"\n# Added via LLM policy compiler\n{request.turtle}\n")

    engine.reload()
    return {"applied": True}


@router.get("/audit/{audit_id}/explain")
async def explain_decision(audit_id: str):
    engine = _get_engine()
    if not hasattr(engine, "explainer") or engine.explainer is None:
        raise HTTPException(status_code=503, detail="LLM not configured (set SAFECLAW_MISTRAL_API_KEY)")

    records = engine.audit.get_recent_records(limit=200)
    record = next((r for r in records if r.id == audit_id), None)
    if not record:
        raise HTTPException(status_code=404, detail="Audit record not found")

    explanation = await engine.explainer.explain(record)
    return {"auditId": audit_id, "explanation": explanation}


@router.get("/audit/session/{session_id}/explain")
async def explain_session(session_id: str):
    engine = _get_engine()
    if not hasattr(engine, "explainer") or engine.explainer is None:
        raise HTTPException(status_code=503, detail="LLM not configured (set SAFECLAW_MISTRAL_API_KEY)")

    records = engine.audit.get_session_records(session_id)
    if not records:
        raise HTTPException(status_code=404, detail="No records found for session")

    explanation = await engine.explainer.explain_session(records)
    return {"sessionId": session_id, "explanation": explanation}


@router.get("/llm/findings")
async def get_findings():
    # For now, findings are logged but not persisted to a queryable store.
    # This returns an empty list until the findings store is implemented.
    return {"findings": []}


@router.get("/llm/suggestions")
async def get_suggestions():
    import json
    from safeclaw.config import SafeClawConfig

    config = SafeClawConfig()
    suggestions_file = config.data_dir / "llm" / "classification_suggestions.jsonl"

    if not suggestions_file.exists():
        return {"suggestions": []}

    suggestions = []
    for line in suggestions_file.read_text().strip().split("\n"):
        if line.strip():
            try:
                suggestions.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return {"suggestions": suggestions}
```

**Step 5: Run tests to verify they pass**

Run: `cd safeclaw-service && python -m pytest tests/test_llm_api.py -v`
Expected: ALL PASS

**Step 6: Run full test suite**

Run: `cd safeclaw-service && python -m pytest tests/ -v`
Expected: ALL PASS

**Step 7: Commit**

```bash
git add safeclaw-service/safeclaw/api/routes.py safeclaw-service/safeclaw/api/models.py safeclaw-service/tests/test_llm_api.py
git commit -m "feat: add API routes for policy compile, explain, findings, suggestions"
```

---

## Task 10: Add CLI commands for LLM features

**Files:**
- Create: `safeclaw-service/safeclaw/cli/llm_cmd.py`
- Modify: `safeclaw-service/safeclaw/cli/main.py`
- Modify: `safeclaw-service/safeclaw/cli/policy_cmd.py` (add `add-nl` command)
- Modify: `safeclaw-service/safeclaw/cli/audit_cmd.py` (add `explain` command)

**Step 1: Create the LLM CLI subcommand**

Create `safeclaw-service/safeclaw/cli/llm_cmd.py`:

```python
"""CLI commands for LLM layer features."""

import json

import typer
from rich.console import Console
from rich.table import Table

llm_app = typer.Typer(help="LLM layer commands")
console = Console()


@llm_app.command("findings")
def findings(
    last: int = typer.Option(20, help="Number of recent findings to show"),
):
    """Show recent security findings from the LLM reviewer."""
    # Findings are currently log-only; this reads the suggestions file as a placeholder
    console.print("[yellow]Security findings are currently logged to the safeclaw.llm.security logger.[/yellow]")
    console.print("Use log aggregation to review findings, or check the API: GET /api/v1/llm/findings")


@llm_app.command("suggestions")
def suggestions():
    """Show classification improvement suggestions from the LLM observer."""
    from safeclaw.config import SafeClawConfig

    config = SafeClawConfig()
    suggestions_file = config.data_dir / "llm" / "classification_suggestions.jsonl"

    if not suggestions_file.exists():
        console.print("[yellow]No classification suggestions yet[/yellow]")
        return

    table = Table(title="Classification Suggestions")
    table.add_column("Tool", style="cyan")
    table.add_column("Current", style="dim")
    table.add_column("Suggested", style="green")
    table.add_column("Risk", style="yellow")
    table.add_column("Reasoning")

    for line in suggestions_file.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            s = json.loads(line)
            table.add_row(
                s.get("tool_name", ""),
                s.get("symbolic_class", ""),
                s.get("suggested_class", ""),
                s.get("suggested_risk", ""),
                s.get("reasoning", "")[:60],
            )
        except json.JSONDecodeError:
            continue

    console.print(table)
```

**Step 2: Add `add-nl` to policy_cmd.py**

In `safeclaw-service/safeclaw/cli/policy_cmd.py`, add this command after the existing `add` command:

```python
@policy_app.command("add-nl")
def add_nl(
    description: str = typer.Argument(help="Natural language policy description"),
):
    """Add a policy using natural language (requires LLM)."""
    import asyncio
    from safeclaw.config import SafeClawConfig
    from safeclaw.llm.client import create_client

    config = SafeClawConfig()
    client = create_client(config)
    if client is None:
        console.print("[red]LLM not configured. Set SAFECLAW_MISTRAL_API_KEY environment variable.[/red]")
        raise typer.Exit(1)

    from safeclaw.engine.knowledge_graph import KnowledgeGraph
    from safeclaw.llm.policy_compiler import PolicyCompiler

    kg = KnowledgeGraph()
    kg.load_directory(config.get_ontology_dir())
    compiler = PolicyCompiler(client, kg)

    result = asyncio.run(compiler.compile(description))

    if not result.success:
        console.print("[red]Failed to compile policy:[/red]")
        for err in result.validation_errors:
            console.print(f"  - {err}")
        raise typer.Exit(1)

    console.print(f"\n[bold]Generated policy: {result.policy_name}[/bold]")
    console.print(f"Type: {result.policy_type}")
    console.print(f"\n[dim]{result.turtle}[/dim]\n")

    if typer.confirm("Apply this policy?"):
        policy_file = config.get_ontology_dir() / "safeclaw-policy.ttl"
        with open(policy_file, "a") as f:
            f.write(f"\n# Added via NL compiler: {description}\n{result.turtle}\n")
        console.print("[green]Policy applied successfully[/green]")
        console.print("[yellow]Restart the service or use hot-reload for changes to take effect[/yellow]")
    else:
        console.print("[yellow]Policy not applied[/yellow]")
```

**Step 3: Add `explain` to audit_cmd.py**

In `safeclaw-service/safeclaw/cli/audit_cmd.py`, add this command after the existing `compliance` command:

```python
@audit_app.command("explain")
def explain(
    audit_id: str = typer.Argument(help="Audit record ID to explain"),
):
    """Explain a decision in plain English (requires LLM)."""
    import asyncio
    from safeclaw.llm.client import create_client

    config = SafeClawConfig()
    client = create_client(config)
    if client is None:
        console.print("[red]LLM not configured. Set SAFECLAW_MISTRAL_API_KEY environment variable.[/red]")
        raise typer.Exit(1)

    audit_logger = AuditLogger(config.get_audit_dir())
    records = audit_logger.get_recent_records(limit=200)
    record = next((r for r in records if r.id == audit_id), None)

    if record is None:
        console.print(f"[red]Audit record '{audit_id}' not found[/red]")
        raise typer.Exit(1)

    from safeclaw.llm.explainer import DecisionExplainer

    explainer = DecisionExplainer(client)
    explanation = asyncio.run(explainer.explain(record))
    console.print(f"\n{explanation}\n")
```

**Step 4: Register LLM subcommand in main.py**

In `safeclaw-service/safeclaw/cli/main.py`, add the import and registration:

```python
from safeclaw.cli.llm_cmd import llm_app
```

And add after line 17 (`app.add_typer(pref_app, name="pref")`):

```python
app.add_typer(llm_app, name="llm")
```

**Step 5: Run full test suite**

Run: `cd safeclaw-service && python -m pytest tests/ -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add safeclaw-service/safeclaw/cli/
git commit -m "feat: add CLI commands for LLM features (add-nl, explain, suggestions)"
```

---

## Task 11: Final verification and cleanup

**Files:**
- All files from Tasks 1-10

**Step 1: Run lint**

Run: `cd safeclaw-service && ruff check safeclaw/ tests/`
Fix any issues found.

**Step 2: Run format check**

Run: `cd safeclaw-service && ruff format --check safeclaw/ tests/`
If issues: `cd safeclaw-service && ruff format safeclaw/ tests/`

**Step 3: Run full test suite**

Run: `cd safeclaw-service && python -m pytest tests/ -v`
Expected: ALL PASS (233+ original + ~30 new LLM tests)

**Step 4: Verify graceful degradation**

Run: `cd safeclaw-service && python -c "from safeclaw.engine.full_engine import FullEngine; from safeclaw.config import SafeClawConfig; import tempfile, pathlib; t=tempfile.mkdtemp(); e=FullEngine(SafeClawConfig(data_dir=pathlib.Path(t), ontology_dir=pathlib.Path('safeclaw/ontologies'), audit_dir=pathlib.Path(t)/'audit', run_reasoner_on_startup=False)); print('LLM client:', e.llm_client); print('Security reviewer:', e.security_reviewer)"`
Expected: `LLM client: None` and `Security reviewer: None`

**Step 5: Commit any lint fixes**

```bash
git add -A
git commit -m "chore: lint and format LLM layer code"
```

**Step 6: Final commit — update __init__.py exports**

Verify `safeclaw/llm/__init__.py` exports are clean:

```python
"""SafeClaw LLM layer — passive observer and advisor."""

from safeclaw.llm.client import SafeClawLLMClient, create_client
from safeclaw.llm.security_reviewer import SecurityReviewer, SecurityFinding, ReviewEvent
from safeclaw.llm.classification_observer import ClassificationObserver, ClassificationSuggestion
from safeclaw.llm.explainer import DecisionExplainer
from safeclaw.llm.policy_compiler import PolicyCompiler, CompileResult

__all__ = [
    "SafeClawLLMClient",
    "create_client",
    "SecurityReviewer",
    "SecurityFinding",
    "ReviewEvent",
    "ClassificationObserver",
    "ClassificationSuggestion",
    "DecisionExplainer",
    "PolicyCompiler",
    "CompileResult",
]
```

```bash
git add safeclaw-service/safeclaw/llm/__init__.py
git commit -m "chore: add public exports to llm __init__.py"
```
