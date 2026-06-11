"""
User-settings routes — notification preferences + delegates (Stellvertreter).
"""
from fastapi import APIRouter, Request, HTTPException

from dependencies import get_current_user
from database import db
from services.notification_prefs import (
    get_prefs,
    update_prefs,
    KNOWN_CATEGORIES,
    KNOWN_CHANNELS,
)

router = APIRouter()


# --- Stellvertreter (Delegates) ---------------------------------------------
# Each user has `users.delegates: [user_id, ...]` — the user_ids of colleagues
# who are authorised to book resources ON BEHALF OF this user. Reverse lookup
# (who-can-book-for-me) is performed by the booking dialog (`bookable-for`).

async def _hydrate_users(user_ids):
    if not user_ids:
        return []
    cursor = db.users.find(
        {"user_id": {"$in": list(user_ids)}, "status": {"$ne": "inactive"}},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "avatar": 1},
    ).sort("name", 1)
    return await cursor.to_list(length=500)


@router.get("/users/me/delegates")
async def get_my_delegates(request: Request):
    """Iter 283 — return the colleagues I authorised to book resources for me."""
    user = await get_current_user(request)
    doc = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "delegates": 1})
    ids = (doc or {}).get("delegates") or []
    return await _hydrate_users(ids)


@router.put("/users/me/delegates")
async def update_my_delegates(request: Request):
    """Iter 283 — set the list of users who may book on my behalf.

    Body: {"user_ids": ["user_xxx", ...]}
    Invalid/inactive/self-reference ids are silently filtered.
    """
    user = await get_current_user(request)
    body = await request.json()
    raw = body.get("user_ids") if isinstance(body, dict) else None
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="user_ids must be a list")
    # Validate against DB to avoid storing junk
    candidates = [u for u in raw if isinstance(u, str) and u and u != user["user_id"]]
    if candidates:
        active = await db.users.find(
            {"user_id": {"$in": candidates}, "status": {"$ne": "inactive"}},
            {"_id": 0, "user_id": 1},
        ).to_list(length=500)
        valid_ids = [u["user_id"] for u in active]
    else:
        valid_ids = []
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"delegates": valid_ids}},
    )
    try:
        from services.user_cache import invalidate as _inv
        await _inv(user["user_id"])
    except Exception:
        pass
    return await _hydrate_users(valid_ids)


@router.get("/users/search")
async def search_users(request: Request, q: str = "", limit: int = 20):
    """Iter 283 — typeahead-search for the delegate picker. Returns max 20."""
    await get_current_user(request)  # auth required
    q = (q or "").strip()
    filt = {"status": {"$ne": "inactive"}}
    if q:
        # case-insensitive prefix-ish match on name OR email
        import re
        rx = re.compile(re.escape(q), re.IGNORECASE)
        filt["$or"] = [{"name": rx}, {"email": rx}]
    cursor = db.users.find(filt, {"_id": 0, "user_id": 1, "name": 1, "email": 1, "avatar": 1}).sort("name", 1).limit(max(1, min(limit, 50)))
    return await cursor.to_list(length=50)


@router.get("/users/bookable-for")
async def list_bookable_users(request: Request):
    """Iter 282/283 — directory used by the booking dialog's "Buchen fuer …"
    picker.

    Two paths return a non-empty list:
      1. Caller has the `resources.book_for_others` capability → full directory
         (admins / assistants with org-wide authority).
      2. Otherwise → only colleagues that have explicitly added the caller as
         their delegate (`users.delegates` contains caller_id). This keeps the
         dropdown short and consent-based for regular users.
    """
    user = await get_current_user(request)
    from services.permissions import has_cap
    if await has_cap(user, "resources.book_for_others", db):
        cursor = db.users.find(
            {"user_id": {"$ne": user["user_id"]}, "status": {"$ne": "inactive"}},
            {"_id": 0, "user_id": 1, "name": 1, "email": 1, "avatar": 1},
        ).sort("name", 1).limit(500)
        return await cursor.to_list(length=500)
    # Delegate-based: find users whose `delegates` list contains me
    cursor = db.users.find(
        {"delegates": user["user_id"], "status": {"$ne": "inactive"}},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "avatar": 1},
    ).sort("name", 1).limit(100)
    return await cursor.to_list(length=100)


@router.get("/users/me/notification-prefs")
async def read_my_notification_prefs(request: Request):
    user = await get_current_user(request)
    data = await get_prefs(user["user_id"])
    data["categories"] = list(KNOWN_CATEGORIES)
    data["channels"] = list(KNOWN_CHANNELS)
    return data


@router.put("/users/me/notification-prefs")
async def update_my_notification_prefs(request: Request):
    user = await get_current_user(request)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be an object")
    return await update_prefs(user["user_id"], body)
