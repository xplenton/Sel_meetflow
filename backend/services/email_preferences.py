"""
One-click unsubscribe + newsletter preference management.
Uses HMAC-signed tokens so unsubscribe links survive without a login.
"""
from __future__ import annotations

import os
import hmac
import hashlib
import base64
import logging
from typing import Optional, Dict, Any

from database import db

logger = logging.getLogger(__name__)


def _secret() -> bytes:
    key = os.environ.get("JWT_SECRET", "").strip() or os.environ.get("SECRET_KEY", "").strip()
    if not key:
        key = "meetflow-unsubscribe-fallback"  # Dev-only fallback; never for production
    return key.encode("utf-8")


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def make_unsubscribe_token(user_id: str) -> str:
    """Return a stable, HMAC-signed token for the given user_id."""
    payload = user_id.encode("utf-8")
    sig = hmac.new(_secret(), payload, hashlib.sha256).digest()[:12]
    return f"{_b64url_encode(payload)}.{_b64url_encode(sig)}"


def verify_unsubscribe_token(token: str) -> Optional[str]:
    """Return the user_id encoded in the token, or None if signature is invalid."""
    try:
        payload_b64, sig_b64 = token.split(".")
        payload = _b64url_decode(payload_b64)
        expected = hmac.new(_secret(), payload, hashlib.sha256).digest()[:12]
        received = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected, received):
            return None
        return payload.decode("utf-8")
    except Exception:
        return None


async def is_newsletter_allowed(user: Dict[str, Any]) -> bool:
    """Return True if the given user has not opted out of newsletter e-mails."""
    prefs = user.get("email_preferences") or {}
    if not prefs:
        return True  # default: opted-in
    return bool(prefs.get("newsletter_enabled", True))


async def set_newsletter_enabled(user_id: str, enabled: bool, *, source: str = "api") -> None:
    """Update the user's newsletter-enabled flag and log the action."""
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"email_preferences.newsletter_enabled": enabled}},
    )
    try:
        from datetime import datetime, timezone
        await db.email_preferences_audit.insert_one({
            "user_id": user_id, "enabled": enabled, "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass


def build_unsubscribe_url(user_id: str) -> str:
    token = make_unsubscribe_token(user_id)
    frontend = (os.environ.get("FRONTEND_URL", "") or "").rstrip("/")
    if not frontend:
        return f"/unsubscribe/{token}"
    return f"{frontend}/unsubscribe/{token}"
