"""
AI-powered meeting summaries — extracted from routes/meetings.py.
Generates a structured meeting summary via GPT-5.2 using chat-history and metadata.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from database import db
from services.llm_key import get_llm_key
from services.email import send_email_real, build_summary_email_html

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are a professional meeting assistant. Create a clear, structured "
    "meeting summary in the language of the meeting title."
)


def _build_summary_prompt(meeting: Dict[str, Any], participants: List[Dict[str, Any]],
                          chat_messages: List[Dict[str, Any]]) -> str:
    names = ", ".join([p.get("name", "") for p in participants if p.get("name")])
    chat_text = "\n".join([f"{m.get('user_name','?')}: {m.get('message','')}" for m in chat_messages])
    return (
        f"Meeting: {meeting.get('title','')}\n"
        f"Participants: {names}\n"
        f"Duration: {meeting.get('duration', 60)} min\n\n"
        f"Chat:\n{chat_text}\n\n"
        "Provide: 1) Overview 2) Key decisions 3) Action items"
    )


async def generate_summary_text(meeting_id: str) -> Optional[str]:
    """Produce an AI-summary for the given meeting. Returns None on failure."""
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        return None
    messages = await db.chat_messages.find(
        {"meeting_id": meeting_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(500)
    if len(messages) < 2:
        return None
    participants = await db.meeting_participants.find(
        {"meeting_id": meeting_id}, {"_id": 0}
    ).to_list(100)
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        api_key = await get_llm_key()
        chat = LlmChat(
            api_key=api_key,
            session_id=f"auto_summary_{meeting_id}",
            system_message=SYSTEM_PROMPT,
        )
        chat.with_model("openai", "gpt-5.2")
        prompt = _build_summary_prompt(meeting, participants, messages)
        return await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.error(f"[SUMMARY] LLM failed for {meeting_id}: {e}")
        return None


async def persist_summary(meeting_id: str, summary_text: str) -> str:
    """Upsert the generated summary and return its summary_id."""
    summary_id = f"sum_{uuid.uuid4().hex[:10]}"
    await db.meeting_summaries.update_one(
        {"meeting_id": meeting_id},
        {"$set": {
            "summary_id": summary_id, "meeting_id": meeting_id,
            "content": summary_text,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return summary_id


async def auto_send_summary_email(meeting_id: str) -> None:
    """Trigger summary generation + e-mail dispatch if email config is enabled."""
    try:
        config = await db.email_config.find_one({"config_id": "global"}, {"_id": 0})
        if not config or not config.get("enabled"):
            logger.info(f"[AUTO-SUMMARY] Skipped for {meeting_id} - email not configured")
            return
        meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
        if not meeting:
            return
        summary_text = await generate_summary_text(meeting_id)
        if not summary_text:
            return
        await persist_summary(meeting_id, summary_text)
        participants = await db.meeting_participants.find(
            {"meeting_id": meeting_id}, {"_id": 0}
        ).to_list(100)
        participant_emails: List[str] = []
        for p in participants:
            p_user = await db.users.find_one({"user_id": p.get("user_id")}, {"_id": 0})
            if p_user and p_user.get("email"):
                participant_emails.append(p_user["email"])
        html = build_summary_email_html(
            meeting["title"],
            meeting.get("scheduled_at") or meeting.get("created_at", ""),
            participants,
            summary_text,
        )
        for email in participant_emails:
            await send_email_real(email, f"Meeting-Zusammenfassung: {meeting['title']}", html, category="meetings")
        await db.meetings.update_one(
            {"meeting_id": meeting_id},
            {"$set": {
                "summary_email_sent": True,
                "summary_email_sent_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        logger.info(f"[AUTO-SUMMARY] Sent for {meeting_id} to {len(participant_emails)} participants")
    except Exception as e:
        logger.error(f"[AUTO-SUMMARY] Error for {meeting_id}: {e}")
