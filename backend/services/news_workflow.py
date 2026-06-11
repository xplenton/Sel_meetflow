"""News approval workflow — submit / approve / reject transitions.

Extracted from routes/news/workflow.py (Iter 93). Each transition writes
an audit-log entry; approve triggers the auto-push side effect when the
final status is 'published' with critical/important priority.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import HTTPException

from database import db

logger = logging.getLogger(__name__)


async def submit_for_review(post_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """Author submits a draft for editorial review."""
    post = await db.news_posts.find_one({"post_id": post_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    if post["author_id"] != user["user_id"] and user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Nur der Autor kann einreichen")
    now = datetime.now(timezone.utc).isoformat()
    await db.news_posts.update_one({"post_id": post_id}, {"$set": {
        "status": "review", "updated_at": now,
        "approval_status": "pending_review",
        "submitted_at": now, "submitted_by": user["user_id"],
    }})
    await db.news_audit.insert_one({
        "action": "submitted_for_review", "post_id": post_id,
        "user_id": user["user_id"], "user_name": user.get("name", ""),
        "timestamp": now, "details": "Zur Prüfung eingereicht",
    })
    return {"message": "Zur Prüfung eingereicht", "status": "review"}


async def approve_review(post_id: str, user: Dict[str, Any], comment: str = "") -> Dict[str, Any]:
    """Redakteur approves and forwards to Freigeber — OR Admin/Freigeber
    publishes directly, triggering auto-push for critical/important posts."""
    from routes.news._helpers import _can_review, _can_approve
    if not await _can_review(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung zur Prüfung")
    post = await db.news_posts.find_one({"post_id": post_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    now = datetime.now(timezone.utc).isoformat()

    if await _can_approve(user):
        # Freigeber / Admin: directly publish
        await db.news_posts.update_one({"post_id": post_id}, {"$set": {
            "status": "published", "approval_status": "approved",
            "published_at": now, "updated_at": now,
            "approved_by": user["user_id"], "approved_at": now,
        }})
        await db.news_audit.insert_one({
            "action": "approved_and_published", "post_id": post_id,
            "user_id": user["user_id"], "user_name": user.get("name", ""),
            "timestamp": now, "details": f"Freigegeben und veroeffentlicht. {comment}",
        })
        updated = await db.news_posts.find_one({"post_id": post_id}, {"_id": 0})
        if updated:
            from services.news_channel_dispatch import dispatch_post_to_channels
            await dispatch_post_to_channels(updated, sent_by=user.get("name", ""))
        return {"message": "Freigegeben und veroeffentlicht", "status": "published"}

    # Redakteur: forward to Freigeber
    await db.news_posts.update_one({"post_id": post_id}, {"$set": {
        "status": "approval", "approval_status": "pending_approval",
        "updated_at": now, "reviewed_by": user["user_id"], "reviewed_at": now,
    }})
    await db.news_audit.insert_one({
        "action": "reviewed", "post_id": post_id,
        "user_id": user["user_id"], "user_name": user.get("name", ""),
        "timestamp": now, "details": f"Geprüft, wartet auf Freigabe. {comment}",
    })
    return {"message": "Geprüft, wartet auf Freigabe", "status": "approval"}


async def reject_post(post_id: str, user: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
    """Redakteur/Freigeber rejects a post back to draft status."""
    from routes.news._helpers import _can_review
    if not await _can_review(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    now = datetime.now(timezone.utc).isoformat()
    await db.news_posts.update_one({"post_id": post_id}, {"$set": {
        "status": "draft", "approval_status": "rejected",
        "updated_at": now, "rejection_reason": reason,
        "rejected_by": user["user_id"], "rejected_at": now,
    }})
    await db.news_audit.insert_one({
        "action": "rejected", "post_id": post_id,
        "user_id": user["user_id"], "user_name": user.get("name", ""),
        "timestamp": now, "details": f"Abgelehnt: {reason}",
    })
    return {"message": "Abgelehnt", "status": "draft"}
