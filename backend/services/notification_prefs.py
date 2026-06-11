"""
Per-user notification preferences (iter 183).

Each user has a preferences document at db.notification_prefs[user_id]
with one entry per (category, channel) tuple, e.g.:

    {
      "user_id": "user_123",
      "prefs": {
        "news":     {"email": True,  "push": True},
        "meetings": {"email": True,  "push": True},
        "surveys":  {"email": False, "push": True},
        "chat":     {"email": False, "push": True},
        "feedback": {"email": True,  "push": False},
      },
      "quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00"},
    }

`category` is a free-form string but UI offers the 5 above.
`channel` is "email" or "push".

Call `is_allowed(user_id, category, channel)` before firing any notification
— it reads the user's prefs (default=True for unknown categories, preserving
the old behaviour) and honours quiet-hours for push.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from database import db

logger = logging.getLogger(__name__)

# Sensible defaults — what a fresh user gets before they visit the settings
DEFAULT_PREFS: Dict[str, Dict[str, bool]] = {
    "news":     {"email": True,  "push": True},
    "meetings": {"email": True,  "push": True},
    "surveys":  {"email": True,  "push": True},
    "chat":     {"email": False, "push": True},
    "feedback": {"email": True,  "push": False},
}

KNOWN_CATEGORIES = list(DEFAULT_PREFS.keys())
KNOWN_CHANNELS = ("email", "push")


async def get_prefs(user_id: str) -> Dict[str, Any]:
    """Return the user's prefs doc, filling in defaults for missing keys."""
    if not user_id:
        return {"prefs": DEFAULT_PREFS, "quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00"}, "checkin_reminder_minutes": 15, "checkout_reminder_enabled": True}
    doc = await db.notification_prefs.find_one({"user_id": user_id}, {"_id": 0}) or {}
    stored = doc.get("prefs") or {}
    # Merge: user-stored overrides default, but unknown user-added keys are kept
    merged: Dict[str, Dict[str, bool]] = {}
    for cat, defaults in DEFAULT_PREFS.items():
        merged[cat] = {
            ch: bool(stored.get(cat, {}).get(ch, defaults[ch])) for ch in KNOWN_CHANNELS
        }
    # Include any additional categories the user might have
    for cat, chans in stored.items():
        if cat not in merged and isinstance(chans, dict):
            merged[cat] = {ch: bool(chans.get(ch, True)) for ch in KNOWN_CHANNELS}
    return {
        "prefs": merged,
        "quiet_hours": doc.get("quiet_hours") or {"enabled": False, "start": "22:00", "end": "07:00"},
        "checkin_reminder_minutes": int(doc.get("checkin_reminder_minutes", 15)),
        "checkout_reminder_enabled": bool(doc.get("checkout_reminder_enabled", True)) if doc.get("checkout_reminder_enabled") is not None else True,
    }


async def update_prefs(user_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """Partially update a user's prefs document.

    `patch` may contain:
      prefs: partial dict {category: {channel: bool}}
      quiet_hours: {enabled, start, end}
      checkin_reminder_minutes: int (0..240) — minutes BEFORE booking start
        for the "Bitte einchecken"-reminder (Iter 283). 0 disables it.
      checkout_reminder_enabled: bool — send "Bitte auschecken" reminder when
        a booking's end_at has passed without check-out (Iter 283).
    """
    if not user_id:
        raise ValueError("user_id required")
    current = await db.notification_prefs.find_one({"user_id": user_id}, {"_id": 0}) or {}
    stored_prefs = current.get("prefs") or {}

    prefs_patch = patch.get("prefs") if isinstance(patch.get("prefs"), dict) else None
    if prefs_patch:
        for cat, chans in prefs_patch.items():
            if not isinstance(chans, dict):
                continue
            cur = stored_prefs.get(cat, {})
            for ch, val in chans.items():
                if ch in KNOWN_CHANNELS:
                    cur[ch] = bool(val)
            stored_prefs[cat] = cur

    quiet = current.get("quiet_hours") or {"enabled": False, "start": "22:00", "end": "07:00"}
    qh_in = patch.get("quiet_hours") if isinstance(patch.get("quiet_hours"), dict) else None
    if qh_in:
        if "enabled" in qh_in:
            quiet["enabled"] = bool(qh_in["enabled"])
        for k in ("start", "end"):
            v = qh_in.get(k)
            if isinstance(v, str) and len(v) in (4, 5) and ":" in v:
                quiet[k] = v

    # Iter 283 — resource booking reminder configuration (per user)
    checkin_min = current.get("checkin_reminder_minutes")
    if checkin_min is None:
        checkin_min = 15
    if "checkin_reminder_minutes" in patch:
        try:
            checkin_min = max(0, min(240, int(patch["checkin_reminder_minutes"])))
        except Exception:
            pass
    checkout_enabled = current.get("checkout_reminder_enabled")
    if checkout_enabled is None:
        checkout_enabled = True
    if "checkout_reminder_enabled" in patch:
        checkout_enabled = bool(patch["checkout_reminder_enabled"])

    await db.notification_prefs.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "prefs": stored_prefs,
            "quiet_hours": quiet,
            "checkin_reminder_minutes": checkin_min,
            "checkout_reminder_enabled": checkout_enabled,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return await get_prefs(user_id)


def _is_in_quiet_hours(quiet: Dict[str, Any]) -> bool:
    """True if the current UTC-converted-to-local HH:MM sits inside the
    user's quiet window. Quiet-hours wrap across midnight (22:00 → 07:00)."""
    if not quiet or not quiet.get("enabled"):
        return False
    try:
        # We don't know the user's TZ — treat quiet hours as server-local.
        # Future improvement: store tz on the user doc and convert here.
        now = datetime.now().strftime("%H:%M")
        start = quiet.get("start") or "22:00"
        end = quiet.get("end") or "07:00"
        if start <= end:
            return start <= now <= end
        # Wraps midnight: inside if now >= start OR now <= end
        return now >= start or now <= end
    except Exception:
        return False


async def is_allowed(user_id: str, category: str, channel: str) -> bool:
    """Check if a given notification should be delivered to the user.

    Safe defaults:
      * unknown user_id → True (preserve current behaviour)
      * unknown category → True (don't silently drop new notification types)
      * unknown channel → True
      * quiet-hours only applies to `push`, never to `email`
    """
    if not user_id or channel not in KNOWN_CHANNELS:
        return True
    try:
        doc = await get_prefs(user_id)
    except Exception as e:
        logger.warning(f"[notif_prefs] read failed for {user_id}: {e}")
        return True
    cat_prefs = doc["prefs"].get(category)
    if cat_prefs is None:
        return True
    if not cat_prefs.get(channel, True):
        return False
    if channel == "push" and _is_in_quiet_hours(doc["quiet_hours"]):
        return False
    return True
