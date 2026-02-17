"""Tests for the audit system."""

from pathlib import Path

from safeclaw.audit.logger import AuditLogger
from safeclaw.audit.models import (
    ActionDetail,
    ConstraintCheck,
    DecisionRecord,
    Justification,
)


def test_audit_logger_writes_jsonl(tmp_path):
    logger = AuditLogger(tmp_path)
    record = DecisionRecord(
        session_id="test-session",
        user_id="test-user",
        action=ActionDetail(
            tool_name="exec",
            params={"command": "ls"},
            ontology_class="ExecuteCommand",
            risk_level="HighRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
        ),
        decision="allowed",
        justification=Justification(
            constraints_checked=[
                ConstraintCheck(
                    constraint_uri="shacl:validation",
                    constraint_type="SHACL",
                    result="satisfied",
                    reason="All shapes conform",
                )
            ],
            elapsed_ms=5.2,
        ),
    )
    logger.log(record)

    records = logger.get_session_records("test-session")
    assert len(records) == 1
    assert records[0].action.tool_name == "exec"
    assert records[0].decision == "allowed"


def test_audit_logger_multiple_records(tmp_path):
    logger = AuditLogger(tmp_path)
    for i in range(5):
        record = DecisionRecord(
            session_id="multi-test",
            user_id="user",
            action=ActionDetail(
                tool_name="read",
                params={"file_path": f"/file{i}.py"},
                ontology_class="ReadFile",
                risk_level="LowRisk",
                is_reversible=True,
                affects_scope="LocalOnly",
            ),
            decision="allowed",
            justification=Justification(),
        )
        logger.log(record)

    records = logger.get_session_records("multi-test")
    assert len(records) == 5


def test_audit_logger_blocked_records(tmp_path):
    logger = AuditLogger(tmp_path)

    # Write some allowed and blocked records
    for decision in ["allowed", "blocked", "allowed", "blocked", "blocked"]:
        record = DecisionRecord(
            session_id="block-test",
            user_id="user",
            action=ActionDetail(
                tool_name="exec",
                params={"command": "test"},
                ontology_class="ExecuteCommand",
                risk_level="HighRisk",
                is_reversible=True,
                affects_scope="LocalOnly",
            ),
            decision=decision,
            justification=Justification(),
        )
        logger.log(record)

    blocked = logger.get_blocked_records(10)
    assert len(blocked) == 3
    assert all(r.decision == "blocked" for r in blocked)


def test_decision_record_serialization():
    record = DecisionRecord(
        session_id="ser-test",
        user_id="user",
        action=ActionDetail(
            tool_name="write",
            params={"file_path": "/test.py"},
            ontology_class="WriteFile",
            risk_level="MediumRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
        ),
        decision="allowed",
        justification=Justification(elapsed_ms=3.5),
    )
    json_str = record.model_dump_json()
    restored = DecisionRecord.model_validate_json(json_str)
    assert restored.session_id == "ser-test"
    assert restored.action.tool_name == "write"
