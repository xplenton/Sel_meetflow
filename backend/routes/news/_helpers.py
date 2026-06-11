"""Shared helpers across the news route sub-modules.
Pulled out of the original monolithic news.py to avoid circular imports
between posts.py / workflow.py / push.py.
"""
from database import db
from services.permissions import has_cap

NEWS_ROLES = ["admin", "moderator", "member"]


async def _can_create(user):
    return await has_cap(user, "news.create", db)


async def _can_review(user):
    return await has_cap(user, "news.review", db)


async def _can_approve(user):
    return await has_cap(user, "news.approve", db)


async def _can_moderate(user):
    return await has_cap(user, "news.moderate", db)


async def _dispatch_push_for_post(post: dict, sent_by: str = "system") -> dict:
    """Thin wrapper to keep backward compat inside routes/news.py; delegates to service."""
    from services.news_push import dispatch_push_for_post
    return await dispatch_push_for_post(post, sent_by=sent_by)
