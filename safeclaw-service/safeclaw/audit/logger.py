"""Audit logger - append-only JSONL writer with daily rotation."""

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

    def get_session_records(
        self,
        session_id: str,
        since: date | None = None,
        until: date | None = None,
    ) -> list[DecisionRecord]:
        """Get all records for a session, optionally filtered by date range (R3-38)."""
        records = []
        safe_id = self._safe_id(session_id)
        if not self.audit_dir.exists():
            return records
        for day_dir in sorted(self.audit_dir.iterdir()):
            if not day_dir.is_dir():
                continue
            # Only iterate directories within the requested date range (R3-38)
            try:
                dir_date = date.fromisoformat(day_dir.name)
            except ValueError:
                continue
            if since and dir_date < since:
                continue
            if until and dir_date > until:
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
        """Get the most recent records across all sessions (R3-39).

        Collects all records from the most recent day directory, sorts globally
        by timestamp, then moves to older directories only if limit not met.
        """
        records: list[DecisionRecord] = []
        if not self.audit_dir.exists():
            return records
        for day_dir in sorted(self.audit_dir.iterdir(), reverse=True):
            if not day_dir.is_dir():
                continue
            # Validate directory name is a date
            try:
                date.fromisoformat(day_dir.name)
            except ValueError:
                continue
            day_records: list[DecisionRecord] = []
            for session_file in day_dir.glob("session-*.jsonl"):
                with open(session_file) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                day_records.append(DecisionRecord.model_validate_json(line))
                            except Exception as e:
                                logger.warning(f"Skipping malformed audit record: {e}")
            records.extend(day_records)
            if len(records) >= limit:
                break
        records.sort(key=lambda r: r.timestamp, reverse=True)
        return records[:limit]

    def get_blocked_records(self, limit: int = 20) -> list[DecisionRecord]:
        """Get blocked records efficiently by filtering at file-read level (R3-40)."""
        blocked: list[DecisionRecord] = []
        if not self.audit_dir.exists():
            return blocked
        for day_dir in sorted(self.audit_dir.iterdir(), reverse=True):
            if not day_dir.is_dir():
                continue
            try:
                date.fromisoformat(day_dir.name)
            except ValueError:
                continue
            for session_file in day_dir.glob("session-*.jsonl"):
                with open(session_file) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        # Quick string check before full parse
                        if '"blocked"' not in line:
                            continue
                        try:
                            record = DecisionRecord.model_validate_json(line)
                            if record.decision == "blocked":
                                blocked.append(record)
                        except Exception as e:
                            logger.warning(f"Skipping malformed audit record: {e}")
            if len(blocked) >= limit:
                break
        blocked.sort(key=lambda r: r.timestamp, reverse=True)
        return blocked[:limit]
