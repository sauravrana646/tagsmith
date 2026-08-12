"""Symmetric encryption for tenant refresh tokens (Phase 5)."""

from __future__ import annotations

import hashlib

from cryptography.fernet import Fernet, InvalidToken


class TokenCryptoError(RuntimeError):
    pass


def _fernet_from_secret(secret: str) -> Fernet:
    # Derive a 32-byte url-safe key from an arbitrary secret string.
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    import base64

    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(plaintext: str, *, secret_key: str) -> str:
    if not secret_key:
        raise TokenCryptoError("TAGSMITH_TOKEN_ENCRYPTION_KEY is required to encrypt tokens")
    return _fernet_from_secret(secret_key).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str, *, secret_key: str) -> str:
    if not secret_key:
        raise TokenCryptoError("TAGSMITH_TOKEN_ENCRYPTION_KEY is required to decrypt tokens")
    try:
        return _fernet_from_secret(secret_key).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise TokenCryptoError("Failed to decrypt token — wrong encryption key?") from exc
