from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime, timezone
from database import db
from services.ws_broker import ws_broker

from ._shared import chat_ws

router = APIRouter()


@router.websocket("/api/ws/chat/{user_id}")
async def chat_websocket(websocket: WebSocket, user_id: str):
    await chat_ws.connect(user_id, websocket)
    await db.users.update_one({"user_id": user_id}, {"$set": {"online": True, "last_seen": datetime.now(timezone.utc).isoformat()}})
    # Iter 176.2 — cross-pod presence via Redis sorted-set
    await ws_broker.mark_online(user_id)
    # Check if user is in focus mode and set status accordingly
    now_iso = datetime.now(timezone.utc).isoformat()
    active_focus = await db.focus_times.find_one(
        {"user_id": user_id, "start_time": {"$lte": now_iso}, "end_time": {"$gte": now_iso}},
        {"_id": 0}
    )
    if active_focus:
        await db.users.update_one({"user_id": user_id}, {"$set": {"status_mode": "dnd"}})
    else:
        # Respect manual override (away/dnd). Only auto-set to 'online' if previously 'offline'.
        existing = await db.users.find_one({"user_id": user_id}, {"_id": 0, "status_mode": 1})
        current = (existing or {}).get("status_mode", "offline")
        if current in ("offline", "", None):
            await db.users.update_one({"user_id": user_id}, {"$set": {"status_mode": "online"}})
    # Notify peers about effective status
    effective = await db.users.find_one({"user_id": user_id}, {"_id": 0, "status_mode": 1, "name": 1})
    if effective:
        try:
            await chat_ws.broadcast_status(user_id, "dnd" if active_focus else effective.get("status_mode", "online"), effective.get("name", ""))
        except Exception:
            pass
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "ping":
                # Keep-alive: clients ping every ~25 s so the ingress/proxy
                # doesn't drop the idle WebSocket. Round-tripping a pong also
                # lets the client detect a silently-dead connection.
                try:
                    await websocket.send_json({"type": "pong", "ts": datetime.now(timezone.utc).isoformat()})
                except Exception:
                    pass
                # Refresh presence heartbeat so the Redis sorted-set doesn't
                # expire the entry (iter 176.2).
                await ws_broker.mark_online(user_id)
            elif msg_type == "typing":
                conv_id = data.get("conversation_id")
                if conv_id:
                    await chat_ws.send_to_conversation(conv_id, {
                        "type": "typing", "conversation_id": conv_id,
                        "user_id": user_id, "user_name": data.get("user_name", "")
                    }, exclude_user=user_id)
            elif msg_type == "read":
                conv_id = data.get("conversation_id")
                if conv_id:
                    now_iso = datetime.now(timezone.utc).isoformat()
                    await db.conversations.update_one(
                        {"conversation_id": conv_id, "members.user_id": user_id},
                        {"$set": {"members.$.last_read": now_iso}}
                    )
                    # Iter 179: broadcast read-receipt to other conversation
                    # members so they can surface "Gelesen" indicators in
                    # real time. Cross-pod via Redis broker.
                    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "name": 1})
                    await chat_ws.send_to_conversation(conv_id, {
                        "type": "read-receipt",
                        "conversation_id": conv_id,
                        "user_id": user_id,
                        "user_name": (u or {}).get("name", ""),
                        "last_read": now_iso,
                    }, exclude_user=user_id)
    except WebSocketDisconnect:
        pass
    finally:
        chat_ws.disconnect(user_id, websocket)
        # Iter 280 — Only flip the user to offline if THIS pod has no other
        # live sockets AND no other pod owns a presence entry for them.
        # Without this guard, a single transient ingress drop (or a second
        # browser tab closing) momentarily flips the user to "offline" even
        # though they are still actively using the app. The cross-pod check
        # uses the same Redis sorted-set the WS broker maintains.
        still_local = chat_ws.is_online_locally(user_id)
        if not still_local:
            await ws_broker.mark_offline(user_id)
        still_anywhere = await ws_broker.is_online(user_id) if not still_local else True
        if not still_anywhere:
            await db.users.update_one(
                {"user_id": user_id},
                {"$set": {
                    "online": False, "status_mode": "offline",
                    "last_seen": datetime.now(timezone.utc).isoformat(),
                    "status_manually_set_at": None, "status_auto_dnd": False,
                }},
            )
            try:
                u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "name": 1})
                await chat_ws.broadcast_status(user_id, "offline", (u or {}).get("name", ""))
            except Exception:
                pass
        else:
            # Other connections remain — keep the user online, just refresh last_seen
            await db.users.update_one(
                {"user_id": user_id},
                {"$set": {"last_seen": datetime.now(timezone.utc).isoformat()}},
            )
