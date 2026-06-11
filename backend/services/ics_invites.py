"""
ICS-Auto-Email: send calendar invitation e-mails to invited meeting participants.

Used after:
  * POST /api/meetings  (when invited_emails is present)
  * confirm of a schedule-poll that auto-creates a meeting

The message body is a standard HTML invite with a `Meeting beitreten`-Button; the
`.ics` file is attached (via Resend attachments API if available, else embedded
as an inline data: link so recipients without mail clients can still save it).
"""
from __future__ import annotations

import os
import asyncio
import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from database import db

logger = logging.getLogger(__name__)


def _build_ics_bytes(meeting: Dict[str, Any]) -> Optional[bytes]:
    """Return raw ICS bytes for a single meeting (adds RRULE for simple patterns)."""
    try:
        from icalendar import Calendar, Event
    except Exception:
        return None
    cal = Calendar()
    cal.add("prodid", "-//MeetFlow//Invitation//DE")
    cal.add("version", "2.0")
    cal.add("method", "REQUEST")
    event = Event()
    event.add("summary", meeting.get("title", "MeetFlow Meeting"))
    code = meeting.get("meeting_code", "")
    frontend_url = (os.environ.get("FRONTEND_URL", "") or "").rstrip("/")
    join_url = f"{frontend_url}/meetings/{meeting['meeting_id']}/join" if frontend_url else ""
    desc_parts: List[str] = []
    if meeting.get("description"):
        desc_parts.append(meeting["description"])
    desc_parts.append(f"Meeting-Code: {code}")
    if join_url:
        desc_parts.append(f"Beitreten: {join_url}")
        event.add("url", join_url)
    event.add("description", "\n\n".join(desc_parts))
    event.add("uid", f"{meeting['meeting_id']}@meetflow")
    if meeting.get("scheduled_at"):
        try:
            start = datetime.fromisoformat(meeting["scheduled_at"].replace("Z", "+00:00"))
            event.add("dtstart", start)
            event.add("dtend", start + timedelta(minutes=int(meeting.get("duration") or 60)))
            event.add("dtstamp", datetime.now(timezone.utc))
        except Exception:
            return None
    else:
        return None  # No time → no usable ICS
    pattern = (meeting.get("recurring_pattern") or "").lower()
    rrule_map = {
        "daily": {"freq": "DAILY"},
        "weekly": {"freq": "WEEKLY"},
        "biweekly": {"freq": "WEEKLY", "interval": 2},
        "monthly": {"freq": "MONTHLY"},
    }
    if meeting.get("recurring") and pattern in rrule_map:
        event.add("rrule", rrule_map[pattern])
    event.add("location", f"MeetFlow Online (Code: {code})")
    cal.add_component(event)
    return cal.to_ical()


def _build_invite_html(meeting: Dict[str, Any], host_name: str, join_url: str, ics_b64: Optional[str]) -> str:
    start_str = ""
    if meeting.get("scheduled_at"):
        try:
            d = datetime.fromisoformat(meeting["scheduled_at"].replace("Z", "+00:00"))
            start_str = d.astimezone().strftime("%a, %d.%m.%Y · %H:%M Uhr")
        except Exception:
            pass
    duration = meeting.get("duration") or 60
    title = meeting.get("title", "MeetFlow Meeting")
    description = meeting.get("description") or ""
    ics_link = (
        f'<a href="data:text/calendar;base64,{ics_b64}" download="meetflow_{meeting["meeting_id"]}.ics" '
        f'style="display:inline-block;color:#4A5D4E;text-decoration:underline;margin-top:12px;font-size:12px;">'
        'Als Kalender-Datei herunterladen (.ics)</a>' if ics_b64 else ''
    )
    return f"""
    <div style="font-family:'Work Sans',Arial,sans-serif;max-width:560px;margin:0 auto;padding:32px;background:#F9F9F8;border-radius:12px;">
      <div style="text-align:center;margin-bottom:24px;">
        <span style="font-family:'Manrope',sans-serif;font-size:20px;font-weight:600;color:#4A5D4E;">MeetFlow</span>
      </div>
      <div style="background:#fff;border:1px solid #E2E4E0;border-radius:12px;padding:24px;">
        <h2 style="font-family:'Manrope',sans-serif;font-size:18px;color:#1C1F1D;margin:0 0 8px 0;">Meeting-Einladung</h2>
        <p style="color:#4B5563;font-size:14px;margin:0 0 16px 0;"><strong>{host_name}</strong> laedt dich ein zu:</p>
        <div style="background:#F3F4F1;border-radius:8px;padding:16px;margin-bottom:16px;">
          <p style="font-weight:600;color:#1C1F1D;margin:0 0 4px 0;font-size:16px;">{title}</p>
          {f'<p style="color:#6B7280;font-size:13px;margin:0 0 6px 0;">{start_str} · {duration} Min.</p>' if start_str else ''}
          {f'<p style="color:#4B5563;font-size:13px;margin:6px 0 0 0;">{description}</p>' if description else ''}
        </div>
        <a href="{join_url}" style="display:inline-block;background:#4A5D4E;color:#fff;text-decoration:none;padding:12px 32px;border-radius:9999px;font-weight:500;font-size:14px;margin-top:8px;">Meeting beitreten</a>
        <br />{ics_link}
      </div>
      <p style="text-align:center;color:#9CA3AF;font-size:11px;margin-top:16px;">Gesendet via MeetFlow · Termin zum Kalender hinzufuegen via .ics-Anhang</p>
    </div>
    """


async def _send_with_attachment(to_email: str, subject: str, html: str, ics_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Resend-native attachment send. Falls back to attachment-less send_email_real."""
    resend_key = os.environ.get("RESEND_API_KEY", "").strip()
    config = await db.email_config.find_one({"config_id": "global"}, {"_id": 0})
    if config and config.get("provider") == "resend" and config.get("api_key"):
        resend_key = config["api_key"]
    sender = os.environ.get("SENDER_EMAIL", "noreply@meetflow.app")
    if config and config.get("sender_email"):
        sender = config["sender_email"]
    if resend_key and ics_bytes:
        try:
            import resend
            resend.api_key = resend_key
            params = {
                "from": sender, "to": [to_email], "subject": subject, "html": html,
                "attachments": [{
                    "filename": filename,
                    "content": base64.b64encode(ics_bytes).decode("ascii"),
                    "content_type": "text/calendar; method=REQUEST",
                }],
            }
            result = await asyncio.to_thread(resend.Emails.send, params)
            logger.info(f"[ICS-INVITE] sent to {to_email}: {result}")
            return {"provider": "resend", "status": "sent"}
        except Exception as e:
            logger.warning(f"[ICS-INVITE] Resend failed, falling back: {e}")
    # Fallback: send without attachment (ics link is already embedded in HTML)
    from services.email import send_email_real
    return await send_email_real(to_email, subject, html)


async def send_meeting_invitations(meeting_id: str, recipient_emails: List[str], host_name: str = "") -> Dict[str, Any]:
    """Send ICS-Invitation e-mails to `recipient_emails` for a given meeting_id.
    Returns summary {total, sent, failed}."""
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        return {"error": "meeting_not_found"}
    if not host_name:
        host_name = meeting.get("host_name", "Host")
    ics_bytes = _build_ics_bytes(meeting)
    if ics_bytes is None and not meeting.get("scheduled_at"):
        # Instant meetings have no scheduled_at → no ICS sensible
        return {"total": 0, "sent": 0, "failed": 0, "skipped_reason": "no_scheduled_at"}
    ics_b64 = base64.b64encode(ics_bytes).decode("ascii") if ics_bytes else None
    frontend_url = (os.environ.get("FRONTEND_URL", "") or "").rstrip("/")
    join_url = f"{frontend_url}/meetings/{meeting_id}/join" if frontend_url else meeting.get("meeting_code", "")
    subject = f"Einladung: {meeting.get('title', 'MeetFlow Meeting')}"
    html = _build_invite_html(meeting, host_name, join_url, ics_b64)
    filename = f"meetflow_{meeting_id}.ics"
    sent = 0
    failed = 0
    seen: set = set()
    for email in recipient_emails:
        email_clean = (email or "").strip().lower()
        if not email_clean or email_clean in seen or "@" not in email_clean:
            continue
        seen.add(email_clean)
        try:
            res = await _send_with_attachment(email_clean, subject, html, ics_bytes or b"", filename)
            if res.get("status") == "sent":
                sent += 1
            else:
                failed += 1
        except Exception as e:
            logger.warning(f"[ICS-INVITE] send to {email_clean} failed: {e}")
            failed += 1
    return {"total": sent + failed, "sent": sent, "failed": failed}
