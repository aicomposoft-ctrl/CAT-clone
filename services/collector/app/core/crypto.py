"""
Token encryption/decryption for platform API credentials.

Uses MultiFernet (key rotation support) from the `cryptography` package.

Environment variable:
  PLATFORM_SECRET_KEYS — comma-separated list of Fernet keys (base64-url).
  The FIRST key is used for encryption; ALL keys are tried for decryption
  (enables zero-downtime key rotation).

Key generation:
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet


@lru_cache(maxsize=1)
def _get_fernet() -> MultiFernet:
    """
    Build and cache a MultiFernet instance from PLATFORM_SECRET_KEYS.
    Cached at module level — parsing env var and constructing Fernet objects
    once per process instead of per encrypt/decrypt call.
    """
    keys_str = os.environ.get("PLATFORM_SECRET_KEYS", "")
    if not keys_str:
        raise RuntimeError(
            "PLATFORM_SECRET_KEYS env var not set — cannot encrypt/decrypt platform tokens"
        )
    keys = [Fernet(k.strip().encode()) for k in keys_str.split(",") if k.strip()]
    if not keys:
        raise RuntimeError("PLATFORM_SECRET_KEYS contains no valid Fernet keys")
    return MultiFernet(keys)


def encrypt_token(token: str) -> str:
    """Encrypt a plaintext API token. Returns a Fernet-token string (base64-url safe)."""
    return _get_fernet().encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt a Fernet-encrypted API token back to plaintext."""
    return _get_fernet().decrypt(encrypted.encode()).decode()
