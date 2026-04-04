"""End-to-end integration tests for NemoClaw sandbox governance.

These tests exercise the full NemoClaw pipeline:
  NemoClaw YAML -> NemoClawPolicyLoader -> KnowledgeGraph -> PolicyChecker -> FullEngine

Each test creates temporary YAML policy files, loads them through the real
loader and checker (or FullEngine), and verifies that tool calls are
allowed or blocked according to the policy.
"""

import pytest
from pathlib import Path

from safeclaw.config import SafeClawConfig
from safeclaw.engine.core import ToolCallEvent
from safeclaw.engine.full_engine import FullEngine
from safeclaw.engine.knowledge_graph import KnowledgeGraph
from safeclaw.constraints.policy_checker import PolicyChecker
from safeclaw.constraints.action_classifier import ClassifiedAction
from safeclaw.nemoclaw.policy_loader import NemoClawPolicyLoader

ONTOLOGY_DIR = Path(__file__).parent.parent / "safeclaw" / "ontologies"


def _write_yaml(policy_dir: Path, filename: str, content: str) -> None:
    """Helper to write a YAML file to the policy directory."""
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / filename).write_text(content, encoding="utf-8")


def _make_action(ontology_class: str, tool_name: str = "web_fetch", **params) -> ClassifiedAction:
    """Helper to create a ClassifiedAction for checker-level tests."""
    return ClassifiedAction(
        ontology_class=ontology_class,
        risk_level="MediumRisk",
        is_reversible=True,
        affects_scope="ExternalWorld",
        tool_name=tool_name,
        params=params,
    )


# ======================================================================
# Legacy format: Network rules block/allow tool calls end-to-end
# ======================================================================


class TestLegacyNetworkRuleBlocksToolCall:
    """Legacy format: Create a NemoClaw policy allowing only github.com:443,
    then verify that web_fetch to github.com passes and web_fetch to evil.com
    blocks.
    """

    @pytest.fixture
    def setup(self, tmp_path):
        policy_dir = tmp_path / "nemoclaw"
        _write_yaml(
            policy_dir,
            "network.yaml",
            """
rules:
  - name: github-https
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""",
        )
        kg = KnowledgeGraph()
        kg.load_directory(ONTOLOGY_DIR)
        NemoClawPolicyLoader(policy_dir).load(kg)
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        return checker

    def test_allowed_host_passes(self, setup):
        checker = setup
        action = _make_action("WebFetch", url="https://github.com/api/repos")
        result = checker.check(action)
        assert result.violated is False

    def test_disallowed_host_blocked(self, setup):
        checker = setup
        action = _make_action("WebFetch", url="https://evil.com/exfiltrate")
        result = checker.check(action)
        assert result.violated is True
        assert "Not in NemoClaw network allowlist" in result.reason
        assert "evil.com" in result.reason

    @pytest.mark.asyncio
    async def test_full_engine_allowed(self, tmp_path):
        """Full engine integration: allowed host passes all pipeline steps."""
        policy_dir = tmp_path / "nemoclaw"
        _write_yaml(
            policy_dir,
            "network.yaml",
            """
rules:
  - name: github-https
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""",
        )
        config = SafeClawConfig(
            data_dir=tmp_path,
            ontology_dir=ONTOLOGY_DIR,
            audit_dir=tmp_path / "audit",
            nemoclaw_enabled=True,
            nemoclaw_policy_dir=policy_dir,
        )
        engine = FullEngine(config)
        event = ToolCallEvent(
            session_id="integ-net",
            user_id="test-user",
            tool_name="web_fetch",
            params={"url": "https://github.com/api/repos"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_full_engine_blocked(self, tmp_path):
        """Full engine integration: disallowed host is blocked at policy step."""
        policy_dir = tmp_path / "nemoclaw"
        _write_yaml(
            policy_dir,
            "network.yaml",
            """
rules:
  - name: github-https
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""",
        )
        config = SafeClawConfig(
            data_dir=tmp_path,
            ontology_dir=ONTOLOGY_DIR,
            audit_dir=tmp_path / "audit",
            nemoclaw_enabled=True,
            nemoclaw_policy_dir=policy_dir,
        )
        engine = FullEngine(config)
        event = ToolCallEvent(
            session_id="integ-net",
            user_id="test-user",
            tool_name="web_fetch",
            params={"url": "https://evil.com/exfiltrate"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True
        assert "NemoClaw" in decision.reason or "network allowlist" in decision.reason


# ======================================================================
# Real format: Network rules block/allow tool calls end-to-end
# ======================================================================


class TestRealNetworkRuleBlocksToolCall:
    """Real NemoClaw format: network_policies with rest protocol."""

    @pytest.fixture
    def setup(self, tmp_path):
        policy_dir = tmp_path / "nemoclaw"
        _write_yaml(
            policy_dir,
            "network.yaml",
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
    binaries: []
""",
        )
        kg = KnowledgeGraph()
        kg.load_directory(ONTOLOGY_DIR)
        NemoClawPolicyLoader(policy_dir).load(kg)
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        return checker

    def test_allowed_host_passes(self, setup):
        checker = setup
        action = _make_action("WebFetch", url="https://github.com/api/repos")
        result = checker.check(action)
        assert result.violated is False

    def test_disallowed_host_blocked(self, setup):
        checker = setup
        action = _make_action("WebFetch", url="https://evil.com/exfiltrate")
        result = checker.check(action)
        assert result.violated is True
        assert "evil.com" in result.reason

    @pytest.mark.asyncio
    async def test_full_engine_allowed(self, tmp_path):
        policy_dir = tmp_path / "nemoclaw"
        _write_yaml(
            policy_dir,
            "network.yaml",
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
    binaries: []
""",
        )
        config = SafeClawConfig(
            data_dir=tmp_path,
            ontology_dir=ONTOLOGY_DIR,
            audit_dir=tmp_path / "audit",
            nemoclaw_enabled=True,
            nemoclaw_policy_dir=policy_dir,
        )
        engine = FullEngine(config)
        event = ToolCallEvent(
            session_id="integ-net-real",
            user_id="test-user",
            tool_name="web_fetch",
            params={"url": "https://github.com/api/repos"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_full_engine_blocked(self, tmp_path):
        policy_dir = tmp_path / "nemoclaw"
        _write_yaml(
            policy_dir,
            "network.yaml",
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
    binaries: []
""",
        )
        config = SafeClawConfig(
            data_dir=tmp_path,
            ontology_dir=ONTOLOGY_DIR,
            audit_dir=tmp_path / "audit",
            nemoclaw_enabled=True,
            nemoclaw_policy_dir=policy_dir,
        )
        engine = FullEngine(config)
        event = ToolCallEvent(
            session_id="integ-net-real",
            user_id="test-user",
            tool_name="web_fetch",
            params={"url": "https://evil.com/exfiltrate"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True


# ======================================================================
# Legacy format: Filesystem rules enforce read-only / read-write
# ======================================================================


class TestLegacyFilesystemRuleBlocksWrite:
    """Legacy format: Create a NemoClaw policy with /usr read-only and
    /sandbox read-write.
    """

    @pytest.fixture
    def setup(self, tmp_path):
        policy_dir = tmp_path / "nemoclaw"
        _write_yaml(
            policy_dir,
            "filesystem.yaml",
            """
filesystem:
  - path: "/usr"
    mode: "read-only"
  - path: "/sandbox"
    mode: "read-write"
""",
        )
        kg = KnowledgeGraph()
        kg.load_directory(ONTOLOGY_DIR)
        NemoClawPolicyLoader(policy_dir).load(kg)
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        return checker

    def test_write_to_sandbox_allowed(self, setup):
        checker = setup
        action = _make_action("WriteFile", tool_name="write", file_path="/sandbox/foo.txt")
        result = checker.check(action)
        assert result.violated is False

    def test_write_to_usr_blocked(self, setup):
        checker = setup
        action = _make_action("WriteFile", tool_name="write", file_path="/usr/bin/evil")
        result = checker.check(action)
        assert result.violated is True
        assert "read-only" in result.reason

    def test_read_from_usr_allowed(self, setup):
        checker = setup
        action = _make_action("ReadFile", tool_name="read", file_path="/usr/bin/ls")
        result = checker.check(action)
        assert result.violated is False

    @pytest.mark.asyncio
    async def test_full_engine_write_sandbox_allowed(self, tmp_path):
        policy_dir = tmp_path / "nemoclaw"
        _write_yaml(
            policy_dir,
            "filesystem.yaml",
            """
filesystem:
  - path: "/usr"
    mode: "read-only"
  - path: "/sandbox"
    mode: "read-write"
""",
        )
        config = SafeClawConfig(
            data_dir=tmp_path,
            ontology_dir=ONTOLOGY_DIR,
            audit_dir=tmp_path / "audit",
            nemoclaw_enabled=True,
            nemoclaw_policy_dir=policy_dir,
        )
        engine = FullEngine(config)
        event = ToolCallEvent(
            session_id="integ-fs",
            user_id="test-user",
            tool_name="write",
            params={"file_path": "/sandbox/foo.txt"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_full_engine_write_usr_blocked(self, tmp_path):
        policy_dir = tmp_path / "nemoclaw"
        _write_yaml(
            policy_dir,
            "filesystem.yaml",
            """
filesystem:
  - path: "/usr"
    mode: "read-only"
  - path: "/sandbox"
    mode: "read-write"
""",
        )
        config = SafeClawConfig(
            data_dir=tmp_path,
            ontology_dir=ONTOLOGY_DIR,
            audit_dir=tmp_path / "audit",
            nemoclaw_enabled=True,
            nemoclaw_policy_dir=policy_dir,
        )
        engine = FullEngine(config)
        event = ToolCallEvent(
            session_id="integ-fs",
            user_id="test-user",
            tool_name="write",
            params={"file_path": "/usr/bin/evil"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True
        assert "read-only" in decision.reason


# ======================================================================
# Real format: Filesystem rules enforce read-only / read-write
# ======================================================================


class TestRealFilesystemRuleBlocksWrite:
    """Real NemoClaw format: filesystem_policy with read_only/read_write."""

    @pytest.fixture
    def setup(self, tmp_path):
        policy_dir = tmp_path / "nemoclaw"
        _write_yaml(
            policy_dir,
            "filesystem.yaml",
            """
filesystem_policy:
  read_only:
    - /usr
  read_write:
    - /sandbox
""",
        )
        kg = KnowledgeGraph()
        kg.load_directory(ONTOLOGY_DIR)
        NemoClawPolicyLoader(policy_dir).load(kg)
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        return checker

    def test_write_to_sandbox_allowed(self, setup):
        checker = setup
        action = _make_action("WriteFile", tool_name="write", file_path="/sandbox/foo.txt")
        result = checker.check(action)
        assert result.violated is False

    def test_write_to_usr_blocked(self, setup):
        checker = setup
        action = _make_action("WriteFile", tool_name="write", file_path="/usr/bin/evil")
        result = checker.check(action)
        assert result.violated is True
        assert "read-only" in result.reason

    def test_read_from_usr_allowed(self, setup):
        checker = setup
        action = _make_action("ReadFile", tool_name="read", file_path="/usr/bin/ls")
        result = checker.check(action)
        assert result.violated is False

    @pytest.mark.asyncio
    async def test_full_engine_write_sandbox_allowed(self, tmp_path):
        policy_dir = tmp_path / "nemoclaw"
        _write_yaml(
            policy_dir,
            "filesystem.yaml",
            """
filesystem_policy:
  read_only:
    - /usr
  read_write:
    - /sandbox
""",
        )
        config = SafeClawConfig(
            data_dir=tmp_path,
            ontology_dir=ONTOLOGY_DIR,
            audit_dir=tmp_path / "audit",
            nemoclaw_enabled=True,
            nemoclaw_policy_dir=policy_dir,
        )
        engine = FullEngine(config)
        event = ToolCallEvent(
            session_id="integ-fs-real",
            user_id="test-user",
            tool_name="write",
            params={"file_path": "/sandbox/foo.txt"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_full_engine_write_usr_blocked(self, tmp_path):
        policy_dir = tmp_path / "nemoclaw"
        _write_yaml(
            policy_dir,
            "filesystem.yaml",
            """
filesystem_policy:
  read_only:
    - /usr
  read_write:
    - /sandbox
""",
        )
        config = SafeClawConfig(
            data_dir=tmp_path,
            ontology_dir=ONTOLOGY_DIR,
            audit_dir=tmp_path / "audit",
            nemoclaw_enabled=True,
            nemoclaw_policy_dir=policy_dir,
        )
        engine = FullEngine(config)
        event = ToolCallEvent(
            session_id="integ-fs-real",
            user_id="test-user",
            tool_name="write",
            params={"file_path": "/usr/bin/evil"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True
        assert "read-only" in decision.reason


# ======================================================================
# Hot reload picks up new NemoClaw policies
# ======================================================================


class TestHotReloadPicksUpNewPolicy:
    @pytest.mark.asyncio
    async def test_reload_adds_network_restriction(self, tmp_path):
        policy_dir = tmp_path / "nemoclaw"
        policy_dir.mkdir(parents=True, exist_ok=True)

        config = SafeClawConfig(
            data_dir=tmp_path,
            ontology_dir=ONTOLOGY_DIR,
            audit_dir=tmp_path / "audit",
            nemoclaw_enabled=True,
            nemoclaw_policy_dir=policy_dir,
        )
        engine = FullEngine(config)

        event_other = ToolCallEvent(
            session_id="integ-reload",
            user_id="test-user",
            tool_name="web_fetch",
            params={"url": "https://other.com/page"},
        )
        decision1 = await engine.evaluate_tool_call(event_other)
        assert decision1.block is False, "With no NemoClaw rules, web_fetch should pass"

        _write_yaml(
            policy_dir,
            "sandbox.yaml",
            """
rules:
  - name: example-only
    host: "example.com"
    port: 443
    protocol: https
    allow: true
""",
        )

        await engine.reload()

        decision2 = await engine.evaluate_tool_call(event_other)
        assert (
            decision2.block is True
        ), "After reload with NemoClaw rules, other.com should be blocked"
        assert "NemoClaw" in decision2.reason or "network allowlist" in decision2.reason

        event_example = ToolCallEvent(
            session_id="integ-reload",
            user_id="test-user",
            tool_name="web_fetch",
            params={"url": "https://example.com/data"},
        )
        decision3 = await engine.evaluate_tool_call(event_example)
        assert decision3.block is False, "example.com should be allowed after reload"

    @pytest.mark.asyncio
    async def test_reload_adds_filesystem_restriction(self, tmp_path):
        """Hot reload also picks up new filesystem rules."""
        policy_dir = tmp_path / "nemoclaw"
        policy_dir.mkdir(parents=True, exist_ok=True)

        config = SafeClawConfig(
            data_dir=tmp_path,
            ontology_dir=ONTOLOGY_DIR,
            audit_dir=tmp_path / "audit",
            nemoclaw_enabled=True,
            nemoclaw_policy_dir=policy_dir,
        )
        engine = FullEngine(config)

        event_write = ToolCallEvent(
            session_id="integ-reload-fs",
            user_id="test-user",
            tool_name="write",
            params={"file_path": "/data/output.txt"},
        )
        decision1 = await engine.evaluate_tool_call(event_write)
        assert decision1.block is False

        _write_yaml(
            policy_dir,
            "fs.yaml",
            """
filesystem:
  - path: "/data"
    mode: "read-only"
""",
        )

        await engine.reload()

        decision2 = await engine.evaluate_tool_call(event_write)
        assert decision2.block is True
        assert "read-only" in decision2.reason

    @pytest.mark.asyncio
    async def test_reload_real_format(self, tmp_path):
        """Hot reload with real NemoClaw format."""
        policy_dir = tmp_path / "nemoclaw"
        policy_dir.mkdir(parents=True, exist_ok=True)

        config = SafeClawConfig(
            data_dir=tmp_path,
            ontology_dir=ONTOLOGY_DIR,
            audit_dir=tmp_path / "audit",
            nemoclaw_enabled=True,
            nemoclaw_policy_dir=policy_dir,
        )
        engine = FullEngine(config)

        event_other = ToolCallEvent(
            session_id="integ-reload-real",
            user_id="test-user",
            tool_name="web_fetch",
            params={"url": "https://other.com/page"},
        )
        decision1 = await engine.evaluate_tool_call(event_other)
        assert decision1.block is False

        _write_yaml(
            policy_dir,
            "sandbox.yaml",
            """
network_policies:
  api_group:
    name: api_group
    endpoints:
      - host: example.com
        port: 443
        protocol: rest
        enforcement: enforce
    binaries: []
""",
        )

        await engine.reload()

        decision2 = await engine.evaluate_tool_call(event_other)
        assert decision2.block is True

        event_allowed = ToolCallEvent(
            session_id="integ-reload-real",
            user_id="test-user",
            tool_name="web_fetch",
            params={"url": "https://example.com/data"},
        )
        decision3 = await engine.evaluate_tool_call(event_allowed)
        assert decision3.block is False


# ======================================================================
# No NemoClaw directory has no impact on existing behavior
# ======================================================================


class TestNoNemoClawDirNoImpact:
    @pytest.fixture
    def engine(self, tmp_path):
        config = SafeClawConfig(
            data_dir=tmp_path,
            ontology_dir=ONTOLOGY_DIR,
            audit_dir=tmp_path / "audit",
        )
        return FullEngine(config)

    @pytest.mark.asyncio
    async def test_web_fetch_allowed_without_nemoclaw(self, engine):
        """Without NemoClaw, web_fetch to any host should pass."""
        event = ToolCallEvent(
            session_id="integ-no-nemo",
            user_id="test-user",
            tool_name="web_fetch",
            params={"url": "https://any-site.example.com/page"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_file_write_allowed_without_nemoclaw(self, engine):
        """Without NemoClaw, file writes should not be restricted."""
        event = ToolCallEvent(
            session_id="integ-no-nemo",
            user_id="test-user",
            tool_name="write",
            params={"file_path": "/any/path/file.txt"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_file_read_allowed_without_nemoclaw(self, engine):
        """Without NemoClaw, file reads should not be restricted."""
        event = ToolCallEvent(
            session_id="integ-no-nemo",
            user_id="test-user",
            tool_name="read",
            params={"file_path": "/src/main.py"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_existing_policy_still_applies(self, engine):
        """Existing SafeClaw policy (e.g., force push block) still works."""
        event = ToolCallEvent(
            session_id="integ-no-nemo",
            user_id="test-user",
            tool_name="exec",
            params={"command": "git push --force origin main"},
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True

    def test_policy_checker_nemoclaw_disabled(self, engine):
        """PolicyChecker should report nemoclaw as disabled."""
        assert engine.policy_checker._nemoclaw_enabled is False


# ======================================================================
# Real format: Combined network + filesystem in one document
# ======================================================================


class TestRealCombinedIntegration:
    @pytest.fixture
    def setup(self, tmp_path):
        policy_dir = tmp_path / "nemoclaw"
        _write_yaml(
            policy_dir,
            "policy.yaml",
            """
network_policies:
  claude_code:
    name: claude_code
    endpoints:
      - host: api.anthropic.com
        port: 443
        protocol: rest
        enforcement: enforce
        tls: terminate
    binaries:
      - { path: /usr/local/bin/claude }

filesystem_policy:
  include_workdir: true
  read_only:
    - /usr
    - /lib
  read_write:
    - /sandbox
    - /tmp
""",
        )
        kg = KnowledgeGraph()
        kg.load_directory(ONTOLOGY_DIR)
        NemoClawPolicyLoader(policy_dir).load(kg)
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        return checker

    def test_allowed_api_call(self, setup):
        checker = setup
        action = _make_action("WebFetch", url="https://api.anthropic.com/v1/messages")
        assert checker.check(action).violated is False

    def test_blocked_api_call(self, setup):
        checker = setup
        action = _make_action("WebFetch", url="https://evil.com/exfiltrate")
        assert checker.check(action).violated is True

    def test_write_to_sandbox(self, setup):
        checker = setup
        action = _make_action(
            "WriteFile",
            tool_name="write",
            file_path="/sandbox/result.txt",
        )
        assert checker.check(action).violated is False

    def test_write_to_read_only(self, setup):
        checker = setup
        action = _make_action("WriteFile", tool_name="write", file_path="/usr/bin/evil")
        result = checker.check(action)
        assert result.violated is True
        assert "read-only" in result.reason

    def test_read_from_read_only(self, setup):
        checker = setup
        action = _make_action("ReadFile", tool_name="read", file_path="/usr/lib/libz.so")
        assert checker.check(action).violated is False

    def test_outside_sandbox(self, setup):
        checker = setup
        action = _make_action(
            "WriteFile",
            tool_name="write",
            file_path="/home/user/.ssh/key",
        )
        result = checker.check(action)
        assert result.violated is True
        assert "outside NemoClaw sandbox" in result.reason
