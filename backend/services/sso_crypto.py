"""SSO secret-at-rest encryption.

Fernet symmetric encryption with key derived from JWT_SECRET via HKDF.
We deliberately do NOT introduce a new env variable: JWT_SECRET is already
required (>= 32 chars, see dependencies.py) and rotating it already
invalidates all sessions, so coupling SSO secrets to it has the same
operational footprint as a dedicated key.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    secret = os.environ["JWT_SECRET"].encode()
    # Derive 32-byte key, then urlsafe-b64 encode for Fernet.
    key = hashlib.sha256(b"meetflow-sso-v1::" + secret).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return ""
