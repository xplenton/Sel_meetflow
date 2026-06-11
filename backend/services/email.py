import os
import asyncio
import logging
from database import db

logger = logging.getLogger("server")


async def send_email_real(to_email: str, subject: str, html_content: str) -> dict:
    """Dispatch via configured provider (Resend/SendGrid/SMTP/none).

    If `fallback_to_smtp` is enabled in `email_config` and the primary provider
    returns a failed status, SMTP is tried as a fallback. Returns the last non-
    simulated result.
    """
    config = await db.email_config.find_one({"config_id": "global"}, {"_id": 0}) or {}
    provider = (config.get("provider") or "none").lower()
    smtp_doc = config.get("smtp") if isinstance(config.get("smtp"), dict) else None
    smtp_complete = bool(
        smtp_doc and smtp_doc.get("host") and smtp_doc.get("port")
        and smtp_doc.get("username") and smtp_doc.get("password")
    )
    # iter 207 — Auto-promote: if the admin saved a complete SMTP config but
    # forgot to switch the provider dropdown to "smtp", treat it as smtp.
    # Previously the request short-circuited to "logged" and the UI showed
    # "E-Mail-Versand fehlgeschlagen" even though credentials were ready.
    if provider == "none" and config.get("enabled") is not False and smtp_complete:
        logger.info("[EMAIL] provider='none' but SMTP fully configured — auto-using SMTP")
        provider = "smtp"
    # iter 154 — Respect the `enabled` flag: when the admin has disabled
    # email or not explicitly configured a provider (`provider='none'`),
    # short-circuit to a simulated/logged send. Previously an old stale
    # SMTP stub in the config doc triggered a real-but-failing SMTP call
    # and the UI reported "E-Mail konnte nicht gesendet werden" even
    # though the admin never enabled email.
    if config.get("enabled") is False or provider == "none":
        logger.info(f"[EMAIL DISABLED] To: {to_email} | Subject: {subject}")
        return {"provider": "simulated", "status": "logged"}
    resend_key = config["api_key"] if provider == "resend" and config.get("api_key") else ""
    sendgrid_key = config["api_key"] if provider == "sendgrid" and config.get("api_key") else ""
    smtp_cfg = config.get("smtp") if provider == "smtp" else None
    sender = config.get("sender_email") or os.environ.get("SENDER_EMAIL", "noreply@meetflow.app")
    fallback_smtp = bool(config.get("fallback_to_smtp")) and isinstance(config.get("smtp"), dict) and (config.get("smtp") or {}).get("host")

    if not resend_key:
        resend_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not sendgrid_key:
        sendgrid_key = os.environ.get("SENDGRID_API_KEY", "").strip()

    last_result = None

    if provider == "smtp" or (provider in ("none", "") and smtp_cfg is None and not resend_key and not sendgrid_key and config.get("smtp")):
        # SMTP as primary (explicit or only provider configured)
        from services.email_smtp import send_via_smtp
        last_result = await send_via_smtp(config.get("smtp") or {}, to_email, subject, html_content, from_email=sender)
        if last_result.get("status") == "sent":
            return last_result

    if resend_key:
        try:
            import resend
            resend.api_key = resend_key
            # iter 176 — Resend's sandbox sender (`onboarding@resend.dev`)
            # only delivers to the Resend account owner; every other
            # recipient is rejected with 550 "Sender address is not allowed".
            # Detect this pattern early and return a clear, actionable error
            # instead of surfacing the raw 550.
            if '@resend.dev' in (sender or '') or (sender or '').startswith('onboarding@'):
                err = (
                    "Resend-Sandbox-Absender (onboarding@resend.dev) kann nur an "
                    "die E-Mail des Resend-Kontoinhabers senden. Bitte unter "
                    "resend.com/domains eine eigene Domain verifizieren und den "
                    "Absender in der Admin → Integrationen auf deine Domain "
                    "ändern (z. B. noreply@deine-klinik.de)."
                )
                logger.warning(f"[RESEND] sandbox sender rejected: {sender}")
                last_result = {"provider": "resend", "status": "failed", "error": err}
            else:
                params = {"from": sender, "to": [to_email], "subject": subject, "html": html_content}
                result = await asyncio.to_thread(resend.Emails.send, params)
                logger.info(f"[RESEND] Email sent to {to_email}: {result}")
                last_result = {"provider": "resend", "status": "sent", "id": str(result.get("id", "") if isinstance(result, dict) else result)}
                return last_result
        except Exception as e:
            msg = str(e)
            # Translate the raw Resend 550 sandbox rejection into a
            # friendly, actionable message (covers edge case where the
            # sender was accepted but the recipient triggers the 550).
            if "Sender address is not allowed" in msg or ("550" in msg and "resend.dev" in msg):
                msg = (
                    "Resend lehnt den Absender ab. Wahrscheinlich nutzt du den "
                    "Sandbox-Absender (onboarding@resend.dev), der nur an den "
                    "Kontoinhaber zustellt. Verifiziere eine eigene Domain unter "
                    "resend.com/domains und setze den Absender in Admin → "
                    "Integrationen auf deine Domain."
                )
            logger.warning(f"[RESEND] Failed: {e}")
            last_result = {"provider": "resend", "status": "failed", "error": msg}
            # fall through to possible fallback below

    if sendgrid_key:
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail
            message = Mail(from_email=sender, to_emails=to_email, subject=subject, html_content=html_content)
            sg = SendGridAPIClient(sendgrid_key)
            resp = await asyncio.to_thread(sg.send, message)
            logger.info(f"[SENDGRID] Email sent to {to_email}: {resp.status_code}")
            last_result = {"provider": "sendgrid", "status": "sent", "code": resp.status_code}
            return last_result
        except Exception as e:
            logger.warning(f"[SENDGRID] Failed: {e}")
            last_result = {"provider": "sendgrid", "status": "failed", "error": str(e)}

    if fallback_smtp and (not last_result or last_result.get("status") != "sent"):
        from services.email_smtp import send_via_smtp
        smtp_res = await send_via_smtp(config.get("smtp") or {}, to_email, subject, html_content, from_email=sender)
        smtp_res["fallback"] = True
        if smtp_res.get("status") == "sent":
            return smtp_res
        last_result = smtp_res

    if last_result and last_result.get("status") == "failed":
        return last_result

    logger.info(f"[EMAIL SIMULATED] To: {to_email} | Subject: {subject}")
    return {"provider": "simulated", "status": "logged"}


# Decorate send_email_real with fire-and-forget logging
_orig_send = send_email_real


async def send_email_real(to_email: str, subject: str, html_content: str, category: str | None = None) -> dict:  # type: ignore[no-redef]
    """Send transactional or notification email.

    Iter 277 — `category` parameter (one of news/meetings/surveys/chat/feedback)
    activates the per-user opt-out filter. If the user disabled email for that
    category in their profile, the send is short-circuited and we return a
    `{"status": "suppressed_by_prefs"}` result. Transactional mails (password
    reset, security, SSO, ICS invites) MUST omit `category` so they always go
    out regardless of the user's preferences.
    """
    if category:
        try:
            # Find the recipient by email and check preferences
            user = await db.users.find_one({"email": (to_email or "").lower().strip()}, {"_id": 0, "user_id": 1})
            if user and user.get("user_id"):
                from services.notification_prefs import is_allowed
                allowed = await is_allowed(user["user_id"], category, "email")
                if not allowed:
                    logger.info(f"[EMAIL SUPPRESSED] {to_email} muted '{category}' (email) — skip")
                    return {"provider": "suppressed_by_prefs", "status": "suppressed_by_prefs", "category": category}
        except Exception as e:
            # Never block sending because of a pref-lookup failure
            logger.warning(f"[EMAIL pref-check failed] {e} — sending anyway")

    result = await _orig_send(to_email, subject, html_content)
    try:
        from services.health_metrics import log_email_send
        await log_email_send(to_email, subject, result)
    except Exception:
        pass
    return result


def build_meeting_email_html(inviter_name: str, meeting_title: str, join_link: str, message: str = "") -> str:
    return f"""
    <div style="font-family:'Work Sans',Arial,sans-serif;max-width:520px;margin:0 auto;padding:32px;background:#F9F9F8;border-radius:12px;">
      <div style="text-align:center;margin-bottom:24px;">
        <span style="font-family:'Manrope',sans-serif;font-size:20px;font-weight:600;color:#4A5D4E;">MeetFlow</span>
      </div>
      <div style="background:#fff;border:1px solid #E2E4E0;border-radius:12px;padding:24px;">
        <h2 style="font-family:'Manrope',sans-serif;font-size:18px;color:#1C1F1D;margin:0 0 8px 0;">Meeting Invitation</h2>
        <p style="color:#4B5563;font-size:14px;margin:0 0 16px 0;"><strong>{inviter_name}</strong> invited you to:</p>
        <div style="background:#F3F4F1;border-radius:8px;padding:16px;margin-bottom:16px;">
          <p style="font-weight:600;color:#1C1F1D;margin:0;font-size:16px;">{meeting_title}</p>
        </div>
        {f'<p style="color:#4B5563;font-size:14px;">{message}</p>' if message else ''}
        <a href="{join_link}" style="display:inline-block;background:#4A5D4E;color:#fff;text-decoration:none;padding:12px 32px;border-radius:9999px;font-weight:500;font-size:14px;margin-top:8px;">Join Meeting</a>
      </div>
      <p style="text-align:center;color:#9CA3AF;font-size:11px;margin-top:16px;">Sent via MeetFlow</p>
    </div>
    """


def build_summary_email_html(meeting_title: str, meeting_date: str, participants: list, summary_text: str) -> str:
    date_str = ""
    if meeting_date:
        try:
            from datetime import datetime as dt
            d = dt.fromisoformat(meeting_date.replace("Z", "+00:00")) if isinstance(meeting_date, str) else meeting_date
            date_str = d.strftime("%d.%m.%Y, %H:%M Uhr")
        except Exception:
            date_str = str(meeting_date)
    participant_names = ", ".join([p.get("name", "Unknown") for p in participants[:20]])
    summary_html = summary_text.replace("\n", "<br>") if summary_text else "Keine Zusammenfassung verfügbar."
    return f"""
    <div style="font-family:'Work Sans',Arial,sans-serif;max-width:600px;margin:0 auto;padding:32px;background:#F9F9F8;border-radius:12px;">
      <div style="text-align:center;margin-bottom:24px;">
        <span style="font-family:'Manrope',sans-serif;font-size:20px;font-weight:600;color:#4A5D4E;">MeetFlow</span>
      </div>
      <div style="background:#fff;border:1px solid #E2E4E0;border-radius:12px;padding:24px;">
        <h2 style="font-family:'Manrope',sans-serif;font-size:18px;color:#1C1F1D;margin:0 0 16px 0;">Meeting-Zusammenfassung</h2>
        <div style="background:#F3F4F1;border-radius:8px;padding:16px;margin-bottom:16px;">
          <p style="font-weight:600;color:#1C1F1D;margin:0 0 4px 0;font-size:16px;">{meeting_title}</p>
          {f'<p style="color:#6B7280;font-size:13px;margin:0 0 4px 0;">{date_str}</p>' if date_str else ''}
          <p style="color:#9CA3AF;font-size:12px;margin:0;">Teilnehmer: {participant_names}</p>
        </div>
        <div style="color:#4B5563;font-size:14px;line-height:1.7;border-left:3px solid #4A5D4E;padding-left:16px;margin:16px 0;">
          {summary_html}
        </div>
      </div>
      <p style="text-align:center;color:#9CA3AF;font-size:11px;margin-top:16px;">Automatisch generiert von MeetFlow KI</p>
    </div>
    """


def build_invite_email_html(inviter_name: str, invitee_name: str, email: str, temp_password: str, login_url: str, role: str = "Mitglied") -> str:
    role_labels = {"admin": "Administrator", "manager": "Manager", "member": "Mitglied", "guest": "Gast"}
    role_label = role_labels.get(role, role)
    return f"""
    <div style="font-family:'Work Sans',Arial,sans-serif;max-width:520px;margin:0 auto;padding:32px;background:#F9F9F8;border-radius:12px;">
      <div style="text-align:center;margin-bottom:24px;">
        <span style="font-family:'Manrope',sans-serif;font-size:20px;font-weight:600;color:#4A5D4E;">MeetFlow</span>
      </div>
      <div style="background:#fff;border:1px solid #E2E4E0;border-radius:12px;padding:24px;">
        <h2 style="font-family:'Manrope',sans-serif;font-size:18px;color:#1C1F1D;margin:0 0 8px 0;">Willkommen bei MeetFlow!</h2>
        <p style="color:#4B5563;font-size:14px;margin:0 0 16px 0;"><strong>{inviter_name}</strong> hat Sie als <strong>{role_label}</strong> eingeladen.</p>
        <div style="background:#F3F4F1;border-radius:8px;padding:16px;margin-bottom:16px;">
          <p style="color:#6B7280;font-size:12px;margin:0 0 8px 0;">Ihre Zugangsdaten:</p>
          <p style="color:#1C1F1D;font-size:14px;margin:0 0 4px 0;"><strong>E-Mail:</strong> {email}</p>
          <p style="color:#1C1F1D;font-size:14px;margin:0;"><strong>Passwort:</strong> {temp_password}</p>
        </div>
        <p style="color:#C87967;font-size:12px;margin:0 0 16px 0;">Bitte aendern Sie Ihr Passwort nach der ersten Anmeldung.</p>
        <a href="{login_url}" style="display:inline-block;background:#4A5D4E;color:#fff;text-decoration:none;padding:12px 32px;border-radius:9999px;font-weight:500;font-size:14px;">Jetzt anmelden</a>
      </div>
      <p style="text-align:center;color:#9CA3AF;font-size:11px;margin-top:16px;">Gesendet via MeetFlow</p>
    </div>
    """
