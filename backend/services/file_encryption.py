"""File-Transfer Encryption (iter 386).

AES-256-GCM authenticated encryption for files stored on untrusted media
(network shares, NAS). The encryption key is derived from a master secret
in `FT_ENCRYPTION_KEY` env var via HKDF-SHA256 with a per-key version so
future key rotation only adds a new derived key alongside the old.

Each encrypted blob layout:
    [version:1][nonce:12][ciphertext+tag:N]

`tag` is the built-in 16-byte GCM authentication tag — any tampering with
either the ciphertext or the version/nonce header will fail decryption
with a clean exception (no plaintext returned).

Public API: encrypt_bytes(plain) -> bytes, decrypt_bytes(blob) -> bytes,
            current_key_version() -> int.
"""
from __future__ import annotations
import os
import secrets
import hashlib
import hmac
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# We support multiple key versions for future rotation. The active version
# is what new uploads use; old versions remain decryptable as long as the
# master secret hash matches.
_ACTIVE_VERSION = 1

# Master secret resolution order:
#   1) FT_ENCRYPTION_KEY env (preferred, opaque hex/base64 string)
#   2) Derived from JWT_SECRET as a last-resort BOOTSTRAP fallback so a
#      fresh install does not crash. Production deployments MUST set
#      FT_ENCRYPTION_KEY explicitly.
def _master_secret() -> bytes:
    raw = os.environ.get("FT_ENCRYPTION_KEY") or ""
    if raw:
        # Allow hex, base64, or raw; we just hash to a fixed-length input
        return hashlib.sha256(raw.encode("utf-8")).digest()
    js = os.environ.get("JWT_SECRET") or ""
    if not js:
        raise RuntimeError(
            "Neither FT_ENCRYPTION_KEY nor JWT_SECRET is set. Configure "
            "FT_ENCRYPTION_KEY (>= 32 chars) for file-transfer encryption."
        )
    return hashlib.sha256(b"meetflow-ft-bootstrap|" + js.encode("utf-8")).digest()


def _hkdf_expand(secret: bytes, info: bytes, length: int = 32) -> bytes:
    """HKDF-SHA256 (simplified, salt=zeros). 32 bytes = AES-256 key."""
    # Extract
    prk = hmac.new(b"\x00" * 32, secret, hashlib.sha256).digest()
    # Expand
    okm, t, i = b"", b"", 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
        i += 1
    return okm[:length]


def _derive_key(version: int) -> bytes:
    return _hkdf_expand(_master_secret(), f"meetflow-ft-v{version}".encode("ascii"), 32)


def current_key_version() -> int:
    return _ACTIVE_VERSION


def encrypt_bytes(plain: bytes) -> tuple[bytes, int]:
    """Encrypt with the active key. Returns (blob, key_version)."""
    version = _ACTIVE_VERSION
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(_derive_key(version))
    ct = aesgcm.encrypt(nonce, plain, associated_data=bytes([version]))
    blob = bytes([version]) + nonce + ct
    return blob, version


def decrypt_bytes(blob: bytes) -> bytes:
    """Decrypt a blob produced by `encrypt_bytes`. Raises on any tamper."""
    if not blob or len(blob) < 1 + 12 + 16:
        raise ValueError("encrypted blob too short / corrupted")
    version = blob[0]
    nonce = blob[1:13]
    ct = blob[13:]
    aesgcm = AESGCM(_derive_key(version))
    return aesgcm.decrypt(nonce, ct, associated_data=bytes([version]))


def integrity_check(blob: bytes) -> bool:
    """Light-weight integrity probe — decrypt header to confirm key+tag
    validity without returning plaintext to the caller. Used by the
    storage-health endpoint."""
    try:
        decrypt_bytes(blob)
        return True
    except Exception:
        return False
