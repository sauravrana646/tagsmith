"""Symmetric encryption for tenant refresh tokens (Phase 5)."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_V2_PREFIX = "v2:"
_HKDF_SALT = b"tagsmith-token-v2"
_HKDF_INFO = b"fernet"


class TokenCryptoError(RuntimeError):
    pass


def _fernet_v1(secret: str) -> Fernet:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _fernet_v2(secret: str) -> Fernet:
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=_HKDF_INFO,
    ).derive(secret.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_secret(plaintext: str, *, secret_key: str) -> str:
    if not secret_key:
        raise TokenCryptoError("TAGSMITH_TOKEN_ENCRYPTION_KEY is required to encrypt tokens")
    token = _fernet_v2(secret_key).encrypt(plaintext.encode("utf-8")).decode("ascii")
    return _V2_PREFIX + token


def decrypt_secret(ciphertext: str, *, secret_key: str) -> str:
    if not secret_key:
        raise TokenCryptoError("TAGSMITH_TOKEN_ENCRYPTION_KEY is required to decrypt tokens")
    try:
        if ciphertext.startswith(_V2_PREFIX):
            raw = ciphertext[len(_V2_PREFIX) :].encode("ascii")
            return _fernet_v2(secret_key).decrypt(raw).decode("utf-8")
        return _fernet_v1(secret_key).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise TokenCryptoError("Failed to decrypt token — wrong encryption key?") from exc
