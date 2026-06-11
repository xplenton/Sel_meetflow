"""
Background maintenance tasks for MeetFlow — runs in a lightweight asyncio loop
started from server.py on startup. Currently handles:

  * publish-scheduled-news: promotes news posts with status='scheduled' and
    publish_at<=now to status='published' (fires auto-push like manual publish)
  * cleanup-test-data: removes leftover TEST_* test fixtures older than 7 days
    (news / polls / surveys / meetings) to keep dashboards and statistics clean
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from database import db

logger = logging.getLogger(__name__)

PUBLISH_TICK_SECONDS = 60   # Check pending scheduled news once per minute
CLEANUP_TICK_SECONDS = 6 * 60 * 60  # Cleanup every 6 hours

_task: Optional[asyncio.Task] = None


async def _promote_scheduled_news():
    now_iso = datetime.now(timezone.utc).isoformat()
    pending = await db.news_posts.find(
        {"status": "scheduled", "publish_at": {"$lte": now_iso, "$ne": ""}},
        {"_id": 0}
    ).to_list(100)
    if not pending:
        return
    from routes.news import _dispatch_push_for_post  # late import to avoid cycle
    for post in pending:
        await db.news_posts.update_one(
            {"post_id": post["post_id"]},
            {"$set": {"status": "published", "published_at": now_iso, "updated_at": now_iso}}
        )
        await db.news_audit.insert_one({
            "action": "scheduled_publish", "post_id": post["post_id"],
            "user_id": post.get("owner_id") or post.get("author_id", ""),
            "user_name": post.get("owner_name") or post.get("author_name", ""),
            "timestamp": now_iso,
            "details": f"News '{post.get('title','')}' zeitgesteuert veroeffentlicht",
        })
        if post.get("priority") in ("critical", "important"):
            try:
                await _dispatch_push_for_post({**post, "status": "published"},
                                              sent_by=post.get("owner_name") or post.get("author_name", ""))
            except Exception as e:
                logger.warning(f"Scheduled publish push failed: {e}")
        # HTML Newsletter for 'email' channel
        if "email" in (post.get("channels") or []):
            try:
                from services.news_email_newsletter import dispatch_newsletter_for_post
                await dispatch_newsletter_for_post({**post, "status": "published", "published_at": now_iso})
            except Exception as e:
                logger.warning(f"Scheduled publish newsletter failed: {e}")
    logger.info(f"Promoted {len(pending)} scheduled news posts")


async def cleanup_test_data(min_age_days: int = 7) -> dict:
    """Remove TEST_* fixtures older than min_age_days. Returns counts per collection."""
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=min_age_days)
    cutoff_iso = cutoff_dt.isoformat()
    prefix_regex = r"^TEST[_\- ]"
    # news_posts
    n_news = await db.news_posts.delete_many(
        {"title": {"$regex": prefix_regex, "$options": "i"}, "created_at": {"$lt": cutoff_iso}}
    )
    # schedule_polls
    n_polls = await db.schedule_polls.delete_many(
        {"title": {"$regex": prefix_regex, "$options": "i"}, "created_at": {"$lt": cutoff_iso}}
    )
    # surveys
    n_surv = await db.surveys.delete_many(
        {"title": {"$regex": prefix_regex, "$options": "i"}, "created_at": {"$lt": cutoff_iso}}
    )
    # meetings
    n_meet = await db.meetings.delete_many(
        {"title": {"$regex": prefix_regex, "$options": "i"}, "created_at": {"$lt": cutoff_iso}}
    )
    return {
        "news_posts": n_news.deleted_count,
        "schedule_polls": n_polls.deleted_count,
        "surveys": n_surv.deleted_count,
        "meetings": n_meet.deleted_count,
        "cutoff": cutoff_iso,
    }


async def _cleanup_loop_tick():
    from services.health_metrics import log_maintenance_run
    import time as _time
    t0 = _time.time()
    try:
        result = await cleanup_test_data()
        total = sum(v for k, v in result.items() if k != "cutoff")
        if total:
            logger.info(f"Cleanup purged {total} TEST_* items: {result}")
        await log_maintenance_run("cleanup_test_data", total, int((_time.time() - t0) * 1000))
    except Exception as e:
        logger.warning(f"Cleanup tick failed: {e}")
    t0 = _time.time()
    try:
        from services.surveys_archive import auto_archive_expired_surveys
        res = await auto_archive_expired_surveys()
        await log_maintenance_run("auto_archive_surveys", int(res.get("archived", 0)), int((_time.time() - t0) * 1000))
    except Exception as e:
        logger.warning(f"Survey auto-archive tick failed: {e}")
    t0 = _time.time()
    try:
        from services.health_alerts import check_and_alert
        res = await check_and_alert()
        fired = len((res or {}).get("fired") or [])
        await log_maintenance_run("health_alerts_check", fired, int((_time.time() - t0) * 1000))
    except Exception as e:
        logger.warning(f"Health alerts tick failed: {e}")
    t0 = _time.time()
    try:
        from services.caldav_sync import sync_all_enabled_users
        res = await sync_all_enabled_users()
        await log_maintenance_run("caldav_sync", int(res.get("ok", 0)), int((_time.time() - t0) * 1000))
    except Exception as e:
        logger.warning(f"CalDAV sync tick failed: {e}")
    t0 = _time.time()
    try:
        from services.calendar_status import sync_calendar_dnd
        res = await sync_calendar_dnd()
        await log_maintenance_run(
            "calendar_status_sync",
            int(res.get("auto_dnd", 0)) + int(res.get("auto_online", 0)),
            int((_time.time() - t0) * 1000),
        )
    except Exception as e:
        logger.warning(f"Calendar-status sync tick failed: {e}")


async def _main_loop():
    """Runs forever: alternates scheduled-publish ticks and periodic cleanup."""
    last_cleanup_at = 0.0
    loop = asyncio.get_event_loop()
    while True:
        try:
            await _promote_scheduled_news()
            now = loop.time()
            if now - last_cleanup_at >= CLEANUP_TICK_SECONDS:
                await _cleanup_loop_tick()
                last_cleanup_at = now
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Maintenance tick failed: {e}")
        try:
            await asyncio.sleep(PUBLISH_TICK_SECONDS)
        except asyncio.CancelledError:
            raise


def start():
    """Start the background maintenance loop (idempotent)."""
    global _task
    if _task and not _task.done():
        return
    loop = asyncio.get_event_loop()
    _task = loop.create_task(_main_loop())
    logger.info("Maintenance background task started")


def stop():
    global _task
    if _task and not _task.done():
        _task.cancel()
        _task = None
