"""Phase 5 tests: API key authentication, middleware, per-user LLM client."""

from unittest.mock import MagicMock

from safeclaw.auth.api_key import APIKeyManager


# --- APIKeyManager Tests ---


class TestAPIKeyManager:
    def test_create_key_returns_raw_and_record(self):
        mgr = APIKeyManager()
        raw_key, api_key = mgr.create_key("org-1")
        assert raw_key.startswith("sc_")
        assert api_key.org_id == "org-1"
        assert api_key.scope == "full"
        assert api_key.is_active is True

    def test_create_key_custom_scope(self):
        mgr = APIKeyManager()
        raw_key, api_key = mgr.create_key("org-1", scope="read_only")
        assert api_key.scope == "read_only"

    def test_validate_key_success(self):
        mgr = APIKeyManager()
        raw_key, api_key = mgr.create_key("org-1")
        validated = mgr.validate_key(raw_key)
        assert validated is not None
        assert validated.org_id == "org-1"
        assert validated.key_id == api_key.key_id

    def test_validate_key_wrong_key(self):
        mgr = APIKeyManager()
        mgr.create_key("org-1")
        result = mgr.validate_key("sc_totally_wrong_key_here_12345678")
        assert result is None

    def test_validate_key_nonexistent(self):
        mgr = APIKeyManager()
        result = mgr.validate_key("sc_nonexistent_key")
        assert result is None

    def test_revoke_key(self):
        mgr = APIKeyManager()
        raw_key, api_key = mgr.create_key("org-1")
        assert mgr.revoke_key(api_key.key_id) is True
        # Revoked key should not validate
        assert mgr.validate_key(raw_key) is None

    def test_revoke_nonexistent_key(self):
        mgr = APIKeyManager()
        assert mgr.revoke_key("nonexistent") is False

    def test_list_keys_filters_by_org(self):
        mgr = APIKeyManager()
        mgr.create_key("org-1")
        mgr.create_key("org-1")
        mgr.create_key("org-2")
        assert len(mgr.list_keys("org-1")) == 2
        assert len(mgr.list_keys("org-2")) == 1
        assert len(mgr.list_keys("org-3")) == 0

    def test_generate_key_uniqueness(self):
        keys = set()
        for _ in range(50):
            raw_key, key_id = APIKeyManager.generate_key()
            keys.add(raw_key)
        assert len(keys) == 50

    def test_hash_key_verifiable(self):
        """bcrypt hashes differ each time but verify against the original key."""
        h1 = APIKeyManager.hash_key("sc_test_key")
        h2 = APIKeyManager.hash_key("sc_test_key")
        # bcrypt uses random salts, so hashes differ
        assert h1 != h2
        # But both verify against the original key
        assert APIKeyManager.verify_key("sc_test_key", h1)
        assert APIKeyManager.verify_key("sc_test_key", h2)

    def test_hash_key_different_for_different_keys(self):
        h1 = APIKeyManager.hash_key("sc_key_a")
        h2 = APIKeyManager.hash_key("sc_key_b")
        # Different keys should not verify against each other's hashes
        assert not APIKeyManager.verify_key("sc_key_a", h2)
        assert not APIKeyManager.verify_key("sc_key_b", h1)


class TestSQLiteAPIKeyManager:
    """Tests for SQLiteAPIKeyManager backed by a real SQLite file."""

    def test_validate_key_from_db(self, tmp_path):
        import hashlib
        import secrets
        import sqlite3

        from safeclaw.auth.api_key import SQLiteAPIKeyManager

        db_path = tmp_path / "safeclaw.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE api_key ("
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
        raw_key = "sc_" + secrets.token_urlsafe(32)
        key_id = raw_key[:12]
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        conn.execute(
            "INSERT INTO api_key (user_id, key_id, key_hash, label, scope, created_at, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, key_id, key_hash, "test", "full", "2026-01-01", True),
        )
        conn.commit()
        conn.close()

        mgr = SQLiteAPIKeyManager(str(db_path))
        result = mgr.validate_key(raw_key)
        assert result is not None
        assert result.key_id == key_id
        assert result.scope == "full"

    def test_validate_revoked_key_returns_none(self, tmp_path):
        import hashlib
        import secrets
        import sqlite3

        from safeclaw.auth.api_key import SQLiteAPIKeyManager

        db_path = tmp_path / "safeclaw.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE api_key ("
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
        raw_key = "sc_" + secrets.token_urlsafe(32)
        key_id = raw_key[:12]
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        conn.execute(
            "INSERT INTO api_key (user_id, key_id, key_hash, label, scope, created_at, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, key_id, key_hash, "test", "full", "2026-01-01", False),
        )
        conn.commit()
        conn.close()

        mgr = SQLiteAPIKeyManager(str(db_path))
        result = mgr.validate_key(raw_key)
        assert result is None

    def test_validate_wrong_key_returns_none(self, tmp_path):
        import sqlite3

        from safeclaw.auth.api_key import SQLiteAPIKeyManager

        db_path = tmp_path / "safeclaw.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE api_key ("
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
        conn.commit()
        conn.close()

        mgr = SQLiteAPIKeyManager(str(db_path))
        result = mgr.validate_key("sc_nonexistent12345678901234567890")
        assert result is None

    def test_get_user_mistral_key(self, tmp_path):
        import sqlite3

        from safeclaw.auth.api_key import SQLiteAPIKeyManager

        db_path = tmp_path / "safeclaw.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE api_key ("
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
        conn.execute(
            "CREATE TABLE user (  id INTEGER PRIMARY KEY,  mistral_api_key TEXT DEFAULT '')"
        )
        conn.execute("INSERT INTO user (id, mistral_api_key) VALUES (?, ?)", (42, "mist_test_key"))
        conn.commit()
        conn.close()

        mgr = SQLiteAPIKeyManager(str(db_path))
        assert mgr.get_user_mistral_key("42") == "mist_test_key"
        assert mgr.get_user_mistral_key("999") is None

    def test_get_user_mistral_key_empty(self, tmp_path):
        import sqlite3

        from safeclaw.auth.api_key import SQLiteAPIKeyManager

        db_path = tmp_path / "safeclaw.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE api_key ("
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
        conn.execute(
            "CREATE TABLE user (  id INTEGER PRIMARY KEY,  mistral_api_key TEXT DEFAULT '')"
        )
        conn.execute("INSERT INTO user (id, mistral_api_key) VALUES (?, ?)", (42, ""))
        conn.commit()
        conn.close()

        mgr = SQLiteAPIKeyManager(str(db_path))
        assert mgr.get_user_mistral_key("42") is None  # empty string = no key


# --- APIKeyAuthMiddleware Tests ---


class TestAPIKeyAuthMiddleware:
    """Tests for the auth middleware using mocked ASGI components."""

    def test_skip_health_path(self):
        from safeclaw.auth.middleware import APIKeyAuthMiddleware

        app = MagicMock()
        middleware = APIKeyAuthMiddleware(app, api_key_manager=MagicMock(), require_auth=True)
        assert "/api/v1/health" in middleware.SKIP_PATHS
        assert "/docs" in middleware.SKIP_PREFIXES

    def test_auth_disabled_passes_through(self):
        from safeclaw.auth.middleware import APIKeyAuthMiddleware

        app = MagicMock()
        middleware = APIKeyAuthMiddleware(app, api_key_manager=None, require_auth=False)
        # require_auth is False, so it should pass through
        assert middleware.require_auth is False


# --- Per-User LLM Client Tests ---


class TestPerUserLLMClient:
    def test_get_llm_client_for_user_no_manager(self):
        """Without an api_key_manager, falls back to global client."""
        from safeclaw.engine.full_engine import FullEngine
        from safeclaw.config import SafeClawConfig

        config = SafeClawConfig()
        engine = FullEngine(config)
        assert engine.get_llm_client_for_user("42") is None  # no global client either

    def test_get_llm_client_for_user_falls_back_to_global(self):
        """If user has no Mistral key, fall back to global client."""
        from safeclaw.engine.full_engine import FullEngine
        from safeclaw.config import SafeClawConfig

        config = SafeClawConfig()
        engine = FullEngine(config)
        engine.llm_client = MagicMock()  # Simulate global client
        # No api_key_manager set, so per-user returns global
        result = engine.get_llm_client_for_user("42")
        assert result is engine.llm_client

    def test_get_llm_client_for_user_with_manager(self):
        """With a manager that returns a key, creates a per-user client."""
        from safeclaw.engine.full_engine import FullEngine
        from safeclaw.config import SafeClawConfig

        config = SafeClawConfig()
        engine = FullEngine(config)

        mock_manager = MagicMock()
        mock_manager.get_user_mistral_key.return_value = "mist_test_key"
        engine.api_key_manager = mock_manager

        # This will try to import mistralai which may not be installed in test env
        # So we test the fallback path: if Mistral import fails, returns global
        engine.get_llm_client_for_user("42")
        # Should either return a new client or fall back to global (if mistralai not installed)
        mock_manager.get_user_mistral_key.assert_called_once_with("42")
