"""
Lightweight MongoDB-based rate limiter.

Uses a fixed-window counter per (key, window_start) document. No external
dependencies. Each `check_rate_limit` call increments the current window's
counter and returns whether the caller is still under the limit.

Typical usage in a FastAPI route:

    from services.rate_limit import enforce_rate_limit
    await enforce_rate_limit(request, key="news.report", limit=5, window_sec=60,
                             per_user_id=user["user_id"])
    ...

On limit-exceeded a 429 is raised automatically. The helper never crashes the
request on DB errors — it fails open (allows through) with a warning log.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request

from database import db

logger = logging.getLogger(__name__)

_indexes_ensured = False


async def _ensure_indexes():
    global _indexes_ensured
    if _indexes_ensured:
        return
    try:
        # TTL 1h — self-purge old windows
        await db.rate_limit_counters.create_index("expires_at", expireAfterSeconds=0)
        await db.rate_limit_counters.create_index([("key", 1), ("subject", 1), ("window_start", 1)], unique=True)
        _indexes_ensured = True
    except Exception as e:
        logger.debug(f"[rate_limit] index ensure failed: {e}")


def _subject(request: Request, per_user_id: Optional[str]) -> str:
    if per_user_id:
        return f"u:{per_user_id}"
    ip = request.client.host if request and request.client else "unknown"
    # Respect common proxy headers if present
    xff = request.headers.get("x-forwarded-for") if request else None
    if xff:
        ip = xff.split(",")[0].strip()
    return f"ip:{ip}"


async def check_rate_limit(*, key: str, subject: str, limit: int, window_sec: int) -> dict:
    """Atomically increment the current window's counter. Returns
    {allowed:bool, current:int, limit:int, retry_after:int}."""
    await _ensure_indexes()
    now = datetime.now(timezone.utc)
    window_start = int(now.timestamp() // window_sec) * window_sec
    expires_at = datetime.fromtimestamp(window_start + window_sec + 300, tz=timezone.utc)
    try:
        doc = await db.rate_limit_counters.find_one_and_update(
            {"key": key, "subject": subject, "window_start": window_start},
            {
                "$inc": {"count": 1},
                "$setOnInsert": {"key": key, "subject": subject, "window_start": window_start,
                                 "expires_at": expires_at, "first_at": now},
                "$set": {"last_at": now},
            },
            upsert=True,
            return_document=True,  # pymongo/motor: returns the new doc
        )
        current = int((doc or {}).get("count", 1))
    except Exception as e:
        # Fail open — never block users on infrastructure errors
        logger.warning(f"[rate_limit] {key}/{subject} DB error: {e} (failing open)")
        return {"allowed": True, "current": 0, "limit": limit, "retry_after": 0}
    retry_after = max(0, (window_start + window_sec) - int(now.timestamp()))
    return {
        "allowed": current <= limit,
        "current": current, "limit": limit, "retry_after": retry_after,
    }


async def enforce_rate_limit(request: Request, *, key: str, limit: int, window_sec: int,
                             per_user_id: Optional[str] = None) -> None:
    """Raises HTTPException 429 when the limit is exceeded."""
    subject = _subject(request, per_user_id)
    result = await check_rate_limit(key=key, subject=subject, limit=limit, window_sec=window_sec)
    if not result["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {limit}/{window_sec}s. Try again in {result['retry_after']}s.",
            headers={"Retry-After": str(result["retry_after"])},
        )
