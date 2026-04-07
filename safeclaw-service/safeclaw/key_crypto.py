"""Encrypt and decrypt API keys at rest using Fernet symmetric encryption.

Keys are stored with an ``enc:`` prefix so plaintext legacy values can be
detected and auto-migrated on the next save.

The encryption key is co-located with the shared SQLite DB so both the
landing site and the SafeClaw service can access the same key.
"""

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_ENC_PREFIX = "enc:"


def _resolve_key_dir() -> Path:
    """Find the directory containing the encryption key.

    Priority:
    1. SAFECLAW_DB_DIR env var (landing site sets this)
    2. Parent of SAFECLAW_DB_PATH (service sets this to the shared DB file)
    3. ~/.safeclaw-landing (local dev default)
    """
    db_dir = os.environ.get("SAFECLAW_DB_DIR")
    if db_dir:
        return Path(db_dir)
    db_path = os.environ.get("SAFECLAW_DB_PATH")
    if db_path:
        return Path(db_path).parent
    return Path.home() / ".safeclaw-landing"


_KEY_DIR = _resolve_key_dir()
_KEY_PATH = _KEY_DIR / ".encryption_key"

_fernet = None


def _get_fernet() -> Fernet:
    """Return a cached Fernet instance, generating the key file if needed."""
    global _fernet
    if _fernet is not None:
        return _fernet

    _KEY_DIR.mkdir(parents=True, exist_ok=True)

    if _KEY_PATH.exists():
        key = _KEY_PATH.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        fd = os.open(str(_KEY_PATH), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, key)
        finally:
            os.close(fd)

    _fernet = Fernet(key)
    return _fernet


def encrypt_key(plaintext: str) -> str:
    """Encrypt an API key. Returns ``enc:<ciphertext>``."""
    if not plaintext:
        return ""
    return _ENC_PREFIX + _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_key(stored: str) -> str:
    """Decrypt an API key. Passes through plaintext values for migration."""
    if not stored:
        return ""
    if not stored.startswith(_ENC_PREFIX):
        return stored  # Legacy plaintext — will be encrypted on next save
    try:
        return _get_fernet().decrypt(stored[len(_ENC_PREFIX) :].encode()).decode()
    except InvalidToken:
        logger.warning("Failed to decrypt API key — encryption key may have changed")
        return ""


def encrypt_keys_dict(keys: dict) -> dict:
    """Encrypt all values in a {provider: api_key} dict."""
    return {pid: encrypt_key(v) for pid, v in keys.items() if v}


def decrypt_keys_dict(keys: dict) -> dict:
    """Decrypt all values in a {provider: encrypted_key} dict."""
    return {pid: decrypt_key(v) for pid, v in keys.items() if v}
