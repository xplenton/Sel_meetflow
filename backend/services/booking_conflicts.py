"""Booking-conflict detection & race-condition winner selection.

Extracted from `routes/resources/_common.py` in iter 346 to keep the routes
package focused on HTTP wiring and to give a single home for the (now quite
non-trivial) conflict-check semantics.

The public API exposed here mirrors the original underscore-prefixed helpers
1:1 so that existing call sites continue to work via thin shims in
`routes/resources/_common.py`:

  - `check_conflicts(...)`        ↔ legacy `_check_conflicts`
  - `verify_booking_winner(...)`  ↔ legacy `_verify_booking_winner`
  - `validate_allowed_combination(...)` ↔ legacy `_validate_allowed_combination`

Conflict rules (Sprint 4, iter 225, kept verbatim from the original):
  - direct overlap on the same resource
  - booking a parent (whole splitable room): any child booking blocks it
  - booking a sub-room: parent booking blocks it
  - sub-rooms can coexist with their siblings
  - `buffer_time_min`: bookings within the buffer window of either side of
    an existing booking are blocked (configurable per resource)
  - blackout / maintenance windows from `db.blackout_periods` are reported
    as `{"reason": "blackout", ...}` conflicts

Iter 248: `verify_booking_winner` resolves a TOCTOU race that occurs when two
concurrent POSTs both pass `check_conflicts`. After inserting, the caller
re-queries; the booking with the alphabetically lowest booking_id wins.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import HTTPException

from database import db


async def check_conflicts(
    resource_id: str,
    start_at: datetime,
    end_at: datetime,
    exclude_booking_id: Optional[str] = None,
) -> List[dict]:
    """Return overlapping bookings + blackout windows for a resource.

    Returns an empty list when the resource is free; otherwise a list of
    conflict dicts (either existing bookings projected to JSON-safe ISO
    strings, or `{"reason": "blackout", ...}` entries).

    Returns `[{"reason": "resource_not_found"}]` if the resource does not exist.
    """
    # Iter 352 — Children/parent/buffer expansion centralised in
    # services.resource_hierarchy so the snapshot + list endpoints share it.
    from services.resource_hierarchy import expand_blocking_ids
    blocking_ids, res, buffer_min = await expand_blocking_ids(resource_id)
    if res is None:
        return [{"reason": "resource_not_found"}]

    # Buffer window expands the query — max of resource's and parent's buffer.
    win_start = start_at - timedelta(minutes=buffer_min)
    win_end = end_at + timedelta(minutes=buffer_min)

    q: dict = {
        "resource_id": {"$in": blocking_ids},
        "status": {"$in": ["confirmed", "pending_approval"]},
        "start_at": {"$lt": win_end},
        "end_at": {"$gt": win_start},
    }
    if exclude_booking_id:
        q["booking_id"] = {"$ne": exclude_booking_id}
    conflicts = await db.resource_bookings.find(q, {"_id": 0}).to_list(50)
    for c in conflicts:
        for k in ("start_at", "end_at", "created_at", "updated_at",
                  "approved_at", "cancelled_at", "checked_in_at", "checked_out_at"):
            if isinstance(c.get(k), datetime):
                c[k] = c[k].isoformat()

    # P0 #2 — Blackout / maintenance time-window check (§4)
    bo = await db.blackout_periods.find({
        "resource_id": {"$in": blocking_ids},
        "start_at": {"$lt": win_end},
        "end_at": {"$gt": win_start},
    }, {"_id": 0}).to_list(50)
    for b in bo:
        for k in ("start_at", "end_at"):
            if isinstance(b.get(k), datetime):
                b[k] = b[k].isoformat()
        conflicts.append({
            "reason": "blackout",
            "title": b.get("title", "Sperrzeit"),
            "resource_id": b.get("resource_id"),
            "start_at": b.get("start_at"),
            "end_at": b.get("end_at"),
        })
    return conflicts


async def verify_booking_winner(
    booking_id: str,
    resource_id: str,
    start_at: datetime,
    end_at: datetime,
) -> List[dict]:
    """Race-condition-safe post-insert verification (iter 248).

    Concurrent inserts may all pass `check_conflicts` since the read+write is
    not atomic. After inserting, re-query for overlapping bookings on the same
    resource and pick a deterministic winner (the alphabetically smallest
    booking_id among those with overlapping windows).

    Read-visibility: under heavy concurrency, a request's verify-query may run
    BEFORE a peer's insert has propagated to the connection pool's read view.
    To address this, a 50 ms settle delay is applied (iter 338 dropped the
    pre-sleep query as redundant — it doubled POST latency without any
    correctness benefit).

    Returns the list of *competing* bookings (excluding `booking_id`):
      - empty list → this booking won, keep it
      - non-empty list → this booking lost, the caller MUST delete it and
        return 409 to the client
    """
    await asyncio.sleep(0.05)
    competitors = await db.resource_bookings.find({
        "resource_id": resource_id,
        "booking_id": {"$ne": booking_id},
        "status": {"$in": ["confirmed", "pending_approval"]},
        "start_at": {"$lt": end_at},
        "end_at": {"$gt": start_at},
    }, {
        "_id": 0, "booking_id": 1, "start_at": 1, "end_at": 1,
        "user_id": 1, "title": 1,
    }).to_list(100)
    if not competitors:
        return []
    min_competitor = min(c["booking_id"] for c in competitors)
    if booking_id < min_competitor:
        return []  # we won
    # We lost — return competitors so the caller can delete + report.
    for c in competitors:
        for k in ("start_at", "end_at"):
            if isinstance(c.get(k), datetime):
                c[k] = c[k].isoformat()
    return competitors


async def validate_allowed_combination(resource_id: str) -> None:
    """If booking a sub-room, ensure the (just-this-sub) combination is
    allowed by the parent's `allowed_combinations` whitelist.

    No-op for parents and for sub-rooms whose parent has no whitelist.
    Raises HTTP 400 with a German message when the combination is not
    permitted.
    """
    res = await db.resources.find_one({"resource_id": resource_id}, {"_id": 0})
    if not res or not res.get("parent_resource_id"):
        return
    parent = await db.resources.find_one(
        {"resource_id": res["parent_resource_id"]},
        {"_id": 0, "allowed_combinations": 1},
    )
    combos = (parent or {}).get("allowed_combinations") or []
    if not combos:
        return  # whitelist empty = anything goes
    sub = res.get("sub_id")
    if any(set(c) == {sub} for c in combos):
        return
    raise HTTPException(400, f"Bereich {sub} ist nicht als Einzelbuchung freigegeben")
