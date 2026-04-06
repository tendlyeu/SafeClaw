"""Tests for multi-agent governance features.

Covers: AgentRegistry, RoleManager, DelegationDetector,
TempPermissionManager, hierarchy rate limiting, and engine integration.
"""

from pathlib import Path

import pytest

from safeclaw.engine.agent_registry import AgentRegistry, MAX_AGENTS
from safeclaw.engine.roles import RoleManager
from safeclaw.engine.delegation_detector import (
    DelegationDetector,
    DETECTION_WINDOW,
)
from safeclaw.engine.temp_permissions import TempPermissionManager
from safeclaw.constraints.action_classifier import ClassifiedAction
from safeclaw.constraints.rate_limiter import RateLimiter


# ---------------------------------------------------------------------------
# AgentRegistry
# ---------------------------------------------------------------------------


class TestAgentRegistry:
    def test_register_returns_token(self):
        reg = AgentRegistry()
        token = reg.register_agent("agent-1", "researcher", "sess-1")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_verify_correct_token(self):
        reg = AgentRegistry()
        token = reg.register_agent("agent-1", "researcher", "sess-1")
        assert reg.verify_token("agent-1", token) is True

    def test_verify_wrong_token_fails(self):
        reg = AgentRegistry()
        reg.register_agent("agent-1", "researcher", "sess-1")
        assert reg.verify_token("agent-1", "wrong-token") is False

    def test_verify_unregistered_agent_fails(self):
        reg = AgentRegistry()
        assert reg.verify_token("nonexistent", "any-token") is False

    def test_kill_agent(self):
        reg = AgentRegistry()
        reg.register_agent("agent-1", "researcher", "sess-1")
        assert reg.is_killed("agent-1") is False
        reg.kill_agent("agent-1")
        assert reg.is_killed("agent-1") is True

    def test_revive_agent(self):
        reg = AgentRegistry()
        reg.register_agent("agent-1", "researcher", "sess-1")
        reg.kill_agent("agent-1")
        assert reg.is_killed("agent-1") is True
        reg.revive_agent("agent-1")
        assert reg.is_killed("agent-1") is False

    def test_is_killed_unregistered_returns_false(self):
        """Unknown agents are NOT treated as killed — only explicitly killed agents return True."""
        reg = AgentRegistry()
        assert reg.is_killed("nonexistent") is False

    def test_get_hierarchy_ids_single_agent(self):
        reg = AgentRegistry()
        reg.register_agent("agent-1", "researcher", "sess-1")
        ids = reg.get_hierarchy_ids("agent-1")
        assert ids == {"agent-1"}

    def test_get_hierarchy_ids_parent_child(self):
        reg = AgentRegistry()
        reg.register_agent("parent", "admin", "sess-1")
        reg.register_agent("child", "developer", "sess-1", parent_id="parent")
        # From child perspective
        ids = reg.get_hierarchy_ids("child")
        assert "parent" in ids
        assert "child" in ids
        # From parent perspective
        ids = reg.get_hierarchy_ids("parent")
        assert "parent" in ids
        assert "child" in ids

    def test_get_hierarchy_ids_three_levels(self):
        reg = AgentRegistry()
        reg.register_agent("root", "admin", "sess-1")
        reg.register_agent("mid", "developer", "sess-1", parent_id="root")
        reg.register_agent("leaf", "researcher", "sess-1", parent_id="mid")
        ids = reg.get_hierarchy_ids("leaf")
        assert ids == {"root", "mid", "leaf"}

    def test_max_agents_eviction(self):
        reg = AgentRegistry()
        # Register MAX_AGENTS + 1 agents; the first should be evicted
        for i in range(MAX_AGENTS + 1):
            reg.register_agent(f"agent-{i}", "researcher", "sess-1")
        # The very first agent should have been evicted
        assert reg.get_agent("agent-0") is None
        # The last agent should still be present
        assert reg.get_agent(f"agent-{MAX_AGENTS}") is not None

    def test_re_register_active_agent_raises(self):
        """Re-registering an active (non-killed) agent raises ValueError."""
        reg = AgentRegistry()
        reg.register_agent("agent-1", "researcher", "sess-1")
        with pytest.raises(ValueError, match="already registered and active"):
            reg.register_agent("agent-1", "developer", "sess-1")

    def test_re_register_killed_agent_succeeds(self):
        """Re-registering a killed agent is allowed and resets its state."""
        reg = AgentRegistry()
        token1 = reg.register_agent("agent-1", "researcher", "sess-1")
        reg.kill_agent("agent-1")
        assert reg.is_killed("agent-1") is True
        token2 = reg.register_agent("agent-1", "developer", "sess-1")
        # Old token should no longer work
        assert reg.verify_token("agent-1", token1) is False
        # New token should work
        assert reg.verify_token("agent-1", token2) is True
        # Role should be updated
        assert reg.get_agent("agent-1").role == "developer"
        # Agent should no longer be killed
        assert reg.is_killed("agent-1") is False


# ---------------------------------------------------------------------------
# RoleManager
# ---------------------------------------------------------------------------


class TestRoleManager:
    def test_builtin_roles_loaded_by_default(self):
        rm = RoleManager()
        assert rm.get_role("researcher") is not None
        assert rm.get_role("developer") is not None
        assert rm.get_role("admin") is not None

    def test_get_role_researcher(self):
        rm = RoleManager()
        role = rm.get_role("researcher")
        assert role.name == "researcher"
        assert role.enforcement_mode == "enforce"

    def test_get_role_unknown_returns_none(self):
        rm = RoleManager()
        assert rm.get_role("unknown-role") is None

    def test_researcher_denies_write(self):
        rm = RoleManager()
        role = rm.get_role("researcher")
        assert rm.is_action_allowed(role, "WriteFile") is False

    def test_researcher_allows_read(self):
        rm = RoleManager()
        role = rm.get_role("researcher")
        assert rm.is_action_allowed(role, "ReadFile") is True

    def test_developer_allows_write(self):
        rm = RoleManager()
        role = rm.get_role("developer")
        # Developer has no allowed_action_classes set (empty = allow all not denied)
        assert rm.is_action_allowed(role, "WriteFile") is True

    def test_developer_denies_force_push(self):
        rm = RoleManager()
        role = rm.get_role("developer")
        assert rm.is_action_allowed(role, "ForcePush") is False

    def test_admin_allows_everything(self):
        rm = RoleManager()
        role = rm.get_role("admin")
        # Admin has no denied actions and no allowed list (empty = allow all)
        assert rm.is_action_allowed(role, "ForcePush") is True
        assert rm.is_action_allowed(role, "WriteFile") is True
        assert rm.is_action_allowed(role, "DeleteFile") is True

    def test_resource_denied_secrets_path(self):
        rm = RoleManager()
        role = rm.get_role("developer")
        assert rm.is_resource_allowed(role, "/secrets/api-key.txt") is False

    def test_resource_allowed_normal_path(self):
        rm = RoleManager()
        role = rm.get_role("developer")
        assert rm.is_resource_allowed(role, "/src/main.py") is True

    def test_effective_constraints_org_overrides_role(self):
        rm = RoleManager()
        role = rm.get_role("developer")
        org_policy = {"denied_actions": ["DeployProduction"]}
        parent_constraints = {}
        result = rm.get_effective_constraints(role, org_policy, parent_constraints)
        assert "DeployProduction" in result["denied_actions"]
        # Developer's own denials should also be present
        assert "ForcePush" in result["denied_actions"]

    def test_effective_constraints_parent_adds_denials(self):
        rm = RoleManager()
        role = rm.get_role("developer")
        org_policy = {}
        parent_constraints = {"denied_actions": ["ShellAction"]}
        result = rm.get_effective_constraints(role, org_policy, parent_constraints)
        assert "ShellAction" in result["denied_actions"]

    def test_effective_constraints_most_restrictive_wins(self):
        rm = RoleManager()
        role = rm.get_role("researcher")
        # Researcher allows: ReadFile, ListFiles, SearchFiles
        # Org restricts to just ReadFile
        org_policy = {"allowed_actions": ["ReadFile"]}
        parent_constraints = {}
        result = rm.get_effective_constraints(role, org_policy, parent_constraints)
        # Intersection: only ReadFile should remain
        assert "ReadFile" in result["allowed_actions"]
        assert "ListFiles" not in result["allowed_actions"]


# ---------------------------------------------------------------------------
# DelegationDetector
# ---------------------------------------------------------------------------


class TestDelegationDetector:
    def test_no_delegation_no_blocks(self):
        dd = DelegationDetector(mode="strict")
        result = dd.check_delegation("sess-1", "agent-1", "write", "sig-1")
        assert result.is_delegation is False

    def test_delegation_detected_different_agent_same_action(self):
        dd = DelegationDetector(mode="strict")
        dd.record_block("sess-1", "agent-1", "write", "sig-1")
        result = dd.check_delegation("sess-1", "agent-2", "write", "sig-1")
        assert result.is_delegation is True
        assert result.original_agent_id == "agent-1"

    def test_same_agent_retry_not_delegation(self):
        dd = DelegationDetector(mode="strict")
        dd.record_block("sess-1", "agent-1", "write", "sig-1")
        result = dd.check_delegation("sess-1", "agent-1", "write", "sig-1")
        assert result.is_delegation is False

    def test_different_tool_not_delegation(self):
        dd = DelegationDetector(mode="strict")
        dd.record_block("sess-1", "agent-1", "write", "sig-1")
        result = dd.check_delegation("sess-1", "agent-2", "read", "sig-1")
        assert result.is_delegation is False

    def test_expired_block_not_detected(self, monkeypatch):
        dd = DelegationDetector(mode="strict")
        # Record a block at time 0
        fake_time = [0.0]
        monkeypatch.setattr("safeclaw.engine.delegation_detector.monotonic", lambda: fake_time[0])
        dd.record_block("sess-1", "agent-1", "write", "sig-1")
        # Advance past DETECTION_WINDOW
        fake_time[0] = DETECTION_WINDOW + 1
        result = dd.check_delegation("sess-1", "agent-2", "write", "sig-1")
        assert result.is_delegation is False

    def test_disabled_mode_never_detects(self):
        dd = DelegationDetector(mode="disabled")
        dd.record_block("sess-1", "agent-1", "write", "sig-1")
        result = dd.check_delegation("sess-1", "agent-2", "write", "sig-1")
        assert result.is_delegation is False

    def test_make_signature_deterministic(self):
        params = {"a": 1, "b": "hello"}
        sig1 = DelegationDetector.make_signature(params)
        sig2 = DelegationDetector.make_signature(params)
        assert sig1 == sig2

    def test_make_signature_different_params_different_sig(self):
        sig1 = DelegationDetector.make_signature({"a": 1})
        sig2 = DelegationDetector.make_signature({"a": 2})
        assert sig1 != sig2


# ---------------------------------------------------------------------------
# TempPermissionManager
# ---------------------------------------------------------------------------


class TestTempPermissionManager:
    def test_grant_and_check(self):
        tpm = TempPermissionManager()
        tpm.grant("agent-1", "WriteFile", duration_seconds=60)
        assert tpm.check("agent-1", "WriteFile") is True

    def test_expired_grant_returns_false(self, monkeypatch):
        tpm = TempPermissionManager()
        fake_time = [1000.0]
        monkeypatch.setattr("safeclaw.engine.temp_permissions.monotonic", lambda: fake_time[0])
        tpm.grant("agent-1", "WriteFile", duration_seconds=10)
        # Advance past expiration
        fake_time[0] = 1011.0
        assert tpm.check("agent-1", "WriteFile") is False

    def test_task_bound_revoked_on_complete(self):
        tpm = TempPermissionManager()
        tpm.grant("agent-1", "WriteFile", task_id="task-42")
        assert tpm.check("agent-1", "WriteFile") is True
        count = tpm.complete_task("task-42")
        assert count == 1
        assert tpm.check("agent-1", "WriteFile") is False

    def test_time_and_task_both_set(self):
        tpm = TempPermissionManager()
        grant_id = tpm.grant("agent-1", "WriteFile", duration_seconds=60, task_id="task-1")
        assert isinstance(grant_id, str)
        assert tpm.check("agent-1", "WriteFile") is True

    def test_revoke_specific_grant(self):
        tpm = TempPermissionManager()
        gid = tpm.grant("agent-1", "WriteFile", duration_seconds=60)
        assert tpm.check("agent-1", "WriteFile") is True
        tpm.revoke(gid)
        assert tpm.check("agent-1", "WriteFile") is False

    def test_list_grants_filters_by_agent(self):
        tpm = TempPermissionManager()
        tpm.grant("agent-1", "WriteFile", duration_seconds=60)
        tpm.grant("agent-2", "ReadFile", duration_seconds=60)
        grants_1 = tpm.list_grants(agent_id="agent-1")
        grants_2 = tpm.list_grants(agent_id="agent-2")
        assert len(grants_1) == 1
        assert grants_1[0].agent_id == "agent-1"
        assert len(grants_2) == 1
        assert grants_2[0].agent_id == "agent-2"

    def test_cleanup_expired(self, monkeypatch):
        tpm = TempPermissionManager()
        fake_time = [1000.0]
        monkeypatch.setattr("safeclaw.engine.temp_permissions.monotonic", lambda: fake_time[0])
        tpm.grant("agent-1", "WriteFile", duration_seconds=5)
        tpm.grant("agent-1", "ReadFile", duration_seconds=600)
        # Advance past first grant but not second
        fake_time[0] = 1006.0
        removed = tpm.cleanup_expired()
        assert removed == 1
        assert tpm.check("agent-1", "WriteFile") is False
        assert tpm.check("agent-1", "ReadFile") is True

    def test_grant_requires_duration_or_task(self):
        tpm = TempPermissionManager()
        with pytest.raises(ValueError, match="At least one of"):
            tpm.grant("agent-1", "WriteFile")


# ---------------------------------------------------------------------------
# Hierarchy Rate Limiting
# ---------------------------------------------------------------------------


class TestHierarchyRateLimiting:
    def _make_action(self, risk_level: str = "HighRisk") -> ClassifiedAction:
        return ClassifiedAction(
            ontology_class="WriteFile",
            risk_level=risk_level,
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="write",
            params={},
        )

    def test_per_agent_limit_independent(self):
        rl = RateLimiter()
        action = self._make_action("HighRisk")
        # Record actions for two different agents in the same session
        for _ in range(5):
            rl.record(action, "sess-1", agent_id="agent-1")
        for _ in range(5):
            rl.record(action, "sess-1", agent_id="agent-2")
        # Check hierarchy with only agent-1: should not exceed 30-per-hour limit
        result = rl.check_hierarchy(action, {"agent-1"})
        assert result.exceeded is False

    def test_hierarchy_limit_sums_across_agents(self):
        rl = RateLimiter(
            hierarchy_limits={"HighRisk": (10, 3600)},
        )
        action = self._make_action("HighRisk")
        # 6 actions for each of 2 agents = 12 total, exceeds limit of 10
        for _ in range(6):
            rl.record(action, "sess-1", agent_id="agent-1")
        for _ in range(6):
            rl.record(action, "sess-1", agent_id="agent-2")
        result = rl.check_hierarchy(action, {"agent-1", "agent-2"})
        assert result.exceeded is True
        assert "12/10" in result.reason

    def test_hierarchy_limit_not_exceeded_under_threshold(self):
        rl = RateLimiter(
            hierarchy_limits={"HighRisk": (10, 3600)},
        )
        action = self._make_action("HighRisk")
        for _ in range(3):
            rl.record(action, "sess-1", agent_id="agent-1")
        for _ in range(3):
            rl.record(action, "sess-1", agent_id="agent-2")
        result = rl.check_hierarchy(action, {"agent-1", "agent-2"})
        assert result.exceeded is False


# ---------------------------------------------------------------------------
# Engine Multi-Agent Integration (using FullEngine)
# ---------------------------------------------------------------------------


class TestEngineMultiAgentIntegration:
    @pytest.fixture
    def engine(self, tmp_path):
        from safeclaw.config import SafeClawConfig
        from safeclaw.engine.full_engine import FullEngine

        config = SafeClawConfig(
            data_dir=tmp_path,
            ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
            audit_dir=tmp_path / "audit",
        )
        eng = FullEngine(config)
        # Enable token auth for these tests
        eng._require_token_auth = True
        return eng

    @pytest.mark.asyncio
    async def test_killed_agent_blocked(self, engine):
        from safeclaw.engine.core import ToolCallEvent

        token = engine.agent_registry.register_agent("agent-k", "developer", "sess-1")
        engine.agent_registry.kill_agent("agent-k")
        event = ToolCallEvent(
            session_id="sess-1",
            user_id="user-1",
            tool_name="read",
            params={"file_path": "/src/main.py"},
            agent_id="agent-k",
            agent_token=token,
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True
        # Killed agents are blocked — either by the kill switch check or by
        # token verification failing (defense-in-depth: verify_token returns
        # False for killed agents).
        assert "killed" in decision.reason.lower() or "token" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_invalid_token_blocked(self, engine):
        from safeclaw.engine.core import ToolCallEvent

        engine.agent_registry.register_agent("agent-t", "developer", "sess-1")
        event = ToolCallEvent(
            session_id="sess-1",
            user_id="user-1",
            tool_name="read",
            params={"file_path": "/src/main.py"},
            agent_id="agent-t",
            agent_token="bad-token",
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True
        assert "token" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_role_blocks_denied_action(self, engine):
        from safeclaw.engine.core import ToolCallEvent

        token = engine.agent_registry.register_agent("agent-r", "researcher", "sess-1")
        event = ToolCallEvent(
            session_id="sess-1",
            user_id="user-1",
            tool_name="write",
            params={"file_path": "/src/main.py", "content": "hello"},
            agent_id="agent-r",
            agent_token=token,
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True
        assert "role" in decision.reason.lower() or "researcher" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_temp_grant_bypasses_role_block(self, engine):
        from safeclaw.engine.core import ToolCallEvent

        token = engine.agent_registry.register_agent("agent-tg", "researcher", "sess-1")
        # Grant temp WriteFile permission
        engine.temp_permissions.grant("agent-tg", "WriteFile", duration_seconds=60)
        event = ToolCallEvent(
            session_id="sess-1",
            user_id="user-1",
            tool_name="write",
            params={"file_path": "/src/main.py", "content": "hello"},
            agent_id="agent-tg",
            agent_token=token,
        )
        decision = await engine.evaluate_tool_call(event)
        # Temp grant bypasses role block; WriteFile has no other blocking preference (R3-66)
        assert decision.block is False, f"Expected allowed but got blocked: {decision.reason}"

    @pytest.mark.asyncio
    async def test_delegation_recorded_on_block(self, engine):
        from safeclaw.engine.core import ToolCallEvent
        from safeclaw.engine.delegation_detector import DelegationDetector

        engine.delegation_detector.mode = "strict"
        token_r = engine.agent_registry.register_agent("agent-d1", "researcher", "sess-d")
        engine.agent_registry.register_agent("agent-d2", "developer", "sess-d")

        # Agent d1 (researcher) tries to write -> blocked by role
        event1 = ToolCallEvent(
            session_id="sess-d",
            user_id="user-1",
            tool_name="write",
            params={"file_path": "/src/test.py", "content": "x"},
            agent_id="agent-d1",
            agent_token=token_r,
        )
        decision1 = await engine.evaluate_tool_call(event1)
        assert decision1.block is True

        # Agent d2 (developer) tries the same write -> delegation detected
        sig = DelegationDetector.make_signature(event1.params)
        delegation = engine.delegation_detector.check_delegation("sess-d", "agent-d2", "write", sig)
        assert delegation.is_delegation is True
        assert delegation.original_agent_id == "agent-d1"

    @pytest.mark.asyncio
    async def test_agent_id_in_audit_record(self, engine):
        from safeclaw.engine.core import ToolCallEvent

        token = engine.agent_registry.register_agent("agent-audit", "developer", "sess-a")
        event = ToolCallEvent(
            session_id="sess-a",
            user_id="user-1",
            tool_name="read",
            params={"file_path": "/src/main.py"},
            agent_id="agent-audit",
            agent_token=token,
        )
        decision = await engine.evaluate_tool_call(event)
        # Get the audit record by the audit_id on the decision
        assert decision.audit_id != ""
        records = engine.audit.get_session_records("sess-a")
        assert len(records) >= 1
        found = [r for r in records if r.agent_id == "agent-audit"]
        assert len(found) >= 1

    @pytest.mark.asyncio
    async def test_resource_deny_secrets_via_pipeline(self, engine):
        from safeclaw.engine.core import ToolCallEvent

        token = engine.agent_registry.register_agent("agent-sd", "developer", "sess-1")
        event = ToolCallEvent(
            session_id="sess-1",
            user_id="user-1",
            tool_name="read",
            params={"path": "/secrets/api-key.txt"},
            agent_id="agent-sd",
            agent_token=token,
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True
        assert "denied access" in decision.reason.lower(), (
            f"Expected role-based resource denial but got: {decision.reason}"
        )
        assert "/secrets/api-key.txt" in decision.reason, (
            f"Expected denied path in reason but got: {decision.reason}"
        )

    @pytest.mark.asyncio
    async def test_resource_deny_with_alternate_param_key(self, engine):
        from safeclaw.engine.core import ToolCallEvent

        token = engine.agent_registry.register_agent("agent-fp", "developer", "sess-1")
        event = ToolCallEvent(
            session_id="sess-1",
            user_id="user-1",
            tool_name="read",
            params={"filepath": "/secrets/api-key.txt"},
            agent_id="agent-fp",
            agent_token=token,
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True
        assert "denied" in decision.reason.lower() or "secrets" in decision.reason.lower()
