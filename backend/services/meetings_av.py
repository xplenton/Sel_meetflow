"""Live recording & transcript lifecycle (start/stop/upload/play).

Extracted from routes/meetings/live.py (Iter 96). The route layer is a
thin adapter — all file I/O, storage paths, transcript rendering and
audit events live here.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException

from database import db
from services.storage import put_object, get_object, APP_STORAGE_PREFIX
from services.ws_manager import ws_manager

logger = logging.getLogger(__name__)

MAX_RECORDING_BYTES = 500 * 1024 * 1024  # 500 MB


# ---------- Recording ----------

async def start_recording(meeting_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    await db.meetings.update_one(
        {"meeting_id": meeting_id},
        {"$set": {"recording_active": True, "recording_started_at": now}},
    )
    await db.attendance_events.insert_one({
        "event_id": f"evt_{uuid.uuid4().hex[:10]}",
        "meeting_id": meeting_id, "user_id": user["user_id"],
        "event_type": "recording_started", "created_at": now,
    })
    return {"status": "recording_started"}


async def stop_recording(meeting_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    duration = 0
    if meeting and meeting.get("recording_started_at"):
        try:
            start_dt = datetime.fromisoformat(meeting["recording_started_at"])
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            duration = int((datetime.now(timezone.utc) - start_dt).total_seconds() / 60)
        except Exception:
            duration = 0
    await db.meetings.update_one({"meeting_id": meeting_id}, {"$set": {"recording_active": False}})
    rec = {
        "recording_id": f"rec_{uuid.uuid4().hex[:10]}",
        "meeting_id": meeting_id,
        "title": f"Recording - {(meeting or {}).get('title', 'Meeting')}",
        "url": "", "duration": duration,
        "created_by": user["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.recordings.insert_one(rec)
    await ws_manager.broadcast(meeting_id, {"type": "recording-stopped"})
    return {"status": "recording_stopped", "recording_id": rec["recording_id"], "duration": duration}


async def upload_recording(meeting_id: str, filename: str, content_type: str,
                           data: bytes, user: Dict[str, Any]) -> Dict[str, Any]:
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if len(data) > MAX_RECORDING_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 500MB)")
    ext = filename.split(".")[-1].lower() if filename and "." in filename else "webm"
    path = f"{APP_STORAGE_PREFIX}/recordings/{meeting_id}/{uuid.uuid4().hex[:8]}.{ext}"
    try:
        result = await asyncio.to_thread(put_object, path, data, content_type or "video/webm")
        storage_path = result.get("path", path)
        serve_url = f"/api/meetings/{meeting_id}/recording/play/{storage_path.split('/')[-1]}"
        last_rec = await db.recordings.find_one(
            {"meeting_id": meeting_id}, {"_id": 0}, sort=[("created_at", -1)]
        )
        if last_rec:
            await db.recordings.update_one(
                {"recording_id": last_rec["recording_id"]},
                {"$set": {"url": serve_url, "storage_path": storage_path, "file_size": len(data)}},
            )
        else:
            rec = {
                "recording_id": f"rec_{uuid.uuid4().hex[:10]}",
                "meeting_id": meeting_id,
                "title": f"Recording - {meeting.get('title', 'Meeting')}",
                "url": serve_url, "storage_path": storage_path,
                "file_size": len(data), "duration": 0,
                "created_by": user["user_id"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.recordings.insert_one(rec)
        return {"message": "Recording uploaded", "url": serve_url}
    except Exception as e:
        logger.error(f"Recording upload failed: {e}")
        raise HTTPException(status_code=500, detail="Recording upload failed")


async def play_recording(meeting_id: str, filename: str) -> tuple[bytes, Optional[str]]:
    """Fetch recording bytes from storage. Returns (data, content_type)."""
    path = f"{APP_STORAGE_PREFIX}/recordings/{meeting_id}/{filename}"
    try:
        return await asyncio.to_thread(get_object, path)
    except Exception:
        raise HTTPException(status_code=404, detail="Recording not found")


# ---------- Transcript ----------

async def start_transcript(meeting_id: str) -> Dict[str, Any]:
    await db.meetings.update_one({"meeting_id": meeting_id}, {"$set": {"transcript_active": True}})
    return {"status": "transcript_started"}


async def stop_transcript(meeting_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    await db.meetings.update_one({"meeting_id": meeting_id}, {"$set": {"transcript_active": False}})
    messages = await db.chat_messages.find(
        {"meeting_id": meeting_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(500)
    lines = [
        f"[{m.get('created_at', '')}] {m.get('user_name', '')}: {m.get('message', '')}"
        for m in messages
    ]
    content = "\n".join(lines) if lines else "No messages recorded."
    tr = {
        "transcript_id": f"tr_{uuid.uuid4().hex[:10]}",
        "meeting_id": meeting_id,
        "meeting_title": (meeting or {}).get("title", ""),
        "content": content,
        "created_by": user["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.transcripts.insert_one(tr)
    await ws_manager.broadcast(meeting_id, {"type": "transcript-stopped"})
    return {"status": "transcript_stopped", "transcript_id": tr["transcript_id"]}
