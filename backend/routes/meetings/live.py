from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File
import uuid
import time as _time
from datetime import datetime, timezone
from database import db
from dependencies import get_current_user
from services.ws_manager import ws_manager

# Iter 172 (perf): module-level TTL cache for dashboard stats (60s per user)
_DASHBOARD_CACHE: "dict[str, tuple[float, dict]]" = {}
# Iter 335 (perf): same idea for /calendar/events — 30s TTL is short enough
# to keep RSVP updates fresh but smooths repeat polls from the calendar page.
_CALENDAR_CACHE: "dict[str, tuple[float, list]]" = {}
from models import (
    OrganizationRequest, ActionItemRequest
)

router = APIRouter()


@router.post("/meetings/{meeting_id}/recording/start")
async def start_recording(meeting_id: str, request: Request):
    from services.meetings_av import start_recording as _start
    user = await get_current_user(request)
    return await _start(meeting_id, user)

@router.post("/meetings/{meeting_id}/recording/stop")
async def stop_recording(meeting_id: str, request: Request):
    from services.meetings_av import stop_recording as _stop
    user = await get_current_user(request)
    return await _stop(meeting_id, user)

@router.post("/meetings/{meeting_id}/recording/upload")
async def upload_recording(meeting_id: str, request: Request, file: UploadFile = File(...)):
    from services.meetings_av import upload_recording as _upload
    user = await get_current_user(request)
    data = await file.read()
    return await _upload(meeting_id, file.filename or "", file.content_type or "", data, user)

@router.get("/meetings/{meeting_id}/recording/play/{filename}")
async def play_recording(meeting_id: str, filename: str):
    from services.meetings_av import play_recording as _play
    data, ct = await _play(meeting_id, filename)
    return Response(content=data, media_type=ct or "video/webm")

@router.post("/meetings/{meeting_id}/transcript/start")
async def start_transcript(meeting_id: str, request: Request):
    from services.meetings_av import start_transcript as _start
    await get_current_user(request)
    return await _start(meeting_id)

@router.post("/meetings/{meeting_id}/transcript/stop")
async def stop_transcript(meeting_id: str, request: Request):
    from services.meetings_av import stop_transcript as _stop
    user = await get_current_user(request)
    return await _stop(meeting_id, user)




@router.post("/meetings/{meeting_id}/breakout-rooms/auto-assign")
async def auto_assign_breakout(meeting_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    room_count = body.get("room_count", 2)
    rooms = await db.breakout_rooms.find({"meeting_id": meeting_id}, {"_id": 0}).to_list(20)
    participants = await db.meeting_participants.find(
        {"meeting_id": meeting_id, "role": {"$nin": ["host"]}, "joined_at": {"$ne": None}, "left_at": None}, {"_id": 0}
    ).to_list(100)
    while len(rooms) < room_count:
        room = {
            "room_id": f"br_{uuid.uuid4().hex[:10]}", "meeting_id": meeting_id,
            "name": f"Room {len(rooms) + 1}", "participant_ids": [],
            "status": "open", "created_by": user["user_id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.breakout_rooms.insert_one(room)
        rooms.append(room)
    for i, p in enumerate(participants):
        room_idx = i % len(rooms)
        await db.breakout_rooms.update_one(
            {"room_id": rooms[room_idx]["room_id"]},
            {"$addToSet": {"participant_ids": p["user_id"]}}
        )
    updated = await db.breakout_rooms.find({"meeting_id": meeting_id}, {"_id": 0}).to_list(20)
    return updated

@router.post("/meetings/{meeting_id}/breakout-rooms/broadcast")
async def broadcast_breakout(meeting_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    message = body.get("message", "")
    rooms = await db.breakout_rooms.find({"meeting_id": meeting_id, "status": "open"}, {"_id": 0}).to_list(20)
    for room in rooms:
        msg = {
            "message_id": f"msg_{uuid.uuid4().hex[:10]}", "meeting_id": meeting_id,
            "user_id": "system", "user_name": f"[Broadcast] {user['name']}",
            "avatar": "", "message": message, "message_type": "host",
            "room_id": room["room_id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.chat_messages.insert_one(msg)
    await ws_manager.broadcast(meeting_id, {
        "type": "breakout-broadcast", "message": message,
        "by": user.get("name", ""), "rooms": len(rooms),
    })
    return {"broadcast": True, "rooms": len(rooms)}

@router.post("/meetings/{meeting_id}/breakout-rooms/close-all")
async def close_all_breakout(meeting_id: str, request: Request):
    await get_current_user(request)
    await db.breakout_rooms.update_many({"meeting_id": meeting_id}, {"$set": {"status": "closed"}})
    await ws_manager.broadcast(meeting_id, {"type": "breakout-ended"})
    return {"status": "all_closed"}

@router.post("/meetings/{meeting_id}/breakout-rooms/start")
async def start_breakout_session(meeting_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    duration = body.get("duration", 600)  # default 10 min
    rooms = await db.breakout_rooms.find({"meeting_id": meeting_id, "status": "open"}, {"_id": 0}).to_list(20)
    if not rooms:
        raise HTTPException(status_code=400, detail="No open breakout rooms")
    await db.meetings.update_one({"meeting_id": meeting_id}, {"$set": {
        "breakout_active": True,
        "breakout_started_at": datetime.now(timezone.utc).isoformat(),
        "breakout_duration": duration,
    }})
    await ws_manager.broadcast(meeting_id, {
        "type": "breakout-started",
        "rooms": [{
            "room_id": r["room_id"], "name": r["name"],
            "participant_ids": r.get("participant_ids", []),
        } for r in rooms],
        "duration": duration,
        "by": user.get("name", ""),
    })
    return {"started": True, "rooms": len(rooms), "duration": duration}

@router.post("/meetings/{meeting_id}/breakout-rooms/end")
async def end_breakout_session(meeting_id: str, request: Request):
    user = await get_current_user(request)
    await db.breakout_rooms.update_many({"meeting_id": meeting_id}, {"$set": {"status": "closed"}})
    await db.meetings.update_one({"meeting_id": meeting_id}, {"$set": {"breakout_active": False}})
    await ws_manager.broadcast(meeting_id, {
        "type": "breakout-ended", "by": user.get("name", ""),
    })
    return {"ended": True}




@router.post("/meetings/{meeting_id}/chat/announcement")
async def send_announcement(meeting_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    hp = await db.meeting_participants.find_one({"meeting_id": meeting_id, "user_id": user["user_id"]}, {"_id": 0})
    if not hp or hp["role"] not in ["host", "co-host"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    msg = {
        "message_id": f"msg_{uuid.uuid4().hex[:10]}", "meeting_id": meeting_id,
        "user_id": user["user_id"], "user_name": user["name"],
        "avatar": user.get("avatar", ""), "message": body.get("message", ""),
        "message_type": "host", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.chat_messages.insert_one(msg)
    return await db.chat_messages.find_one({"message_id": msg["message_id"]}, {"_id": 0})




@router.get("/organization")
async def get_organization(request: Request):
    org = await db.organizations.find_one({}, {"_id": 0})
    if not org:
        return {"name": "Default Organization", "domain": "", "description": "", "member_count": await db.users.count_documents({})}
    org["member_count"] = await db.users.count_documents({})
    return org

@router.put("/organization")
async def update_organization(req: OrganizationRequest, request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    updates = {"name": req.name, "domain": req.domain, "description": req.description, "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.organizations.update_one({}, {"$set": updates}, upsert=True)
    return await db.organizations.find_one({}, {"_id": 0})




@router.get("/meetings/{meeting_id}/attendance")
async def get_attendance(meeting_id: str, request: Request):
    await get_current_user(request)
    events = await db.attendance_events.find({"meeting_id": meeting_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
    participants = await db.meeting_participants.find({"meeting_id": meeting_id}, {"_id": 0}).to_list(200)
    return {"events": events, "participants": participants}

@router.post("/meetings/{meeting_id}/attendance")
async def log_attendance(meeting_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    event = {
        "event_id": f"evt_{uuid.uuid4().hex[:10]}", "meeting_id": meeting_id,
        "user_id": user["user_id"], "event_type": body.get("event_type", "join"),
        "metadata": body.get("metadata", {}),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.attendance_events.insert_one(event)
    return await db.attendance_events.find_one({"event_id": event["event_id"]}, {"_id": 0})




@router.get("/meetings/{meeting_id}/insights")
async def get_insights(meeting_id: str, request: Request):
    from services.meetings_workbench import list_insights
    await get_current_user(request)
    return await list_insights(meeting_id)

@router.post("/meetings/{meeting_id}/insights/generate")
async def generate_insights(meeting_id: str, request: Request):
    from services.meetings_workbench import generate_insights as _gen
    user = await get_current_user(request)
    return await _gen(meeting_id, user)

@router.post("/meetings/{meeting_id}/action-items")
async def create_action_item(meeting_id: str, req: ActionItemRequest, request: Request):
    from services.meetings_workbench import create_action_item as _create
    user = await get_current_user(request)
    return await _create(meeting_id, req, user)

@router.get("/meetings/{meeting_id}/action-items")
async def list_action_items(meeting_id: str, request: Request):
    from services.meetings_workbench import list_action_items as _list
    await get_current_user(request)
    return await _list(meeting_id)

@router.put("/meetings/{meeting_id}/action-items/{item_id}")
async def update_action_item(meeting_id: str, item_id: str, request: Request):
    from services.meetings_workbench import update_action_item as _update
    await get_current_user(request)
    body = await request.json()
    return await _update(item_id, body)




@router.get("/calendar/events")
async def get_calendar_events(request: Request):
    from services.meetings_dashboard import build_calendar_events
    user = await get_current_user(request)
    # Iter 335 — 30s TTL cache per user. Calendar page often polls + multiple
    # widgets render the same events; without cache this dominated load p95.
    uid = user["user_id"]
    now = _time.monotonic()
    entry = _CALENDAR_CACHE.get(uid)
    if entry and (now - entry[0]) < 30:
        return entry[1]
    events = await build_calendar_events(user)
    _CALENDAR_CACHE[uid] = (now, events)
    if len(_CALENDAR_CACHE) > 2000:
        cutoff = now - 30
        for k in [k for k, v in _CALENDAR_CACHE.items() if v[0] < cutoff]:
            _CALENDAR_CACHE.pop(k, None)
    return events

@router.put("/calendar/events/{meeting_id}/rsvp")
async def rsvp_event(meeting_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    status = body.get("status", "accepted")  # accepted, declined, tentative
    await db.meeting_participants.update_one(
        {"meeting_id": meeting_id, "user_id": user["user_id"]},
        {"$set": {"rsvp_status": status}}
    )
    # Iter 335 — invalidate calendar cache so the RSVP shows up immediately
    _CALENDAR_CACHE.pop(user["user_id"], None)
    return {"meeting_id": meeting_id, "rsvp_status": status}


@router.get("/dashboard/stats")
async def get_dashboard_stats(request: Request):
    from services.meetings_dashboard import build_stats
    user = await get_current_user(request)
    # Iter 172 (perf): 60 s in-memory TTL cache per user. Under load the
    # heavy aggregation in build_stats was the #1 dashboard cost.
    now = _time.monotonic()
    entry = _DASHBOARD_CACHE.get(user["user_id"])
    if entry and (now - entry[0]) < 60:
        return entry[1]
    stats = await build_stats(user)
    _DASHBOARD_CACHE[user["user_id"]] = (now, stats)
    if len(_DASHBOARD_CACHE) > 2000:
        cutoff = now - 60
        for k in [k for k, v in _DASHBOARD_CACHE.items() if v[0] < cutoff]:
            _DASHBOARD_CACHE.pop(k, None)
    return stats


@router.get("/dashboard/agenda")
async def get_dashboard_agenda(request: Request):
    """Get today's meetings and next 7 days grouped by date, plus recent activity."""
    from services.meetings_dashboard import build_agenda
    user = await get_current_user(request)
    return await build_agenda(user)


# ============ FOCUS TIME ============

@router.get("/focus-times")
async def get_focus_times(request: Request):
    from services.meetings_workbench import list_focus_times
    user = await get_current_user(request)
    return await list_focus_times(user)

@router.post("/focus-times")
async def create_focus_time(request: Request):
    from services.meetings_workbench import create_focus_time as _create
    user = await get_current_user(request)
    body = await request.json()
    return await _create(body, user)

@router.delete("/focus-times/{focus_id}")
async def delete_focus_time(focus_id: str, request: Request):
    from services.meetings_workbench import delete_focus_time as _delete
    user = await get_current_user(request)
    return await _delete(focus_id, user)

@router.delete("/focus-series/{series_id}")
async def delete_focus_series(series_id: str, request: Request):
    """Iter 279 — delete a whole recurring focus-time series at once."""
    from services.meetings_workbench import delete_focus_series as _del_series
    user = await get_current_user(request)
    return await _del_series(series_id, user)

@router.get("/focus-times/active")
async def get_active_focus(request: Request):
    from services.meetings_workbench import get_active_focus as _active
    user = await get_current_user(request)
    return await _active(user)


# ----- Quick-Scan: Host pushes a diagnostic request to a live participant -----

@router.post("/meetings/{meeting_id}/quick-scan/{target_user_id}")
async def send_quick_scan(meeting_id: str, target_user_id: str, request: Request):
    from services.meetings_quickscan import send_quick_scan as _send
    host = await get_current_user(request)
    return await _send(meeting_id, target_user_id, host, request)

@router.get("/meetings/{meeting_id}/quick-scans")
async def list_quick_scans(meeting_id: str, request: Request):
    from services.meetings_quickscan import list_quick_scans_for_meeting as _list
    host = await get_current_user(request)
    return await _list(meeting_id, host)
