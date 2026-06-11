from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from database import db
from dependencies import get_current_user

from ._shared import (
    chat_ws,
)

router = APIRouter()

@router.get("/chat/my-status")
async def get_my_status(request: Request):
    user = await get_current_user(request)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    active_focus = await db.focus_times.find_one(
        {"user_id": user["user_id"], "start_time": {"$lte": now_iso}, "end_time": {"$gte": now_iso}},
        {"_id": 0}
    )
    # Auto-expire DND if dnd_until has passed
    dnd_until = user.get("dnd_until")
    status_mode = user.get("status_mode", "online")
    if status_mode == "dnd" and dnd_until:
        try:
            until_dt = datetime.fromisoformat(dnd_until.replace("Z", "+00:00"))
            if now >= until_dt:
                await db.users.update_one({"user_id": user["user_id"]},
                    {"$set": {"status_mode": "online", "dnd_until": None}})
                status_mode = "online"
                dnd_until = None
        except Exception:
            pass
    # Iter 280 — heartbeat & auto-repair. The fact that the user is making an
    # authenticated request means they're actively using the app. If the DB
    # somehow still has them as "offline" (e.g., a stale WS disconnect
    # finalizer ran after a fast reconnect), promote them back to "online"
    # and refresh `last_seen`. This catches the visible-but-shown-offline
    # symptom users reported.
    if status_mode == "offline":
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {
                "online": True,
                "status_mode": "online",
                "last_seen": now_iso,
            }},
        )
        status_mode = "online"
        # Best-effort: refresh user_cache so a follow-up /auth/me sees it
        try:
            from services import user_cache
            await user_cache.invalidate(user["user_id"])
        except Exception:
            pass
        # Tell peers we're back
        try:
            await chat_ws.broadcast_status(user["user_id"], "online", user.get("name", ""))
        except Exception:
            pass
    else:
        # Even when the status is correct, keep last_seen warm so the
        # "Heute im Büro"/presence-sorted lists stay accurate.
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"last_seen": now_iso}},
        )
    status = "dnd" if active_focus else status_mode
    return {"status_mode": status, "focus": active_focus, "dnd_until": dnd_until}


@router.put("/chat/my-status")
async def set_my_status(request: Request):
    """Manually set the user's presence status.

    Allowed values: 'online', 'away', 'dnd', 'offline'.
    Optional `dnd_until` (ISO timestamp) for temporary DND — auto-expires back to online.
    """
    user = await get_current_user(request)
    body = await request.json()
    status = body.get("status_mode", "online")
    dnd_until = body.get("dnd_until")  # ISO string, optional
    if status not in ("online", "away", "dnd", "offline"):
        raise HTTPException(status_code=400, detail="Ungültiger Status")
    update = {
        "status_mode": status,
        "status_updated_at": datetime.now(timezone.utc).isoformat(),
        # Mark this as a manual pick so the calendar-DND auto-sync
        # (services.calendar_status) leaves it alone for 24 h (iter 148).
        # Cleared on WS disconnect (user logged out / closed the app).
        "status_manually_set_at": datetime.now(timezone.utc).isoformat(),
        "status_auto_dnd": False,
    }
    if status == "dnd" and dnd_until:
        update["dnd_until"] = dnd_until
    else:
        update["dnd_until"] = None
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": update})
    try:
        await chat_ws.broadcast_status(user["user_id"], status, user.get("name", ""))
    except Exception:
        pass
    return {"status_mode": status, "dnd_until": update.get("dnd_until")}


@router.post("/chat/statuses")
async def bulk_statuses(request: Request):
    """Return effective status + last_seen for a list of user_ids.
    Effective status accounts for focus-time override."""
    await get_current_user(request)
    body = await request.json()
    ids = body.get("user_ids", [])
    if not ids or not isinstance(ids, list):
        return {"statuses": {}}
    users = await db.users.find(
        {"user_id": {"$in": ids}},
        {"_id": 0, "user_id": 1, "online": 1, "status_mode": 1, "last_seen": 1}
    ).to_list(500)
    now_iso = datetime.now(timezone.utc).isoformat()
    out = {}
    for u in users:
        uid = u["user_id"]
        if not u.get("online", False):
            effective = "offline"
        else:
            focus = await db.focus_times.find_one(
                {"user_id": uid, "start_time": {"$lte": now_iso}, "end_time": {"$gte": now_iso}},
                {"_id": 0}
            )
            if focus:
                effective = "dnd"
            else:
                effective = u.get("status_mode") or "online"
                if effective == "offline":
                    effective = "online"
        out[uid] = {"status_mode": effective, "last_seen": u.get("last_seen", "")}
    return {"statuses": out}



# ============ GIF SEARCH (Tenor API) ============

