"""Audit logger - append-only JSONL writer with daily rotation."""

import hashlib
import json
import logging
import os
import re
import stat
import threading
from datetime import date, timedelta
from pathlib import Path

from safeclaw.audit.models import DecisionRecord

logger = logging.getLogger("safeclaw.audit")

# Permissions: owner read/write only (0o600 for files, 0o700 for dirs)
_DIR_MODE = 0o700
_FILE_MODE = 0o600

# Default retention: 90 days
DEFAULT_RETENTION_DAYS = 90


class AuditLogger:
    """Thread-safe, append-only JSONL audit logger with tamper detection."""

    def __init__(self, audit_dir: Path, retention_days: int = DEFAULT_RETENTION_DAYS):
        self.audit_dir = audit_dir
        self.retention_days = retention_days
        self._lock = threading.Lock()
        self._prev_hash: str | None = self._load_last_hash()
        self._rotate_logs()

    @staticmethod
    def _safe_id(session_id: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)

    def _ensure_dir(self, dir_path: Path) -> None:
        """Create directory with restricted permissions (owner-only)."""
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            # Set restrictive permissions on the directory and all parents up to audit_dir
            try:
                os.chmod(dir_path, _DIR_MODE)
            except OSError:
                pass
        elif not stat.S_IMODE(dir_path.stat().st_mode) & ~_DIR_MODE == 0:
            # Fix overly-permissive existing directory
            try:
                os.chmod(dir_path, _DIR_MODE)
            except OSError:
                pass

    def _load_last_hash(self) -> str | None:
        """Read the last hash from the most recent audit log file.

        This preserves the hash chain across service restarts by scanning
        day directories in reverse chronological order and reading the last
        line of the first session file found.
        """
        if not self.audit_dir.exists():
            return None
        try:
            for day_dir in sorted(self.audit_dir.iterdir(), reverse=True):
                if not day_dir.is_dir():
                    continue
                try:
                    date.fromisoformat(day_dir.name)
                except ValueError:
                    continue
                # Find the most recently modified session file in this day
                session_files = sorted(
                    day_dir.glob("session-*.jsonl"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                for session_file in session_files:
                    last_line = self._read_last_line(session_file)
                    if last_line:
                        try:
                            entry = json.loads(last_line)
                            if "_hash" in entry:
                                return entry["_hash"]
                        except (json.JSONDecodeError, KeyError):
                            continue
        except OSError as e:
            logger.warning(f"Could not load last audit hash: {e}")
        return None

    @staticmethod
    def _read_last_line(filepath: Path) -> str | None:
        """Read the last non-empty line from a file."""
        try:
            with open(filepath, "rb") as f:
                # Seek to end and walk backwards to find last newline
                f.seek(0, 2)
                size = f.tell()
                if size == 0:
                    return None
                # Read up to the last 8KB (more than enough for one JSONL line)
                read_size = min(size, 8192)
                f.seek(-read_size, 2)
                lines = f.read().decode("utf-8").strip().split("\n")
                for line in reversed(lines):
                    stripped = line.strip()
                    if stripped:
                        return stripped
        except OSError:
            pass
        return None

    def _rotate_logs(self) -> None:
        """Delete audit log directories older than retention_days."""
        if not self.audit_dir.exists():
            return
        cutoff = date.today() - timedelta(days=self.retention_days)
        try:
            for day_dir in list(self.audit_dir.iterdir()):
                if not day_dir.is_dir():
                    continue
                try:
                    dir_date = date.fromisoformat(day_dir.name)
                except ValueError:
                    continue
                if dir_date < cutoff:
                    # Remove all files in the directory, then the directory itself
                    try:
                        for f in day_dir.iterdir():
                            f.unlink()
                        day_dir.rmdir()
                        logger.info(f"Rotated old audit log directory: {day_dir.name}")
                    except OSError as e:
                        logger.warning(f"Failed to rotate audit directory {day_dir.name}: {e}")
        except OSError as e:
            logger.warning(f"Error during audit log rotation: {e}")

    def _get_session_file(self, session_id: str) -> Path:
        today = date.today().isoformat()
        day_dir = self.audit_dir / today
        self._ensure_dir(self.audit_dir)
        self._ensure_dir(day_dir)
        safe_id = self._safe_id(session_id)
        return day_dir / f"session-{safe_id}.jsonl"

    @staticmethod
    def _compute_hash(prev_hash: str | None, record_json: str) -> str:
        """Compute a SHA-256 hash chain entry: H(prev_hash || record_json)."""
        h = hashlib.sha256()
        h.update((prev_hash or "").encode("utf-8"))
        h.update(record_json.encode("utf-8"))
        return h.hexdigest()

    def log(self, record: DecisionRecord) -> None:
        record_json = record.model_dump_json()

        # Compute integrity hash chain
        record_hash = self._compute_hash(self._prev_hash, record_json)
        line = (
            f'{{"_hash":"{record_hash}","_prev_hash":"{self._prev_hash or ""}",{record_json[1:]}\n'
        )

        filepath = self._get_session_file(record.session_id)
        with self._lock:
            # Open file with restricted permissions (owner read/write only)
            fd = os.open(
                str(filepath),
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                _FILE_MODE,
            )
            try:
                os.write(fd, line.encode("utf-8"))
            finally:
                os.close(fd)
            self._prev_hash = record_hash

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
                with open(session_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                records.append(DecisionRecord.model_validate_json(line))
                            except Exception as e:
                                logger.warning(f"Skipping malformed audit record: {e}")
        return records

    def get_record_by_id(self, record_id: str) -> DecisionRecord | None:
        """Look up a single record by its ID across all session files."""
        if not self.audit_dir.exists():
            return None
        for day_dir in sorted(self.audit_dir.iterdir(), reverse=True):
            if not day_dir.is_dir():
                continue
            try:
                date.fromisoformat(day_dir.name)
            except ValueError:
                continue
            for session_file in day_dir.glob("session-*.jsonl"):
                with open(session_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        if f'"id":"{record_id}"' not in line and f'"id": "{record_id}"' not in line:
                            continue
                        try:
                            record = DecisionRecord.model_validate_json(line)
                            if record.id == record_id:
                                return record
                        except Exception as e:
                            logger.warning(f"Skipping malformed audit record: {e}")
        return None

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
                with open(session_file, encoding="utf-8") as f:
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
                with open(session_file, encoding="utf-8") as f:
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
