"""Encrypt and decrypt API keys at rest using Fernet symmetric encryption.

Keys are stored with an ``enc:`` prefix so plaintext legacy values can be
detected and auto-migrated on the next save.

The encryption key is auto-generated on first use and stored at
``~/.safeclaw-landing/.encryption_key`` with 0o600 permissions.
"""

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_ENC_PREFIX = "enc:"

_DB_DIR = Path(os.environ.get("SAFECLAW_DB_DIR", os.path.expanduser("~/.safeclaw-landing")))
_KEY_PATH = _DB_DIR / ".encryption_key"

_fernet = None


def _get_fernet() -> Fernet:
    """Return a cached Fernet instance, generating the key file if needed."""
    global _fernet
    if _fernet is not None:
        return _fernet

    _DB_DIR.mkdir(parents=True, exist_ok=True)

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
        return _get_fernet().decrypt(stored[len(_ENC_PREFIX):].encode()).decode()
    except InvalidToken:
        import logging

        logging.getLogger(__name__).warning(
            "Failed to decrypt API key — encryption key may have changed"
        )
        return ""


def encrypt_keys_dict(keys: dict) -> dict:
    """Encrypt all values in a {provider: api_key} dict."""
    return {pid: encrypt_key(v) for pid, v in keys.items() if v}


def decrypt_keys_dict(keys: dict) -> dict:
    """Decrypt all values in a {provider: encrypted_key} dict."""
    return {pid: decrypt_key(v) for pid, v in keys.items() if v}
