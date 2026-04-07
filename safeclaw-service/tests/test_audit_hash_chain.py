"""Regression tests for audit hash chain persistence across restarts (#134).

Verifies that the hash chain continues correctly when a new AuditLogger
instance is created from the same audit directory, preventing hash chain
resets on service restart.
"""

import json

from safeclaw.audit.logger import AuditLogger
from safeclaw.audit.models import (
    ActionDetail,
    DecisionRecord,
    Justification,
)


def _make_record(session_id: str = "chain-test", decision: str = "allowed") -> DecisionRecord:
    return DecisionRecord(
        session_id=session_id,
        user_id="test-user",
        action=ActionDetail(
            tool_name="exec",
            params={"command": "ls"},
            ontology_class="ExecuteCommand",
            risk_level="HighRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
        ),
        decision=decision,
        justification=Justification(elapsed_ms=1.0),
    )


def test_hash_chain_continues_after_restart(tmp_path):
    """Hash chain must not reset when a new AuditLogger is created from the same dir.

    Simulates a service restart by:
    1. Creating an AuditLogger, logging a decision, recording _prev_hash.
    2. Deleting the logger (simulating shutdown).
    3. Creating a new AuditLogger from the same directory.
    4. Verifying _prev_hash matches the hash from step 1.
    5. Logging another record and verifying _prev_hash in the written JSONL
       references the hash from step 1 (not empty/None).
    """
    # Step 1: First logger instance - log a decision
    logger1 = AuditLogger(tmp_path)
    logger1.log(_make_record())
    hash_after_first_log = logger1._prev_hash
    assert hash_after_first_log is not None, "Hash should be set after logging"

    # Step 2: Destroy the first logger (simulates service shutdown)
    del logger1

    # Step 3: Create a new logger from the same directory (simulates restart)
    logger2 = AuditLogger(tmp_path)

    # Step 4: Verify hash chain continuity
    assert logger2._prev_hash == hash_after_first_log, (
        f"New logger should load previous hash from audit files. "
        f"Expected {hash_after_first_log!r}, got {logger2._prev_hash!r}"
    )

    # Step 5: Log another record and verify the chain links correctly
    logger2.log(_make_record())
    hash_after_second_log = logger2._prev_hash
    assert hash_after_second_log is not None
    assert (
        hash_after_second_log != hash_after_first_log
    ), "Second log entry should produce a different hash"

    # Verify the JSONL file contains correct _prev_hash references
    all_lines = []
    for day_dir in tmp_path.iterdir():
        for session_file in day_dir.glob("session-*.jsonl"):
            with open(session_file) as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        all_lines.append(json.loads(stripped))

    assert len(all_lines) == 2, f"Expected 2 audit entries, found {len(all_lines)}"

    # First entry should have empty _prev_hash (start of chain)
    assert all_lines[0]["_prev_hash"] == "", "First entry should have empty _prev_hash"
    assert all_lines[0]["_hash"] == hash_after_first_log

    # Second entry (written after restart) should chain to the first
    assert all_lines[1]["_prev_hash"] == hash_after_first_log, (
        "Second entry's _prev_hash should reference first entry's hash, "
        "proving the chain survived the restart"
    )
    assert all_lines[1]["_hash"] == hash_after_second_log


def test_hash_chain_starts_fresh_on_empty_dir(tmp_path):
    """When no prior audit logs exist, _prev_hash should start as None."""
    logger = AuditLogger(tmp_path)
    assert logger._prev_hash is None, "Fresh logger should have None _prev_hash"


def test_hash_chain_survives_multiple_restarts(tmp_path):
    """Hash chain should survive multiple restart cycles without breaking."""
    prev_hash = None

    for i in range(3):
        lgr = AuditLogger(tmp_path)
        assert (
            lgr._prev_hash == prev_hash
        ), f"Restart {i}: expected _prev_hash={prev_hash!r}, got {lgr._prev_hash!r}"
        lgr.log(_make_record(session_id=f"restart-{i}"))
        prev_hash = lgr._prev_hash
        del lgr

    # Final verification: all entries form a valid chain
    all_lines = []
    for day_dir in sorted(tmp_path.iterdir()):
        for session_file in sorted(day_dir.glob("session-*.jsonl")):
            with open(session_file) as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        all_lines.append(json.loads(stripped))

    assert len(all_lines) == 3
    # Verify chain integrity: each entry's _prev_hash matches the prior entry's _hash
    assert all_lines[0]["_prev_hash"] == ""
    for j in range(1, len(all_lines)):
        assert (
            all_lines[j]["_prev_hash"] == all_lines[j - 1]["_hash"]
        ), f"Entry {j}'s _prev_hash should match entry {j - 1}'s _hash"
