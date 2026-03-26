"""Tests for bcrypt-based API key hashing (#139)."""

import hashlib

from safeclaw.auth.api_key import APIKeyManager


class TestBcryptHashing:
    """Verify API key hashing uses bcrypt, not SHA-256."""

    def test_hash_key_is_not_sha256(self):
        """Hash must not equal the raw SHA-256 hex digest."""
        raw_key = "sc_test_key_for_hash_check"
        sha256_digest = hashlib.sha256(raw_key.encode()).hexdigest()
        hashed = APIKeyManager.hash_key(raw_key)
        assert hashed != sha256_digest

    def test_hash_key_uses_bcrypt(self):
        """Hash must start with the bcrypt $2b$ prefix."""
        hashed = APIKeyManager.hash_key("sc_some_key")
        assert hashed.startswith("$2b$")

    def test_hash_key_different_each_time(self):
        """bcrypt salt produces different hashes for the same input."""
        raw_key = "sc_same_key_twice"
        h1 = APIKeyManager.hash_key(raw_key)
        h2 = APIKeyManager.hash_key(raw_key)
        assert h1 != h2

    def test_verify_key_matches(self):
        """Correct key must verify against its own hash."""
        raw_key = "sc_correct_key"
        hashed = APIKeyManager.hash_key(raw_key)
        assert APIKeyManager.verify_key(raw_key, hashed) is True

    def test_verify_key_rejects_wrong_key(self):
        """Wrong key must not verify."""
        hashed = APIKeyManager.hash_key("sc_real_key")
        assert APIKeyManager.verify_key("sc_wrong_key", hashed) is False

    def test_verify_key_legacy_sha256_fallback(self):
        """Legacy SHA-256 hashes should still verify during migration."""
        raw_key = "sc_legacy_key"
        legacy_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        assert APIKeyManager.verify_key(raw_key, legacy_hash) is True

    def test_verify_key_legacy_sha256_rejects_wrong(self):
        """Legacy SHA-256 path should reject wrong keys."""
        legacy_hash = hashlib.sha256(b"sc_original").hexdigest()
        assert APIKeyManager.verify_key("sc_imposter", legacy_hash) is False


class TestAPIKeyManagerIntegration:
    """End-to-end create + validate with bcrypt hashing."""

    def test_create_and_validate_roundtrip(self):
        """Creating a key and validating it should succeed."""
        mgr = APIKeyManager()
        raw_key, api_key = mgr.create_key("org-bcrypt")
        result = mgr.validate_key(raw_key)
        assert result is not None
        assert result.key_id == api_key.key_id
        assert result.org_id == "org-bcrypt"

    def test_validate_wrong_key_returns_none(self):
        """Validating a wrong key should fail."""
        mgr = APIKeyManager()
        raw_key, _ = mgr.create_key("org-bcrypt")
        # Tamper with the key but keep the same prefix (key_id)
        wrong_key = raw_key[:12] + "XXXX_wrong_suffix"
        result = mgr.validate_key(wrong_key)
        assert result is None
