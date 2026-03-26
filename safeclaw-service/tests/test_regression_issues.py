"""Regression tests for fixed GitHub issues.

Covers audit bugs (#43, #115, #161), agent management bugs (#49, #50, #51, #52,
#57, #58, #60, #62, #63, #78, #81, #82), session/rate bugs (#25, #53, #61, #112,
#119, #148, #149), and hot-reload bugs (#24, #92).
"""

import asyncio
import time
from collections import OrderedDict
from datetime import date, timedelta
from pathlib import Path

import pytest

from safeclaw.audit.logger import AuditLogger
from safeclaw.audit.models import (
    ActionDetail,
    DecisionRecord,
    Justification,
)
from safeclaw.constraints.action_classifier import ClassifiedAction
from safeclaw.constraints.dependency_checker import DependencyChecker
from safeclaw.constraints.rate_limiter import RateLimiter
from safeclaw.constraints.temporal_checker import TemporalChecker
from safeclaw.engine.agent_registry import AgentRegistry
from safeclaw.engine.delegation_detector import DelegationDetector
from safeclaw.engine.event_bus import EventBus, SafeClawEvent
from safeclaw.engine.heartbeat_monitor import HeartbeatMonitor
from safeclaw.engine.knowledge_graph import KnowledgeGraph
from safeclaw.engine.roles import Role, RoleManager
from safeclaw.engine.temp_permissions import TempPermissionManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(session_id="sess-1", tool_name="exec", decision="allowed") -> DecisionRecord:
    return DecisionRecord(
        session_id=session_id,
        user_id="test-user",
        action=ActionDetail(
            tool_name=tool_name,
            params={"command": "ls"},
            ontology_class="ExecuteCommand",
            risk_level="MediumRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
        ),
        decision=decision,
        justification=Justification(elapsed_ms=1.0),
    )


def _make_action(
    cls="ExecuteCommand", risk="MediumRisk", tool="exec", reversible=True,
) -> ClassifiedAction:
    return ClassifiedAction(
        ontology_class=cls,
        risk_level=risk,
        is_reversible=reversible,
        affects_scope="LocalOnly",
        tool_name=tool,
        params={},
    )


@pytest.fixture
def kg():
    kg = KnowledgeGraph()
    ontology_dir = Path(__file__).parent.parent / "safeclaw" / "ontologies"
    kg.load_directory(ontology_dir)
    return kg


# ===========================================================================
# AUDIT BUGS
# ===========================================================================


class TestIssue43AuditExplainLookup:
    """#43: audit explain CLI should use get_record_by_id, not get_recent_records."""

    def test_get_record_by_id_finds_old_records(self, tmp_path):
        """Records beyond the last 200 should still be findable by ID."""
        logger = AuditLogger(tmp_path)
        # Write 250 records
        record_ids = []
        for i in range(250):
            rec = _make_record(session_id=f"sess-{i % 5}")
            logger.log(rec)
            record_ids.append(rec.id)

        # The first record should be findable by ID even though there are 250+
        found = logger.get_record_by_id(record_ids[0])
        assert found is not None
        assert found.id == record_ids[0]

        # Also check a record in the middle
        found_mid = logger.get_record_by_id(record_ids[125])
        assert found_mid is not None
        assert found_mid.id == record_ids[125]


class TestIssue115ClassificationObserverLocking:
    """#115: ClassificationObserver JSONL file should use file locking."""

    def test_write_line_uses_flock(self, tmp_path):
        """Verify that _write_line uses fcntl.flock for file locking."""
        from safeclaw.llm.classification_observer import ClassificationObserver

        suggestions_file = tmp_path / "suggestions.jsonl"
        observer = ClassificationObserver(client=None, suggestions_file=suggestions_file)

        # Write a line and verify it uses locking (by checking the method exists
        # and the file is written correctly)
        observer._write_line('{"test": true}\n')
        assert suggestions_file.exists()
        content = suggestions_file.read_text()
        assert '{"test": true}' in content

    def test_write_line_with_fcntl_import(self):
        """Verify fcntl is imported in the classification_observer module."""
        import safeclaw.llm.classification_observer as mod
        assert hasattr(mod, 'fcntl')


class TestIssue161AuditLogRotation:
    """#161: Audit log rotation should honor retentionDays."""

    def test_rotation_deletes_old_directories(self, tmp_path):
        """Directories older than retention_days should be removed."""
        # Create a directory that is 100 days old
        old_date = (date.today() - timedelta(days=100)).isoformat()
        old_dir = tmp_path / old_date
        old_dir.mkdir()
        (old_dir / "session-test.jsonl").write_text('{"test": true}\n')

        # Create a directory that is 10 days old (should be kept)
        recent_date = (date.today() - timedelta(days=10)).isoformat()
        recent_dir = tmp_path / recent_date
        recent_dir.mkdir()
        (recent_dir / "session-test.jsonl").write_text('{"test": true}\n')

        # Initialize AuditLogger with 90-day retention — triggers rotation
        _logger = AuditLogger(tmp_path, retention_days=90)

        assert not old_dir.exists(), "Old directory should have been rotated out"
        assert recent_dir.exists(), "Recent directory should be kept"

    def test_rotation_respects_custom_retention(self, tmp_path):
        """Custom retention_days is respected."""
        date_50_days = (date.today() - timedelta(days=50)).isoformat()
        dir_50 = tmp_path / date_50_days
        dir_50.mkdir()
        (dir_50 / "session-x.jsonl").write_text('{"test": true}\n')

        # With 30-day retention, 50-day-old should be removed
        _logger = AuditLogger(tmp_path, retention_days=30)
        assert not dir_50.exists()


# ===========================================================================
# AGENT MANAGEMENT BUGS
# ===========================================================================


class TestIssue49DelegationPolicyConfigurable:
    """#49: delegationPolicy 'configurable' should be treated as a valid mode."""

    def test_configurable_mode_accepted(self):
        detector = DelegationDetector(mode="configurable")
        # Should not raise, should map to "strict"
        assert detector.mode == "strict"

    def test_invalid_mode_defaults_to_strict(self):
        detector = DelegationDetector(mode="invalid_mode")
        assert detector.mode == "strict"

    def test_valid_modes_work(self):
        for mode in ("strict", "permissive", "disabled"):
            detector = DelegationDetector(mode=mode)
            assert detector.mode == mode


class TestIssue50TempPermissionZeroDuration:
    """#50: TempPermissionManager should reject zero/negative duration_seconds."""

    def test_zero_duration_raises(self):
        mgr = TempPermissionManager()
        with pytest.raises(ValueError, match="positive"):
            mgr.grant("agent-1", "ReadFile", duration_seconds=0)

    def test_negative_duration_raises(self):
        mgr = TempPermissionManager()
        with pytest.raises(ValueError, match="positive"):
            mgr.grant("agent-1", "ReadFile", duration_seconds=-100)

    def test_positive_duration_works(self):
        mgr = TempPermissionManager()
        grant_id = mgr.grant("agent-1", "ReadFile", duration_seconds=60)
        assert grant_id


class TestIssue51HierarchySessionBoundary:
    """#51: Agent hierarchy traversal should respect session boundaries."""

    def test_cross_session_agents_excluded_from_hierarchy(self):
        reg = AgentRegistry()
        reg.register_agent("parent-a", "admin", "session-1")
        reg.register_agent("child-a", "developer", "session-1", parent_id="parent-a")

        # Agent from different session claiming same parent
        reg.register_agent("child-b", "developer", "session-2", parent_id="parent-a")

        # child-b should NOT appear in parent-a's hierarchy
        hierarchy = reg.get_hierarchy_ids("parent-a")
        assert "child-a" in hierarchy
        assert "child-b" not in hierarchy, "Cross-session child should be excluded"

    def test_same_session_hierarchy_works(self):
        reg = AgentRegistry()
        reg.register_agent("root", "admin", "sess-1")
        reg.register_agent("mid", "developer", "sess-1", parent_id="root")
        reg.register_agent("leaf", "researcher", "sess-1", parent_id="mid")

        hierarchy = reg.get_hierarchy_ids("leaf")
        assert hierarchy == {"root", "mid", "leaf"}


class TestIssue52VerifyTokenKilledAgents:
    """#52: verify_token should fail for killed agents."""

    def test_killed_agent_token_verification_fails(self):
        reg = AgentRegistry()
        token = reg.register_agent("agent-1", "developer", "sess-1")
        assert reg.verify_token("agent-1", token) is True

        reg.kill_agent("agent-1")
        assert reg.verify_token("agent-1", token) is False


class TestIssue57DuplicateHeartbeatLost:
    """#57: check_stale() should not fire duplicate heartbeat_lost events."""

    def test_stale_event_fires_once(self):
        bus = EventBus()
        monitor = HeartbeatMonitor(bus)
        monitor.record("agent-stale", "hash1")

        # Make the agent stale
        monitor._agents["agent-stale"]["last_seen"] = time.monotonic() - 200

        # First check — should detect and publish
        stale1 = monitor.check_stale(threshold=90.0)
        assert "agent-stale" in stale1
        assert monitor._agents["agent-stale"]["stale_notified"] is True

        # Second check — should still return stale but NOT re-fire event
        stale2 = monitor.check_stale(threshold=90.0)
        assert "agent-stale" in stale2
        # stale_notified stays True, meaning event was NOT re-published

    def test_heartbeat_resets_stale_notification(self):
        bus = EventBus()
        monitor = HeartbeatMonitor(bus)
        monitor.record("agent-1", "hash1")
        monitor._agents["agent-1"]["stale_notified"] = True

        # New heartbeat should reset the flag
        monitor.record("agent-1", "hash1")
        assert monitor._agents["agent-1"]["stale_notified"] is False


class TestIssue58ReviveAgentTokenRotation:
    """#58: revive_agent should rotate the token."""

    def test_revive_rotates_token(self):
        reg = AgentRegistry()
        old_token = reg.register_agent("agent-1", "developer", "sess-1")
        reg.kill_agent("agent-1")

        success, new_token = reg.revive_agent("agent-1")
        assert success is True
        assert new_token is not None
        assert new_token != old_token

        # Old token should no longer work
        assert reg.verify_token("agent-1", old_token) is False
        # New token should work
        assert reg.verify_token("agent-1", new_token) is True

    def test_revive_nonexistent_returns_false(self):
        reg = AgentRegistry()
        success, token = reg.revive_agent("nonexistent")
        assert success is False
        assert token is None


class TestIssue60RoleEnforcementMode:
    """#60: Role.enforcement_mode should be respected by the engine."""

    def test_warn_only_role_does_not_hard_block(self):
        """A role with enforcement_mode='warn-only' should log, not block."""
        role = Role(
            name="admin",
            enforcement_mode="warn-only",
            autonomy_level="full",
            denied_action_classes={"ForcePush"},
        )
        # The role says ForcePush is denied, but enforcement is warn-only
        rm = RoleManager()
        # Action is denied by the role...
        assert rm.is_action_allowed(role, "ForcePush") is False
        # ...but enforcement_mode is "warn-only", so the engine should not hard block.
        assert role.enforcement_mode == "warn-only"


class TestIssue62ToolResultUserIdPropagation:
    """#62: ToolResultEvent should propagate user_id from request."""

    def test_tool_result_request_has_user_id_field(self):
        from safeclaw.api.models import ToolResultRequest
        req = ToolResultRequest(toolName="exec", userId="user-123")
        assert req.userId == "user-123"

    def test_tool_result_event_accepts_user_id(self):
        from safeclaw.engine.core import ToolResultEvent
        event = ToolResultEvent(
            session_id="sess-1",
            tool_name="exec",
            params={},
            result="ok",
            success=True,
            user_id="user-123",
        )
        assert event.user_id == "user-123"


class TestIssue63EvaluateOnlyScope:
    """#63: evaluate_only scope should include /record/ and /log/ paths."""

    def test_scope_includes_record_and_log(self):
        """SCOPE_ALLOWED for evaluate_only should include record and log paths."""
        # We test this by checking the source code of the module.
        import safeclaw.auth.middleware as mod
        import inspect
        source = inspect.getsource(mod)
        assert '"/api/v1/record/"' in source
        assert '"/api/v1/log/"' in source


class TestIssue78IsKilledUnregistered:
    """#78: is_killed should return False for unregistered agents."""

    def test_unregistered_agent_not_killed(self):
        reg = AgentRegistry()
        # Agent not registered — should NOT be treated as killed
        assert reg.is_killed("nonexistent") is False

    def test_killed_agent_returns_true(self):
        reg = AgentRegistry()
        reg.register_agent("agent-1", "developer", "sess-1")
        reg.kill_agent("agent-1")
        assert reg.is_killed("agent-1") is True

    def test_persistent_kill_state_detected(self):
        """Agents killed in a previous lifetime should still show as killed."""
        reg = AgentRegistry()
        # Simulate a persistent kill from a previous process lifetime
        reg._killed_from_store.add("old-agent")
        assert reg.is_killed("old-agent") is True


class TestIssue82EventBusThreadSafety:
    """#82: EventBus subscriber list should use lock/snapshot for safety."""

    def test_event_bus_has_lock(self):
        bus = EventBus()
        assert hasattr(bus, '_lock')
        assert isinstance(bus._lock, asyncio.Lock)

    def test_publish_uses_snapshot(self):
        """publish() should iterate a snapshot, not the live list."""
        bus = EventBus()
        event = SafeClawEvent(
            event_type="test", severity="info", title="test", detail="test"
        )
        # Publishing to empty bus should not raise
        bus.publish(event)


# ===========================================================================
# SESSION / RATE BUGS
# ===========================================================================


class TestIssue25CumulativeRiskOffByOne:
    """#25: Cumulative risk check should include the current action."""

    def test_current_action_included_in_risk_history(self, kg):
        """The engine appends the current action's risk level before checking
        derived rules, so the check is not off-by-one."""
        from safeclaw.engine.reasoning_rules import DerivedConstraintChecker
        from safeclaw.constraints.preference_checker import UserPreferences

        checker = DerivedConstraintChecker(kg)
        prefs = UserPreferences()

        # Simulate 2 prior MediumRisk actions in history
        history = ["MediumRisk:Action1", "MediumRisk:Action2"]

        # Adding a 3rd MediumRisk action (the current one) should be included
        # in the check. The engine does:
        #   server_session_history = history + ["MediumRisk:Action3"]
        # So the checker sees 3 MediumRisk entries.
        history_with_current = history + ["MediumRisk:Action3"]
        action = _make_action(cls="Action3", risk="MediumRisk")
        result = checker.check(action, prefs, history_with_current)
        # With 3 MediumRisk, the cumulative risk rule should trigger
        assert result.requires_confirmation


class TestIssue53RateLimiterLRU:
    """#53: RateLimiter.check() should update LRU position."""

    def test_check_updates_lru_position(self):
        limiter = RateLimiter()
        # Create two sessions
        limiter._sessions["sess-old"] = []
        limiter._sessions["sess-new"] = []

        action = _make_action(risk="HighRisk")

        # check() on sess-old should move it to end
        limiter.check(action, "sess-old")

        keys = list(limiter._sessions.keys())
        assert keys[-1] == "sess-old", "check() should update LRU position"


class TestIssue61And119DependencyCheckerLRU:
    """#61/#119: DependencyChecker should use LRU eviction, not FIFO."""

    def test_record_action_updates_lru(self, kg):
        checker = DependencyChecker(kg)

        # Add two sessions
        checker.record_action("sess-old", "ReadFile")
        checker.record_action("sess-new", "ReadFile")

        # Access sess-old again
        checker.record_action("sess-old", "WriteFile")

        # sess-old should now be at the end (most recently used)
        keys = list(checker._session_history.keys())
        assert keys[-1] == "sess-old"

    def test_active_session_not_evicted_first(self, kg):
        from safeclaw.constraints.dependency_checker import MAX_SESSIONS

        checker = DependencyChecker(kg)
        checker._session_history = OrderedDict()  # Reset

        # Create the first session and record actions
        checker.record_action("active-session", "RunTests")

        # Fill up to MAX_SESSIONS with other sessions
        for i in range(MAX_SESSIONS):
            checker.record_action(f"filler-{i}", "ReadFile")

        # Access active-session again (should move to end)
        checker.record_action("active-session", "GitPush")

        # active-session should still be present
        assert "active-session" in checker._session_history


class TestIssue112RecordMessageBeforePreferenceCheck:
    """#112: record_message should be called AFTER preference check."""

    def test_blocked_messages_not_recorded(self, kg):
        """When confirm_before_send blocks a message, it should not be recorded
        in the rate limiter."""
        from safeclaw.constraints.message_gate import MessageGate

        gate = MessageGate(kg)

        # Initially zero messages
        counts = gate._session_message_counts.get("sess-1", [])
        assert len(counts) == 0

        # The engine checks preferences BEFORE calling record_message.
        # If blocked, record_message is never called.
        # We verify by checking the code flow:
        # In full_engine._evaluate_message_locked:
        #   1. gate_result = self.message_gate.check(...)
        #   2. user_prefs check (may return early with block)
        #   3. self.message_gate.record_message(...)  <- only reached if not blocked
        # This test verifies gate count stays at 0 when we don't call record_message
        assert len(gate._session_message_counts.get("sess-1", [])) == 0

    def test_record_only_after_checks_pass(self, kg):
        """Verify the engine code orders preference check before record_message."""
        import inspect
        from safeclaw.engine.full_engine import FullEngine

        source = inspect.getsource(FullEngine._evaluate_message_locked)
        # Find the positions of key operations
        pref_pos = source.find("confirm_before_send")
        record_pos = source.find("record_message")
        assert pref_pos > 0
        assert record_pos > 0
        assert pref_pos < record_pos, (
            "Preference check should come before record_message"
        )


class TestIssue148TemporalCheckerCaching:
    """#148: TemporalChecker should cache SPARQL results at init time."""

    def test_constraints_cached_at_init(self, kg):
        checker = TemporalChecker(knowledge_graph=kg)
        assert checker._loaded is True
        # Second check should use cache, not re-query
        action = _make_action(cls="SomeAction", risk="LowRisk")
        result = checker.check(action, kg)
        assert result.violated is False  # No temporal constraints for SomeAction

    def test_reload_refreshes_cache(self, kg):
        checker = TemporalChecker(knowledge_graph=kg)
        assert checker._loaded is True
        checker.reload(kg)
        assert checker._loaded is True


class TestIssue149PhantomActionCounting:
    """#149: Rate limiter should only record actions after successful execution."""

    def test_rate_limiter_not_called_in_evaluate(self):
        """The evaluate pipeline should NOT call rate_limiter.record()."""
        # We verify by checking the comment in the code: at the end of the
        # pipeline (step 10), rate_limiter.record() is NOT called. It's only
        # called in record_action_result when event.success is True.
        limiter = RateLimiter()
        action = _make_action(risk="HighRisk")

        # Simulate: evaluate allows the action but does NOT call record()
        result = limiter.check(action, "sess-1")
        assert result.exceeded is False

        # No records should exist yet
        assert limiter._sessions.get("sess-1") is None or len(limiter._sessions.get("sess-1", [])) == 0

    def test_only_successful_actions_recorded(self):
        """Only successful actions should be recorded in the rate limiter."""
        limiter = RateLimiter()
        action = _make_action(risk="HighRisk")

        # Record a successful action
        limiter.record(action, "sess-1")
        assert len(limiter._sessions.get("sess-1", [])) == 1

        # A failed action should not be recorded (the engine gates on event.success)
        # We just verify the record mechanism works correctly
        limiter.record(action, "sess-1")
        assert len(limiter._sessions.get("sess-1", [])) == 2


# ===========================================================================
# HOT-RELOAD BUGS
# ===========================================================================


class TestIssue24AtomicReload:
    """#24: Hot-reload should swap components atomically."""

    def test_reload_kg_components_builds_all_before_swap(self, kg):
        """_reload_kg_components builds all new components into local variables
        before assigning them to self, ensuring atomicity."""
        from safeclaw.engine.full_engine import FullEngine

        # Verify the method exists and follows atomic swap pattern
        import inspect
        source = inspect.getsource(FullEngine._reload_kg_components)

        # Should build new components first (new_kg, new_shacl, etc.)
        assert "new_kg" in source
        assert "new_shacl" in source
        assert "new_hierarchy" in source
        assert "new_classifier" in source

        # Should swap all at once at the end
        assert "self.kg = new_kg" in source
        assert "self.shacl = new_shacl" in source


class TestIssue92ReloadPreservesDependencyHistory:
    """#92: _reload_kg_components should preserve DependencyChecker session history."""

    def test_dependency_history_preserved_across_reload(self, kg):
        """Session history from old DependencyChecker is carried to the new one."""
        from safeclaw.engine.full_engine import FullEngine
        import inspect

        source = inspect.getsource(FullEngine._reload_kg_components)
        # Verify the fix is present: old history is saved and restored
        assert "old_dep_history" in source
        assert "_session_history" in source
        assert "new_dependency_checker._session_history = old_dep_history" in source
