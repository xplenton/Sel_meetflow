"""
News-Push dispatch — extracted from routes/news.py.

Resolves the audience for a news post, filters by DND/Focus-Zeit, dispatches
web-push, records a push_notifications log entry, and prunes expired subscriptions.
"""
from __future__ import annotations

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from database import db

logger = logging.getLogger(__name__)


async def _resolve_audience_subscriptions(post: Dict[str, Any]) -> List[Dict[str, Any]]:
    target_groups = post.get("target_groups", [])
    target_user_ids = post.get("target_user_ids", [])
    if post.get("target_all") or (not target_groups and not target_user_ids):
        return await db.push_subscriptions.find({}, {"_id": 0}).to_list(5000)
    target_uids: List[str] = list(target_user_ids or [])
    if target_groups:
        users_in_grp = await db.users.find(
            {"groups": {"$in": target_groups}}, {"_id": 0, "user_id": 1}
        ).to_list(5000)
        target_uids.extend(u["user_id"] for u in users_in_grp)
    # Dedupe
    target_uids = list(set(target_uids))
    if not target_uids:
        return []
    return await db.push_subscriptions.find(
        {"user_id": {"$in": target_uids}}, {"_id": 0}
    ).to_list(5000)


async def _filter_by_dnd(subs: List[Dict[str, Any]], priority: str) -> tuple:
    """Returns (filtered_subs, skipped_count). Critical priority bypasses DND."""
    if priority == "critical":
        return subs, 0
    now_iso = datetime.now(timezone.utc).isoformat()
    filtered: List[Dict[str, Any]] = []
    skipped = 0
    for sub in subs:
        uid = sub.get("user_id")
        user_doc = await db.users.find_one(
            {"user_id": uid}, {"_id": 0, "status_mode": 1, "dnd_until": 1}
        )
        status = (user_doc or {}).get("status_mode", "online")
        focus = await db.focus_times.find_one(
            {"user_id": uid, "start_time": {"$lte": now_iso}, "end_time": {"$gte": now_iso}},
            {"_id": 0}
        )
        if focus or status == "dnd":
            skipped += 1
            continue
        filtered.append(sub)
    return filtered, skipped


def _build_push_payload(post: Dict[str, Any]) -> Dict[str, Any]:
    frontend_url = (os.environ.get("FRONTEND_URL", "") or "").rstrip("/")
    return {
        "title": f"[{post.get('priority','normal').upper()}] {post.get('title','News')}",
        "body": (post.get("excerpt") or post.get("content", ""))[:160] or "Neue Mitteilung",
        "icon": "/favicon.svg",
        "tag": f"news-{post.get('post_id','')}",
        "url": f"{frontend_url}/news" if frontend_url else "/news",
    }


async def send_push_to_user(user_id: str, *, title: str, body: str, data: Optional[Dict[str, Any]] = None, category: Optional[str] = None) -> Dict[str, Any]:
    """Low-level helper to push a single arbitrary message to a user — used by
    health alerting etc. Returns {sent, errors, expired}.

    Iter 277 — pass `category` (news/meetings/surveys/chat/feedback) to honour
    per-user preferences. Transactional/critical pushes (incoming calls,
    emergency alerts) MUST omit `category` so they always reach the user even
    when normal notifications for that bucket are muted.
    """
    # Per-user preference filter
    if category:
        try:
            from services.notification_prefs import is_allowed
            if not await is_allowed(user_id, category, "push"):
                logger.info(f"[PUSH SUPPRESSED] user={user_id} muted '{category}' (push) — skip")
                return {"sent": 0, "errors": 0, "expired": 0, "subscriptions": 0, "suppressed_by_prefs": True}
        except Exception:
            # Pref-lookup failure must never block a push
            pass
    from services.push import send_web_push
    subs = await db.push_subscriptions.find({"user_id": user_id}, {"_id": 0}).to_list(20)
    payload = {"title": title, "body": (body or "")[:160], "icon": "/favicon.svg", **(data or {})}
    # iter 150 — use `Urgency: high` so iOS actually wakes the screen on
    # a locked device. Without this header APNS/FCM throttles the push.
    is_call = (data or {}).get("kind") in ("meeting_call", "chat_call") or (data or {}).get("urgent") is True
    urgency = "high" if is_call else "normal"
    sent = expired = errors = 0
    for sub in subs:
        res = send_web_push(sub.get("subscription", {}), payload, urgency=urgency)
        st = res.get("status")
        if st == "sent":
            sent += 1
        elif st == "expired":
            expired += 1
            try:
                await db.push_subscriptions.delete_one({"endpoint": sub.get("endpoint")})
            except Exception:
                pass
        else:
            errors += 1
    return {"sent": sent, "errors": errors, "expired": expired, "subscriptions": len(subs)}


async def dispatch_push_for_post(post: Dict[str, Any], sent_by: str = "system") -> Dict[str, Any]:
    """Send web push notifications to target audience for a given news post.
    Returns stats dict {target, sent, expired, errors, skipped_dnd, skipped_prefs, notification_id}."""
    from services.push import send_web_push
    from services.notification_prefs import is_allowed
    subs = await _resolve_audience_subscriptions(post)
    subs, skipped = await _filter_by_dnd(subs, post.get("priority", "normal"))
    payload = _build_push_payload(post)

    sent, expired, errors, skipped_prefs = 0, 0, 0, 0
    urgency = "high" if post.get("priority") in ("high", "critical", "urgent") else "normal"
    is_critical = post.get("priority") in ("critical", "urgent")
    for sub in subs:
        # Iter 183 — honour per-user notification preferences. Critical /
        # urgent priority bypasses user opt-out so emergency broadcasts
        # still reach everyone (already the DND behaviour).
        if not is_critical and not await is_allowed(sub.get("user_id", ""), "news", "push"):
            skipped_prefs += 1
            continue
        res = send_web_push(sub.get("subscription", {}), payload, urgency=urgency)
        status = res.get("status")
        if status == "sent":
            sent += 1
        elif status == "expired":
            expired += 1
            try:
                await db.push_subscriptions.delete_one({"endpoint": sub.get("endpoint")})
            except Exception:
                pass
        else:
            errors += 1

    notif_id = f"notif_{uuid.uuid4().hex[:10]}"
    await db.push_notifications.insert_one({
        "notification_id": notif_id, "post_id": post.get("post_id", ""),
        "title": post.get("title", ""), "priority": post.get("priority", "normal"),
        "target_count": len(subs), "sent": sent, "expired": expired, "errors": errors,
        "skipped_dnd": skipped, "skipped_prefs": skipped_prefs,
        "sent_by": sent_by,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "target": len(subs), "sent": sent, "expired": expired,
        "errors": errors, "skipped_dnd": skipped, "skipped_prefs": skipped_prefs,
        "notification_id": notif_id,
    }
