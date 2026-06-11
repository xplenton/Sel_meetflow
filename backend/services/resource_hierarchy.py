"""Resource-hierarchy helpers.

Centralises the parent/child expansion logic used wherever we need to ask
"which other resources' bookings affect this one?". Iter 351 surfaced the
fact that three independent code paths (`check_conflicts`, `availability_
snapshot`, `availability_only` list filter) each open-coded the same
splittable-room rules — and the snapshot/list paths had drifted, causing
the "Parent shows free while both subrooms are booked" bug.

Public API:
    `expand_blocking_ids(resource_id) -> (ids, resource, parent_buffer)`
    `child_to_parent_map() -> dict[child_id, parent_id]`

Rules (kept verbatim from the original conflict-check):
- A resource is always its own blocker.
- If the resource has a parent (= it's a sub-room), the parent blocks too.
- If the resource is_splitable (= it's a parent), each direct child blocks.
- Buffer-time is the MAX of the resource's own buffer and its parent's buffer.
"""
from __future__ import annotations

from typing import Optional

from database import db


async def expand_blocking_ids(resource_id: str) -> tuple[list[str], Optional[dict], int]:
    """Return the list of resource_ids whose bookings block ``resource_id``.

    Includes ``resource_id`` itself. The second tuple entry is the resource
    document (or ``None`` if not found). The third is the effective
    buffer-time-in-minutes (max of this resource's and its parent's).

    Used by:
    - `services.booking_conflicts.check_conflicts` (with buffer)
    - `routes.resources.bookings.crud.list_bookings` (`availability_only=True`)
    """
    res = await db.resources.find_one({"resource_id": resource_id}, {"_id": 0})
    if not res:
        return [resource_id], None, 0

    ids: list[str] = [resource_id]
    parent_buffer = 0
    if res.get("parent_resource_id"):
        ids.append(res["parent_resource_id"])
        parent = await db.resources.find_one(
            {"resource_id": res["parent_resource_id"]},
            {"_id": 0, "buffer_time_min": 1},
        )
        if parent:
            parent_buffer = int(parent.get("buffer_time_min") or 0)
    if res.get("is_splitable"):
        async for child in db.resources.find(
            {"parent_resource_id": resource_id},
            {"_id": 0, "resource_id": 1},
        ):
            ids.append(child["resource_id"])

    own_buffer = int(res.get("buffer_time_min") or 0)
    return ids, res, max(own_buffer, parent_buffer)


async def child_to_parent_map() -> dict[str, str]:
    """Return a ``{child_id: parent_id}`` map across all sub-rooms.

    Used by `routes.resources.admin.analytics.availability_snapshot` to fold
    each child booking into the parent's availability entry in one bulk pass.
    """
    out: dict[str, str] = {}
    async for r in db.resources.find(
        {"parent_resource_id": {"$ne": None}},
        {"_id": 0, "resource_id": 1, "parent_resource_id": 1},
    ):
        out[r["resource_id"]] = r["parent_resource_id"]
    return out
