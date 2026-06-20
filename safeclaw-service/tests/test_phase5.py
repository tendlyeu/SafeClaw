"""Phase 5 tests: API key authentication, middleware, per-user LLM client."""

from unittest.mock import MagicMock

from safeclaw.auth.api_key import APIKeyManager


def _seed_user_db(db_path, user_id, *, mistral_key="", llm_config=None):
    """Create the user table and insert one row, for LLM-config cache tests."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS user ("
        "  id INTEGER PRIMARY KEY,"
        "  mistral_api_key TEXT DEFAULT '',"
        "  llm_config TEXT DEFAULT NULL"
        ")"
    )
    conn.execute(
        "INSERT INTO user (id, mistral_api_key, llm_config) VALUES (?, ?, ?)",
        (user_id, mistral_key, llm_config),
    )
    conn.commit()
    conn.close()


def _update_user_mistral_key(db_path, user_id, mistral_key):
    """Update a user's mistral_api_key directly in the DB (simulates landing-site write)."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE user SET mistral_api_key = ? WHERE id = ?", (mistral_key, user_id))
    conn.commit()
    conn.close()


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
            "CREATE TABLE user ("
            "  id INTEGER PRIMARY KEY,"
            "  mistral_api_key TEXT DEFAULT '',"
            "  llm_config TEXT DEFAULT NULL"
            ")"
        )
        conn.execute("INSERT INTO user (id, mistral_api_key) VALUES (?, ?)", (42, "mist_test_key"))
        conn.commit()
        conn.close()

        mgr = SQLiteAPIKeyManager(str(db_path))
        # get_user_llm_config falls back to mistral_api_key column for legacy compat
        result = mgr.get_user_llm_config("42")
        assert result is not None
        assert result["active_provider"] == "mistral"
        assert result["keys"]["mistral"] == "mist_test_key"
        assert mgr.get_user_llm_config("999") is None

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
            "CREATE TABLE user ("
            "  id INTEGER PRIMARY KEY,"
            "  mistral_api_key TEXT DEFAULT '',"
            "  llm_config TEXT DEFAULT NULL"
            ")"
        )
        conn.execute("INSERT INTO user (id, mistral_api_key) VALUES (?, ?)", (42, ""))
        conn.commit()
        conn.close()

        mgr = SQLiteAPIKeyManager(str(db_path))
        assert mgr.get_user_llm_config("42") is None  # empty string = no key

    def test_llm_config_cache_hit_skips_db(self, tmp_path):
        """A second lookup within the TTL is served from cache, with no DB read."""
        from safeclaw.auth.api_key import SQLiteAPIKeyManager

        db_path = tmp_path / "safeclaw.db"
        _seed_user_db(db_path, 42, mistral_key="key_v1")

        mgr = SQLiteAPIKeyManager(str(db_path), llm_config_cache_ttl=60)

        reads = 0
        real_fresh_conn = mgr._fresh_conn

        def counting_fresh_conn():
            nonlocal reads
            reads += 1
            return real_fresh_conn()

        mgr._fresh_conn = counting_fresh_conn

        first = mgr.get_user_llm_config("42")
        second = mgr.get_user_llm_config("42")

        assert first == {"active_provider": "mistral", "keys": {"mistral": "key_v1"}}
        assert second == first
        assert reads == 1  # second call hit the cache, not the DB

    def test_llm_config_cache_serves_stale_within_ttl(self, tmp_path):
        """Within the TTL the cached value is returned even after the DB changes."""
        from safeclaw.auth.api_key import SQLiteAPIKeyManager

        db_path = tmp_path / "safeclaw.db"
        _seed_user_db(db_path, 42, mistral_key="key_v1")

        mgr = SQLiteAPIKeyManager(str(db_path), llm_config_cache_ttl=60)
        assert mgr.get_user_llm_config("42")["keys"]["mistral"] == "key_v1"

        _update_user_mistral_key(db_path, 42, "key_v2")
        # Still within TTL → cached value, not the freshly written one.
        assert mgr.get_user_llm_config("42")["keys"]["mistral"] == "key_v1"

    def test_llm_config_cache_expiry_refetches(self, tmp_path):
        """Once an entry expires, the next lookup re-reads from the DB."""
        import time

        from safeclaw.auth.api_key import SQLiteAPIKeyManager

        db_path = tmp_path / "safeclaw.db"
        _seed_user_db(db_path, 42, mistral_key="key_v1")

        mgr = SQLiteAPIKeyManager(str(db_path), llm_config_cache_ttl=60)
        assert mgr.get_user_llm_config("42")["keys"]["mistral"] == "key_v1"

        # Update the DB and force the cached entry to look older than the TTL.
        _update_user_mistral_key(db_path, 42, "key_v2")
        value, _ = mgr._llm_config_cache["42"]
        mgr._llm_config_cache["42"] = (value, time.monotonic() - 61)

        assert mgr.get_user_llm_config("42")["keys"]["mistral"] == "key_v2"

    def test_llm_config_cache_caches_missing_user(self, tmp_path):
        """An unknown user caches the None result and serves it without re-reading."""
        from safeclaw.auth.api_key import SQLiteAPIKeyManager

        db_path = tmp_path / "safeclaw.db"
        _seed_user_db(db_path, 42, mistral_key="key_v1")

        mgr = SQLiteAPIKeyManager(str(db_path), llm_config_cache_ttl=60)

        reads = 0
        real_fresh_conn = mgr._fresh_conn

        def counting_fresh_conn():
            nonlocal reads
            reads += 1
            return real_fresh_conn()

        mgr._fresh_conn = counting_fresh_conn

        assert mgr.get_user_llm_config("999") is None  # unknown user
        assert mgr.get_user_llm_config("999") is None  # served from the negative cache
        assert reads == 1
        assert mgr._llm_config_cache["999"][0] is None

    def test_llm_config_cache_does_not_cache_transient_db_error(self, tmp_path):
        """A transient DB error returns None and is not cached, so it retries."""
        import sqlite3

        from safeclaw.auth.api_key import SQLiteAPIKeyManager

        db_path = tmp_path / "safeclaw.db"
        _seed_user_db(db_path, 42, mistral_key="key_v1")

        mgr = SQLiteAPIKeyManager(str(db_path), llm_config_cache_ttl=60)
        real_fresh_conn = mgr._fresh_conn

        # Simulate a transient DB error on the read path (e.g. DB locked/read-only).
        def boom():
            raise sqlite3.OperationalError("database is locked")

        mgr._fresh_conn = boom
        assert mgr.get_user_llm_config("42") is None
        assert "42" not in mgr._llm_config_cache  # failure not pinned for the TTL

        # Recovery: once the DB is reachable again, the real value is returned —
        # no stale negative entry blocks it.
        mgr._fresh_conn = real_fresh_conn
        assert mgr.get_user_llm_config("42")["keys"]["mistral"] == "key_v1"

    def test_llm_config_cache_disabled_with_zero_ttl(self, tmp_path):
        """ttl=0 effectively disables caching — every call re-reads the DB."""
        from safeclaw.auth.api_key import SQLiteAPIKeyManager

        db_path = tmp_path / "safeclaw.db"
        _seed_user_db(db_path, 42, mistral_key="key_v1")

        mgr = SQLiteAPIKeyManager(str(db_path), llm_config_cache_ttl=0)
        assert mgr.get_user_llm_config("42")["keys"]["mistral"] == "key_v1"
        _update_user_mistral_key(db_path, 42, "key_v2")
        assert mgr.get_user_llm_config("42")["keys"]["mistral"] == "key_v2"

    def test_llm_config_cache_thread_safe_under_contention(self, tmp_path):
        """Concurrent lookups with constant expiry must not raise (check-then-del race)."""
        import threading

        from safeclaw.auth.api_key import SQLiteAPIKeyManager

        db_path = tmp_path / "safeclaw.db"
        _seed_user_db(db_path, 42, mistral_key="key_v1")

        # ttl=0 forces the expiry+delete branch on every call, maximizing the
        # chance of a check-then-delete race under the old (lockless) code.
        mgr = SQLiteAPIKeyManager(str(db_path), llm_config_cache_ttl=0)

        errors = []

        def worker():
            try:
                for _ in range(100):
                    mgr.get_user_llm_config("42")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"cache access raced under concurrency: {errors[:3]}"

    def test_llm_config_cache_is_bounded(self, tmp_path):
        """The cache evicts entries once it reaches its max size."""
        import sqlite3

        from safeclaw.auth.api_key import SQLiteAPIKeyManager

        db_path = tmp_path / "safeclaw.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE user ("
            "  id INTEGER PRIMARY KEY,"
            "  mistral_api_key TEXT DEFAULT '',"
            "  llm_config TEXT DEFAULT NULL"
            ")"
        )
        for uid in range(10):
            conn.execute("INSERT INTO user (id, mistral_api_key) VALUES (?, ?)", (uid, f"key{uid}"))
        conn.commit()
        conn.close()

        mgr = SQLiteAPIKeyManager(str(db_path), llm_config_cache_ttl=60)
        mgr._llm_config_cache_max = 3  # shrink the bound for the test

        for uid in range(10):
            mgr.get_user_llm_config(str(uid))

        assert len(mgr._llm_config_cache) <= 3

    def test_llm_config_cache_ttl_is_config_driven(self, monkeypatch):
        """The cache TTL is wired through SafeClawConfig (deployment-tunable)."""
        from safeclaw.config import SafeClawConfig

        monkeypatch.delenv("SAFECLAW_LLM_CONFIG_CACHE_TTL", raising=False)
        assert SafeClawConfig().llm_config_cache_ttl == 60  # default

        monkeypatch.setenv("SAFECLAW_LLM_CONFIG_CACHE_TTL", "5")
        assert SafeClawConfig().llm_config_cache_ttl == 5  # env override


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
        """With a manager that returns an LLM config, creates a per-user client."""
        from safeclaw.engine.full_engine import FullEngine
        from safeclaw.config import SafeClawConfig

        config = SafeClawConfig()
        engine = FullEngine(config)

        mock_manager = MagicMock()
        mock_manager.get_user_llm_config.return_value = {
            "active_provider": "mistral",
            "keys": {"mistral": "mist_test_key"},
        }
        engine.api_key_manager = mock_manager

        engine.get_llm_client_for_user("42")
        # get_user_llm_config is called to look up per-user LLM settings
        mock_manager.get_user_llm_config.assert_called_once_with("42")
