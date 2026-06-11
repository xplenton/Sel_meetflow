"""News post reactions + comments — social interaction logic.

Extracted from routes/news/posts.py (Iter 94). Keeps the mention/notification
side effects (post author, parent-comment author, @mention pings) next to
the comment creation logic they belong to.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List

from fastapi import HTTPException

from database import db


# ---------- Reactions ----------

async def toggle_reaction(post_id: str, reaction_type: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """Toggle a reaction: same type → remove, different type → change, none → add.

    Iter 253 — race-safe via DB-level unique index on (post_id, user_id) plus
    atomic operations. Under concurrent calls the unique constraint guarantees
    at most ONE reaction document per (post, user).
    """
    # Step 1: try atomic upsert that sets to the new type. If a document already
    # existed with the SAME type, we treat this as "remove" — handled below by
    # a follow-up delete with strict match. ReturnDocument.BEFORE lets us
    # inspect the pre-state in a single round-trip.
    from pymongo import ReturnDocument
    now = datetime.now(timezone.utc).isoformat()
    try:
        pre = await db.news_reactions.find_one_and_update(
            {"post_id": post_id, "user_id": user["user_id"]},
            {
                "$set": {"reaction_type": reaction_type, "updated_at": now},
                "$setOnInsert": {
                    "post_id": post_id, "user_id": user["user_id"],
                    "user_name": user.get("name", ""),
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.BEFORE,
        )
    except Exception as e:
        # DuplicateKeyError race window with the unique index — retry once,
        # because the doc now definitely exists.
        msg = str(e).lower()
        if "duplicate" in msg or "e11000" in msg:
            pre = await db.news_reactions.find_one(
                {"post_id": post_id, "user_id": user["user_id"]}
            )
            if pre and pre.get("reaction_type") != reaction_type:
                await db.news_reactions.update_one(
                    {"post_id": post_id, "user_id": user["user_id"]},
                    {"$set": {"reaction_type": reaction_type, "updated_at": now}},
                )
        else:
            raise

    if pre is None:
        return {"action": "added", "reaction_type": reaction_type}
    if pre.get("reaction_type") == reaction_type:
        # User clicked the same reaction → remove. Strict match so we don't
        # delete a concurrent change.
        await db.news_reactions.delete_one(
            {"post_id": post_id, "user_id": user["user_id"], "reaction_type": reaction_type}
        )
        return {"action": "removed", "reaction_type": reaction_type}
    return {"action": "changed", "reaction_type": reaction_type}


# ---------- Comments ----------

async def list_comments(post_id: str) -> List[Dict[str, Any]]:
    """Return non-deleted comments for a post, with attachment metadata enriched."""
    comments = await db.news_comments.find(
        {"post_id": post_id, "deleted": {"$ne": True}}, {"_id": 0}
    ).sort("created_at", 1).to_list(500)
    all_ids: List[str] = []
    for c in comments:
        all_ids.extend(c.get("attachments") or [])
    if all_ids:
        from routes.attachments import fetch_attachments_meta
        metas = await fetch_attachments_meta(all_ids)
        by_id = {m["attachment_id"]: m for m in metas}
        for c in comments:
            c["attachments"] = [by_id[a] for a in (c.get("attachments") or []) if a in by_id]
    else:
        for c in comments:
            c["attachments"] = []
    return comments


_MENTION_RE = re.compile(r"@([A-Za-z0-9_\u00C0-\u017F\.\-]+)")


async def _collect_notification_recipients(
    post_id: str, comment_content: str, parent_id: str,
    user: Dict[str, Any], post: Dict[str, Any] | None,
) -> tuple[set, str]:
    """Figure out who to notify + the strongest notification type (reply/mention/comment)."""
    recipients: set = set()
    notif_type = "news_comment"
    if parent_id:
        parent = await db.news_comments.find_one({"comment_id": parent_id}, {"_id": 0, "user_id": 1})
        if parent and parent.get("user_id") and parent["user_id"] != user["user_id"]:
            recipients.add(parent["user_id"])
            notif_type = "news_reply"
    if post and post.get("author_id") and post["author_id"] != user["user_id"]:
        recipients.add(post["author_id"])
    mentioned_names = _MENTION_RE.findall(comment_content)
    if mentioned_names:
        mentioned_users = await db.users.find(
            {"$or": [{"name": {"$in": mentioned_names}}, {"email": {"$in": mentioned_names}}]},
            {"_id": 0, "user_id": 1, "name": 1},
        ).to_list(50)
        for mu in mentioned_users:
            if mu["user_id"] != user["user_id"]:
                recipients.add(mu["user_id"])
                notif_type = "news_mention"
    return recipients, notif_type


async def add_comment(post_id: str, body: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    """Append a new comment to a post. Sends notifications to the post author,
    parent-comment author and any @-mentioned users."""
    post = await db.news_posts.find_one(
        {"post_id": post_id}, {"_id": 0, "comments_enabled": 1, "title": 1, "author_id": 1, "author_name": 1}
    )
    if post and post.get("comments_enabled") is False:
        raise HTTPException(status_code=403, detail="Kommentare sind für diesen Beitrag deaktiviert")
    content = (body.get("content") or "").strip()
    parent_id = body.get("parent_id")
    attachments = [str(a) for a in (body.get("attachments") or []) if isinstance(a, str)][:10]
    if not content and not attachments:
        raise HTTPException(status_code=400, detail="Inhalt oder Anhang erforderlich")
    comment_id = f"cmt_{uuid.uuid4().hex[:10]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    comment = {
        "comment_id": comment_id, "post_id": post_id,
        "parent_id": parent_id,
        "user_id": user["user_id"], "user_name": user.get("name", ""),
        "user_avatar": user.get("avatar", ""),
        "content": content, "deleted": False,
        "attachments": attachments,
        "created_at": now_iso,
    }
    await db.news_comments.insert_one(comment)
    comment.pop("_id", None)
    if attachments:
        from routes.attachments import fetch_attachments_meta
        comment["attachments"] = await fetch_attachments_meta(attachments)

    recipients, notif_type = await _collect_notification_recipients(
        post_id, content, parent_id, user, post
    )
    for rid in recipients:
        await db.notifications.insert_one({
            "notification_id": f"notif_{uuid.uuid4().hex[:10]}",
            "user_id": rid,
            "type": notif_type,
            "title": f"{user.get('name', 'Jemand')} " + (
                "hat dich erwaehnt" if notif_type == "news_mention"
                else "hat auf deinen Kommentar geantwortet" if notif_type == "news_reply"
                else "hat einen Kommentar geschrieben"
            ),
            "body": content[:120],
            "post_id": post_id,
            "post_title": (post or {}).get("title", ""),
            "comment_id": comment_id,
            "from_user_id": user["user_id"],
            "from_user_name": user.get("name", ""),
            "read": False,
            "created_at": now_iso,
        })
    return comment
