"""API key authentication for the remote SafeClaw service."""

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import bcrypt


@dataclass
class APIKey:
    """Represents an API key for authenticating agents."""

    key_id: str
    key_hash: str
    org_id: str
    scope: str = "full"  # "full" | "read_only" | "evaluate_only"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_active: bool = True


class APIKeyManager:
    """Manages API key creation, validation, and revocation.

    In production, this would be backed by a database (PostgreSQL).
    This in-memory implementation serves as the scaffold.
    """

    def __init__(self):
        self._keys: dict[str, APIKey] = {}

    @staticmethod
    def generate_key() -> tuple[str, str]:
        """Generate a new API key. Returns (raw_key, key_id)."""
        raw_key = "sc_" + secrets.token_urlsafe(32)
        key_id = raw_key[:12]
        return raw_key, key_id

    @staticmethod
    def hash_key(raw_key: str) -> str:
        """Hash an API key for storage using bcrypt."""
        return bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def verify_key(raw_key: str, hashed: str) -> bool:
        """Verify a raw API key against a stored hash.

        Supports bcrypt ($2b$ prefix) and falls back to SHA-256
        comparison for legacy hashes that haven't been migrated yet.
        """
        if hashed.startswith("$2b$"):
            return bcrypt.checkpw(raw_key.encode(), hashed.encode())
        # Legacy SHA-256 fallback for migration
        return hashlib.sha256(raw_key.encode()).hexdigest() == hashed

    def create_key(self, org_id: str, scope: str = "full") -> tuple[str, APIKey]:
        """Create a new API key for an organization. Returns (raw_key, api_key_record)."""
        raw_key, key_id = self.generate_key()
        key_hash = self.hash_key(raw_key)

        api_key = APIKey(
            key_id=key_id,
            key_hash=key_hash,
            org_id=org_id,
            scope=scope,
        )
        self._keys[key_id] = api_key
        return raw_key, api_key

    def validate_key(self, raw_key: str) -> APIKey | None:
        """Validate an API key and return the key record if valid."""
        key_id = raw_key[:12]
        api_key = self._keys.get(key_id)
        if not api_key or not api_key.is_active:
            return None

        if not self.verify_key(raw_key, api_key.key_hash):
            return None

        return api_key

    def revoke_key(self, key_id: str) -> bool:
        """Revoke an API key."""
        api_key = self._keys.get(key_id)
        if api_key:
            api_key.is_active = False
            return True
        return False

    def list_keys(self, org_id: str) -> list[APIKey]:
        """List all API keys for an organization."""
        return [k for k in self._keys.values() if k.org_id == org_id]


class SQLiteAPIKeyManager:
    """API key manager backed by a shared SQLite database.

    Reads from the same api_key table that the landing site writes to.
    Used in SaaS mode when db_path is configured.
    """

    def __init__(self, db_path: str, llm_config_cache_ttl: int = 60):
        import sqlite3

        self._db_path = db_path
        self._write_lock = threading.Lock()
        # TTL cache for user LLM configs to avoid DB round-trips on every call
        self._llm_config_cache: dict[str, tuple[dict | None, float]] = {}
        self._llm_config_cache_ttl = llm_config_cache_ttl
        # Keep a connection for writes (audit logging) but read operations
        # open fresh connections to always see the latest data from the
        # landing site's WAL writes.
        self._conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass  # Read-only DB — WAL not required for reads
        # Try to ensure tables exist (service may start before landing creates them).
        # If the DB is read-only (owned by another container), skip — landing will create them.
        try:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS api_key ("
                "  id INTEGER PRIMARY KEY,"
                "  user_id INTEGER,"
                "  key_id TEXT,"
                "  key_hash TEXT,"
                "  label TEXT,"
                "  scope TEXT,"
                "  created_at TEXT,"
                "  is_active BOOLEAN"
                ")"
            )
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS user ("
                "  id INTEGER PRIMARY KEY,"
                "  mistral_api_key TEXT DEFAULT '',"
                "  llm_config TEXT DEFAULT ''"
                ")"
            )
            try:
                self._conn.execute("ALTER TABLE user ADD COLUMN llm_config TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass  # Column already exists
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS audit_log ("
                "  id INTEGER PRIMARY KEY,"
                "  user_id INTEGER,"
                "  timestamp TEXT,"
                "  session_id TEXT,"
                "  tool_name TEXT,"
                "  params_summary TEXT,"
                "  decision TEXT,"
                "  risk_level TEXT,"
                "  reason TEXT,"
                "  elapsed_ms REAL"
                ")"
            )
        except sqlite3.OperationalError:
            pass  # Read-only — tables will exist once landing container starts

    def _fresh_conn(self):
        """Open a short-lived connection that sees the latest WAL data."""
        import sqlite3

        conn = sqlite3.connect(self._db_path, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def validate_key(self, raw_key: str) -> APIKey | None:
        """Validate an API key by looking it up in SQLite."""
        import sqlite3

        key_id = raw_key[:12]

        try:
            conn = self._fresh_conn()
            try:
                row = conn.execute(
                    "SELECT key_id, key_hash, scope, created_at, is_active, user_id "
                    "FROM api_key WHERE key_id = ? AND is_active = 1",
                    (key_id,),
                ).fetchone()
            finally:
                conn.close()
        except sqlite3.OperationalError:
            return None  # Table doesn't exist yet

        if row is None:
            return None

        db_key_id, db_key_hash, scope, created_at, is_active, user_id = row
        if not APIKeyManager.verify_key(raw_key, db_key_hash):
            return None

        return APIKey(
            key_id=db_key_id,
            key_hash=db_key_hash,
            org_id=str(user_id),
            scope=scope,
            created_at=created_at,
            is_active=bool(is_active),
        )

    def is_audit_logging_enabled(self, user_id: str) -> bool:
        """Check if a user has audit logging enabled. Defaults to True."""
        import sqlite3

        try:
            conn = self._fresh_conn()
            try:
                row = conn.execute(
                    "SELECT audit_logging FROM user WHERE id = ?",
                    (user_id,),
                ).fetchone()
            finally:
                conn.close()
        except sqlite3.OperationalError:
            return True  # Default: enabled
        if row is None:
            return True  # Unknown user: default enabled
        return bool(row[0])

    def log_audit_decision(
        self,
        user_id: str,
        timestamp: str,
        session_id: str,
        tool_name: str,
        params_summary: str,
        decision: str,
        risk_level: str,
        reason: str,
        elapsed_ms: float,
    ) -> None:
        """Insert an audit decision row if logging is enabled for this user."""
        import sqlite3

        if not self.is_audit_logging_enabled(user_id):
            return
        try:
            with self._write_lock:
                self._conn.execute(
                    "INSERT INTO audit_log (user_id, timestamp, session_id, tool_name, "
                    "params_summary, decision, risk_level, reason, elapsed_ms) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        int(user_id),
                        timestamp,
                        session_id,
                        tool_name,
                        params_summary[:500],
                        decision,
                        risk_level,
                        reason,
                        elapsed_ms,
                    ),
                )
                self._conn.commit()
        except (sqlite3.OperationalError, ValueError):
            pass  # DB read-only, table missing, or non-numeric user_id — skip

    def get_user_llm_config(self, user_id: str) -> dict | None:
        """Look up a user's LLM config from the shared DB.

        Tries llm_config JSON first, falls back to mistral_api_key for compat.
        Returns parsed dict or None.

        Results are cached for the configured TTL (default 60s) to avoid
        DB round-trips on every call.
        """
        now = time.monotonic()
        # Check cache first
        if user_id in self._llm_config_cache:
            cached_value, cached_at = self._llm_config_cache[user_id]
            if now - cached_at < self._llm_config_cache_ttl:
                return cached_value
            # Expired — remove stale entry
            del self._llm_config_cache[user_id]

        import sqlite3

        try:
            conn = self._fresh_conn()
            try:
                row = conn.execute(
                    "SELECT llm_config, mistral_api_key FROM user WHERE id = ?",
                    (user_id,),
                ).fetchone()
            finally:
                conn.close()
        except sqlite3.OperationalError:
            return None  # Table doesn't exist or columns missing

        if row is None:
            return None

        llm_config_str, mistral_key = row[0], row[1]
        result: dict | None = None

        # Prefer llm_config JSON if populated
        if llm_config_str:
            try:
                import json

                data = json.loads(llm_config_str)
                # Decrypt keys if encryption module is available
                if data.get("keys"):
                    try:
                        from safeclaw.key_crypto import decrypt_keys_dict

                        data["keys"] = decrypt_keys_dict(data["keys"])
                    except ImportError:
                        pass  # No encryption module — keys are plaintext
                result = data
            except (json.JSONDecodeError, TypeError):
                pass

        # Fall back to legacy mistral_api_key
        if result is None and mistral_key:
            result = {
                "active_provider": "mistral",
                "keys": {"mistral": mistral_key},
            }

        # Store in cache
        self._llm_config_cache[user_id] = (result, now)
        return result
