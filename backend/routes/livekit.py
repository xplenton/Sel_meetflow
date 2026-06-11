"""LiveKit routes (iter 136).

* `GET  /api/livekit/config-status`      → public: is LiveKit available?
* `GET  /api/livekit/admin/config`       → admin only: read config (secret masked)
* `POST /api/livekit/admin/config`       → admin only: save config
* `POST /api/livekit/meetings/{id}/token`→ authed user: mint join token
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
import os

from dependencies import get_current_user
from services import livekit_service

router = APIRouter(tags=["livekit"])

_MONGO_URL = os.environ.get("MONGO_URL")
_DB_NAME = os.environ.get("DB_NAME")
_client = AsyncIOMotorClient(_MONGO_URL)
db = _client[_DB_NAME]


def _mask(secret: str) -> str:
    """Return a masked version for admin UI display — we never ship raw secrets to the browser twice."""
    if not secret:
        return ""
    if len(secret) <= 8:
        return "*" * len(secret)
    return secret[:4] + "*" * (len(secret) - 8) + secret[-4:]


@router.get("/livekit/config-status")
async def livekit_config_status():
    """Public: the frontend consults this to decide whether the LiveKit
    path is available at all. Returns only booleans + threshold — no
    secrets, no URL."""
    cfg = await livekit_service.get_config()
    return {
        "configured": bool(cfg["url"] and cfg["api_key"] and cfg["api_secret"]),
        "upgrade_threshold": cfg["upgrade_threshold"],
    }


class LiveKitConfigPayload(BaseModel):
    url: str = ""
    api_key: str = ""
    api_secret: str = ""  # empty string = "keep existing secret"
    upgrade_threshold: int = 4


@router.get("/livekit/admin/config")
async def livekit_admin_get_config(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    cfg = await livekit_service.get_config()
    return {
        "url": cfg["url"],
        "api_key": cfg["api_key"],
        "api_secret_masked": _mask(cfg["api_secret"]),
        "api_secret_set": bool(cfg["api_secret"]),
        "upgrade_threshold": cfg["upgrade_threshold"],
    }


@router.post("/livekit/admin/config")
async def livekit_admin_save_config(payload: LiveKitConfigPayload, request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    # When the admin leaves api_secret empty, keep the old one — lets them edit URL/key without re-entering the secret
    existing = await livekit_service.get_config()
    api_secret = payload.api_secret.strip() or existing["api_secret"]
    saved = await livekit_service.save_config(
        url=payload.url,
        api_key=payload.api_key,
        api_secret=api_secret,
        upgrade_threshold=payload.upgrade_threshold,
    )
    return {"ok": True, "upgrade_threshold": saved["upgrade_threshold"]}


@router.get("/meetings/{meeting_id}/transport")
async def meetings_transport(meeting_id: str, request: Request):
    """Sticky transport decision for a meeting (iter 139).

    Once the FIRST participant queries this endpoint, we commit to either
    `livekit` or `mesh` based on whether LiveKit is configured AND the
    meeting is a multi-party candidate. Every subsequent joiner receives
    the same answer — that way all participants land on the same
    transport regardless of sequential join order (which previously left
    the early joiners on mesh while late joiners crossed the threshold
    and landed on LiveKit, making them invisible to each other).

    Heuristic for the first-time decision:
      * LiveKit configured? If not → mesh.
      * Scheduled meeting with explicit attendees >= threshold? → livekit.
      * Recurring / group meeting? → livekit.
      * Otherwise → livekit if threshold <= 2 else mesh.
    Once set, it never changes for the life of the meeting.
    """
    user = await get_current_user(request)
    meeting = await db.meetings.find_one(
        {"meeting_id": meeting_id},
        {"_id": 0, "transport": 1, "participants": 1, "attendees": 1,
         "recurring": 1, "meeting_type": 1},
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    cfg = await livekit_service.get_config()
    threshold = cfg["upgrade_threshold"]

    transport = meeting.get("transport")
    if transport in ("livekit", "mesh"):
        # Already decided — return existing decision so all participants stay in sync
        return {"transport": transport, "upgrade_threshold": threshold}

    # First-time decision
    livekit_configured = bool(cfg["url"] and cfg["api_key"] and cfg["api_secret"])
    if not livekit_configured:
        chosen = "mesh"
    elif threshold <= 2:
        # Admin wants LiveKit for everything with ≥ 2 people — default safe choice.
        chosen = "livekit"
    else:
        invitee_count = len(meeting.get("attendees") or []) or len(meeting.get("participants") or [])
        # Trust the invite list: if host invited threshold-or-more people, the
        # meeting is a multi-party one from the start.
        if invitee_count >= threshold:
            chosen = "livekit"
        elif meeting.get("recurring"):
            chosen = "livekit"
        else:
            chosen = "mesh"

    # Persist so the decision is sticky for all subsequent participants
    await db.meetings.update_one({"meeting_id": meeting_id}, {"$set": {"transport": chosen}})
    return {"transport": chosen, "upgrade_threshold": threshold, "decided_by": user["user_id"]}


@router.post("/livekit/meetings/{meeting_id}/token")
async def livekit_meeting_token(meeting_id: str, request: Request):
    """Mint a short-lived SFU token for the current user to join `meeting_id`.

    The room name mirrors the meeting_id so every user joining the same
    meeting lands in the same LiveKit room.
    """
    user = await get_current_user(request)
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0, "title": 1})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    try:
        return await livekit_service.generate_token(
            room_name=meeting_id,
            identity=user["user_id"],
            display_name=user.get("name") or user.get("email") or user["user_id"],
            metadata=meeting.get("title", ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/livekit/meetings/{meeting_id}/breakout/{room_id}/token")
async def livekit_breakout_token(meeting_id: str, room_id: str, request: Request):
    """Mint a LiveKit token for a breakout sub-room (iter 208).

    The breakout room name is `{meeting_id}__{room_id}` so the LiveKit SFU
    keeps each sub-conference isolated from the main room and from sibling
    breakouts. Authorisation:
      * The meeting host can always join any breakout (used to "visit" rooms).
      * Anyone listed in `participant_ids` of that breakout can join.
    """
    user = await get_current_user(request)
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0, "title": 1, "host_id": 1})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    room = await db.breakout_rooms.find_one({"room_id": room_id, "meeting_id": meeting_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Breakout room not found")
    is_host = (meeting.get("host_id") == user["user_id"]) or (user.get("role") == "admin")
    is_member = user["user_id"] in (room.get("participant_ids") or [])
    if not (is_host or is_member):
        raise HTTPException(status_code=403, detail="Nicht für diesen Gruppenraum freigegeben")
    try:
        return await livekit_service.generate_token(
            room_name=f"{meeting_id}__{room_id}",
            identity=user["user_id"],
            display_name=user.get("name") or user.get("email") or user["user_id"],
            metadata=f"{meeting.get('title', '')} · {room.get('name', '')}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
