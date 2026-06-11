"""
Survey archival helper.

A survey is considered *auto-archivable* when
  * status == 'published'
  * expires_at is set AND lies more than ARCHIVE_GRACE_DAYS days in the past

The auto-archive task flips such surveys to status='archived' and stamps
`archived_at`. Archived surveys are hidden from the normal list + pending-count,
but remain queryable via ?status=archived.

Surveys can also be manually archived/restored by admins or moderators.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from database import db

logger = logging.getLogger(__name__)

ARCHIVE_GRACE_DAYS = 14


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def auto_archive_expired_surveys(grace_days: int = ARCHIVE_GRACE_DAYS) -> Dict[str, Any]:
    """Flip surveys whose expires_at is older than `grace_days` days ago to
    status='archived'. Returns a summary."""
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=grace_days)).isoformat()
    result = await db.surveys.update_many(
        {
            "status": {"$ne": "archived"},
            "expires_at": {"$nin": ["", None], "$lt": cutoff_iso},
        },
        {"$set": {"status": "archived", "archived_at": _iso_now(), "archived_by": "system"}},
    )
    if result.modified_count:
        logger.info(f"[SURVEY_ARCHIVE] auto-archived {result.modified_count} expired surveys (cutoff={cutoff_iso})")
    return {"archived": result.modified_count, "cutoff": cutoff_iso, "grace_days": grace_days}


async def set_archive_state(survey_id: str, archived: bool, actor_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Manually archive/restore a single survey. Returns the updated doc."""
    if archived:
        updates = {"status": "archived", "archived_at": _iso_now(), "archived_by": actor_id or "manual"}
    else:
        updates = {"status": "published", "archived_at": "", "archived_by": ""}
    await db.surveys.update_one({"survey_id": survey_id}, {"$set": updates})
    return await db.surveys.find_one({"survey_id": survey_id}, {"_id": 0})
