"""Database setup — SQLite via fastlite."""

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from fastlite import database

# Use absolute path relative to this file, not CWD (#110)
_DB_DIR = Path(__file__).resolve().parent / "data"
_DB_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = str(_DB_DIR / "safeclaw.db")

db = database(_DB_PATH)
db.execute("PRAGMA journal_mode=WAL")

# Best-effort: tighten DB file permissions if we own them
for suffix in ("", "-wal", "-shm"):
    p = f"{_DB_PATH}{suffix}"
    if os.path.exists(p):
        try:
            os.chmod(p, 0o660)
        except OSError:
            pass


class User:
    id: int
    github_id: int
    github_login: str
    name: str
    avatar_url: str
    email: str
    created_at: str
    last_login: str
    onboarded: bool = False
    autonomy_level: str = "moderate"
    mistral_api_key: str = ""
    confirm_before_delete: bool = True
    confirm_before_push: bool = True
    confirm_before_send: bool = True
    max_files_per_commit: int = 10
    self_hosted: bool = False
    service_url: str = ""
    admin_password: str = ""
    audit_logging: bool = True


class APIKey:
    id: int
    user_id: int
    key_id: str
    key_hash: str
    label: str
    scope: str
    created_at: str
    is_active: bool


users = db.create(User, pk="id", transform=True)
# Ensure github_id is unique to prevent duplicate user rows on concurrent OAuth (#109)
try:
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_github_id ON user(github_id)")
except Exception:
    pass
api_keys = db.create(APIKey, pk="id", transform=True)


class AuditLog:
    id: int
    user_id: int
    timestamp: str
    session_id: str
    tool_name: str
    params_summary: str
    decision: str
    risk_level: str
    reason: str
    elapsed_ms: float


audit_log = db.create(AuditLog, pk="id", transform=True)


def hash_admin_password(password: str) -> str:
    """Hash an admin password using SHA-256 with a salt for storage (#99)."""
    if not password:
        return ""
    salt = os.urandom(16).hex()
    h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{h}"


def verify_admin_password(password: str, stored_hash: str) -> bool:
    """Verify an admin password against a stored hash (#99)."""
    if not stored_hash or not password:
        return not stored_hash and not password
    if ":" not in stored_hash:
        # Legacy plaintext — compare directly and return True to allow migration
        return password == stored_hash
    salt, expected = stored_hash.split(":", 1)
    h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return h == expected


def upsert_user(github_id: int, github_login: str, name: str, avatar_url: str, email: str = "") -> User:
    """Create or update a user from GitHub profile data."""
    now = datetime.now(timezone.utc).isoformat()
    existing = users(where="github_id = ?", where_args=[github_id])
    if existing:
        user = existing[0]
        user.github_login = github_login
        user.name = name
        user.avatar_url = avatar_url
        user.email = email or user.email
        user.last_login = now
        return users.update(user)
    try:
        return users.insert(
            github_id=github_id,
            github_login=github_login,
            name=name,
            avatar_url=avatar_url,
            email=email or "",
            created_at=now,
            last_login=now,
        )
    except Exception:
        # Race condition: another request already inserted this github_id (#109)
        existing = users(where="github_id = ?", where_args=[github_id])
        if existing:
            user = existing[0]
            user.last_login = now
            return users.update(user)
        raise
