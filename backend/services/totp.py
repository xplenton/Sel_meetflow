"""TOTP / 2FA helpers (iter 188).

* Time-based One-Time Passwords via pyotp (RFC 6238)
* Recovery codes: 10 single-use bcrypt-hashed strings
* Storage: extra fields on the `users` document
    - totp_enabled: bool
    - totp_secret: str (base32) -- only stored once 2FA is fully verified
    - totp_pending_secret: str -- transient, until first successful verify
    - totp_recovery_hashes: List[str] (bcrypt hashes)
    - totp_enabled_at: ISO str
"""
from __future__ import annotations

import base64
import io
import secrets
from typing import Dict, List, Tuple

import bcrypt
import pyotp
import qrcode
from qrcode.image.pil import PilImage


ISSUER = "MeetFlow"
RECOVERY_CODE_COUNT = 10


# ---------------------------------------------------------------------------

def generate_secret() -> str:
    """Return a fresh base32 TOTP secret."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, account: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=ISSUER)


def qr_png_data_url(uri: str) -> str:
    """Render `uri` as a PNG QR-code, base64-encoded data URL ready for <img src=...>."""
    qr = qrcode.QRCode(border=2, box_size=6)
    qr.add_data(uri)
    qr.make(fit=True)
    img: PilImage = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def verify_code(secret: str, code: str, *, valid_window: int = 1) -> bool:
    """Verify a 6-digit code with a ±1-step tolerance (default ±30 s)."""
    if not secret or not code:
        return False
    try:
        return pyotp.TOTP(secret).verify(code.strip(), valid_window=valid_window)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Recovery codes

def generate_recovery_codes(n: int = RECOVERY_CODE_COUNT) -> List[str]:
    """Return `n` human-readable recovery codes (e.g. `7H3M-D9K2-PL4F`)."""
    out: List[str] = []
    for _ in range(n):
        raw = secrets.token_hex(6).upper()  # 12 hex chars
        chunks = [raw[i:i + 4] for i in range(0, 12, 4)]
        out.append("-".join(chunks))
    return out


def hash_recovery_codes(codes: List[str]) -> List[str]:
    return [
        bcrypt.hashpw(c.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")
        for c in codes
    ]


def consume_recovery_code(stored_hashes: List[str], submitted: str) -> Tuple[bool, List[str]]:
    """Try each stored hash against the submitted code. If a match is found,
    return (True, hashes-with-the-match-removed). Otherwise (False, hashes)."""
    if not stored_hashes or not submitted:
        return False, stored_hashes or []
    cleaned = submitted.strip().upper()
    out: List[str] = []
    matched = False
    for h in stored_hashes:
        if not matched and bcrypt.checkpw(cleaned.encode("utf-8"), h.encode("utf-8")):
            matched = True
            continue  # drop this hash
        out.append(h)
    return matched, out


# ---------------------------------------------------------------------------
# Public summary (safe for /auth/me responses)

def public_status(user: Dict) -> Dict:
    return {
        "totp_enabled": bool(user.get("totp_enabled")),
        "totp_enabled_at": user.get("totp_enabled_at"),
        "recovery_codes_remaining": len(user.get("totp_recovery_hashes") or []),
    }
