"""
News HTML-Newsletter dispatcher — sends nicely formatted e-mails to the target audience
of a news post when the post includes 'email' in its `channels` list.

Triggered from:
  * POST /news/posts (on immediate publish)
  * POST /news/posts/{id}/publish (approval flow)
  * services/maintenance.py (scheduled publish promotion)

Designed to be idempotent — guards against duplicate dispatch via `email_dispatched_at`.
"""
from __future__ import annotations

import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

from database import db

logger = logging.getLogger(__name__)


PRIORITY_STYLE: Dict[str, Dict[str, str]] = {
    "critical":  {"label": "KRITISCH",  "color": "#C87967"},
    "important": {"label": "WICHTIG",   "color": "#D4A373"},
    "normal":    {"label": "News",      "color": "#4A5D4E"},
}


async def _resolve_email_audience(post: Dict[str, Any]) -> List[str]:
    """Return a de-duplicated list of e-mails the post should go to."""
    query: Dict[str, Any] = {"email": {"$exists": True, "$ne": ""}}
    conds: List[Dict[str, Any]] = []
    if post.get("target_all"):
        pass  # no filtering
    else:
        if post.get("target_groups"):
            conds.append({"groups": {"$in": post["target_groups"]}})
        if post.get("target_departments"):
            conds.append({"department": {"$in": post["target_departments"]}})
        if post.get("target_locations"):
            conds.append({"location": {"$in": post["target_locations"]}})
        if post.get("target_professions"):
            conds.append({"profession": {"$in": post["target_professions"]}})
        if post.get("target_roles"):
            conds.append({"role": {"$in": post["target_roles"]}})
        if post.get("target_user_ids"):
            conds.append({"user_id": {"$in": post["target_user_ids"]}})
        if conds:
            query["$or"] = conds
        else:
            # Targeting said 'no target_all' but no criteria → treat as nobody
            return []
    users = await db.users.find(query, {"_id": 0, "email": 1, "user_id": 1, "email_preferences": 1}).to_list(5000)
    seen = set()
    out: List[tuple] = []  # list of (email, user_id)
    for u in users:
        # Respect opt-out
        prefs = u.get("email_preferences") or {}
        if prefs.get("newsletter_enabled") is False:
            continue
        e = (u.get("email") or "").strip().lower()
        uid = u.get("user_id") or ""
        if e and e not in seen and "@" in e and uid:
            seen.add(e)
            out.append((e, uid))
    return out


def _build_newsletter_html(post: Dict[str, Any], unsubscribe_url: str = "") -> str:
    pri = PRIORITY_STYLE.get(post.get("priority", "normal"), PRIORITY_STYLE["normal"])
    frontend_url = (os.environ.get("FRONTEND_URL", "") or "").rstrip("/")
    read_url = f"{frontend_url}/news?post={post.get('post_id', '')}" if frontend_url else ""
    title = (post.get("title") or "").replace("<", "&lt;").replace(">", "&gt;")
    excerpt = (post.get("excerpt") or "").replace("<", "&lt;").replace(">", "&gt;")
    content_preview = (post.get("content") or "").replace("<", "&lt;").replace(">", "&gt;")[:500]
    if not excerpt and content_preview:
        excerpt = content_preview
    author = post.get("owner_name") or post.get("author_name") or "MeetFlow"
    published_at = post.get("published_at") or post.get("created_at", "")
    pub_str = ""
    if published_at:
        try:
            d = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            pub_str = d.astimezone().strftime("%d.%m.%Y · %H:%M Uhr")
        except Exception:
            pub_str = published_at[:10]
    mandatory_banner = (
        '<div style="background:#C87967;color:#fff;padding:8px 16px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;border-radius:4px;margin-bottom:12px;text-align:center;">'
        "Pflichtlektuere — Lesebestaetigung erforderlich</div>"
        if post.get("is_mandatory") else ""
    )
    cta_btn = (
        f'<a href="{read_url}" style="display:inline-block;background:#4A5D4E;color:#fff;text-decoration:none;padding:12px 32px;border-radius:9999px;font-weight:500;font-size:14px;margin-top:8px;">Vollständigen Beitrag lesen</a>'
        if read_url else ''
    )
    unsub_line = (
        f'<br/><a href="{unsubscribe_url}" style="color:#9CA3AF;text-decoration:underline;">Aus dem Newsletter austragen</a>'
        if unsubscribe_url else ''
    )
    return f"""
    <div style="font-family:'Work Sans',Arial,sans-serif;max-width:600px;margin:0 auto;padding:32px 16px;background:#F9F9F8;">
      <div style="text-align:center;margin-bottom:16px;">
        <span style="font-family:'Manrope',sans-serif;font-size:20px;font-weight:600;color:#4A5D4E;">MeetFlow</span>
        <span style="display:inline-block;margin-left:8px;padding:2px 10px;border-radius:9999px;background:{pri['color']};color:#fff;font-size:10px;font-weight:600;vertical-align:middle;">{pri['label']}</span>
      </div>
      <div style="background:#fff;border:1px solid #E2E4E0;border-radius:12px;overflow:hidden;">
        <div style="padding:24px;">
          {mandatory_banner}
          <h1 style="font-family:'Manrope',sans-serif;font-size:20px;line-height:1.3;color:#1C1F1D;margin:0 0 8px 0;">{title}</h1>
          <p style="color:#9CA3AF;font-size:12px;margin:0 0 16px 0;">Von {author} · {pub_str}</p>
          <div style="color:#4B5563;font-size:14px;line-height:1.6;margin-bottom:16px;white-space:pre-wrap;">{excerpt}</div>
          {cta_btn}
        </div>
      </div>
      <p style="text-align:center;color:#9CA3AF;font-size:11px;margin-top:20px;line-height:1.5;">
        Du erhaeltst diese E-Mail als MeetFlow-Nutzer.<br/>
        Newsletter-Einstellungen jederzeit im Profil anpassbar.{unsub_line}
      </p>
    </div>
    """


async def _send_newsletter_email(to_email: str, subject: str, html: str) -> bool:
    """Thin wrapper around services.email.send_email_real with Resend-native send."""
    try:
        from services.email import send_email_real
        res = await send_email_real(to_email, subject, html, category="news")
        return bool(res and res.get("status") == "sent")
    except Exception as e:
        logger.warning(f"[NEWSLETTER] send to {to_email} failed: {e}")
        return False


async def dispatch_newsletter_for_post(post: Dict[str, Any], *, force: bool = False) -> Dict[str, Any]:
    """Send the newsletter e-mail for a post if it has 'email' in channels and has not been
    dispatched yet. Returns stats dict. Pass force=True to bypass the idempotency guard."""
    channels = post.get("channels") or ["intranet"]
    if "email" not in channels:
        return {"skipped": "email_not_in_channels"}
    if not force:
        existing = await db.news_posts.find_one(
            {"post_id": post.get("post_id")}, {"_id": 0, "email_dispatched_at": 1}
        )
        if existing and existing.get("email_dispatched_at"):
            return {"skipped": "already_dispatched", "at": existing["email_dispatched_at"]}
    recipients = await _resolve_email_audience(post)
    if not recipients:
        return {"total": 0, "sent": 0, "failed": 0, "reason": "no_recipients"}
    pri = PRIORITY_STYLE.get(post.get("priority", "normal"), PRIORITY_STYLE["normal"])
    subject_prefix = f"[{pri['label']}] " if post.get("priority") in ("critical", "important") else ""
    subject = f"{subject_prefix}{post.get('title', 'News von MeetFlow')}"
    sent = 0
    failed = 0
    # Respect Resend free-tier rate limit of 5/sec: batch of 5 with 1s pause
    from services.email_preferences import build_unsubscribe_url
    batch_size = 5
    for i in range(0, len(recipients), batch_size):
        batch = recipients[i:i + batch_size]
        async def _send_to(item):
            email, user_id = item
            html = _build_newsletter_html(post, unsubscribe_url=build_unsubscribe_url(user_id))
            return await _send_newsletter_email(email, subject, html)
        results = await asyncio.gather(*[_send_to(item) for item in batch], return_exceptions=True)
        for ok in results:
            if ok is True:
                sent += 1
            else:
                failed += 1
        if i + batch_size < len(recipients):
            await asyncio.sleep(1.05)  # Stay safely under Resend's 5/sec limit
    now_iso = datetime.now(timezone.utc).isoformat()
    # Audit & idempotency record
    await db.news_posts.update_one(
        {"post_id": post.get("post_id")},
        {"$set": {
            "email_dispatched_at": now_iso,
            "email_dispatch_stats": {"total": sent + failed, "sent": sent, "failed": failed},
        }},
    )
    await db.news_audit.insert_one({
        "action": "email_dispatched", "post_id": post.get("post_id", ""),
        "user_id": post.get("owner_id") or post.get("author_id", ""),
        "user_name": post.get("owner_name") or post.get("author_name", ""),
        "timestamp": now_iso,
        "details": f"Newsletter an {sent}/{sent + failed} Empfaenger (Channels: {','.join(channels)})",
    })
    logger.info(f"[NEWSLETTER] Post {post.get('post_id')} dispatched: {sent}/{sent + failed}")
    return {"total": sent + failed, "sent": sent, "failed": failed, "dispatched_at": now_iso}
