"""API key authentication for the remote SafeClaw service."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone


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
        """Hash an API key for storage."""
        return hashlib.sha256(raw_key.encode()).hexdigest()

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

        key_hash = self.hash_key(raw_key)
        if not hmac.compare_digest(key_hash, api_key.key_hash):
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

    Reads from the same api_keys table that the landing site writes to.
    Used in SaaS mode when db_path is configured.
    """

    def __init__(self, db_path: str):
        import sqlite3
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")

    def validate_key(self, raw_key: str) -> APIKey | None:
        """Validate an API key by looking it up in SQLite."""
        key_id = raw_key[:12]
        key_hash = APIKeyManager.hash_key(raw_key)

        row = self._conn.execute(
            "SELECT key_id, key_hash, scope, created_at, is_active, user_id "
            "FROM api_keys WHERE key_id = ? AND is_active = 1",
            (key_id,),
        ).fetchone()

        if row is None:
            return None

        db_key_id, db_key_hash, scope, created_at, is_active, user_id = row
        if not hmac.compare_digest(key_hash, db_key_hash):
            return None

        return APIKey(
            key_id=db_key_id,
            key_hash=db_key_hash,
            org_id=str(user_id),
            scope=scope,
            created_at=created_at,
            is_active=bool(is_active),
        )
