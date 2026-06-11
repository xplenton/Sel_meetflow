"""Post-meeting / productivity helpers: action-items, AI insights, focus-times.

Extracted from routes/meetings/live.py (Iter 97). Each function returns a
ready-to-serialize dict; route handlers do auth + body parse + delegation.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import HTTPException

from database import db

logger = logging.getLogger(__name__)


# ---------- Action Items ----------

_ACTION_ITEM_UPDATABLE = ("title", "assignee", "due_date", "status")


async def create_action_item(meeting_id: str, req, user: Dict[str, Any]) -> Dict[str, Any]:
    item = {
        "item_id": f"ai_{uuid.uuid4().hex[:10]}",
        "meeting_id": meeting_id,
        "title": req.title,
        "assignee": req.assignee, "due_date": req.due_date,
        "status": req.status or "open",
        "created_by": user["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.action_items.insert_one(item)
    return await db.action_items.find_one({"item_id": item["item_id"]}, {"_id": 0})


async def list_action_items(meeting_id: str) -> List[Dict[str, Any]]:
    return await db.action_items.find(
        {"meeting_id": meeting_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)


async def update_action_item(item_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    updates = {k: v for k, v in body.items() if k in _ACTION_ITEM_UPDATABLE}
    if updates:
        await db.action_items.update_one({"item_id": item_id}, {"$set": updates})
    doc = await db.action_items.find_one({"item_id": item_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Action-Item nicht gefunden")
    return doc


# ---------- AI Insights ----------

_INSIGHTS_SYSTEM_MESSAGE = (
    "Extract meeting insights. Return JSON with keys: summary, key_decisions, "
    "action_items (array of {text, assignee}), sentiment, follow_ups"
)


async def list_insights(meeting_id: str) -> List[Dict[str, Any]]:
    return await db.ai_insights.find(
        {"meeting_id": meeting_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(20)


async def generate_insights(meeting_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """Run GPT-5.2 over the meeting's chat transcript and persist the result."""
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    messages = await db.chat_messages.find({"meeting_id": meeting_id}, {"_id": 0}).to_list(500)
    participants = await db.meeting_participants.find({"meeting_id": meeting_id}, {"_id": 0}).to_list(100)
    chat_text = "\n".join(f"{m.get('user_name', '')}: {m.get('message', '')}" for m in messages)

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        api_key = os.environ.get("EMERGENT_LLM_KEY", "")
        chat = LlmChat(
            api_key=api_key,
            session_id=f"insight_{meeting_id}_{uuid.uuid4().hex[:6]}",
            system_message=_INSIGHTS_SYSTEM_MESSAGE,
        )
        chat.with_model("openai", "gpt-5.2")
        prompt = (
            f"Meeting: {meeting['title']}\n"
            f"Participants: {', '.join(p['name'] for p in participants)}\n"
            f"Chat:\n{chat_text or 'No messages.'}"
        )
        ai_resp = await chat.send_message(UserMessage(text=prompt))
        insight = {
            "insight_id": f"ins_{uuid.uuid4().hex[:10]}",
            "meeting_id": meeting_id,
            "content": ai_resp,
            "type": "ai_generated",
            "created_by": user["user_id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.ai_insights.insert_one(insight)
        return await db.ai_insights.find_one({"insight_id": insight["insight_id"]}, {"_id": 0})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI insights error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------- Focus Times ----------

async def list_focus_times(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    now_iso = datetime.now(timezone.utc).isoformat()
    return await db.focus_times.find(
        {"user_id": user["user_id"], "end_time": {"$gte": now_iso}},
        {"_id": 0},
    ).sort("start_time", 1).to_list(50)


async def create_focus_time(body: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    """Create a single focus time OR a daily/weekly recurring series.

    Body fields:
      - start_time, end_time (ISO 8601, required) — defines the first occurrence
      - label (str, default "Fokus-Zeit")
      - recurrence (str, default "none"): "none" | "daily" | "weekly"
      - until_date (YYYY-MM-DD, required for non-none): inclusive last day
        the rule should generate. Capped at 365 days from start to keep
        the document count sane.

    Returns:
      - `{focus_id, ...}`  for a single non-recurring entry
      - `{series_id, count, items}` for a series (each item gets its own
        focus_id so users can delete individual occurrences later if they
        want, and the whole series shares `series_id`).
    """
    start_time = body.get("start_time")
    end_time = body.get("end_time")
    if not start_time or not end_time:
        raise HTTPException(status_code=400, detail="start_time und end_time erforderlich")
    label = body.get("label", "Fokus-Zeit")
    recurrence = (body.get("recurrence") or "none").lower()
    if recurrence not in ("none", "daily", "weekly"):
        raise HTTPException(status_code=400, detail="recurrence muss 'none', 'daily' oder 'weekly' sein")

    now_iso = datetime.now(timezone.utc).isoformat()

    if recurrence == "none":
        doc = {
            "focus_id": f"focus_{uuid.uuid4().hex[:10]}",
            "user_id": user["user_id"],
            "label": label,
            "start_time": start_time,
            "end_time": end_time,
            "recurrence": "none",
            "created_at": now_iso,
        }
        await db.focus_times.insert_one(doc)
        doc.pop("_id", None)
        return doc

    # Recurring: build a series. Cap to 365 days, default 90.
    until_str = body.get("until_date")
    if not until_str:
        raise HTTPException(status_code=400, detail="until_date erforderlich für wiederkehrende Fokus-Zeit")
    try:
        start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        until_dt = datetime.fromisoformat(f"{until_str}T23:59:59+00:00")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Ungültiges Datum: {e}")
    if until_dt < start_dt:
        raise HTTPException(status_code=400, detail="until_date muss nach dem Startdatum liegen")
    # Hard cap to prevent runaway insert (1 year = 365 daily entries max)
    max_until = start_dt + timedelta(days=365)
    if until_dt > max_until:
        until_dt = max_until
    duration = end_dt - start_dt
    step = timedelta(days=1) if recurrence == "daily" else timedelta(days=7)
    series_id = f"series_{uuid.uuid4().hex[:10]}"
    docs = []
    cur = start_dt
    while cur <= until_dt:
        docs.append({
            "focus_id": f"focus_{uuid.uuid4().hex[:10]}",
            "user_id": user["user_id"],
            "label": label,
            "start_time": cur.isoformat(),
            "end_time": (cur + duration).isoformat(),
            "recurrence": recurrence,
            "series_id": series_id,
            "created_at": now_iso,
        })
        cur += step
    if not docs:
        raise HTTPException(status_code=400, detail="Keine Termine im Zeitraum")
    await db.focus_times.insert_many(docs)
    for d in docs:
        d.pop("_id", None)
    return {
        "series_id": series_id,
        "count": len(docs),
        "recurrence": recurrence,
        "items": docs,
    }


async def delete_focus_time(focus_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """Delete a single occurrence. Use delete_focus_series() to remove a
    whole recurring series at once."""
    result = await db.focus_times.delete_one(
        {"focus_id": focus_id, "user_id": user["user_id"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    return {"message": "Fokus-Zeit gelöscht"}


async def delete_focus_series(series_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """Delete every occurrence of a recurring series."""
    result = await db.focus_times.delete_many(
        {"series_id": series_id, "user_id": user["user_id"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Serie nicht gefunden")
    return {"message": "Serie gelöscht", "deleted": result.deleted_count}


async def get_active_focus(user: Dict[str, Any]) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    active = await db.focus_times.find_one(
        {
            "user_id": user["user_id"],
            "start_time": {"$lte": now_iso},
            "end_time": {"$gte": now_iso},
        },
        {"_id": 0},
    )
    return {"active": active is not None, "focus": active}
