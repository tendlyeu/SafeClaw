import time
from unittest.mock import MagicMock

from safeclaw.engine.heartbeat_monitor import HeartbeatMonitor


def test_record_and_check_fresh():
    bus = MagicMock()
    monitor = HeartbeatMonitor(bus)
    monitor.record("agent-1", "hash-abc")
    stale = monitor.check_stale(threshold=90)
    assert len(stale) == 0


def test_check_stale_after_threshold():
    bus = MagicMock()
    monitor = HeartbeatMonitor(bus)
    monitor.record("agent-1", "hash-abc")
    # Manually backdate the timestamp
    monitor._agents["agent-1"]["last_seen"] = time.monotonic() - 100
    stale = monitor.check_stale(threshold=90)
    assert "agent-1" in stale
    # Verify event was published
    bus.publish.assert_called_once()
    event = bus.publish.call_args[0][0]
    assert event.severity == "critical"
    assert "agent-1" in event.title


def test_config_drift_detection():
    bus = MagicMock()
    monitor = HeartbeatMonitor(bus)
    monitor.record("agent-1", "hash-abc")
    assert monitor.check_config_drift("agent-1", "hash-abc") is False
    assert monitor.check_config_drift("agent-1", "hash-CHANGED") is True
    # Verify event was published for drift
    bus.publish.assert_called_once()
    event = bus.publish.call_args[0][0]
    assert "config" in event.title.lower()


def test_record_updates_timestamp(monkeypatch):
    bus = MagicMock()
    monitor = HeartbeatMonitor(bus)
    fake_time = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_time[0])
    monitor.record("agent-1", "hash-abc")
    t1 = monitor._agents["agent-1"]["last_seen"]
    fake_time[0] = 1001.0
    monitor.record("agent-1", "hash-abc")
    t2 = monitor._agents["agent-1"]["last_seen"]
    assert t2 > t1


def test_shutdown_removes_agent():
    bus = MagicMock()
    monitor = HeartbeatMonitor(bus)
    monitor.record("agent-1", "hash-abc")
    monitor.remove("agent-1")
    stale = monitor.check_stale(threshold=0)
    assert len(stale) == 0


def test_config_drift_fires_only_once():
    """Regression test for #141: config drift should not fire continuously.

    After a config hash change is detected, repeated heartbeats with the
    same new hash must NOT re-publish config_drift events.
    """
    bus = MagicMock()
    monitor = HeartbeatMonitor(bus)

    # Initial registration
    monitor.record("agent-1", config_hash="abc")
    monitor.check_config_drift("agent-1", "abc")  # no drift

    # Config changes — first drift fires
    monitor.record("agent-1", config_hash="xyz")
    assert monitor.check_config_drift("agent-1", "xyz") is True

    # Subsequent heartbeats with the same drifted hash — must NOT re-fire
    monitor.record("agent-1", config_hash="xyz")
    assert monitor.check_config_drift("agent-1", "xyz") is False

    monitor.record("agent-1", config_hash="xyz")
    assert monitor.check_config_drift("agent-1", "xyz") is False

    # Only one drift event should have been published
    drift_calls = [
        c
        for c in bus.publish.call_args_list
        if c[0][0].event_type == "config_drift"
    ]
    assert len(drift_calls) == 1


def test_config_drift_fires_again_after_revert_and_new_drift():
    """After the config reverts to the known hash and then drifts again,
    a new drift event should fire."""
    bus = MagicMock()
    monitor = HeartbeatMonitor(bus)

    monitor.record("agent-1", config_hash="abc")

    # First drift: abc -> xyz
    monitor.record("agent-1", config_hash="xyz")
    assert monitor.check_config_drift("agent-1", "xyz") is True

    # Revert: xyz -> xyz (still drifted, no re-fire)
    monitor.record("agent-1", config_hash="xyz")
    assert monitor.check_config_drift("agent-1", "xyz") is False

    # Hash stabilises back to "xyz" (last_known_hash == "xyz"), no drift
    # Now hash changes again: xyz -> pqr
    monitor.record("agent-1", config_hash="pqr")
    assert monitor.check_config_drift("agent-1", "pqr") is True

    # Should have exactly 2 drift events total
    drift_calls = [
        c
        for c in bus.publish.call_args_list
        if c[0][0].event_type == "config_drift"
    ]
    assert len(drift_calls) == 2


def test_config_drift_notified_resets_on_hash_match():
    """The drift_notified flag should reset when the hash returns to the
    last known value, so future genuine drifts are reported."""
    bus = MagicMock()
    monitor = HeartbeatMonitor(bus)

    monitor.record("agent-1", config_hash="abc")

    # Drift: abc -> xyz
    assert monitor.check_config_drift("agent-1", "xyz") is True
    assert monitor._agents["agent-1"]["drift_notified"] is True

    # Hash returns to "xyz" (matches last_known_hash now)
    assert monitor.check_config_drift("agent-1", "xyz") is False
    assert monitor._agents["agent-1"]["drift_notified"] is False


def test_config_drift_heartbeat_endpoint_flow():
    """Simulate the actual heartbeat endpoint flow: record() then
    check_config_drift() with the same hash, over many heartbeats."""
    bus = MagicMock()
    monitor = HeartbeatMonitor(bus)

    # 5 heartbeats with original config
    for _ in range(5):
        monitor.record("agent-1", "abc")
        monitor.check_config_drift("agent-1", "abc")

    # Config changes
    monitor.record("agent-1", "xyz")
    monitor.check_config_drift("agent-1", "xyz")

    # 10 more heartbeats with new config — no re-fires
    for _ in range(10):
        monitor.record("agent-1", "xyz")
        monitor.check_config_drift("agent-1", "xyz")

    drift_calls = [
        c
        for c in bus.publish.call_args_list
        if c[0][0].event_type == "config_drift"
    ]
    assert len(drift_calls) == 1, (
        f"Expected 1 drift event, got {len(drift_calls)}. "
        "Config drift is firing continuously (issue #141)."
    )
