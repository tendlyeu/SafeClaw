"""Database setup — SQLite via fastlite."""

from datetime import datetime, timezone
from fastlite import database

db = database("data/safeclaw.db")
db.execute("PRAGMA journal_mode=WAL")


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
api_keys = db.create(APIKey, pk="id", transform=True)


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
    return users.insert(
        github_id=github_id,
        github_login=github_login,
        name=name,
        avatar_url=avatar_url,
        email=email or "",
        created_at=now,
        last_login=now,
    )
