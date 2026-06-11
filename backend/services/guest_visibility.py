"""Helper: detect whether a user is a "Guest" — members of the `Gast`
group (case-insensitive). Guests have heavily restricted visibility of
other users across the app (iter 154).
"""
from __future__ import annotations
from database import db


async def is_guest_user(user: dict) -> bool:
    """True when the user is in a group named 'Gast' (any case)."""
    group_ids = user.get("groups") or []
    if not group_ids:
        return False
    match = await db.groups.find_one(
        {"group_id": {"$in": group_ids}, "name": {"$regex": "^gast$", "$options": "i"}},
        {"_id": 0, "group_id": 1},
    )
    return match is not None
