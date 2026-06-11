"""
User-declared 'busy' time slots — marks a user as unavailable during a given
window for MeetFlow's internal scheduling (booking pages, schedule polls).

Slots can originate from:
    - manual user action: 'busy:manual'
    - marked from an external CalDAV event: 'busy:caldav:{event_hash}'

The source field lets us deduplicate automatic imports and show them with a
slightly different UI (calendar icon) vs. manually-entered blocks.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from database import db

logger = logging.getLogger(__name__)

_indexes_ensured = False


async def _ensure_indexes():
    global _indexes_ensured
    if _indexes_ensured:
        return
    try:
        await db.user_busy_slots.create_index([("user_id", 1), ("start", 1)])
        # Drop the legacy sparse-unique index (treats null as a real value → collisions)
        # and replace with a partial unique index that only applies when source_id exists.
        try:
            await db.user_busy_slots.drop_index("user_id_1_source_id_1")
        except Exception:
            pass
        await db.user_busy_slots.create_index(
            [("user_id", 1), ("source_id", 1)],
            unique=True,
            partialFilterExpression={"source_id": {"$exists": True, "$type": "string"}},
            name="user_id_1_source_id_1_partial",
        )
        _indexes_ensured = True
    except Exception as e:
        logger.debug(f"[busy_slots] index ensure failed: {e}")


async def list_busy_slots(user_id: str, start: Optional[str] = None, end: Optional[str] = None) -> List[Dict[str, Any]]:
    await _ensure_indexes()
    q: Dict[str, Any] = {"user_id": user_id}
    if start:
        q["end"] = {"$gte": start}
    if end:
        q["start"] = {"$lte": end}
    cursor = db.user_busy_slots.find(q, {"_id": 0}).sort("start", 1).limit(500)
    return await cursor.to_list(500)


async def create_busy_slot(user_id: str, *, start_iso: str, end_iso: str,
                           title: str = "", source_id: Optional[str] = None,
                           source: str = "manual") -> Dict[str, Any]:
    """Upsert a busy slot. If source_id is provided (e.g. event_hash) and the
    user already has a block for that source, it's updated in place."""
    await _ensure_indexes()
    if not start_iso or not end_iso:
        raise ValueError("start und end sind erforderlich")
    try:
        s = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
    except Exception:
        raise ValueError("Ungültiges Datumsformat")
    if e <= s:
        raise ValueError("Ende muss nach dem Start liegen")

    slot = {
        "slot_id": f"busy_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "start": s.isoformat(), "end": e.isoformat(),
        "title": (title or "").strip()[:200],
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # Only persist source_id when provided — the sparse unique index treats
    # {source_id: null} as a real indexed value, causing DuplicateKeyError on
    # a second manual slot.
    if source_id:
        slot["source_id"] = source_id
    if source_id:
        existing = await db.user_busy_slots.find_one({"user_id": user_id, "source_id": source_id}, {"_id": 0, "slot_id": 1})
        if existing:
            slot["slot_id"] = existing["slot_id"]
            await db.user_busy_slots.update_one(
                {"user_id": user_id, "source_id": source_id},
                {"$set": slot},
            )
            return slot
    await db.user_busy_slots.insert_one(slot)
    # Remove MongoDB's _id before returning (not JSON serializable)
    slot.pop("_id", None)
    return slot


async def delete_busy_slot(user_id: str, slot_id: str) -> bool:
    res = await db.user_busy_slots.delete_one({"user_id": user_id, "slot_id": slot_id})
    return res.deleted_count > 0


async def is_user_busy(user_id: str, start_iso: str, end_iso: str) -> bool:
    """Cheap check — returns True if ANY busy slot overlaps the window."""
    if not start_iso or not end_iso:
        return False
    # A busy slot [s, e] overlaps [start, end] iff s < end AND e > start
    doc = await db.user_busy_slots.find_one({
        "user_id": user_id,
        "start": {"$lt": end_iso},
        "end": {"$gt": start_iso},
    }, {"_id": 0, "slot_id": 1})
    return doc is not None


async def overlapping_slots(user_id: str, start_iso: str, end_iso: str) -> List[Dict[str, Any]]:
    if not start_iso or not end_iso:
        return []
    cursor = db.user_busy_slots.find({
        "user_id": user_id,
        "start": {"$lt": end_iso},
        "end": {"$gt": start_iso},
    }, {"_id": 0}).sort("start", 1).limit(100)
    return await cursor.to_list(100)
