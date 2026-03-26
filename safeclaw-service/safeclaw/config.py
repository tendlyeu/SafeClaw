"""SafeClaw configuration via Pydantic settings."""

import os
import secrets
from pathlib import Path

import bcrypt
from pydantic_settings import BaseSettings


class SafeClawConfig(BaseSettings):
    model_config = {"env_prefix": "SAFECLAW_", "arbitrary_types_allowed": True}

    host: str = "127.0.0.1"
    port: int = 8420

    # Paths
    data_dir: Path = Path.home() / ".safeclaw"
    ontology_dir: Path | None = None  # defaults to bundled ontologies
    audit_dir: Path | None = None  # defaults to data_dir / "audit"

    # CORS
    cors_origin_regex: str = r"https?://localhost:\d+$"

    # Auth
    require_auth: bool = False

    # Logging
    log_level: str = "INFO"

    db_path: str = ""  # Path to shared SQLite DB (SaaS mode)

    # Admin dashboard
    admin_password: str = ""

    # NemoClaw integration
    nemoclaw_enabled: bool = False
    nemoclaw_policy_dir: Path | None = None

    # LLM layer (passive observer — all features gated on mistral_api_key)
    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-latest"
    mistral_model_large: str = "mistral-large-latest"
    mistral_timeout_ms: int = 3000
    llm_security_review_enabled: bool = True
    llm_classification_observe: bool = True

    def get_ontology_dir(self) -> Path:
        if self.ontology_dir:
            return self.ontology_dir
        return Path(__file__).parent / "ontologies"

    def get_audit_dir(self) -> Path:
        if self.audit_dir:
            return self.audit_dir
        return self.data_dir / "audit"

    def get_nemoclaw_policy_dir(self) -> Path | None:
        """Resolve NemoClaw policy directory via fallback chain."""
        if self.nemoclaw_policy_dir and self.nemoclaw_policy_dir.exists():
            return self.nemoclaw_policy_dir
        home_dir = Path.home() / ".nemoclaw"
        if home_dir.exists() and any(home_dir.glob("*.yaml")):
            return home_dir
        sandbox_dir = os.environ.get("OPENSHELL_SANDBOX")
        if sandbox_dir:
            p = Path(sandbox_dir) / "policies"
            if p.exists():
                return p
        return None

    @property
    def is_nemoclaw_enabled(self) -> bool:
        if self.nemoclaw_enabled:
            return True
        return self.get_nemoclaw_policy_dir() is not None

    @property
    def raw(self) -> dict:
        config_path = self.data_dir / "config.json"
        if not config_path.exists():
            object.__setattr__(self, "_raw_cache", {})
            object.__setattr__(self, "_raw_cache_mtime", None)
            return {}

        current_mtime = config_path.stat().st_mtime
        cached = getattr(self, "_raw_cache", None)
        cached_mtime = getattr(self, "_raw_cache_mtime", None)
        if cached is not None and cached_mtime is not None and current_mtime == cached_mtime:
            return cached

        import json

        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
        object.__setattr__(self, "_raw_cache", data)
        object.__setattr__(self, "_raw_cache_mtime", current_mtime)
        return data

    def verify_admin_password(self, candidate: str) -> bool:
        """Verify a candidate password against the configured admin password.

        Supports two storage formats:
        - Bcrypt hashes (starting with "$2b$"): verified via bcrypt.checkpw.
        - Legacy plaintext: verified via secrets.compare_digest for constant-time
          comparison. This exists purely as a migration path; operators should
          switch to bcrypt hashes.

        Returns False when admin_password is empty (no password configured) or
        the candidate is empty, to prevent accidental auth bypass.
        """
        stored = self.admin_password
        if not stored or not candidate:
            return False

        if stored.startswith("$2b$"):
            return bcrypt.checkpw(candidate.encode("utf-8"), stored.encode("utf-8"))

        # Legacy plaintext fallback -- constant-time comparison
        return secrets.compare_digest(candidate, stored)

    def invalidate_raw_cache(self) -> None:
        """Invalidate the cached raw config, forcing a re-read on next access."""
        object.__setattr__(self, "_raw_cache", None)
        object.__setattr__(self, "_raw_cache_mtime", None)
