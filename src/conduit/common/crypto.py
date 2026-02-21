"""Cryptographic utilities for API key and secret management."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


# API Key Generation

KEY_PREFIX = "cnd_sk_"


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns:
        (raw_key, key_hash, key_prefix)
        - raw_key: Full key shown to user ONCE (e.g., cnd_sk_abc123...)
        - key_hash: SHA-256 hash stored in DB for lookup
        - key_prefix: First 12 chars for display (e.g., cnd_sk_abc1)
    """
    raw = f"{KEY_PREFIX}{secrets.token_urlsafe(32)}"
    key_hash = hash_api_key(raw)
    prefix = raw[:12]
    return raw, key_hash, prefix


def hash_api_key(raw_key: str) -> str:
    """Hash an API key with SHA-256 for secure storage."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


# Provider API Key Encryption

_ENCRYPTION_KEY: bytes | None = None


def _get_encryption_key() -> bytes:
    """Derive a Fernet key from CONDUIT_ENCRYPTION_KEY env var."""
    global _ENCRYPTION_KEY  # noqa: PLW0603
    if _ENCRYPTION_KEY is not None:
        return _ENCRYPTION_KEY

    master = os.environ.get("CONDUIT_ENCRYPTION_KEY", "conduit-dev-encryption-key")
    salt = os.environ.get("CONDUIT_ENCRYPTION_SALT", "conduit-salt").encode()

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    _ENCRYPTION_KEY = base64.urlsafe_b64encode(kdf.derive(master.encode()))
    return _ENCRYPTION_KEY


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string (e.g., provider API key) for DB storage."""
    f = Fernet(_get_encryption_key())
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a string from DB storage."""
    f = Fernet(_get_encryption_key())
    return f.decrypt(ciphertext.encode()).decode()