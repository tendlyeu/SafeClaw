"""SQLite-backed persistence for governance state.

Persists agent kills, rate-limit counters, and temporary permission grants
so that they survive service restarts. The in-memory data structures in
AgentRegistry, RateLimiter, and TempPermissionManager remain the fast path
for reads; this store acts as the durable backing layer.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PersistedKill:
    """A persisted agent kill record."""

    agent_id: str
    reason: str
    killed_at: float


@dataclass
class PersistedRateCounter:
    """A persisted rate-limit counter entry."""

    agent_id: str
    action: str
    window_key: str
    count: int


@dataclass
class PersistedTempPermission:
    """A persisted temporary permission grant."""

    id: str
    agent_id: str
    action_class: str
    task_id: str | None
    expires_at: float | None  # epoch time (not monotonic)
    granted_at: float  # epoch time


_SCHEMA_VERSION = 1

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_kills (
    agent_id   TEXT PRIMARY KEY,
    reason     TEXT NOT NULL DEFAULT '',
    killed_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS rate_counters (
    agent_id   TEXT NOT NULL,
    action     TEXT NOT NULL,
    window_key TEXT NOT NULL,
    count      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (agent_id, action, window_key)
);

CREATE TABLE IF NOT EXISTS temp_permissions (
    id            TEXT PRIMARY KEY,
    agent_id      TEXT NOT NULL,
    action_class  TEXT NOT NULL,
    task_id       TEXT,
    expires_at    REAL,
    granted_at    REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_temp_perm_agent
    ON temp_permissions(agent_id);
CREATE INDEX IF NOT EXISTS idx_temp_perm_expires
    ON temp_permissions(expires_at);
CREATE INDEX IF NOT EXISTS idx_rate_counters_agent
    ON rate_counters(agent_id);
"""


class StateStore:
    """SQLite-backed store for governance state that must survive restarts.

    Uses WAL mode for concurrent read performance and wraps all writes in
    transactions.  The store is designed to be used alongside the existing
    in-memory data structures -- it persists only the subset of state that
    is critical to preserve across restarts (kills, rate counters, temp
    permissions).
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables if they don't exist, and manage schema versioning."""
        self._conn.executescript(_CREATE_TABLES)

        row = self._conn.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()

        if row is None:
            self._conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (_SCHEMA_VERSION,),
            )
        else:
            stored_version = row["version"]
            if stored_version < _SCHEMA_VERSION:
                # Future migrations would go here
                self._conn.execute(
                    "UPDATE schema_version SET version = ?",
                    (_SCHEMA_VERSION,),
                )

    # ------------------------------------------------------------------
    # Agent kills
    # ------------------------------------------------------------------

    def save_agent_kill(self, agent_id: str, reason: str = "") -> None:
        """Record an agent kill. Idempotent -- overwrites existing entry."""
        now = time.time()
        self._conn.execute(
            """
            INSERT INTO agent_kills (agent_id, reason, killed_at)
            VALUES (?, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET reason=excluded.reason, killed_at=excluded.killed_at
            """,
            (agent_id, reason, now),
        )
        logger.debug("Persisted agent kill: %s", agent_id)

    def revive_agent(self, agent_id: str) -> bool:
        """Remove an agent kill record. Returns True if a row was deleted."""
        cursor = self._conn.execute(
            "DELETE FROM agent_kills WHERE agent_id = ?",
            (agent_id,),
        )
        revived = cursor.rowcount > 0
        if revived:
            logger.debug("Revived agent in store: %s", agent_id)
        return revived

    def is_agent_killed(self, agent_id: str) -> bool:
        """Check if an agent has a persisted kill record."""
        row = self._conn.execute(
            "SELECT 1 FROM agent_kills WHERE agent_id = ? LIMIT 1",
            (agent_id,),
        ).fetchone()
        return row is not None

    def get_all_killed_agents(self) -> list[PersistedKill]:
        """Return all persisted kill records."""
        rows = self._conn.execute("SELECT agent_id, reason, killed_at FROM agent_kills").fetchall()
        return [
            PersistedKill(
                agent_id=r["agent_id"],
                reason=r["reason"],
                killed_at=r["killed_at"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Rate counters
    # ------------------------------------------------------------------

    def increment_rate_counter(
        self, agent_id: str, action: str, window_key: str, amount: int = 1
    ) -> int:
        """Increment a rate counter and return the new count."""
        self._conn.execute(
            """
            INSERT INTO rate_counters (agent_id, action, window_key, count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(agent_id, action, window_key)
            DO UPDATE SET count = count + ?
            """,
            (agent_id, action, window_key, amount, amount),
        )
        row = self._conn.execute(
            "SELECT count FROM rate_counters WHERE agent_id = ? AND action = ? AND window_key = ?",
            (agent_id, action, window_key),
        ).fetchone()
        return row["count"] if row else amount

    def get_rate_counter(self, agent_id: str, action: str, window_key: str) -> int:
        """Get the current count for a rate counter. Returns 0 if not found."""
        row = self._conn.execute(
            "SELECT count FROM rate_counters WHERE agent_id = ? AND action = ? AND window_key = ?",
            (agent_id, action, window_key),
        ).fetchone()
        return row["count"] if row else 0

    def clear_rate_counters(self, agent_id: str | None = None) -> int:
        """Clear rate counters. If agent_id given, only clear that agent's.
        Returns number of rows deleted."""
        if agent_id:
            cursor = self._conn.execute("DELETE FROM rate_counters WHERE agent_id = ?", (agent_id,))
        else:
            cursor = self._conn.execute("DELETE FROM rate_counters")
        return cursor.rowcount

    def clear_expired_rate_counters(self, expired_window_keys: list[str]) -> int:
        """Remove rate counter rows for expired window keys."""
        if not expired_window_keys:
            return 0
        placeholders = ",".join("?" for _ in expired_window_keys)
        cursor = self._conn.execute(
            f"DELETE FROM rate_counters WHERE window_key IN ({placeholders})",
            expired_window_keys,
        )
        return cursor.rowcount

    # ------------------------------------------------------------------
    # Temporary permissions
    # ------------------------------------------------------------------

    def save_temp_permission(
        self,
        grant_id: str,
        agent_id: str,
        action_class: str,
        task_id: str | None = None,
        expires_at: float | None = None,
        granted_at: float | None = None,
    ) -> None:
        """Persist a temporary permission grant."""
        if granted_at is None:
            granted_at = time.time()
        self._conn.execute(
            """
            INSERT INTO temp_permissions (id, agent_id, action_class, task_id, expires_at, granted_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                agent_id=excluded.agent_id,
                action_class=excluded.action_class,
                task_id=excluded.task_id,
                expires_at=excluded.expires_at,
                granted_at=excluded.granted_at
            """,
            (grant_id, agent_id, action_class, task_id, expires_at, granted_at),
        )
        logger.debug("Persisted temp permission: %s for agent %s", grant_id, agent_id)

    def remove_temp_permission(self, grant_id: str) -> bool:
        """Remove a specific temp permission. Returns True if deleted."""
        cursor = self._conn.execute("DELETE FROM temp_permissions WHERE id = ?", (grant_id,))
        return cursor.rowcount > 0

    def remove_temp_permissions_for_task(self, task_id: str) -> int:
        """Remove all temp permissions for a given task. Returns count deleted."""
        cursor = self._conn.execute("DELETE FROM temp_permissions WHERE task_id = ?", (task_id,))
        return cursor.rowcount

    def get_active_temp_permissions(
        self, agent_id: str | None = None
    ) -> list[PersistedTempPermission]:
        """Get active (non-expired) temp permissions, optionally filtered by agent."""
        now = time.time()
        if agent_id:
            rows = self._conn.execute(
                """
                SELECT id, agent_id, action_class, task_id, expires_at, granted_at
                FROM temp_permissions
                WHERE agent_id = ? AND (expires_at IS NULL OR expires_at > ?)
                """,
                (agent_id, now),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT id, agent_id, action_class, task_id, expires_at, granted_at
                FROM temp_permissions
                WHERE expires_at IS NULL OR expires_at > ?
                """,
                (now,),
            ).fetchall()
        return [
            PersistedTempPermission(
                id=r["id"],
                agent_id=r["agent_id"],
                action_class=r["action_class"],
                task_id=r["task_id"],
                expires_at=r["expires_at"],
                granted_at=r["granted_at"],
            )
            for r in rows
        ]

    def cleanup_expired_temp_permissions(self) -> int:
        """Remove all expired temp permissions. Returns count removed."""
        now = time.time()
        cursor = self._conn.execute(
            "DELETE FROM temp_permissions WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (now,),
        )
        return cursor.rowcount

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]
            logger.debug("StateStore closed")

    def __del__(self) -> None:
        if getattr(self, "_conn", None) is not None:
            try:
                self._conn.close()
            except Exception:
                pass
