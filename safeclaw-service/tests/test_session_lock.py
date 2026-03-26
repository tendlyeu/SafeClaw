"""Tests for session lock race condition (issue #131).

Validates that:
1. The meta-lock guards concurrent lock creation (primary race fix)
2. Eviction does not remove locks that are in use or have outstanding references
"""

import asyncio
from pathlib import Path

import pytest

from safeclaw.config import SafeClawConfig
from safeclaw.engine.full_engine import FullEngine


@pytest.fixture
def engine(tmp_path):
    """Create a test engine with ontologies from the project."""
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
    )
    return FullEngine(config)


async def test_concurrent_get_session_lock_returns_same_lock(engine):
    """Two concurrent calls for the same session must return the same lock object.

    This verifies the primary race condition fix: the meta-lock ensures that
    only one asyncio.Lock is created per session, even under concurrent access.
    """
    results = await asyncio.gather(
        engine._get_session_lock("session-1"),
        engine._get_session_lock("session-1"),
    )
    lock_a, lock_b = results
    assert lock_a is lock_b, (
        "Concurrent _get_session_lock calls for the same session returned different lock objects"
    )
    # Clean up ref counts
    await engine._release_session_lock_ref("session-1")
    await engine._release_session_lock_ref("session-1")


async def test_eviction_does_not_remove_in_use_lock(engine):
    """When capacity is 1, acquiring lock1 then requesting lock2 must not evict lock1.

    Scenario: set max_session_locks=1, get lock for session-A, hold it (via the
    context manager), then request a lock for session-B. The eviction triggered by
    session-B's creation must NOT evict session-A's lock because it is in use.
    After session-A is released, eviction should be able to reclaim it.
    """
    engine._max_session_locks = 1

    # Phase 1: acquire session-A's lock and hold it
    lock_a = await engine._get_session_lock("session-A")

    async with lock_a:
        # session-A lock is actively held (locked() == True)
        # Now request session-B which triggers eviction
        lock_b = await engine._get_session_lock("session-B")

        # session-A must still be in the dict (not evicted while held)
        assert "session-A" in engine._session_locks, (
            "session-A was evicted while its lock was actively held"
        )
        # Both locks should exist
        assert "session-B" in engine._session_locks
        # They must be different objects
        assert lock_a is not lock_b

    # Clean up refs
    await engine._release_session_lock_ref("session-A")
    await engine._release_session_lock_ref("session-B")


async def test_eviction_does_not_remove_referenced_but_unacquired_lock(engine):
    """A lock with outstanding references must not be evicted even if not locked().

    This tests the critical edge case: a caller has obtained a lock reference
    via _get_session_lock but has not yet entered `async with lock:`. The lock's
    locked() returns False, but eviction must still skip it because the ref
    count is > 0.
    """
    engine._max_session_locks = 1

    # Get lock for session-A but do NOT acquire it (simulating the window between
    # _get_session_lock returning and the caller entering async with lock)
    lock_a = await engine._get_session_lock("session-A")
    assert not lock_a.locked(), "Lock should not be acquired yet"

    # Ref count for session-A should be 1
    assert engine._session_lock_refs.get("session-A", 0) == 1

    # Now request session-B, which triggers eviction (capacity is 1, we have 1 + new = 2)
    lock_b = await engine._get_session_lock("session-B")

    # session-A must NOT have been evicted because it has refs > 0
    assert "session-A" in engine._session_locks, (
        "session-A was evicted while it had outstanding references (ref count > 0)"
    )
    assert engine._session_locks["session-A"] is lock_a

    # Both should be in the dict (capacity exceeded but nothing is evictable)
    assert "session-B" in engine._session_locks
    assert engine._session_locks["session-B"] is lock_b

    # Clean up refs
    await engine._release_session_lock_ref("session-A")
    await engine._release_session_lock_ref("session-B")


async def test_eviction_reclaims_unreferenced_locks(engine):
    """Locks with zero references and not locked should be evicted normally."""
    engine._max_session_locks = 1

    # Use session-A via the context manager so refs are properly managed
    async with engine._session_lock("session-A"):
        pass  # ref is decremented on exit

    # session-A should have no refs now
    assert engine._session_lock_refs.get("session-A", 0) == 0

    # Now create session-B, triggering eviction
    await engine._get_session_lock("session-B")

    # session-A should have been evicted (not locked, no refs)
    assert "session-A" not in engine._session_locks, (
        "session-A should have been evicted (no refs, not locked)"
    )
    assert "session-B" in engine._session_locks

    # Clean up
    await engine._release_session_lock_ref("session-B")


async def test_session_lock_context_manager_ref_counting(engine):
    """The _session_lock context manager properly increments and decrements refs."""
    assert engine._session_lock_refs.get("session-X", 0) == 0

    async with engine._session_lock("session-X"):
        # Inside the context, the lock is acquired and ref count is 1
        # (the ref was incremented in _get_session_lock, not yet decremented)
        assert engine._session_lock_refs.get("session-X", 0) == 1
        assert engine._session_locks["session-X"].locked()

    # After exiting, ref count should be 0
    assert engine._session_lock_refs.get("session-X", 0) == 0
    # Lock should no longer be held
    assert not engine._session_locks["session-X"].locked()


async def test_concurrent_session_lock_context_manager(engine):
    """Two concurrent _session_lock calls for the same session serialize properly."""
    order = []

    async def task(label, delay):
        async with engine._session_lock("session-serial"):
            order.append(f"{label}-enter")
            await asyncio.sleep(delay)
            order.append(f"{label}-exit")

    await asyncio.gather(task("A", 0.05), task("B", 0.01))

    # One task must fully complete before the other starts
    assert order[0].endswith("-enter")
    assert order[1].endswith("-exit")
    assert order[2].endswith("-enter")
    assert order[3].endswith("-exit")
    # The first to enter must be the first to exit
    first_label = order[0].split("-")[0]
    assert order[1] == f"{first_label}-exit"


async def test_eviction_with_multiple_concurrent_refs(engine):
    """Multiple concurrent references to the same session prevent eviction."""
    engine._max_session_locks = 1

    # Get two references to session-A (simulating two concurrent callers)
    lock_a1 = await engine._get_session_lock("session-A")
    lock_a2 = await engine._get_session_lock("session-A")
    assert lock_a1 is lock_a2

    # Ref count should be 2
    assert engine._session_lock_refs.get("session-A", 0) == 2

    # Release one reference
    await engine._release_session_lock_ref("session-A")
    assert engine._session_lock_refs.get("session-A", 0) == 1

    # Request session-B, triggering eviction
    await engine._get_session_lock("session-B")

    # session-A must not be evicted (still has ref count 1)
    assert "session-A" in engine._session_locks

    # Release the last session-A reference
    await engine._release_session_lock_ref("session-A")
    assert engine._session_lock_refs.get("session-A", 0) == 0

    # Now request session-C, triggering eviction again
    await engine._get_session_lock("session-C")

    # session-A should now be evictable (no refs, not locked)
    # But since max is 1 and we have session-A, session-B, session-C (3 entries),
    # eviction should remove session-A first (oldest), then session-B
    # (session-B has ref=1 so it won't be evicted, leaving us at 2)
    assert "session-A" not in engine._session_locks, (
        "session-A should have been evicted after all refs were released"
    )

    # Clean up
    await engine._release_session_lock_ref("session-B")
    await engine._release_session_lock_ref("session-C")
