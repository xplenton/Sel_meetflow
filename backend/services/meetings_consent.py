"""Consent request/response flow for recording & transcript (DSGVO).

Extracted from routes/meetings/reports.py (Iter 94). Each request creates
a consent_requests row; host auto-consents; participants respond via WS
or REST; when everyone accepts, the corresponding feature (recording_active
or transcript_active) is flipped on the meeting document.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import HTTPException

from database import db
from services.ws_manager import ws_manager


async def _assert_host_or_cohost(meeting_id: str, user: Dict[str, Any]) -> None:
    hp = await db.meeting_participants.find_one(
        {"meeting_id": meeting_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not hp or hp["role"] not in ("host", "co-host"):
        raise HTTPException(status_code=403, detail="Not authorized")


# On approval, flip this Meeting field to True — one line per consent type.
_APPROVE_SET_MAP = {
    "recording": {"recording_active": True, "recording_started_at": None},
    "transcript": {"transcript_active": True},
}


async def request_consent(meeting_id: str, consent_type: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """Host initiates a consent request; if no other participant is joined
    the feature starts immediately (auto-approved). Returns status dict."""
    if consent_type not in _APPROVE_SET_MAP:
        raise HTTPException(status_code=400, detail="Unknown consent type")
    await _assert_host_or_cohost(meeting_id, user)
    now = datetime.now(timezone.utc).isoformat()
    participants = await db.meeting_participants.find(
        {"meeting_id": meeting_id, "joined_at": {"$ne": None}, "left_at": None}, {"_id": 0}
    ).to_list(100)
    consent_id = f"consent_{uuid.uuid4().hex[:10]}"
    consent = {
        "consent_id": consent_id, "meeting_id": meeting_id, "type": consent_type,
        "requested_by": user["user_id"], "requested_by_name": user["name"],
        "status": "pending", "responses": {},
        "participant_ids": [p["user_id"] for p in participants if p["user_id"] != user["user_id"]],
        "created_at": now,
    }
    consent["responses"][user["user_id"]] = {"status": "accepted", "name": user["name"]}
    await db.consent_requests.insert_one(consent)
    await ws_manager.broadcast(meeting_id, {
        "type": "consent-request", "consent_id": consent_id,
        "consent_type": consent_type, "requested_by": user["name"],
    })
    if len(consent["participant_ids"]) == 0:
        # Only host present → start feature immediately
        await _apply_approved(meeting_id, consent_type, now)
        await db.consent_requests.update_one({"consent_id": consent_id}, {"$set": {"status": "approved"}})
        started_key = "recording_started" if consent_type == "recording" else "transcript_started"
        return {"status": started_key, "consent_id": consent_id, "immediate": True}
    return {"status": "consent_pending", "consent_id": consent_id, "awaiting": len(consent["participant_ids"])}


async def respond_consent(meeting_id: str, consent_id: str,
                          response_status: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """Participant accepts/declines a pending consent request. Returns a
    status dict. Declining by anyone rejects the whole request."""
    consent = await db.consent_requests.find_one({"consent_id": consent_id}, {"_id": 0})
    if not consent:
        raise HTTPException(status_code=404, detail="Consent request not found")
    if consent["status"] != "pending":
        return {"status": consent["status"], "message": "Already resolved"}
    await db.consent_requests.update_one(
        {"consent_id": consent_id},
        {"$set": {f"responses.{user['user_id']}": {"status": response_status, "name": user["name"]}}},
    )
    await ws_manager.broadcast(meeting_id, {
        "type": "consent-response", "consent_id": consent_id,
        "user_id": user["user_id"], "user_name": user["name"], "response": response_status,
    })
    if response_status == "declined":
        await db.consent_requests.update_one({"consent_id": consent_id}, {"$set": {"status": "rejected"}})
        await ws_manager.broadcast(meeting_id, {
            "type": "consent-resolved", "consent_id": consent_id,
            "consent_type": consent["type"], "result": "rejected",
            "declined_by": user["name"],
        })
        return {"status": "rejected", "declined_by": user["name"]}

    updated = await db.consent_requests.find_one({"consent_id": consent_id}, {"_id": 0})
    all_ids = set(updated["participant_ids"]) | {updated["requested_by"]}
    responded = set(updated["responses"].keys())
    if responded >= all_ids:
        now = datetime.now(timezone.utc).isoformat()
        await db.consent_requests.update_one({"consent_id": consent_id}, {"$set": {"status": "approved"}})
        await _apply_approved(meeting_id, updated["type"], now)
        await ws_manager.broadcast(meeting_id, {
            "type": "consent-resolved", "consent_id": consent_id,
            "consent_type": updated["type"], "result": "approved",
        })
        return {"status": "approved"}
    return {"status": "pending", "responded": len(responded), "total": len(all_ids)}


async def _apply_approved(meeting_id: str, consent_type: str, now: str) -> None:
    """Flip the meeting's feature-active flag based on the approved consent type."""
    patch = dict(_APPROVE_SET_MAP[consent_type])
    if "recording_started_at" in patch:
        patch["recording_started_at"] = now
    await db.meetings.update_one({"meeting_id": meeting_id}, {"$set": patch})


async def list_active_consents(meeting_id: str):
    return await db.consent_requests.find(
        {"meeting_id": meeting_id, "status": "pending"}, {"_id": 0}
    ).to_list(10)
