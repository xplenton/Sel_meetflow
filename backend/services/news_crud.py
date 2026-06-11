"""News post CRUD business logic, extracted from routes/news/posts.py (Iter 89-91).

Behaviour preserved byte-for-byte — only structural changes:
- Route handler just does auth + payload parsing and delegates here.
- Audit logging, auto-push side-effect and newsletter dispatch stay here.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import HTTPException

from database import db

logger = logging.getLogger(__name__)


# Fields that can be PUT/updated via /api/news/posts/{id}
UPDATABLE_POST_FIELDS = [
    "title", "content", "content_html", "excerpt", "cover_image", "attachments",
    "priority", "pinned", "is_mandatory", "categories", "tags",
    "target_groups", "target_all", "status", "publish_at", "expires_at", "comments_enabled",
    "target_departments", "target_locations", "target_professions", "target_roles",
    "target_user_ids",
    "video_url", "embed_url", "external_link", "channels",
]


async def update_news_post(post_id: str, body: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    """Validate permission (moderator OR owner-of-draft), apply whitelisted
    updates, handle publish_at → scheduled coercion, emit audit log, trigger
    auto-push on draft→published transitions. Returns the updated document."""
    from routes.news._helpers import _can_moderate, _can_create
    post = await db.news_posts.find_one({"post_id": post_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    # Moderators can always edit. Anyone with news.create can edit their own drafts.
    is_owner = post.get("author_id") == user["user_id"]
    is_draft = post.get("status") in ("draft",)
    can_mod = await _can_moderate(user)
    can_create = await _can_create(user)
    if not can_mod:
        if not (is_owner and can_create and is_draft):
            raise HTTPException(status_code=403, detail="Keine Berechtigung")

    updates: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    for k in UPDATABLE_POST_FIELDS:
        if k in body:
            updates[k] = body[k]

    if "priority" in updates:
        updates["priority_order"] = {"normal": 0, "important": 1, "critical": 2}.get(updates["priority"], 0)

    # If publish_at is in the future, coerce status to 'scheduled' instead of 'published'
    if updates.get("status") == "published":
        pa_raw = updates.get("publish_at") or post.get("publish_at") or ""
        if pa_raw:
            try:
                pa = datetime.fromisoformat(pa_raw.replace("Z", "+00:00"))
                if pa > datetime.now(timezone.utc):
                    updates["status"] = "scheduled"
            except Exception:
                pass

    # Set published_at when transitioning to published
    if updates.get("status") == "published" and post.get("status") != "published":
        updates["published_at"] = datetime.now(timezone.utc).isoformat()

    await db.news_posts.update_one({"post_id": post_id}, {"$set": updates})

    await db.news_audit.insert_one({
        "action": "updated", "post_id": post_id, "user_id": user["user_id"],
        "user_name": user.get("name", ""), "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": f"News '{post.get('title')}' aktualisiert"
    })

    updated = await db.news_posts.find_one({"post_id": post_id}, {"_id": 0})
    # Fan-out to every selected distribution channel (push/email/signage)
    # when the post transitions *into* published state. See
    # services/news_channel_dispatch.py for why this supersedes the old
    # priority-only push trigger.
    if updates.get("status") == "published" and post.get("status") != "published" and updated:
        from services.news_channel_dispatch import dispatch_post_to_channels
        await dispatch_post_to_channels(updated, sent_by=user.get("name", ""))
    return updated


async def publish_news_post(post_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """Mark a post as published (admin/moderator only), stamp published_at,
    write audit log, and fan out to every selected distribution channel."""
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    now = datetime.now(timezone.utc).isoformat()
    await db.news_posts.update_one({"post_id": post_id}, {"$set": {
        "status": "published", "published_at": now, "updated_at": now
    }})
    await db.news_audit.insert_one({
        "action": "published", "post_id": post_id, "user_id": user["user_id"],
        "user_name": user.get("name", ""), "timestamp": now, "details": "Veroeffentlicht"
    })
    post = await db.news_posts.find_one({"post_id": post_id}, {"_id": 0})
    if post:
        from services.news_channel_dispatch import dispatch_post_to_channels
        await dispatch_post_to_channels(post, sent_by=user.get("name", ""))
    return {"message": "Veroeffentlicht", "published_at": now}


async def create_news_post(body: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    """Build a news post document from body + author, persist it, write audit
    log, and trigger auto-push / newsletter dispatch when applicable.

    Returns the persisted post document (without MongoDB `_id`).
    Raises ValueError on validation issues (caller converts to HTTP 400).
    """
    title = (body.get("title") or "").strip()
    if not title:
        raise ValueError("Titel erforderlich")

    priority = body.get("priority", "normal")
    priority_order = {"normal": 0, "important": 1, "critical": 2}.get(priority, 0)

    post_id = f"news_{uuid.uuid4().hex[:12]}"
    # Page-Owner defaults to author but can be overridden (for delegated responsibility)
    owner_id = body.get("owner_id") or user["user_id"]
    owner_name = body.get("owner_name") or user.get("name", "")
    if body.get("owner_id") and body["owner_id"] != user["user_id"]:
        owner_user = await db.users.find_one({"user_id": body["owner_id"]}, {"_id": 0, "name": 1})
        if owner_user:
            owner_name = owner_user.get("name") or owner_name
    # Channels: distribution targets (intranet/email/push/digital_signage)
    channels = body.get("channels") or ["intranet"]
    # Normalize status: if publish_at in future, status becomes 'scheduled'
    requested_status = body.get("status", "draft")
    publish_at_raw = body.get("publish_at", "")
    now = datetime.now(timezone.utc)
    if requested_status == "published" and publish_at_raw:
        try:
            pa = datetime.fromisoformat(publish_at_raw.replace("Z", "+00:00"))
            if pa > now:
                requested_status = "scheduled"
        except Exception:
            pass
    post = {
        "post_id": post_id,
        "title": title,
        "content": body.get("content", ""),
        "content_html": body.get("content_html", ""),
        "excerpt": body.get("excerpt", ""),
        "cover_image": body.get("cover_image", ""),
        "attachments": body.get("attachments", []),
        "priority": priority,
        "priority_order": priority_order,
        "pinned": body.get("pinned", False),
        "is_mandatory": body.get("is_mandatory", False),
        "categories": body.get("categories", []),
        "tags": body.get("tags", []),
        "target_groups": body.get("target_groups", []),
        "target_all": body.get("target_all", True),
        "target_departments": body.get("target_departments", []),
        "target_locations": body.get("target_locations", []),
        "target_professions": body.get("target_professions", []),
        "target_roles": body.get("target_roles", []),
        "target_user_ids": body.get("target_user_ids", []),
        "channels": channels,
        "status": requested_status,
        "publish_at": publish_at_raw,
        "expires_at": body.get("expires_at", ""),
        "author_id": user["user_id"],
        "author_name": user.get("name", ""),
        "author_avatar": user.get("avatar", ""),
        "owner_id": owner_id,
        "owner_name": owner_name,
        "approval_status": "",
        "comments_enabled": body.get("comments_enabled", True),
        "video_url": body.get("video_url", ""),
        "embed_url": body.get("embed_url", ""),
        "external_link": body.get("external_link", ""),
        "published_at": datetime.now(timezone.utc).isoformat() if requested_status == "published" else "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.news_posts.insert_one(post)
    post.pop("_id", None)

    # Audit log
    await db.news_audit.insert_one({
        "action": "created", "post_id": post_id, "user_id": user["user_id"],
        "user_name": user.get("name", ""), "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": f"News '{title}' erstellt (Status: {post['status']})"
    })

    # Auto push for critical/important posts published immediately + channel fan-out
    if post.get("status") == "published":
        from services.news_channel_dispatch import dispatch_post_to_channels
        await dispatch_post_to_channels(post, sent_by=user.get("name", ""))

    return post
