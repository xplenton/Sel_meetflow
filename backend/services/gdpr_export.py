"""DSGVO / GDPR Self-Service Data Export (iter 188).

Aggregates everything the platform stores about a single user into a
single JSON dump (Article 15 + 20 GDPR — right of access + right of
data portability). Returns plain Python dicts; the route layer wraps
them into a downloadable file.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from database import db


_USER_PRIVATE_FIELDS = {
    # Sensitive fields that must NEVER appear in the export, even though
    # they live on the user document.
    "password_hash", "totp_secret", "totp_pending_secret",
    "totp_recovery_hashes",
}


def _strip_private(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in doc.items() if k not in _USER_PRIVATE_FIELDS}


async def _list(coll, query, projection=None, limit: int = 5000) -> List[Dict]:
    return await coll.find(query, projection or {"_id": 0}).to_list(limit)


async def build_user_export(user: Dict[str, Any]) -> Dict[str, Any]:
    """Build the full GDPR data dump for `user`."""
    uid = user["user_id"]
    email = (user.get("email") or "").lower()

    profile = await db.users.find_one({"user_id": uid}, {"_id": 0})
    profile = _strip_private(profile or {})

    sections: Dict[str, Any] = {
        "_meta": {
            "user_id": uid,
            "email": email,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "format_version": 1,
            "notes": [
                "Diese Datei enthaelt alle personenbezogenen Daten, die MeetFlow zu Ihrem Konto speichert.",
                "Passwoerter und 2FA-Geheimnisse sind aus Sicherheitsgruenden NICHT enthalten.",
                "Anonyme Umfrage-Antworten erscheinen nicht (sind nicht Ihrer Identitaet zugeordnet).",
            ],
        },
        "profile": profile,
    }

    # ---------- News ----------------------------------------------------
    sections["news"] = {
        "authored_posts": await _list(db.news_posts, {"author_id": uid}),
        "comments": await _list(db.news_comments, {"user_id": uid}),
        "reactions": await _list(db.news_reactions, {"user_id": uid}),
        "reads": await _list(db.news_reads, {"user_id": uid}),
        "reports_filed": await _list(db.news_reports, {"reporter_id": uid}),
    }

    # ---------- Surveys -------------------------------------------------
    sections["surveys"] = {
        "responses": await _list(db.survey_responses, {"user_id": uid}),
        "feedback": await _list(db.feedback_entries, {"user_id": uid}),
    }

    # ---------- Meetings ------------------------------------------------
    sections["meetings"] = {
        "hosted": await _list(db.meetings, {"host_id": uid}),
        "participations": await _list(db.meeting_participants, {"user_id": uid}),
        "chat_messages": await _list(db.chat_messages, {"user_id": uid}),
        "polls_created": await _list(db.polls, {"created_by": uid}),
        "questions_asked": await _list(db.questions, {"asked_by": uid}),
        "action_items_assigned": await _list(db.action_items, {"assignee": email}, {"_id": 0}),
        "focus_times": await _list(db.focus_times, {"user_id": uid}),
    }

    # ---------- Chat ----------------------------------------------------
    conv_ids = await db.conversations.distinct(
        "conversation_id", {"members.user_id": uid}
    )
    sections["chat"] = {
        "conversation_ids": conv_ids,
        "messages_sent": await _list(db.messages, {"sender_id": uid}, limit=20000),
    }

    # ---------- Scheduling ---------------------------------------------
    sections["scheduling"] = {
        "polls": await _list(db.scheduling_polls, {"created_by": uid}),
        "votes": await _list(db.scheduling_votes, {"user_id": uid}),
        "bookings": await _list(db.bookings, {"user_id": uid}),
    }

    # ---------- Calendar / external -----------------------------------
    sections["calendar"] = {
        "external_events": await _list(db.external_calendar_events, {"user_id": uid}),
        "busy_slots": await _list(db.user_busy_slots, {"user_id": uid}),
        "caldav_config": _strip_caldav(await db.caldav_configs.find_one({"user_id": uid}, {"_id": 0}) or {}),
    }

    # ---------- Notifications / preferences ----------------------------
    sections["notifications"] = {
        "push_subscriptions": [
            # Don't leak full endpoint URL — only fingerprint length so the user
            # can confirm subscriptions exist.
            {"endpoint_hash": (s.get("endpoint", "") or "")[-12:],
             "browser": s.get("browser"), "created_at": s.get("created_at")}
            for s in await db.push_subscriptions.find({"user_id": uid}, {"_id": 0}).to_list(50)
        ],
        "preferences": (await db.users.find_one({"user_id": uid}, {"_id": 0, "notification_prefs": 1}) or {}).get("notification_prefs"),
    }

    # ---------- Audit & sessions ---------------------------------------
    sections["audit"] = {
        "auth_refresh_log": await _list(db.auth_refresh_log, {"user_id": uid}),
        "permission_changes": await _list(db.audit_logs, {"$or": [{"actor_id": uid}, {"target_user_id": uid}]}),
        "email_preferences_audit": await _list(db.email_preferences_audit, {"$or": [{"user_id": uid}, {"email": email}]}),
    }

    return sections


def _strip_caldav(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Remove the password (only show URL + auth_user)."""
    out = dict(cfg)
    if "password" in out:
        out["password"] = "***hidden***"
    return out
