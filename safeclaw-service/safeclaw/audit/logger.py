"""Audit logger - append-only JSONL writer with daily rotation."""

import json
import logging
import re
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

    @staticmethod
    def _safe_id(session_id: str) -> str:
        return re.sub(r'[^a-zA-Z0-9_-]', '_', session_id)

    def _get_session_file(self, session_id: str) -> Path:
        today = date.today().isoformat()
        day_dir = self.audit_dir / today
        day_dir.mkdir(parents=True, exist_ok=True)
        safe_id = self._safe_id(session_id)
        return day_dir / f"session-{safe_id}.jsonl"

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
        safe_id = self._safe_id(session_id)
        for day_dir in sorted(self.audit_dir.iterdir()):
            if not day_dir.is_dir():
                continue
            session_file = day_dir / f"session-{safe_id}.jsonl"
            if session_file.exists():
                with open(session_file) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                records.append(DecisionRecord.model_validate_json(line))
                            except Exception as e:
                                logger.warning(f"Skipping malformed audit record: {e}")
        return records

    def get_recent_records(self, limit: int = 20) -> list[DecisionRecord]:
        records = []
        for day_dir in sorted(self.audit_dir.iterdir(), reverse=True):
            if not day_dir.is_dir():
                continue
            for session_file in sorted(day_dir.glob("session-*.jsonl"), reverse=True):
                with open(session_file) as f:
                    for line in reversed(f.readlines()):
                        line = line.strip()
                        if line:
                            try:
                                records.append(DecisionRecord.model_validate_json(line))
                            except Exception as e:
                                logger.warning(f"Skipping malformed audit record: {e}")
                            if len(records) >= limit:
                                records.sort(key=lambda r: r.timestamp, reverse=True)
                                return records
        records.sort(key=lambda r: r.timestamp, reverse=True)
        return records

    def get_blocked_records(self, limit: int = 20) -> list[DecisionRecord]:
        blocked = []
        batch_size = limit * 5
        offset = 0
        while len(blocked) < limit:
            batch = self.get_recent_records(batch_size + offset)
            for r in batch[offset:]:
                if r.decision == "blocked":
                    blocked.append(r)
                    if len(blocked) >= limit:
                        break
            if len(batch) < batch_size + offset:
                break  # All records exhausted
            offset = len(batch)
            batch_size = limit * 5
        return blocked[:limit]
