"""
Health alerting: fires e-mail + web-push notifications to admins when
health metrics cross configured thresholds.

Rules (MVP, all optional):
    email_rate       — alert when 7d e-mail-success-rate drops below a threshold
                       AND total sends in 7d exceed `email_rate_min_sends`
    session_anomaly  — alert when any user has >= threshold refreshes in 24h
    email_last_fail  — alert when the most recent e-mail send failed
                       (de-duped so we don't spam on the same error)

Each rule is throttled to at most one alert per `cooldown_hours` (default 6),
tracked in the `health_alert_state` collection per rule-key.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from database import db

logger = logging.getLogger(__name__)

DEFAULT_CFG = {
    "enabled": True,
    "email_rate_threshold": 80.0,         # percent
    "email_rate_min_sends": 5,            # only fire when we have enough volume
    "session_anomaly_threshold": 30,      # refreshes per user per 24h
    "session_anomaly_count": 1,           # fire if >= this many users hit threshold
    "alert_on_last_failure": True,
    "cron_idle_minutes": 90,              # alert when no maintenance tick within N min
    "cooldown_hours": 6,
    "channels": ["email", "push"],        # which channels to use for alerts
    "recipients": [],                     # explicit admin e-mails; empty = all role=admin
}


async def get_alert_config() -> Dict[str, Any]:
    cfg = await db.health_alert_config.find_one({"config_id": "global"}, {"_id": 0})
    return {**DEFAULT_CFG, **(cfg or {})}


async def set_alert_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    updates = {k: v for k, v in (updates or {}).items() if k in DEFAULT_CFG}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.health_alert_config.update_one(
        {"config_id": "global"},
        {"$set": updates, "$setOnInsert": {"config_id": "global"}},
        upsert=True,
    )
    return await get_alert_config()


async def _within_cooldown(rule_key: str, cooldown_hours: int) -> bool:
    doc = await db.health_alert_state.find_one({"rule_key": rule_key}, {"_id": 0, "last_ts": 1})
    if not doc or not doc.get("last_ts"):
        return False
    last = doc["last_ts"]
    if isinstance(last, str):
        last = datetime.fromisoformat(last)
    # Mongo returns BSON datetimes as tz-naive by default — normalise to UTC
    # so the subtraction below doesn't raise (iter 121 fix).
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last) < timedelta(hours=cooldown_hours)


async def _mark_fired(rule_key: str, details: Dict[str, Any]) -> None:
    await db.health_alert_state.update_one(
        {"rule_key": rule_key},
        {"$set": {
            "rule_key": rule_key,
            "last_ts": datetime.now(timezone.utc),
            "last_details": details,
        }},
        upsert=True,
    )


async def _resolve_recipients(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    explicit = cfg.get("recipients") or []
    if explicit:
        users = await db.users.find({"email": {"$in": explicit}}, {"_id": 0, "user_id": 1, "email": 1, "name": 1}).to_list(200)
        return users
    return await db.users.find({"role": "admin"}, {"_id": 0, "user_id": 1, "email": 1, "name": 1}).to_list(50)


def _render_email_html(subject: str, lines: List[str]) -> str:
    items = "".join(f"<li style='margin:4px 0;'>{line}</li>" for line in lines)
    return f"""
    <div style="font-family:Arial,sans-serif;padding:24px;max-width:580px;">
      <h2 style="color:#4A5D4E;margin:0 0 8px;">MeetFlow Health-Alert</h2>
      <p style="color:#6B7280;margin:0 0 16px;">{subject}</p>
      <ul style="color:#1C1F1D;line-height:1.5;padding-left:20px;">{items}</ul>
      <p style="color:#9CA3AF;font-size:12px;margin-top:20px;">
        Du erhältst diese Nachricht, weil Du als Admin in MeetFlow eingetragen bist.
        Einstellungen änderst Du unter Verwaltung › Health › Alert-Einstellungen.
      </p>
    </div>
    """


async def _dispatch_alert(subject: str, lines: List[str], cfg: Dict[str, Any], *, severity: str = "warn") -> Dict[str, Any]:
    """Send the alert through enabled channels. Returns a per-channel summary."""
    recipients = await _resolve_recipients(cfg)
    if not recipients:
        return {"dispatched": 0, "reason": "no_recipients"}

    channels = cfg.get("channels") or ["email", "push"]
    email_count = push_count = 0

    if "email" in channels:
        from services.email import send_email_real
        html = _render_email_html(subject, lines)
        for u in recipients:
            try:
                await send_email_real(u["email"], f"[MeetFlow] {subject}", html)
                email_count += 1
            except Exception as e:
                logger.warning(f"[health_alerts] email to {u['email']} failed: {e}")

    if "push" in channels:
        try:
            from services.news_push import send_push_to_user
            for u in recipients:
                try:
                    await send_push_to_user(
                        u["user_id"],
                        title="MeetFlow Health-Alert",
                        body=subject,
                        data={"type": "health_alert", "severity": severity},
                    )
                    push_count += 1
                except Exception as e:
                    logger.debug(f"[health_alerts] push to {u['user_id']} skipped: {e}")
        except Exception as e:
            logger.debug(f"[health_alerts] push module missing: {e}")

    # Audit-log the alert (systemic, no user-request context)
    try:
        from services.permission_audit import log_caps_change
        await log_caps_change(
            actor={"user_id": "system", "name": "Health-Alerting", "email": "system@meetflow"},
            target_user_id="admins", action="health_alert",
            category="alert",
            details={"subject": subject, "severity": severity,
                     "emails": email_count, "pushes": push_count,
                     "recipients": len(recipients), "lines": lines[:6]},
        )
    except Exception:
        pass

    return {"dispatched": email_count + push_count, "emails": email_count, "pushes": push_count, "recipients": len(recipients)}


async def check_and_alert(*, force: bool = False) -> Dict[str, Any]:
    """Evaluate all rules. Returns a summary of what fired."""
    cfg = await get_alert_config()
    if not cfg.get("enabled", True) and not force:
        return {"skipped": "disabled"}

    from services.health_metrics import email_stats, auth_refresh_anomalies
    emails = await email_stats(days=7)
    anomalies = await auth_refresh_anomalies(hours=24, threshold=int(cfg["session_anomaly_threshold"]))
    cooldown = int(cfg.get("cooldown_hours", 6)) if not force else 0

    fired: List[Dict[str, Any]] = []

    # Rule 1: e-mail success rate
    rate = emails.get("success_rate")
    if (rate is not None
            and emails.get("total", 0) >= int(cfg["email_rate_min_sends"])
            and rate < float(cfg["email_rate_threshold"])):
        rule_key = "email_rate"
        if force or not await _within_cooldown(rule_key, cooldown):
            lines = [
                f"E-Mail-Erfolgsrate (7 Tage) ist auf <strong>{rate}%</strong> gefallen (Schwelle {cfg['email_rate_threshold']}%).",
                f"Gesendet: {emails['sent']} · Fehler: {emails['failed']} · Simuliert: {emails['simulated']}.",
            ]
            if emails.get("last_failure"):
                lf = emails["last_failure"]
                lines.append(f"Letzter Fehler: {lf.get('to')} via {lf.get('provider')} — {lf.get('error', '')}")
            res = await _dispatch_alert("E-Mail-Versand: Erfolgsrate gefallen", lines, cfg, severity="error")
            await _mark_fired(rule_key, {"rate": rate, "total": emails["total"]})
            fired.append({"rule": rule_key, **res})

    # Rule 2: session anomalies
    if (anomalies.get("anomalies") or []) and len(anomalies["anomalies"]) >= int(cfg["session_anomaly_count"]):
        rule_key = "session_anomaly"
        if force or not await _within_cooldown(rule_key, cooldown):
            top = anomalies["anomalies"][:5]
            lines = [f"{len(anomalies['anomalies'])} Nutzer mit &ge; {cfg['session_anomaly_threshold']} Token-Refreshes in 24h:"]
            for a in top:
                lines.append(f"{a.get('email', a['user_id'])} — {a['count']} Refreshes (zuletzt {a['last']})")
            res = await _dispatch_alert("Session-Anomalie erkannt", lines, cfg, severity="warn")
            await _mark_fired(rule_key, {"count": len(anomalies["anomalies"])})
            fired.append({"rule": rule_key, **res})

    # Rule 3: last e-mail send failed
    last_fail = emails.get("last_failure")
    if cfg.get("alert_on_last_failure") and last_fail:
        rule_key = f"last_failure:{(last_fail.get('error') or '')[:80]}"
        if force or not await _within_cooldown(rule_key, cooldown):
            lines = [
                f"Letzter E-Mail-Versuch fehlgeschlagen an <strong>{last_fail.get('to')}</strong>",
                f"Provider: {last_fail.get('provider')}",
                f"Fehler: {last_fail.get('error')}",
                f"Betreff: {last_fail.get('subject')}",
            ]
            res = await _dispatch_alert("E-Mail-Versand: aktueller Fehler", lines, cfg, severity="error")
            await _mark_fired(rule_key, {"error": last_fail.get("error")})
            fired.append({"rule": "last_failure", **res})

    # Rule 4: cron-idle — maintenance loop hasn't ticked recently
    idle_minutes = int(cfg.get("cron_idle_minutes", 90) or 90)
    if idle_minutes > 0:
        last_tick = await db.maintenance_runs.find_one(
            {}, {"_id": 0, "ts": 1, "task": 1}, sort=[("ts", -1)],
        )
        if last_tick and isinstance(last_tick.get("ts"), datetime):
            tick_ts = last_tick["ts"]
            # Ensure timezone-aware comparison
            if tick_ts.tzinfo is None:
                tick_ts = tick_ts.replace(tzinfo=timezone.utc)
            age_min = (datetime.now(timezone.utc) - tick_ts).total_seconds() / 60
            if age_min >= idle_minutes:
                rule_key = "cron_idle"
                if force or not await _within_cooldown(rule_key, cooldown):
                    lines = [
                        f"Der Wartungs-Cron hat seit <strong>{int(age_min)} Min</strong> keinen Lauf mehr protokolliert.",
                        f"Letzter Task: {last_tick.get('task')} um {last_tick['ts'].isoformat()}.",
                        "Mögliche Ursachen: Backend-Restart-Schleife, blockierter Event-Loop oder Datenbank-Timeout.",
                    ]
                    res = await _dispatch_alert("Wartungs-Cron läuft nicht mehr", lines, cfg, severity="error")
                    await _mark_fired(rule_key, {"idle_minutes": int(age_min)})
                    fired.append({"rule": "cron_idle", **res})

    return {"fired": fired, "checked_at": datetime.now(timezone.utc).isoformat(), "forced": force}


async def list_recent_alerts(limit: int = 20) -> List[Dict[str, Any]]:
    docs = await db.health_alert_state.find({}, {"_id": 0}).sort("last_ts", -1).to_list(limit)
    for d in docs:
        if isinstance(d.get("last_ts"), datetime):
            d["last_ts"] = d["last_ts"].isoformat()
    return docs
