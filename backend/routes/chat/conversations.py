from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from database import db
from dependencies import get_current_user
from services.ws_broker import ws_broker
import uuid

from ._shared import (
    chat_ws, _require_member, _require_admin_or_member,
    _send_system_message,
)

router = APIRouter()


@router.get("/chat/conversations")
async def list_conversations(request: Request):
    """
    Optimised (iter 113): previously this handler issued 3-5 DB queries per
    conversation (one `count_documents` for unread + one `users.find_one` per
    direct-chat peer + one `focus_times.find_one` per peer). For a user with
    50 conversations that meant up to ~200 DB round-trips per page load.

    New strategy: batch-load users + focus_times + unread-counts with
    aggregation pipelines, then merge in Python. Worst case now: 4 DB calls
    total, regardless of how many conversations the user has.
    """
    user = await get_current_user(request)
    uid = user["user_id"]
    # Iter 331 — beide Endpoints müssen exakt die gleichen Convs scannen,
    # sonst weicht die Sidebar-Summe von den Conv-Listen-Badges ab. Vorher
    # nahm /chat/conversations nur 100, /chat/unread-summary nahm 200 → bei
    # >100 Conversations Mismatch. Jetzt beide bis 500.
    convs = await db.conversations.find(
        {"members.user_id": uid},
        {"_id": 0}
    ).sort("updated_at", -1).to_list(500)
    if not convs:
        return []

    # --- batch 1: unread counts for all conversations in a single aggregation
    conv_last_read: dict[str, str | None] = {}
    for c in convs:
        member = next((m for m in c.get("members", []) if m.get("user_id") == uid), None)
        conv_last_read[c["conversation_id"]] = member.get("last_read") if member else None

    # Simple per-conv count; we still need to filter by last_read client-side.
    unread_counts_all = {}
    async for row in db.messages.aggregate([
        {"$match": {
            "conversation_id": {"$in": list(conv_last_read.keys())},
            "sender_id": {"$ne": uid},
        }},
        {"$group": {"_id": "$conversation_id", "items": {"$push": "$created_at"}}},
    ]):
        cid = row["_id"]
        last_read = conv_last_read.get(cid)
        if last_read:
            unread_counts_all[cid] = sum(1 for ts in row["items"] if ts > last_read)
        else:
            unread_counts_all[cid] = len(row["items"])

    # --- batch 2: load all "other" users for direct-conversations in one go
    other_user_ids: set[str] = set()
    for c in convs:
        if c.get("type") == "direct":
            for m in c.get("members", []):
                if m.get("user_id") and m.get("user_id") != uid:
                    other_user_ids.add(m["user_id"])

    users_by_id: dict[str, dict] = {}
    if other_user_ids:
        cursor = db.users.find(
            {"user_id": {"$in": list(other_user_ids)}},
            {"_id": 0, "user_id": 1, "name": 1, "avatar": 1, "online": 1,
             "status_mode": 1, "last_seen": 1},
        )
        async for u in cursor:
            users_by_id[u["user_id"]] = u

    # --- batch 3: active focus_times for those users in one scan
    now_iso = datetime.now(timezone.utc).isoformat()
    focus_user_ids: set[str] = set()
    if other_user_ids:
        async for f in db.focus_times.find(
            {"user_id": {"$in": list(other_user_ids)},
             "start_time": {"$lte": now_iso}, "end_time": {"$gte": now_iso}},
            {"_id": 0, "user_id": 1},
        ):
            focus_user_ids.add(f["user_id"])

    # --- merge results
    for c in convs:
        cid = c["conversation_id"]
        c["unread_count"] = unread_counts_all.get(cid, 0)
        if c.get("type") == "direct":
            other = next((m for m in c.get("members", []) if m.get("user_id") != uid), None)
            if other:
                ou = users_by_id.get(other.get("user_id"), {})
                if ou:
                    c["display_name"] = ou.get("name", "")
                    c["display_avatar"] = ou.get("avatar", "")
                    c["other_online"] = ou.get("online", False)
                    c["other_last_seen"] = ou.get("last_seen", "")
                    other_status = ou.get("status_mode", "offline")
                    if ou.get("online", False):
                        if other.get("user_id") in focus_user_ids:
                            other_status = "dnd"
                        elif other_status not in ("dnd", "busy", "away"):
                            other_status = "online"
                    c["other_status"] = other_status
    return convs

@router.get("/chat/presence")
async def get_presence(request: Request, user_ids: str = ""):
    """Cross-pod online-presence lookup (iter 176.2).

    Returns which of the requested user_ids are currently online (have an
    active WebSocket heartbeat within the last 60 s across ALL pods).
    Falls back to the local in-memory set if Redis is unavailable.

    Query params:
      user_ids — comma-separated list of user_ids to check (max 500).
                 Omit to receive the full set of online users.
    """
    await get_current_user(request)
    ids = [u.strip() for u in user_ids.split(",") if u.strip()][:500] if user_ids else []
    if ws_broker.enabled:
        online_all = set(await ws_broker.online_users())
    else:
        online_all = set(chat_ws.connections.keys())
    if ids:
        return {"online": [uid for uid in ids if uid in online_all]}
    return {"online": list(online_all)}

@router.post("/chat/conversations/{conv_id}/mark-read")
async def mark_read_rest(conv_id: str, request: Request):
    """REST fallback for marking a conversation as read (iter 179).

    Same effect as sending `{"type":"read"}` over WebSocket — updates the
    user's `last_read` and broadcasts a `read-receipt` event to other
    members. Useful for mobile clients where the WS may be paused.
    """
    user = await get_current_user(request)
    now_iso = datetime.now(timezone.utc).isoformat()
    result = await db.conversations.update_one(
        {"conversation_id": conv_id, "members.user_id": user["user_id"]},
        {"$set": {"members.$.last_read": now_iso}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Conversation not found or not a member")
    await chat_ws.send_to_conversation(conv_id, {
        "type": "read-receipt",
        "conversation_id": conv_id,
        "user_id": user["user_id"],
        "user_name": user.get("name", ""),
        "last_read": now_iso,
    }, exclude_user=user["user_id"])
    return {"ok": True, "last_read": now_iso}


@router.get("/chat/conversations/{conv_id}/read-status")
async def get_read_status(conv_id: str, request: Request):
    """Return `last_read` timestamp per member for the given conversation.

    Used by the chat UI to render read-receipts ("Gelesen von X") beneath
    each of the user's own messages.
    """
    user = await get_current_user(request)
    conv = await db.conversations.find_one(
        {"conversation_id": conv_id, "members.user_id": user["user_id"]},
        {"_id": 0, "members": 1},
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    out = {}
    for m in conv.get("members", []):
        if not isinstance(m, dict):
            continue
        uid = m.get("user_id")
        if uid:
            out[uid] = m.get("last_read")
    return {"read_status": out}


@router.get("/chat/unread-summary")
async def get_unread_summary(request: Request):
    """Lightweight counter used by the Sidebar chat badge + quick-access
    popover. Returns just the aggregate unread count plus the top-5
    conversations with unread messages — sorted by most recent activity.

    This is intentionally much cheaper than `/chat/conversations` (skips
    focus_times, skips full user lookups) so it can be polled every ~15s
    from the sidebar without DB pressure.
    """
    user = await get_current_user(request)
    uid = user["user_id"]
    convs = await db.conversations.find(
        {"members.user_id": uid},
        {"_id": 0, "conversation_id": 1, "type": 1, "name": 1,
         "members": 1, "updated_at": 1, "last_message_preview": 1}
    ).sort("updated_at", -1).to_list(500)
    if not convs:
        return {"total_unread": 0, "top": []}
    conv_last_read: dict[str, str | None] = {}
    for c in convs:
        member = next((m for m in c.get("members", []) if m.get("user_id") == uid), None)
        conv_last_read[c["conversation_id"]] = member.get("last_read") if member else None
    unread_counts: dict[str, int] = {}
    # Iter 335 — Performance: instead of $pushing every created_at into an
    # array and counting in Python (O(messages) per call), build a per-conv
    # "last_read" lookup at the $match stage and sum unread directly in
    # MongoDB via $cond. For convs with no last_read we count all messages.
    branches = []
    for cid, lr in conv_last_read.items():
        if lr:
            branches.append({"case": {"$and": [
                {"$eq": ["$conversation_id", cid]},
                {"$gt": ["$created_at", lr]},
            ]}, "then": 1})
        else:
            # No last_read recorded — every msg in this conv counts as unread
            branches.append({"case": {"$eq": ["$conversation_id", cid]}, "then": 1})
    if branches:
        async for row in db.messages.aggregate([
            {"$match": {
                "conversation_id": {"$in": list(conv_last_read.keys())},
                "sender_id": {"$ne": uid},
            }},
            {"$group": {
                "_id": "$conversation_id",
                "cnt": {"$sum": {"$switch": {"branches": branches, "default": 0}}},
            }},
        ]):
            unread_counts[row["_id"]] = int(row.get("cnt") or 0)
    # Resolve display name for direct chats (only for convs with unread>0)
    unread_convs = [(c, unread_counts.get(c["conversation_id"], 0)) for c in convs
                    if unread_counts.get(c["conversation_id"], 0) > 0]
    other_ids = {m.get("user_id") for c, _ in unread_convs if c.get("type") == "direct"
                 for m in (c.get("members") or []) if m.get("user_id") and m.get("user_id") != uid}
    users_by_id: dict[str, dict] = {}
    if other_ids:
        async for u in db.users.find(
            {"user_id": {"$in": list(other_ids)}},
            {"_id": 0, "user_id": 1, "name": 1, "avatar": 1},
        ):
            users_by_id[u["user_id"]] = u
    top = []
    for c, cnt in sorted(unread_convs, key=lambda x: x[0].get("updated_at") or "", reverse=True)[:5]:
        if c.get("type") == "direct":
            other = next((m for m in c.get("members", []) if m.get("user_id") != uid), None)
            ou = users_by_id.get(other.get("user_id"), {}) if other else {}
            display_name = ou.get("name", "") or c.get("name", "")
            display_avatar = ou.get("avatar", "")
        else:
            display_name = c.get("name", "") or "Gruppe"
            display_avatar = ""
        top.append({
            "conversation_id": c["conversation_id"],
            "type": c.get("type"),
            "display_name": display_name,
            "display_avatar": display_avatar,
            "unread_count": cnt,
            "last_message_preview": c.get("last_message_preview", ""),
            "updated_at": c.get("updated_at"),
        })
    return {"total_unread": sum(unread_counts.values()), "top": top}

@router.post("/chat/conversations")
async def create_conversation(request: Request):
    user = await get_current_user(request)
    body = await request.json()
    conv_type = body.get("type", "direct")
    member_ids = body.get("member_ids", [])
    name = body.get("name", "")
    if user["user_id"] not in member_ids:
        member_ids.insert(0, user["user_id"])
    if conv_type == "direct" and len(member_ids) == 2:
        existing = await db.conversations.find_one({
            "type": "direct",
            "members.user_id": {"$all": member_ids},
            "$expr": {"$eq": [{"$size": "$members"}, 2]}
        }, {"_id": 0})
        if existing:
            return existing
        # Iter 323 — DM Opt-In Gate.
        # Only applies to NEW direct conversations (groups bypass the policy,
        # existing DMs work without re-check). Admin override is inside may_dm.
        from services.dm_policy import may_dm
        other_id = next(mid for mid in member_ids if mid != user["user_id"])
        recipient = await db.users.find_one(
            {"user_id": other_id},
            {"_id": 0, "user_id": 1, "role": 1, "department": 1, "dm_policy": 1, "name": 1},
        )
        if not recipient:
            raise HTTPException(404, "Empfaenger nicht gefunden")
        allowed, reason = may_dm(user, recipient)
        if not allowed:
            raise HTTPException(403, reason or "Direkt-Nachricht nicht erlaubt")
    members = []
    for mid in member_ids:
        u = await db.users.find_one({"user_id": mid}, {"_id": 0, "name": 1, "avatar": 1})
        members.append({
            "user_id": mid, "name": u.get("name", "") if u else "",
            "avatar": u.get("avatar", "") if u else "",
            "role": "admin" if mid == user["user_id"] else "member",
            "joined_at": datetime.now(timezone.utc).isoformat(),
            "last_read": datetime.now(timezone.utc).isoformat(),
        })
    conv_id = f"conv_{uuid.uuid4().hex[:10]}"
    conv = {
        "conversation_id": conv_id, "type": conv_type,
        "name": name, "members": members,
        "created_by": user["user_id"],
        "pinned_by": [], "muted_by": [],
        "encrypted": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_message": None,
    }
    await db.conversations.insert_one(conv)
    result = await db.conversations.find_one({"conversation_id": conv_id}, {"_id": 0})
    for mid in member_ids:
        await chat_ws.send_to_user(mid, {"type": "conversation-created", "conversation": result})
    return result

@router.get("/chat/conversations/{conv_id}")
async def get_conversation(conv_id: str, request: Request):
    user = await get_current_user(request)
    conv = await db.conversations.find_one({"conversation_id": conv_id, "members.user_id": user["user_id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Unterhaltung nicht gefunden")
    return conv

@router.put("/chat/conversations/{conv_id}")
async def update_conversation(conv_id: str, request: Request):
    user = await get_current_user(request)
    conv = await db.conversations.find_one({"conversation_id": conv_id, "members.user_id": user["user_id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    body = await request.json()
    updates = {}
    if "name" in body:
        updates["name"] = body["name"]
    if updates:
        await db.conversations.update_one({"conversation_id": conv_id}, {"$set": updates})
    return await db.conversations.find_one({"conversation_id": conv_id}, {"_id": 0})

@router.delete("/chat/conversations/{conv_id}")
async def delete_conversation(conv_id: str, request: Request):
    user = await get_current_user(request)
    conv = await db.conversations.find_one({"conversation_id": conv_id, "members.user_id": user["user_id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    await db.messages.delete_many({"conversation_id": conv_id})
    await db.conversations.delete_one({"conversation_id": conv_id})
    return {"message": "Chat gelöscht"}


@router.put("/chat/conversations/{conv_id}/pin")
async def toggle_pin(conv_id: str, request: Request):
    user = await get_current_user(request)
    conv = await _require_member(conv_id, user["user_id"])
    pinned = conv.get("pinned_by", [])
    if user["user_id"] in pinned:
        await db.conversations.update_one({"conversation_id": conv_id}, {"$pull": {"pinned_by": user["user_id"]}})
        return {"pinned": False}
    else:
        await db.conversations.update_one({"conversation_id": conv_id}, {"$addToSet": {"pinned_by": user["user_id"]}})
        return {"pinned": True}

@router.put("/chat/conversations/{conv_id}/mute")
async def toggle_mute(conv_id: str, request: Request):
    user = await get_current_user(request)
    conv = await _require_member(conv_id, user["user_id"])
    muted = conv.get("muted_by", [])
    if user["user_id"] in muted:
        await db.conversations.update_one({"conversation_id": conv_id}, {"$pull": {"muted_by": user["user_id"]}})
        return {"muted": False}
    else:
        await db.conversations.update_one({"conversation_id": conv_id}, {"$addToSet": {"muted_by": user["user_id"]}})
        return {"muted": True}

# ============ MEMBERS ============

@router.post("/chat/conversations/{conv_id}/members")
async def add_member(conv_id: str, request: Request):
    user = await get_current_user(request)
    # Iter 185 — only existing members (or platform admins) can add
    # other people to a conversation. Previously, ANY logged-in user
    # could add themselves to any conversation just by knowing the
    # conv_id, which leaked group structure and message history.
    await _require_admin_or_member(conv_id, user)
    body = await request.json()
    user_id = body.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id erforderlich")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "name": 1, "avatar": 1})
    if not target:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    member = {
        "user_id": user_id, "name": target.get("name", ""),
        "avatar": target.get("avatar", ""), "role": "member",
        "joined_at": datetime.now(timezone.utc).isoformat(),
        "last_read": datetime.now(timezone.utc).isoformat(),
    }
    await db.conversations.update_one({"conversation_id": conv_id}, {"$addToSet": {"members": member}})
    await _send_system_message(conv_id, f"{target.get('name', '')} wurde hinzugefuegt")
    return await db.conversations.find_one({"conversation_id": conv_id}, {"_id": 0})

@router.delete("/chat/conversations/{conv_id}/members/{member_id}")
async def remove_member(conv_id: str, member_id: str, request: Request):
    user = await get_current_user(request)
    # Iter 185 — only existing members (or admins) can remove someone.
    # A non-member must NEVER be able to manipulate conversation membership.
    # Self-removal (leaving a group) is allowed for any member.
    await _require_admin_or_member(conv_id, user)
    target = await db.users.find_one({"user_id": member_id}, {"_id": 0, "name": 1})
    await db.conversations.update_one({"conversation_id": conv_id}, {"$pull": {"members": {"user_id": member_id}}})
    await _send_system_message(conv_id, f"{target.get('name', '') if target else member_id} wurde entfernt")
    return {"message": "Entfernt"}
