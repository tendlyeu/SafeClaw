"""Database setup — SQLite via fastlite."""

import hashlib
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastlite import database

# Store database outside the web-accessible repo directory (#39).
# Default location: ~/.safeclaw-landing/  (overridable via SAFECLAW_DB_DIR).
_DB_DIR = Path(os.environ.get("SAFECLAW_DB_DIR", os.path.expanduser("~/.safeclaw-landing")))
_DB_DIR.mkdir(parents=True, exist_ok=True)

# Migrate from the old in-repo location if it exists and new location is empty (#39)
_OLD_DB_DIR = Path(__file__).resolve().parent / "data"
_OLD_DB_PATH = _OLD_DB_DIR / "safeclaw.db"
_DB_PATH = str(_DB_DIR / "safeclaw.db")
if _OLD_DB_PATH.exists() and not Path(_DB_PATH).exists():
    try:
        shutil.copy2(str(_OLD_DB_PATH), _DB_PATH)
        # Also migrate WAL/SHM files if present
        for suffix in ("-wal", "-shm"):
            old_extra = _OLD_DB_DIR / f"safeclaw.db{suffix}"
            if old_extra.exists():
                shutil.copy2(str(old_extra), f"{_DB_PATH}{suffix}")
    except OSError:
        pass  # Fall through to create a fresh database

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
    is_admin: bool = False
    is_disabled: bool = False


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
    """Hash an admin password using PBKDF2-SHA256 for storage (#99, #14).

    Returns 'pbkdf2:<hex-salt>:<hex-hash>' so we can distinguish the format
    from legacy plaintext or the old SHA-256 scheme.
    """
    if not password:
        return ""
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=600_000)
    return f"pbkdf2:{salt.hex()}:{h.hex()}"


def verify_admin_password(password: str, stored_hash: str) -> bool:
    """Verify an admin password against a stored hash (#99, #14).

    Uses hmac.compare_digest for constant-time comparison.
    Supports three formats for backward compatibility:
      - 'pbkdf2:<salt>:<hash>'  (current PBKDF2 scheme)
      - '<salt>:<hash>'         (legacy SHA-256 scheme)
      - plain text              (legacy — no separator)
    """
    import hmac as _hmac

    if not stored_hash or not password:
        return not stored_hash and not password

    # Current PBKDF2 format
    if stored_hash.startswith("pbkdf2:"):
        parts = stored_hash.split(":", 2)
        if len(parts) != 3:
            return False
        _, salt_hex, expected_hex = parts
        try:
            salt = bytes.fromhex(salt_hex)
        except ValueError:
            return False
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=600_000)
        return _hmac.compare_digest(h.hex(), expected_hex)

    # Legacy SHA-256 format (salt:hash)
    if ":" in stored_hash:
        salt, expected = stored_hash.split(":", 1)
        h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
        return _hmac.compare_digest(h, expected)

    # Legacy plaintext — constant-time compare
    return _hmac.compare_digest(password, stored_hash)


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
