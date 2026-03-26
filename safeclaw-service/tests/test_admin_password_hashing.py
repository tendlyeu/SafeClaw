"""Tests for admin password hashing and verification."""

import bcrypt

from safeclaw.config import SafeClawConfig


class TestHashPasswordReturnsBcryptHash:
    """verify_admin_password recognises bcrypt-hashed passwords."""

    def test_bcrypt_hash_is_accepted(self):
        raw = "s3cretP@ss!"
        hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
        cfg = SafeClawConfig(admin_password=hashed)
        assert cfg.verify_admin_password(raw)

    def test_bcrypt_hash_rejects_wrong_password(self):
        raw = "s3cretP@ss!"
        hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
        cfg = SafeClawConfig(admin_password=hashed)
        assert not cfg.verify_admin_password("wrongpassword")


class TestVerifyCorrectPassword:
    """verify_admin_password returns True for a correct plaintext password."""

    def test_plaintext_correct(self):
        cfg = SafeClawConfig(admin_password="myplaintext")
        assert cfg.verify_admin_password("myplaintext")


class TestVerifyWrongPassword:
    """verify_admin_password returns False for wrong plaintext password."""

    def test_plaintext_wrong(self):
        cfg = SafeClawConfig(admin_password="myplaintext")
        assert not cfg.verify_admin_password("notmypassword")


class TestConfigVerifyAdminPasswordFunctionExists:
    """SafeClawConfig exposes a verify_admin_password method."""

    def test_method_exists(self):
        cfg = SafeClawConfig(admin_password="x")
        assert callable(getattr(cfg, "verify_admin_password", None))


class TestPlaintextPasswordStillWorksForMigration:
    """Legacy plaintext passwords are still accepted (migration path)."""

    def test_plaintext_migration_correct(self):
        cfg = SafeClawConfig(admin_password="legacypass")
        assert cfg.verify_admin_password("legacypass")

    def test_plaintext_migration_wrong(self):
        cfg = SafeClawConfig(admin_password="legacypass")
        assert not cfg.verify_admin_password("other")

    def test_timing_safe_comparison_for_plaintext(self):
        """Even plaintext comparison should use constant-time comparison."""
        cfg = SafeClawConfig(admin_password="testpass")
        # Correct password
        assert cfg.verify_admin_password("testpass")
        # Wrong password with same prefix should still fail
        assert not cfg.verify_admin_password("testpas")
        assert not cfg.verify_admin_password("testpassx")


class TestEmptyPasswordEdgeCases:
    """Edge cases around empty/unset admin passwords."""

    def test_empty_password_rejects_all(self):
        """When admin_password is empty, verify should return False."""
        cfg = SafeClawConfig(admin_password="")
        assert not cfg.verify_admin_password("")
        assert not cfg.verify_admin_password("anything")

    def test_verify_empty_attempt_against_set_password(self):
        """Empty attempt against a set password should return False."""
        cfg = SafeClawConfig(admin_password="realpass")
        assert not cfg.verify_admin_password("")
