"""
News channel dispatcher — central place that fans out a freshly published
news post to every selected distribution channel (iter 130).

Before this module existed, channel fan-out was scattered across
`news_crud.py` and `news_workflow.py` and — critically — the **push**
channel only fired when `priority in (critical, important)`, so users
who explicitly picked "Push" as a channel but left priority on "normal"
got nothing. This helper honors every channel the user picked, plus
keeps the priority-based auto-push for truly urgent content.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def dispatch_post_to_channels(post: Dict[str, Any], sent_by: str = "system") -> None:
    """Fire-and-forget fan-out: inspects `post.channels` and dispatches on each.

    Channels currently supported:
      - `intranet` — implicit (all users see it in-app via News feed). No-op.
      - `email`    — HTML newsletter (handled by `news_email_newsletter`).
      - `push`     — web-push notification (handled by `news_push`).
      - `digital_signage` — post is tagged `signage_eligible=true` so the
        `/api/news/digital-signage/feed` can return it to lobby/hall TVs.
        The display itself polls that feed, so no active push is needed.

    Non-blocking: all dispatches except signage-tagging happen as
    `asyncio.create_task` so a slow SMTP or web-push batch never blocks
    the HTTP response.
    """
    if not post or post.get("status") != "published":
        return
    channels = set(post.get("channels") or ["intranet"])

    # Push — explicit channel OR implicit auto-push for critical/important
    should_push = "push" in channels or post.get("priority") in ("critical", "important")
    if should_push:
        async def _push():
            try:
                from services.news_push import dispatch_push_for_post
                await dispatch_push_for_post(post, sent_by=sent_by)
            except Exception as e:
                logger.error(f"Push dispatch failed for post {post.get('post_id')}: {e}")
        asyncio.create_task(_push())

    # Email newsletter
    if "email" in channels:
        async def _email():
            try:
                from services.news_email_newsletter import dispatch_newsletter_for_post
                await dispatch_newsletter_for_post(post)
            except Exception as e:
                logger.error(f"Newsletter dispatch failed for post {post.get('post_id')}: {e}")
        asyncio.create_task(_email())

    # Digital signage — mark the post as eligible for the signage feed
    if "digital_signage" in channels:
        try:
            from database import db
            await db.news_posts.update_one(
                {"post_id": post.get("post_id")},
                {"$set": {"signage_eligible": True}},
            )
        except Exception as e:
            logger.error(f"Signage flag failed for post {post.get('post_id')}: {e}")
