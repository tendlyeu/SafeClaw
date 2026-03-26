"""Tests for SQLite-backed StateStore governance persistence.

Covers: agent kill persistence, agent revive persistence,
rate-limit counter persistence, temporary permission persistence
(including expiry), and store lifecycle (close/reopen).
"""

import time
from pathlib import Path

import pytest

from safeclaw.engine.state_store import StateStore


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Return a temporary path for the SQLite database."""
    return tmp_path / "governance_state.db"


@pytest.fixture()
def store(db_path: Path) -> StateStore:
    """Create a fresh StateStore, closing it after the test."""
    s = StateStore(db_path)
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Agent kills
# ---------------------------------------------------------------------------


class TestAgentKillPersistence:
    def test_agent_kill_persists(self, db_path: Path):
        """Kill an agent, close the store, reopen, and verify the kill survives."""
        store = StateStore(db_path)
        store.save_agent_kill("agent-1", reason="safety violation")
        assert store.is_agent_killed("agent-1") is True
        store.close()

        # Reopen and verify persistence
        store2 = StateStore(db_path)
        assert store2.is_agent_killed("agent-1") is True
        kills = store2.get_all_killed_agents()
        assert len(kills) == 1
        assert kills[0].agent_id == "agent-1"
        assert kills[0].reason == "safety violation"
        assert kills[0].killed_at > 0
        store2.close()

    def test_agent_revive_persists(self, db_path: Path):
        """Kill, then revive an agent. The revive should persist across restarts."""
        store = StateStore(db_path)
        store.save_agent_kill("agent-2", reason="rate limit abuse")
        assert store.is_agent_killed("agent-2") is True

        revived = store.revive_agent("agent-2")
        assert revived is True
        assert store.is_agent_killed("agent-2") is False
        store.close()

        # Reopen and verify the revive persisted
        store2 = StateStore(db_path)
        assert store2.is_agent_killed("agent-2") is False
        assert store2.get_all_killed_agents() == []
        store2.close()

    def test_revive_nonexistent_agent(self, store: StateStore):
        """Reviving an agent that was never killed returns False."""
        assert store.revive_agent("no-such-agent") is False

    def test_kill_is_idempotent(self, store: StateStore):
        """Killing the same agent twice does not raise; updates reason."""
        store.save_agent_kill("agent-3", reason="first reason")
        store.save_agent_kill("agent-3", reason="updated reason")
        kills = store.get_all_killed_agents()
        assert len(kills) == 1
        assert kills[0].reason == "updated reason"

    def test_unknown_agent_not_killed(self, store: StateStore):
        """An agent with no kill record is not considered killed."""
        assert store.is_agent_killed("unknown-agent") is False

    def test_multiple_agents_killed(self, store: StateStore):
        """Multiple different agents can be killed independently."""
        store.save_agent_kill("a1", reason="r1")
        store.save_agent_kill("a2", reason="r2")
        store.save_agent_kill("a3", reason="r3")
        assert store.is_agent_killed("a1") is True
        assert store.is_agent_killed("a2") is True
        assert store.is_agent_killed("a3") is True

        store.revive_agent("a2")
        assert store.is_agent_killed("a1") is True
        assert store.is_agent_killed("a2") is False
        assert store.is_agent_killed("a3") is True

        kills = store.get_all_killed_agents()
        assert len(kills) == 2
        agent_ids = {k.agent_id for k in kills}
        assert agent_ids == {"a1", "a3"}


# ---------------------------------------------------------------------------
# Rate counters
# ---------------------------------------------------------------------------


class TestRateCounterPersistence:
    def test_rate_limit_counter_persists(self, db_path: Path):
        """Increment a counter, close, reopen, and verify it survives."""
        store = StateStore(db_path)
        new_count = store.increment_rate_counter("agent-1", "HighRisk", "2026-03-26T14")
        assert new_count == 1

        new_count = store.increment_rate_counter("agent-1", "HighRisk", "2026-03-26T14")
        assert new_count == 2
        store.close()

        # Reopen and verify persistence
        store2 = StateStore(db_path)
        count = store2.get_rate_counter("agent-1", "HighRisk", "2026-03-26T14")
        assert count == 2
        store2.close()

    def test_counter_default_zero(self, store: StateStore):
        """A counter that hasn't been set returns 0."""
        assert store.get_rate_counter("no-agent", "NoAction", "no-key") == 0

    def test_increment_by_amount(self, store: StateStore):
        """Incrementing by a custom amount works correctly."""
        count = store.increment_rate_counter("a1", "CriticalRisk", "w1", amount=5)
        assert count == 5
        count = store.increment_rate_counter("a1", "CriticalRisk", "w1", amount=3)
        assert count == 8

    def test_clear_rate_counters_by_agent(self, store: StateStore):
        """Clearing by agent_id only removes that agent's counters."""
        store.increment_rate_counter("a1", "HighRisk", "w1")
        store.increment_rate_counter("a2", "HighRisk", "w1")

        deleted = store.clear_rate_counters(agent_id="a1")
        assert deleted == 1
        assert store.get_rate_counter("a1", "HighRisk", "w1") == 0
        assert store.get_rate_counter("a2", "HighRisk", "w1") == 1

    def test_clear_all_rate_counters(self, store: StateStore):
        """Clearing without agent_id removes all counters."""
        store.increment_rate_counter("a1", "HighRisk", "w1")
        store.increment_rate_counter("a2", "CriticalRisk", "w2")

        deleted = store.clear_rate_counters()
        assert deleted == 2
        assert store.get_rate_counter("a1", "HighRisk", "w1") == 0
        assert store.get_rate_counter("a2", "CriticalRisk", "w2") == 0

    def test_clear_expired_window_keys(self, store: StateStore):
        """Expired window keys can be bulk-removed."""
        store.increment_rate_counter("a1", "HighRisk", "old-key")
        store.increment_rate_counter("a1", "HighRisk", "current-key")

        deleted = store.clear_expired_rate_counters(["old-key"])
        assert deleted == 1
        assert store.get_rate_counter("a1", "HighRisk", "old-key") == 0
        assert store.get_rate_counter("a1", "HighRisk", "current-key") == 1

    def test_clear_expired_empty_list(self, store: StateStore):
        """Clearing with an empty list does nothing."""
        store.increment_rate_counter("a1", "HighRisk", "w1")
        deleted = store.clear_expired_rate_counters([])
        assert deleted == 0
        assert store.get_rate_counter("a1", "HighRisk", "w1") == 1

    def test_different_actions_same_agent(self, store: StateStore):
        """Different action types for the same agent are tracked independently."""
        store.increment_rate_counter("a1", "HighRisk", "w1", amount=3)
        store.increment_rate_counter("a1", "CriticalRisk", "w1", amount=1)

        assert store.get_rate_counter("a1", "HighRisk", "w1") == 3
        assert store.get_rate_counter("a1", "CriticalRisk", "w1") == 1


# ---------------------------------------------------------------------------
# Temporary permissions
# ---------------------------------------------------------------------------


class TestTempPermissionPersistence:
    def test_temp_permission_persists(self, db_path: Path):
        """Save a temp permission, close, reopen, verify it survives."""
        future_time = time.time() + 3600  # 1 hour from now

        store = StateStore(db_path)
        store.save_temp_permission(
            grant_id="grant-1",
            agent_id="agent-1",
            action_class="FileWrite",
            task_id="task-42",
            expires_at=future_time,
        )
        store.close()

        store2 = StateStore(db_path)
        perms = store2.get_active_temp_permissions(agent_id="agent-1")
        assert len(perms) == 1
        assert perms[0].id == "grant-1"
        assert perms[0].agent_id == "agent-1"
        assert perms[0].action_class == "FileWrite"
        assert perms[0].task_id == "task-42"
        assert perms[0].expires_at == pytest.approx(future_time, abs=1)
        store2.close()

    def test_expired_permission_not_returned(self, store: StateStore):
        """Permissions with expires_at in the past are not returned as active."""
        past_time = time.time() - 10  # 10 seconds ago

        store.save_temp_permission(
            grant_id="expired-grant",
            agent_id="agent-1",
            action_class="FileWrite",
            expires_at=past_time,
        )

        perms = store.get_active_temp_permissions(agent_id="agent-1")
        assert len(perms) == 0

    def test_no_expiry_permission_persists(self, db_path: Path):
        """Permissions with no expiry (task-scoped only) persist and remain active."""
        store = StateStore(db_path)
        store.save_temp_permission(
            grant_id="no-expiry",
            agent_id="agent-1",
            action_class="GitPush",
            task_id="task-99",
            expires_at=None,
        )
        store.close()

        store2 = StateStore(db_path)
        perms = store2.get_active_temp_permissions(agent_id="agent-1")
        assert len(perms) == 1
        assert perms[0].expires_at is None
        assert perms[0].task_id == "task-99"
        store2.close()

    def test_remove_temp_permission(self, store: StateStore):
        """Removing a specific permission works."""
        store.save_temp_permission(
            grant_id="g1",
            agent_id="a1",
            action_class="FileWrite",
            expires_at=time.time() + 3600,
        )
        assert store.remove_temp_permission("g1") is True
        assert store.get_active_temp_permissions(agent_id="a1") == []

    def test_remove_nonexistent_permission(self, store: StateStore):
        """Removing a grant that doesn't exist returns False."""
        assert store.remove_temp_permission("no-such-grant") is False

    def test_remove_permissions_for_task(self, store: StateStore):
        """All permissions for a task are removed together."""
        future = time.time() + 3600
        store.save_temp_permission("g1", "a1", "FileWrite", task_id="task-1", expires_at=future)
        store.save_temp_permission("g2", "a1", "GitPush", task_id="task-1", expires_at=future)
        store.save_temp_permission("g3", "a2", "FileRead", task_id="task-2", expires_at=future)

        removed = store.remove_temp_permissions_for_task("task-1")
        assert removed == 2

        # task-2 permission still exists
        perms = store.get_active_temp_permissions()
        assert len(perms) == 1
        assert perms[0].task_id == "task-2"

    def test_cleanup_expired(self, store: StateStore):
        """Cleanup removes expired, leaves active."""
        past = time.time() - 10
        future = time.time() + 3600

        store.save_temp_permission("expired", "a1", "Act1", expires_at=past)
        store.save_temp_permission("active", "a1", "Act2", expires_at=future)

        removed = store.cleanup_expired_temp_permissions()
        assert removed == 1
        perms = store.get_active_temp_permissions()
        assert len(perms) == 1
        assert perms[0].id == "active"

    def test_get_all_active_permissions(self, store: StateStore):
        """get_active_temp_permissions without agent_id returns all active."""
        future = time.time() + 3600
        store.save_temp_permission("g1", "a1", "Act1", expires_at=future)
        store.save_temp_permission("g2", "a2", "Act2", expires_at=future)

        perms = store.get_active_temp_permissions()
        assert len(perms) == 2

    def test_filter_by_agent(self, store: StateStore):
        """get_active_temp_permissions filters correctly by agent."""
        future = time.time() + 3600
        store.save_temp_permission("g1", "a1", "Act1", expires_at=future)
        store.save_temp_permission("g2", "a2", "Act2", expires_at=future)

        perms = store.get_active_temp_permissions(agent_id="a1")
        assert len(perms) == 1
        assert perms[0].agent_id == "a1"


# ---------------------------------------------------------------------------
# Store lifecycle
# ---------------------------------------------------------------------------


class TestStoreLifecycle:
    def test_close_and_reopen(self, db_path: Path):
        """Closing and reopening the store preserves all data."""
        store = StateStore(db_path)
        store.save_agent_kill("killed-agent", "test")
        store.increment_rate_counter("a1", "HighRisk", "w1", amount=5)
        store.save_temp_permission(
            "perm-1",
            "a1",
            "FileWrite",
            expires_at=time.time() + 3600,
        )
        store.close()

        store2 = StateStore(db_path)
        assert store2.is_agent_killed("killed-agent") is True
        assert store2.get_rate_counter("a1", "HighRisk", "w1") == 5
        perms = store2.get_active_temp_permissions(agent_id="a1")
        assert len(perms) == 1
        store2.close()

    def test_parent_directory_created(self, tmp_path: Path):
        """StateStore creates parent directories if they don't exist."""
        deep_path = tmp_path / "nested" / "dirs" / "state.db"
        store = StateStore(deep_path)
        store.save_agent_kill("test", "creation test")
        assert store.is_agent_killed("test") is True
        store.close()

    def test_wal_mode_enabled(self, db_path: Path):
        """Verify WAL journal mode is active."""
        store = StateStore(db_path)
        row = store._conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal"
        store.close()

    def test_schema_version_recorded(self, db_path: Path):
        """The schema_version table has the expected version."""
        store = StateStore(db_path)
        row = store._conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        assert row["version"] == 1
        store.close()
