"""Iter 252 — Background-job queue using arq + Redis.

Opt-in queue for long-running operations:
  - Survey PDF generation
  - Recurring-booking generation (>4 weeks ahead)
  - Bulk Slack / Web-push notifications

How it works:
  - `enqueue(name, *args, **kwargs)` pushes a job to Redis
  - A separate `arq_worker.py` process consumes jobs
  - If Redis is unavailable, `enqueue` falls back to running the job inline
    in the current request (degraded mode, logged as warning).

Environment:
  - REDIS_URL — defaults to redis://localhost:6379
  - ENABLE_BACKGROUND_QUEUE — set to "0" to disable entirely (inline mode)

Worker:
  Run separately: `arq services.background_queue.WorkerSettings`
  Or under supervisor as program:queue-worker.
"""
import os
import logging
from typing import Any

logger = logging.getLogger("background_queue")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
ENABLED = os.environ.get("ENABLE_BACKGROUND_QUEUE", "1") != "0"


# --- Task functions (called by the worker) ----------------------------------
# Each task receives the arq context dict as first arg.

async def build_survey_pdf(ctx, survey_id: str) -> bytes:
    """Iter 253 Phase 3 — build a survey PDF in the background.
    Returns raw PDF bytes; arq stores them in Redis until fetched by the
    /api/exports/surveys/jobs/{job_id}/pdf download endpoint."""
    from routes.exports import build_survey_pdf_bytes
    return await build_survey_pdf_bytes(survey_id)


async def noop(ctx, **kwargs) -> dict:
    """Placeholder no-op task for testing the queue infrastructure."""
    return {"ok": True, "echoed": kwargs}


# survey PDF migration deferred — current inline generation is fast enough
# under typical load; revisit if survey reports exceed ~5 MB.


async def send_bulk_push(ctx, post_id: str, sent_by: str = "system") -> dict:
    """Async dispatch of a news-push to all targeted subscribers.
    Called from /news/push/send/async (iter 253). Returns the same dict the
    sync `/news/push/send` returns."""
    from database import db
    from services.news_push import dispatch_push_for_post
    post = await db.news_posts.find_one({"post_id": post_id}, {"_id": 0})
    if not post:
        return {"error": "post not found", "post_id": post_id}
    return await dispatch_push_for_post(post, sent_by=sent_by)


async def generate_recurring_bookings(ctx, user_id: str, weeks: int = 8) -> dict:
    """Generate desk bookings for many weeks ahead (async variant — the sync
    endpoint caps at 8 weeks). Called from
    /users/me/office-days/generate/async (iter 253)."""
    from database import db
    from routes.resources.bookings import generate_office_day_bookings
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        return {"error": "user not found", "user_id": user_id}
    try:
        # Bypass the sync cap by calling the underlying function with an
        # explicit weeks payload.
        return await generate_office_day_bookings({"weeks": weeks}, user)
    except Exception as e:
        return {"error": str(e), "user_id": user_id}


async def filetransfer_expire(ctx) -> dict:
    """Iter 386b — periodic sweep that flips Filetransfer rows past
    `expires_at` to status 'expired'. Wired as an arq cron job below
    (every 10 minutes). Also runs once on worker startup."""
    from routes.filetransfer import expire_outdated
    try:
        n = await expire_outdated()
        return {"expired": n}
    except Exception as e:
        logger.warning(f"filetransfer_expire failed: {e}")
        return {"error": str(e)}


async def filetransfer_expiring_reminders(ctx) -> dict:
    """Iter 386d — emit `filetransfer.expiring` notifications for transfers
    that expire within the next 3 days and haven't been reminded yet.
    Idempotent: each transfer has at most one reminder via the
    `expiring_reminder_sent` flag.

    Iter 387 — additionally dispatch reminder e-mails (analog zu
    `_notify_recipients`): we look up the recipient users, respect their
    `email_preferences.filetransfer_enabled` opt-out flag and call
    `services.email.send_email_real` per recipient. Email failures are
    swallowed so they never break the notification batch.
    """
    from datetime import datetime, timezone, timedelta
    from database import db
    from routes.filetransfer import _now_iso
    from services.email import send_email_real
    now = datetime.now(timezone.utc)
    soon = (now + timedelta(days=3)).isoformat()
    cur = db.file_transfers.find({
        "status": "active",
        "expires_at": {"$lte": soon, "$gt": now.isoformat()},
        "expiring_reminder_sent": {"$ne": True},
        "recipient_user_ids": {"$ne": []},
    }, {"_id": 0})
    sent = 0
    mails_sent = 0
    async for t in cur:
        try:
            recipients = list(t.get("recipient_user_ids") or [])
            owner_name = t.get("owner_name") or "Kollege"
            expires_at = t.get("expires_at") or ""
            link = f"/filetransfer/{t['transfer_id']}"
            title = "Transfer läuft bald ab"
            body = (
                f"Dein Transfer von {owner_name} läuft am {expires_at} ab. "
                f"Lade die Dateien rechtzeitig herunter."
            )
            # In-app notifications
            notif_docs = [{
                "notification_id": f"ftn_exp_{t['transfer_id'][-8:]}_{uid[-6:]}",
                "user_id": uid,
                "type": "filetransfer.expiring",
                "title": title,
                "body": body,
                "link": link,
                "transfer_id": t["transfer_id"],
                "read": False,
                "created_at": _now_iso(),
            } for uid in recipients]
            if notif_docs:
                await db.notifications.insert_many(notif_docs)
            # E-Mail-Versand (best-effort, opt-out via email_preferences)
            if recipients:
                users = await db.users.find(
                    {"user_id": {"$in": recipients}},
                    {"_id": 0, "user_id": 1, "email": 1, "name": 1, "email_preferences": 1},
                ).to_list(500)
                html = (
                    f"<p>{body}</p>"
                    f"<p><a href='{link}'>Im Filetransfer öffnen</a></p>"
                    f"<p style='color:#6B7280;font-size:12px;margin-top:24px'>"
                    f"Du erhältst diese Erinnerung 3 Tage vor Ablauf des Transfers."
                    f"</p>"
                )
                for u in users:
                    if not u.get("email"):
                        continue
                    prefs = u.get("email_preferences") or {}
                    if prefs.get("filetransfer_enabled", True) is False:
                        continue
                    try:
                        await send_email_real(u["email"], title, html, category="filetransfer")
                        mails_sent += 1
                    except Exception as e:
                        logger.warning(
                            f"expiring reminder email failed for {u.get('email')}: {e}"
                        )
            await db.file_transfers.update_one(
                {"transfer_id": t["transfer_id"]},
                {"$set": {"expiring_reminder_sent": True, "expiring_reminder_at": _now_iso()}},
            )
            sent += len(notif_docs)
        except Exception as e:
            logger.warning(f"expiring reminder failed for {t.get('transfer_id')}: {e}")
    return {"reminded": sent, "mails_sent": mails_sent}


# --- Queue helper -----------------------------------------------------------

_pool = None


async def _get_pool():
    """Lazy-init the redis connection pool (worker-local)."""
    global _pool
    if _pool is None:
        from arq.connections import create_pool, RedisSettings
        # Parse REDIS_URL → RedisSettings
        from urllib.parse import urlparse
        u = urlparse(REDIS_URL)
        _pool = await create_pool(RedisSettings(
            host=u.hostname or "localhost",
            port=u.port or 6379,
            database=int((u.path or "/0").lstrip("/") or 0),
        ))
    return _pool


async def enqueue(name: str, *args: Any, **kwargs: Any):
    """Enqueue a job. Falls back to inline execution if queue is disabled or
    Redis is unreachable, so feature code never breaks on missing infra."""
    if not ENABLED:
        return await _inline(name, *args, **kwargs)
    try:
        pool = await _get_pool()
        return await pool.enqueue_job(name, *args, **kwargs)
    except Exception as e:
        logger.warning(f"[bg] enqueue failed ({e}), falling back to inline")
        return await _inline(name, *args, **kwargs)


async def _inline(name: str, *args: Any, **kwargs: Any):
    fn = TASK_MAP.get(name)
    if not fn:
        raise ValueError(f"Unknown background task: {name}")
    return await fn({}, *args, **kwargs)


TASK_MAP = {
    "noop": noop,
    "build_survey_pdf": build_survey_pdf,
    "send_bulk_push": send_bulk_push,
    "generate_recurring_bookings": generate_recurring_bookings,
    "filetransfer_expire": filetransfer_expire,
    "filetransfer_expiring_reminders": filetransfer_expiring_reminders,
}


# --- arq worker settings ----------------------------------------------------

class WorkerSettings:
    """Run with: arq services.background_queue.WorkerSettings"""
    functions = list(TASK_MAP.values())
    from urllib.parse import urlparse as _urlparse
    from arq.connections import RedisSettings as _RS
    from arq.cron import cron as _cron
    _u = _urlparse(REDIS_URL)
    redis_settings = _RS(
        host=_u.hostname or "localhost",
        port=_u.port or 6379,
        database=int((_u.path or "/0").lstrip("/") or 0),
    )
    max_jobs = 10
    job_timeout = 300
    # Iter 386b — every 10 minutes (`*/10`), sweep expired Filetransfers.
    cron_jobs = [
        _cron(filetransfer_expire, minute={0, 10, 20, 30, 40, 50}),
        # Iter 386d — daily at 08:00 UTC: 3-day expiry reminders.
        _cron(filetransfer_expiring_reminders, hour={8}, minute={0}),
    ]
