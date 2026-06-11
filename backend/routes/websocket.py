from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime, timezone
import jwt
from database import db, logger
from services.ws_manager import ws_manager
from services.ws_metrics import record as ws_record
from dependencies import JWT_SECRET, JWT_ALGORITHM

router = APIRouter()


async def _authenticate_ws(websocket: WebSocket, user_id: str) -> bool:
    """Verify the connecting client's JWT matches the claimed user_id.
    Accepts the token via cookie (primary) or ?token=... query param (fallback
    for clients that can't send cookies, e.g. during OAuth flow). Returns True
    on success. On failure, closes the socket with code 4401 and returns False.
    """
    token = websocket.cookies.get("access_token") or websocket.query_params.get("token")
    if not token:
        ws_record("reject_no_token", user_id=user_id)
        await websocket.close(code=4401)
        logger.warning(f"[ws-auth] reject: no token for claimed user_id={user_id}")
        return False
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        ws_record("reject_invalid", user_id=user_id)
        await websocket.close(code=4401)
        logger.warning(f"[ws-auth] reject: invalid token for claimed user_id={user_id}")
        return False
    if payload.get("user_id") != user_id:
        ws_record("reject_spoof", user_id=user_id, reason=f"token_user={payload.get('user_id')}")
        await websocket.close(code=4403)
        logger.warning(
            f"[ws-auth] reject: token user={payload.get('user_id')} "
            f"tried to impersonate {user_id}"
        )
        return False
    # Optional: enforce token_version (session invalidation)
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "user_id": 1, "token_version": 1})
    if user is None:
        ws_record("reject_user_missing", user_id=user_id)
        await websocket.close(code=4401)
        logger.warning(f"[ws-auth] reject: user not found user_id={user_id}")
        return False
    if int(payload.get("tv", 0) or 0) < int(user.get("token_version", 0) or 0):
        ws_record("reject_stale_tv", user_id=user_id)
        await websocket.close(code=4401)
        logger.warning(f"[ws-auth] reject: stale token_version for user_id={user_id}")
        return False
    ws_record("accept", user_id=user_id)
    return True


@router.websocket("/api/ws/{meeting_id}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, meeting_id: str, user_id: str):
    # SECURITY (iter 101): validate JWT before accepting the connection so an
    # attacker cannot spoof other participants by guessing user_id.
    await websocket.accept()
    if not await _authenticate_ws(websocket, user_id):
        return
    # ws_manager.connect expects an un-accepted socket — but since we already
    # accepted, use a compatible registration path.
    if meeting_id not in ws_manager.rooms:
        ws_manager.rooms[meeting_id] = {}
    existing = list(ws_manager.rooms[meeting_id].keys())
    ws_manager.rooms[meeting_id][user_id] = websocket
    await websocket.send_json({"type": "peers", "peers": existing})
    for uid, peer_ws in ws_manager.rooms[meeting_id].items():
        if uid != user_id:
            try:
                await peer_ws.send_json({"type": "peer-joined", "peer_id": user_id})
            except Exception:
                pass
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type in ["offer", "answer", "ice-candidate"]:
                target = data.get("target")
                if target:
                    data["sender"] = user_id
                    await ws_manager.send_to(meeting_id, target, data)
            elif msg_type == "chat":
                data["sender"] = user_id
                await ws_manager.broadcast(meeting_id, data, exclude=user_id)
            elif msg_type in ["participant-update", "reaction", "hand-raise"]:
                data["sender"] = user_id
                # iter 211 — persist hand_raise so late joiners see the state
                # in /participants. Other event types stay broadcast-only.
                if msg_type == "hand-raise":
                    try:
                        await db.meeting_participants.update_one(
                            {"meeting_id": meeting_id, "user_id": user_id},
                            {"$set": {"hand_raised": bool(data.get("raised"))}},
                        )
                    except Exception:
                        pass
                await ws_manager.broadcast(meeting_id, data, exclude=user_id)
            elif msg_type == "document-page-change":
                await ws_manager.broadcast(meeting_id, {
                    "type": "document-page-change",
                    "doc_id": data.get("doc_id"),
                    "page": data.get("page", 1),
                }, exclude=user_id)
            elif msg_type == "whiteboard-draw":
                data["sender"] = user_id
                await ws_manager.broadcast(meeting_id, data, exclude=user_id)
            elif msg_type == "whiteboard-clear":
                data["sender"] = user_id
                await ws_manager.broadcast(meeting_id, data, exclude=user_id)
                await db.whiteboard_strokes.delete_many({"meeting_id": meeting_id})
            elif msg_type == "whiteboard-undo":
                data["sender"] = user_id
                await ws_manager.broadcast(meeting_id, data, exclude=user_id)
            elif msg_type == "whiteboard-stroke-complete":
                stroke = data.get("stroke")
                if stroke:
                    await db.whiteboard_strokes.insert_one({
                        "meeting_id": meeting_id, "user_id": user_id,
                        "stroke_id": stroke.get("id", ""),
                        "points": stroke.get("points", []),
                        "color": stroke.get("color", "#1C1F1D"),
                        "width": stroke.get("width", 3),
                        "tool": stroke.get("tool", "pen"),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
            elif msg_type == "subtitle":
                data["sender"] = user_id
                await ws_manager.broadcast(meeting_id, data, exclude=user_id)
            elif msg_type == "whiteboard-note":
                data["sender"] = user_id
                await ws_manager.broadcast(meeting_id, data, exclude=user_id)
            elif msg_type == "whiteboard-note-complete":
                note = data.get("note")
                if note:
                    await db.whiteboard_notes.update_one(
                        {"note_id": note.get("id"), "meeting_id": meeting_id},
                        {"$set": {
                            "meeting_id": meeting_id, "note_id": note.get("id"),
                            "x": note.get("x", 0), "y": note.get("y", 0),
                            "text": note.get("text", ""), "color": note.get("color", "#FEF3C7"),
                            "user_id": user_id,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }},
                        upsert=True
                    )
            elif msg_type == "whiteboard-note-delete":
                note_id = data.get("note_id")
                if note_id:
                    await db.whiteboard_notes.delete_one({"note_id": note_id, "meeting_id": meeting_id})
                data["sender"] = user_id
                await ws_manager.broadcast(meeting_id, data, exclude=user_id)
    except WebSocketDisconnect:
        await ws_manager.disconnect(meeting_id, user_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await ws_manager.disconnect(meeting_id, user_id)
