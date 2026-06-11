"""Web Push notification service using VAPID."""
import os
import json
import logging
from typing import Optional
from pywebpush import webpush, WebPushException

logger = logging.getLogger(__name__)


def get_vapid_public_key() -> str:
    return os.environ.get("VAPID_PUBLIC_KEY", "")


def _get_vapid_private_key_pem() -> Optional[str]:
    """Return VAPID private key as a base64url string (pywebpush accepts the raw base64url format directly)."""
    priv = os.environ.get("VAPID_PRIVATE_KEY", "")
    if not priv:
        return None
    return priv


def send_web_push(subscription: dict, payload: dict, *, urgency: str = "high", ttl: int = 60) -> dict:
    """Send a Web Push notification to a single subscription.

    `urgency` (RFC 8030) tells the push service how aggressively to deliver:
       * `very-low` — background sync, saver-mode OK to defer hours
       * `low`      — informational
       * `normal`   — default
       * `high`     — **required for iOS lock-screen wake-up** (iter 150).
                      Apple Push silently drops notifications tagged as
                      normal/low when the device is on battery-saver or
                      locked, which is exactly the reported bug.
    `ttl` (seconds) — how long the push service retries if the device is
    offline. 60 s matches the ring-timeout so late deliveries don't pop
    up *after* the call already ended.

    Returns a dict with status: 'sent' | 'expired' | 'error'.
    """
    priv = _get_vapid_private_key_pem()
    claim_email = os.environ.get("VAPID_CLAIM_EMAIL", "mailto:admin@example.com")
    if not priv:
        logger.warning("VAPID_PRIVATE_KEY missing; skipping web push")
        return {"status": "error", "reason": "no_vapid_key"}

    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload),
            vapid_private_key=priv,
            vapid_claims={"sub": claim_email},
            ttl=ttl,
            headers={"Urgency": urgency},
        )
        return {"status": "sent"}
    except WebPushException as e:
        status_code = getattr(getattr(e, "response", None), "status_code", None)
        if status_code in (404, 410):
            return {"status": "expired", "reason": str(e)}
        # iter 152 — WebPushException with "Invalid p256dh" / "Invalid auth"
        # messages come from pywebpush's own validation BEFORE the HTTP
        # request is even sent, so there's no status_code. Treat them as
        # terminally broken (expired) so news_push.py deletes the row and
        # the log stops filling up with identical errors each message.
        err_str = str(e)
        if "Invalid p256dh" in err_str or "Invalid auth" in err_str or "ECKey" in err_str:
            return {"status": "expired", "reason": f"malformed: {err_str}"}
        logger.error(f"Web push error: {e}")
        return {"status": "error", "reason": str(e)}
    except ValueError as e:
        # pywebpush raises ValueError on malformed subscriptions — this
        # typically happens when an old subscription has a corrupt p256dh
        # key (seen in production logs iter 148). Mark as 'expired' so
        # the caller treats it the same as a 404/410 and deletes the row
        # from the DB instead of retrying forever.
        logger.warning(f"Web push malformed subscription (marking expired): {e}")
        return {"status": "expired", "reason": f"malformed: {e}"}
    except Exception as e:
        logger.error(f"Web push unexpected error: {e}")
        return {"status": "error", "reason": str(e)}
