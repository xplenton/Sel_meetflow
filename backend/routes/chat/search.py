from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any
from datetime import datetime, timezone
from database import db
from dependencies import get_current_user


router = APIRouter()

@router.get("/chat/search")
async def search_messages(request: Request, q: str = "", conv_id: str = None):
    user = await get_current_user(request)
    if not q or len(q) < 2:
        return []
    user_convs = await db.conversations.find({"members.user_id": user["user_id"]}, {"_id": 0, "conversation_id": 1}).to_list(100)
    conv_ids = [c["conversation_id"] for c in user_convs]
    query = {"conversation_id": {"$in": conv_ids}, "deleted": {"$ne": True}, "content": {"$regex": q, "$options": "i"}}
    if conv_id:
        query["conversation_id"] = conv_id
    results = await db.messages.find(query, {"_id": 0}).sort("created_at", -1).to_list(30)
    return results

# ============ USERS LIST (for creating chats) ============

@router.get("/chat/users")
async def chat_users_list(request: Request, q: str = "", limit: int = 200):
    """List users available for chat. Iter 385 — accepts optional `q`
    server-side filter so large tenants (>200 users) can still find any
    user by name/email instead of only the first 200 alphabetical names.
    """
    user = await get_current_user(request)
    # iter 154 — Members of the "Gast" group cannot discover other users.
    from services.guest_visibility import is_guest_user
    if await is_guest_user(user):
        return []
    mongo_q: Dict[str, Any] = {"user_id": {"$ne": user["user_id"]}, "status": {"$ne": "inactive"}}
    q = (q or "").strip()
    if q:
        import re
        rx = re.compile(re.escape(q), re.IGNORECASE)
        mongo_q["$or"] = [{"name": rx}, {"email": rx}]
    limit = max(1, min(int(limit or 200), 500))
    users = await db.users.find(
        mongo_q,
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "avatar": 1,
         "online": 1, "status_mode": 1, "last_seen": 1,
         # Iter 323 — fields needed for the DM-policy gate
         "role": 1, "department": 1, "dm_policy": 1}
    ).sort("name", 1).to_list(limit)
    now_iso = datetime.now(timezone.utc).isoformat()
    # Iter 323 — Pre-compute the DM-policy verdict so the picker can render
    # a lock icon + tooltip without N extra round-trips.
    from services.dm_policy import may_dm
    for u in users:
        if u.get("online", False):
            focus = await db.focus_times.find_one(
                {"user_id": u["user_id"], "start_time": {"$lte": now_iso}, "end_time": {"$gte": now_iso}},
                {"_id": 0}
            )
            u["status_mode"] = "dnd" if focus else u.get("status_mode", "online")
        else:
            u["status_mode"] = "offline"
        allowed, reason = may_dm(user, u)
        u["dm_blocked"] = not allowed
        u["dm_blocked_reason"] = reason
        # Don't leak the raw policy/role to other users — pickers only need
        # to know "can I DM this person?" and why not.
        u.pop("dm_policy", None)
        u.pop("role", None)
        u.pop("department", None)
    return users


# iter 169 — lightweight user-picker for News/Survey targeting. Accessible to
# admins + moderators + redakteur/freigeber roles. Returns a short list
# optimised for UI pickers (no presence/email-prefs detail).
@router.get("/chat/users/for-targeting")
async def users_for_targeting(request: Request, search: str = "", limit: int = 50):
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator", "redakteur", "freigeber"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    q: Dict[str, Any] = {"status": {"$ne": "inactive"}}
    if search:
        import re
        rx = re.compile(re.escape(search.strip()), re.IGNORECASE)
        q["$or"] = [{"name": rx}, {"email": rx}]
    limit = max(1, min(int(limit or 50), 200))
    users = await db.users.find(
        q, {"_id": 0, "user_id": 1, "name": 1, "email": 1, "avatar": 1, "role": 1, "department": 1}
    ).sort("name", 1).to_list(limit)
    return users

