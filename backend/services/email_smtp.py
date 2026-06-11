"""
SMTP-Provider for MeetFlow — used as primary or as fallback behind Resend/SendGrid.

Config lives in db.email_config and may contain:
    provider: 'resend' | 'sendgrid' | 'smtp' | 'none'
    smtp: {host, port, username, password, use_tls, use_starttls, from_name, from_email}
    fallback_to_smtp: bool (if True, SMTP is tried when the primary provider fails)
"""
from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


async def send_via_smtp(
    smtp_cfg: Dict[str, Any],
    to_email: str,
    subject: str,
    html: str,
    *,
    text_alt: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Send a single e-mail via SMTP. `attachments` items:
    {filename, content (bytes), content_type}.

    Returns {provider:'smtp', status:'sent'|'failed', error?}."""
    try:
        import aiosmtplib
    except Exception as e:
        return {"provider": "smtp", "status": "failed", "error": f"aiosmtplib missing: {e}"}

    host = (smtp_cfg or {}).get("host", "").strip()
    port = int((smtp_cfg or {}).get("port", 587) or 587)
    username = (smtp_cfg or {}).get("username", "")
    password = (smtp_cfg or {}).get("password", "")
    # iter 176 — normalize TLS flags from port (same logic as smtp_health_check)
    raw_use_tls = bool((smtp_cfg or {}).get("use_tls", False))
    raw_starttls = bool((smtp_cfg or {}).get("use_starttls", True))
    if port == 465:
        use_tls, use_starttls = True, False
    elif port == 587:
        use_tls, use_starttls = False, True
    elif raw_use_tls and raw_starttls:
        use_tls, use_starttls = True, False
    else:
        use_tls, use_starttls = raw_use_tls, raw_starttls
    sender_email = from_email or (smtp_cfg or {}).get("from_email") or username
    sender_name = from_name or (smtp_cfg or {}).get("from_name") or "MeetFlow"

    if not host:
        return {"provider": "smtp", "status": "failed", "error": "SMTP host missing"}
    if not sender_email:
        return {"provider": "smtp", "status": "failed", "error": "Sender e-mail missing"}

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender_email}>" if sender_name else sender_email
    msg["To"] = to_email
    # Iter 181 — some SMTP servers (e.g. Office365, IONOS) reject mails that
    # don't carry an explicit Message-ID + Date. Add them defensively.
    import email.utils as _eu
    msg["Message-ID"] = _eu.make_msgid(domain=sender_email.split("@", 1)[-1] if "@" in sender_email else "meetflow.local")
    msg["Date"] = _eu.formatdate(localtime=True)
    body = MIMEMultipart("alternative")
    if text_alt:
        body.attach(MIMEText(text_alt, "plain", "utf-8"))
    body.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(body)

    for att in (attachments or []):
        try:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(att["content"])
            encoders.encode_base64(part)
            part.add_header("Content-Type", att.get("content_type", "application/octet-stream"))
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{att.get("filename", "attachment.bin")}"',
            )
            msg.attach(part)
        except Exception as e:  # non-fatal for a single attachment
            logger.warning(f"[SMTP] attach failed: {e}")

    try:
        # Iter 181 — use an EXPLICIT SMTP session instead of aiosmtplib.send()
        # convenience helper. The helper has a known edge case where, at
        # port 587 with STARTTLS, it may issue STARTTLS even though the
        # server already auto-upgraded the connection via EHLO — producing
        # "Connection already using TLS" for exactly-configured-correctly
        # setups (common with 1&1 / IONOS / Strato on :587). Mirrors the
        # same try/except pattern already used by smtp_health_check.
        client = aiosmtplib.SMTP(hostname=host, port=port, use_tls=use_tls, timeout=25)
        await client.connect()
        if use_starttls and not use_tls:
            try:
                await client.starttls()
            except aiosmtplib.SMTPException as se:
                # Server auto-negotiated TLS already (some IONOS/1&1 servers
                # do this when use_tls flag is implicit). Not a real error.
                if "already using TLS" not in str(se):
                    raise
        if username and password:
            await client.login(username, password)
        await client.send_message(msg, sender=sender_email, recipients=[to_email])
        await client.quit()
        logger.info(f"[SMTP] Email sent to {to_email} via {host}:{port} (from={sender_email})")
        return {"provider": "smtp", "status": "sent"}
    except Exception as e:
        # Iter 181 — translate the raw aiosmtplib exception into an
        # actionable message so the admin can tell apart
        #   auth issue   → check username/password
        #   relay issue  → sender != authenticated user
        #   recipient rej→ typo in to_email / blocked domain
        #   TLS issue    → wrong port/flag combination
        raw = str(e)
        import aiosmtplib as _ais
        hint = None
        if isinstance(e, getattr(_ais, "SMTPAuthenticationError", tuple())):
            hint = "Authentifizierung fehlgeschlagen — Benutzername oder Passwort falsch (manche Provider verlangen ein App-spezifisches Passwort)."
        elif isinstance(e, getattr(_ais, "SMTPRecipientsRefused", tuple())):
            hint = f"Empfaenger abgelehnt: {to_email}"
        elif isinstance(e, getattr(_ais, "SMTPSenderRefused", tuple())):
            hint = (
                f"Absender {sender_email} wurde abgelehnt. Ursache meist: "
                "Envelope-Sender != authentifizierter User, oder fehlender "
                "SPF/DKIM. Setze 'from_email' = dem SMTP-Login-User."
            )
        elif "STARTTLS" in raw or "TLS" in raw or "SSL" in raw:
            hint = (
                "TLS-Problem: Prüfe Port (465 = implicit TLS, 587 = STARTTLS). "
                "Beide Flags gleichzeitig fuehrten historisch zu 'already using TLS'."
            )
        elif "550" in raw or "551" in raw or "553" in raw:
            hint = f"SMTP 5xx Response vom Server: {raw}"
        logger.warning(f"[SMTP] Failed to send to {to_email} via {host}:{port} (from={sender_email}): {raw}")
        return {
            "provider": "smtp",
            "status": "failed",
            "error": f"{hint} (raw: {raw})" if hint else raw,
            "smtp_host": host,
            "smtp_port": port,
            "from_email": sender_email,
        }


async def smtp_health_check(smtp_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Quick connect + EHLO without actually sending. Useful for admin UI."""
    try:
        import aiosmtplib
    except Exception as e:
        return {"ok": False, "error": f"aiosmtplib missing: {e}"}

    host = (smtp_cfg or {}).get("host", "").strip()
    port = int((smtp_cfg or {}).get("port", 587) or 587)
    # iter 176 — normalize TLS flags from port so "beide aktiv" configs
    # don't trip "Connection already using TLS" when the server already
    # negotiated implicit TLS on connect. Resolution rules:
    #   - 465  → implicit TLS (use_tls=True, starttls=False)
    #   - 587  → STARTTLS    (use_tls=False, starttls=True)
    #   - everything else → respect user flags, but never both at once.
    raw_use_tls = bool((smtp_cfg or {}).get("use_tls", False))
    raw_starttls = bool((smtp_cfg or {}).get("use_starttls", True))
    if port == 465:
        use_tls, use_starttls = True, False
    elif port == 587:
        use_tls, use_starttls = False, True
    elif raw_use_tls and raw_starttls:
        # Port unknown, both flags set → prefer implicit TLS (safer choice).
        use_tls, use_starttls = True, False
    else:
        use_tls, use_starttls = raw_use_tls, raw_starttls
    username = (smtp_cfg or {}).get("username") or None
    password = (smtp_cfg or {}).get("password") or None
    if not host:
        return {"ok": False, "error": "SMTP host missing"}
    client = aiosmtplib.SMTP(hostname=host, port=port, use_tls=use_tls, timeout=15)
    try:
        await client.connect()
        if use_starttls and not use_tls:
            try:
                await client.starttls()
            except aiosmtplib.SMTPException as se:
                # Connection may already be TLS-upgraded by the server
                # auto-negotiation — treat as success if the error is exactly
                # "already using TLS". Any other STARTTLS error bubbles up.
                if "already using TLS" not in str(se):
                    raise
        if username and password:
            await client.login(username, password)
        await client.quit()
        return {
            "ok": True,
            "tls_mode": "implicit" if use_tls else ("starttls" if use_starttls else "plain"),
            "port": port,
        }
    except Exception as e:
        try:
            await client.quit()
        except Exception:
            pass
        return {"ok": False, "error": str(e)}
