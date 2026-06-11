"""Quick-Scan — Host sends a short-lived device diagnostic token to a live
participant whose camera/microphone/network appears broken.

Flow:
  1. Host hits POST /meetings/{mid}/quick-scan/{target_user_id}
  2. Service creates a 60-minute single-use diag-share-token tagged with
     `meeting_id` + `host_id` + `target_user_id` in metadata.
  3. Broadcasts WS `{type:"quick-scan-request", share_url, token, from_name}`
     to the target user inside the meeting room. Also sends the QR/URL back
     to the host so they can show/copy it manually if WS delivery fails.
  4. When the user submits from `/diag/shared/{token}`, the diag-share
     submit-handler calls `notify_host_of_result()` → WS broadcast
     `{type:"quick-scan-result", ...}` to everyone in the meeting room
     (host-panel filters by from_user_id).
"""
from __future__ import annotations

import base64
import io
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import HTTPException, Request

from database import db, logger
from services.ws_manager import ws_manager


QUICK_SCAN_TTL_MIN = 60           # short-lived
QUICK_SCAN_MAX_SUBMISSIONS = 3    # host can re-ask if user fumbles


def _build_qr_png(url: str) -> str:
    import qrcode
    img = qrcode.make(url, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


async def _assert_host_or_cohost(meeting_id: str, user: Dict[str, Any]) -> None:
    hp = await db.meeting_participants.find_one(
        {"meeting_id": meeting_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not hp or hp["role"] not in ("host", "co-host"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")


async def send_quick_scan(
    meeting_id: str,
    target_user_id: str,
    host: Dict[str, Any],
    request: Request,
) -> Dict[str, Any]:
    """Create a Quick-Scan token + push it to the target over WS.

    Returns {token, share_url, qr_png} so the host UI can also show/copy the
    link manually as a fallback if the target's WS is not subscribed.
    """
    await _assert_host_or_cohost(meeting_id, host)

    meeting = await db.meetings.find_one(
        {"meeting_id": meeting_id},
        {"_id": 0, "title": 1, "meeting_id": 1},
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting nicht gefunden")

    target = await db.meeting_participants.find_one(
        {"meeting_id": meeting_id, "user_id": target_user_id},
        {"_id": 0, "user_name": 1, "user_id": 1},
    )
    if not target:
        raise HTTPException(status_code=404, detail="Teilnehmer nicht gefunden")

    token = secrets.token_urlsafe(12)
    now = datetime.now(timezone.utc)
    doc = {
        "token": token,
        "created_by": host["user_id"],
        "created_by_name": host.get("name", ""),
        "note": f"Quick-Scan · {meeting.get('title') or meeting_id}",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=QUICK_SCAN_TTL_MIN)).isoformat(),
        "submissions": [],
        # Quick-Scan specific fields
        "kind": "quick_scan",
        "meeting_id": meeting_id,
        "target_user_id": target_user_id,
        "target_user_name": target.get("user_name", ""),
        "max_submissions": QUICK_SCAN_MAX_SUBMISSIONS,
    }
    await db.diag_share_tokens.insert_one(doc)

    frontend_origin = (
        request.headers.get("origin")
        or str(request.base_url).rstrip("/")
    )
    share_url = f"{frontend_origin}/diag/shared/{token}"
    qr_png = _build_qr_png(share_url)

    # Push the request directly to the target user in the meeting room.
    try:
        await ws_manager.send_to(meeting_id, target_user_id, {
            "type": "quick-scan-request",
            "token": token,
            "share_url": share_url,
            "from_user_id": host["user_id"],
            "from_name": host.get("name", ""),
            "message": "Der Host möchte eine Schnell-Diagnose deines Geräts (Cam/Mic/Netzwerk).",
            "expires_at": doc["expires_at"],
        })
    except Exception as e:
        logger.warning(f"[quick-scan] WS send_to failed for {target_user_id}: {e}")

    logger.info(
        f"[quick-scan] host={host['user_id']} → target={target_user_id} "
        f"meeting={meeting_id} token={token[:6]}…"
    )

    return {
        "ok": True,
        "token": token,
        "share_url": share_url,
        "qr_png": qr_png,
        "expires_at": doc["expires_at"],
        "target_user_name": target.get("user_name", ""),
    }


async def notify_host_of_result(token_doc: Dict[str, Any], submission: Dict[str, Any]) -> None:
    """Called by diag_share.submit_diag_report when the token is a quick_scan.
    Broadcasts the result to the meeting room so the host panel picks it up.
    """
    meeting_id = token_doc.get("meeting_id")
    if not meeting_id:
        return
    try:
        await ws_manager.broadcast(meeting_id, {
            "type": "quick-scan-result",
            "token": token_doc["token"],
            "from_user_id": token_doc.get("target_user_id"),
            "from_name": submission.get("reporter_name") or token_doc.get("target_user_name") or "",
            "results": submission.get("results") or {},
            "submitted_at": submission.get("submitted_at"),
        })
    except Exception as e:
        logger.warning(f"[quick-scan] broadcast result failed: {e}")


async def list_quick_scans_for_meeting(meeting_id: str, host: Dict[str, Any]) -> list:
    """Host fetches all Quick-Scan tokens + submissions for this meeting
    (poll fallback when WS messages are missed)."""
    await _assert_host_or_cohost(meeting_id, host)
    tokens = await db.diag_share_tokens.find(
        {"meeting_id": meeting_id, "kind": "quick_scan"},
        {"_id": 0},
    ).sort("created_at", -1).to_list(50)
    return tokens
