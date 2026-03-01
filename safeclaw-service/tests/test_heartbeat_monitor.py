import time
from unittest.mock import MagicMock

import pytest

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


def test_record_updates_timestamp():
    bus = MagicMock()
    monitor = HeartbeatMonitor(bus)
    monitor.record("agent-1", "hash-abc")
    t1 = monitor._agents["agent-1"]["last_seen"]
    time.sleep(0.01)
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
