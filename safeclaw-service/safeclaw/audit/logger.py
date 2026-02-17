"""Audit logger - append-only JSONL writer with daily rotation."""

import json
import logging
import threading
from datetime import date
from pathlib import Path

from safeclaw.audit.models import DecisionRecord

logger = logging.getLogger("safeclaw.audit")


class AuditLogger:
    """Thread-safe, append-only JSONL audit logger."""

    def __init__(self, audit_dir: Path):
        self.audit_dir = audit_dir
        self._lock = threading.Lock()

    def _get_session_file(self, session_id: str) -> Path:
        today = date.today().isoformat()
        day_dir = self.audit_dir / today
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir / f"session-{session_id}.jsonl"

    def log(self, record: DecisionRecord) -> None:
        filepath = self._get_session_file(record.session_id)
        line = record.model_dump_json() + "\n"

        with self._lock:
            with open(filepath, "a") as f:
                f.write(line)

        log_msg = f"[{record.decision}] {record.action.tool_name} → {record.action.ontology_class}"
        if record.decision == "blocked":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

    def get_session_records(self, session_id: str) -> list[DecisionRecord]:
        records = []
        for day_dir in sorted(self.audit_dir.iterdir()):
            if not day_dir.is_dir():
                continue
            session_file = day_dir / f"session-{session_id}.jsonl"
            if session_file.exists():
                with open(session_file) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            records.append(DecisionRecord.model_validate_json(line))
        return records

    def get_recent_records(self, limit: int = 20) -> list[DecisionRecord]:
        records = []
        for day_dir in sorted(self.audit_dir.iterdir(), reverse=True):
            if not day_dir.is_dir():
                continue
            for session_file in sorted(day_dir.glob("session-*.jsonl"), reverse=True):
                with open(session_file) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            records.append(DecisionRecord.model_validate_json(line))
                            if len(records) >= limit:
                                return records
        return records

    def get_blocked_records(self, limit: int = 20) -> list[DecisionRecord]:
        return [r for r in self.get_recent_records(limit * 3) if r.decision == "blocked"][:limit]
