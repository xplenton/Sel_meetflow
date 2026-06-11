"""routes/admin/system.py — Migration, stats, email, audit, health, reminders, API, policies, maintenance, branding (split out from routes/admin.py in iter 261)."""
from fastapi import APIRouter, HTTPException, Request
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from database import db, read_db
from dependencies import get_current_user
from services.email import send_email_real
from services.permissions import (
    migrate_role, extra_grants_for_legacy,
    require_cap,
)
from models import MeetingPolicyRequest

router = APIRouter()

@router.post("/admin/migrate-roles")
async def migrate_legacy_roles(request: Request):
    """One-shot migration of legacy roles → new 4-role system.
    Idempotent — safe to run multiple times."""
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_roles", db)

    results = {"migrated": 0, "unchanged": 0, "details": []}
    async for u in db.users.find({}, {"_id": 0, "user_id": 1, "role": 1, "email": 1, "cap_grants": 1}):
        old_role = u.get("role", "member")
        new_role = migrate_role(old_role)
        extra = extra_grants_for_legacy(old_role)

        if new_role == old_role and not extra:
            results["unchanged"] += 1
            continue

        existing_grants = set(u.get("cap_grants", []) or [])
        existing_grants.update(extra)
        await db.users.update_one(
            {"user_id": u["user_id"]},
            {"$set": {
                "role": new_role,
                "legacy_role": old_role,
                "cap_grants": sorted(list(existing_grants)),
                "migrated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        results["migrated"] += 1
        results["details"].append({"email": u.get("email"), "from": old_role, "to": new_role, "extra_caps": extra})
    return results



@router.get("/admin/stats")
async def admin_stats(request: Request):
    user = await get_current_user(request)
    # Iter 398 — Granular cap check: Admins haben standardmaessig die Cap;
    # zusaetzlich darf jede Gruppe via Capability `analytics.view_platform_stats`
    # diesen Endpoint nutzen ohne Voll-Admin zu sein.
    from services.permissions import require_cap
    from database import db as _db
    await require_cap(user, "analytics.view_platform_stats", _db)
    # Iter 188 — pure read aggregates → SECONDARY when RS deployed.
    total_users = await read_db.users.count_documents({})
    total_meetings = await read_db.meetings.count_documents({})
    active_meetings = await read_db.meetings.count_documents({"status": "active"})
    ended_meetings = await read_db.meetings.count_documents({"status": "ended"})
    total_messages = await read_db.chat_messages.count_documents({})
    total_polls = await read_db.polls.count_documents({})
    total_recordings = await read_db.recordings.count_documents({})
    return {
        "total_users": total_users, "total_meetings": total_meetings,
        "active_meetings": active_meetings, "ended_meetings": ended_meetings,
        "total_messages": total_messages, "total_polls": total_polls,
        "total_recordings": total_recordings,
    }



@router.get("/admin/email-config")
async def get_email_config(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    config = await db.email_config.find_one({"config_id": "global"}, {"_id": 0})
    if not config:
        config = {
            "config_id": "global", "provider": "none", "api_key": "",
            "sender_email": "noreply@meetflow.app", "enabled": False,
            "smtp": {"host": "", "port": 587, "username": "", "password": "",
                     "use_tls": False, "use_starttls": True,
                     "from_name": "MeetFlow", "from_email": ""},
            "fallback_to_smtp": False,
        }
    masked = {**config, "api_key": ("***" + config["api_key"][-6:]) if len(config.get("api_key", "")) > 6 else ("***" if config.get("api_key") else "")}
    smtp = dict(config.get("smtp") or {})
    if smtp.get("password"):
        smtp["password"] = "***" + smtp["password"][-4:] if len(smtp["password"]) > 4 else "***"
    masked["smtp"] = {
        "host": smtp.get("host", ""), "port": smtp.get("port", 587),
        "username": smtp.get("username", ""), "password": smtp.get("password", ""),
        "use_tls": bool(smtp.get("use_tls", False)),
        "use_starttls": bool(smtp.get("use_starttls", True)),
        "from_name": smtp.get("from_name", "MeetFlow"),
        "from_email": smtp.get("from_email", ""),
    }
    masked["fallback_to_smtp"] = bool(config.get("fallback_to_smtp", False))
    return masked

@router.put("/admin/email-config")
async def update_email_config(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    allowed = ["provider", "api_key", "sender_email", "enabled", "fallback_to_smtp"]
    updates = {k: v for k, v in body.items() if k in allowed}
    existing = await db.email_config.find_one({"config_id": "global"}, {"_id": 0}) or {}
    if existing and str(updates.get("api_key", "")).startswith("***"):
        del updates["api_key"]
    # Handle SMTP block: only keep fields explicitly sent, mask-preserve password
    smtp_in = body.get("smtp")
    if isinstance(smtp_in, dict):
        smtp_existing = existing.get("smtp") or {}
        smtp_clean = {
            "host": (smtp_in.get("host") or "").strip(),
            "port": int(smtp_in.get("port") or 587),
            "username": smtp_in.get("username") or "",
            "use_tls": bool(smtp_in.get("use_tls", False)),
            "use_starttls": bool(smtp_in.get("use_starttls", True)),
            "from_name": smtp_in.get("from_name") or "MeetFlow",
            "from_email": smtp_in.get("from_email") or "",
        }
        pw_in = smtp_in.get("password") or ""
        if pw_in and not str(pw_in).startswith("***"):
            smtp_clean["password"] = pw_in
        else:
            smtp_clean["password"] = smtp_existing.get("password") or ""
        updates["smtp"] = smtp_clean
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.email_config.update_one({"config_id": "global"}, {"$set": updates, "$setOnInsert": {"config_id": "global"}}, upsert=True)
    return {"message": "Email config updated"}

@router.post("/admin/email-config/test")
async def test_email_config(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    to_email = body.get("to_email", user.get("email", ""))
    target_provider = (body.get("provider") or "").lower()  # optional override to test SMTP explicitly
    # Iter 182 — allow testing BEFORE saving by accepting an inline smtp
    # config. If provided, we use it directly instead of the stored one.
    # Frontend passes `{to_email, provider:'smtp', smtp:{...currentUIState}}`
    # so the admin can "dry-run" an unsaved configuration.
    inline_smtp = body.get("smtp") if isinstance(body.get("smtp"), dict) else None
    inline_sender = body.get("sender_email") or ""
    if not to_email:
        raise HTTPException(status_code=400, detail="No recipient email")
    subject = "MeetFlow - Test E-Mail"
    html = "<div style='font-family:Arial,sans-serif;padding:24px;'><h2 style='color:#4A5D4E;'>MeetFlow E-Mail Test</h2><p>Diese E-Mail bestätigt, dass Ihre E-Mail-Konfiguration korrekt funktioniert.</p></div>"
    if target_provider == "smtp":
        from services.email_smtp import send_via_smtp
        if inline_smtp:
            # If password is masked, fall back to stored password (admin kept
            # the existing one).
            pw_in = inline_smtp.get("password") or ""
            if not pw_in or str(pw_in).startswith("***"):
                stored = await db.email_config.find_one({"config_id": "global"}, {"_id": 0}) or {}
                inline_smtp["password"] = (stored.get("smtp") or {}).get("password") or ""
            return await send_via_smtp(
                inline_smtp, to_email, subject, html,
                from_email=inline_smtp.get("from_email") or inline_sender or user.get("email"),
                from_name=inline_smtp.get("from_name") or "MeetFlow",
            )
        cfg = await db.email_config.find_one({"config_id": "global"}, {"_id": 0}) or {}
        return await send_via_smtp(
            cfg.get("smtp") or {}, to_email, subject, html,
            from_email=(cfg.get("smtp") or {}).get("from_email") or cfg.get("sender_email"),
        )
    return await send_email_real(to_email, subject, html)


@router.post("/admin/email-config/smtp-health")
async def smtp_health(request: Request):
    """Quick SMTP connect + auth check — does NOT send an e-mail."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    smtp_cfg = body.get("smtp")
    if not isinstance(smtp_cfg, dict):
        cfg = await db.email_config.find_one({"config_id": "global"}, {"_id": 0}) or {}
        smtp_cfg = cfg.get("smtp") or {}
    # Preserve stored password if a masked one was submitted
    if str(smtp_cfg.get("password", "")).startswith("***") or not smtp_cfg.get("password"):
        cfg = await db.email_config.find_one({"config_id": "global"}, {"_id": 0}) or {}
        stored = (cfg.get("smtp") or {}).get("password", "")
        if stored:
            smtp_cfg = {**smtp_cfg, "password": stored}
    from services.email_smtp import smtp_health_check
    return await smtp_health_check(smtp_cfg)


@router.get("/admin/audit/system")
async def admin_system_audit(request: Request, category: str = "", action: str = "",
                              actor: str = "", since_hours: int = 0,
                              search: str = "", limit: int = 100, skip: int = 0):
    """System-level audit log: capability changes, force-logouts, health alerts.
    Iter 267: actor/search/since_hours/skip-pagination filters.
    Filters: category, action, actor (substring on actor_name/email), search
    (substring on action/details), since_hours (rolling window). Admin only."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    q: dict = {}
    if category:
        q["category"] = category
    if action:
        q["action"] = action
    if actor:
        # Case-insensitive substring on actor_name OR actor_email
        rx = {"$regex": re.escape(actor), "$options": "i"}
        q["$or"] = [{"actor_name": rx}, {"actor_email": rx}, {"actor_id": rx}]
    if since_hours and since_hours > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=int(since_hours))).isoformat()
        q["timestamp"] = {"$gte": cutoff}
    if search:
        # Iter 267 — substring on action ODER details (Mongo-Volltext-Fallback).
        # Wenn schon ein $or aus actor existiert, kombiniere via $and.
        s_rx = {"$regex": re.escape(search), "$options": "i"}
        search_clauses = [{"action": s_rx}, {"details.preset_id": s_rx},
                          {"details.label": s_rx}, {"details.rule_name": s_rx},
                          {"details.subject": s_rx}, {"details.target_email": s_rx}]
        if "$or" in q:
            q["$and"] = [{"$or": q.pop("$or")}, {"$or": search_clauses}]
        else:
            q["$or"] = search_clauses
    limit = max(1, min(500, int(limit or 100)))
    skip = max(0, int(skip or 0))
    cur = db.audit_logs.find(q, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit)
    entries = await cur.to_list(limit)
    return {"entries": entries, "total": await db.audit_logs.count_documents(q),
            "limit": limit, "skip": skip}


@router.get("/admin/audit/system.csv")
async def admin_system_audit_csv(request: Request, category: str = "", action: str = "",
                                 actor: str = "", since_hours: int = 0):
    """Iter 267 — CSV export of audit-log entries (max 5000 rows).
    Same filters as /admin/audit/system. Admin only."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    q: dict = {}
    if category:
        q["category"] = category
    if action:
        q["action"] = action
    if actor:
        rx = {"$regex": re.escape(actor), "$options": "i"}
        q["$or"] = [{"actor_name": rx}, {"actor_email": rx}, {"actor_id": rx}]
    if since_hours and since_hours > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=int(since_hours))).isoformat()
        q["timestamp"] = {"$gte": cutoff}
    rows = await db.audit_logs.find(q, {"_id": 0}).sort("timestamp", -1).to_list(5000)
    # Build CSV — RFC 4180 quoting via Python's csv module
    import csv
    import io
    import json as _json
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    w.writerow(["timestamp", "category", "action", "actor_email", "actor_name",
                "target_user_id", "ip", "details"])
    for r in rows:
        details = r.get("details") or {}
        try:
            details_str = _json.dumps(details, ensure_ascii=False, default=str)
        except Exception:
            details_str = str(details)
        w.writerow([
            r.get("timestamp", ""),
            r.get("category", ""),
            r.get("action", ""),
            r.get("actor_email", ""),
            r.get("actor_name", ""),
            r.get("target_user_id", ""),
            r.get("ip", ""),
            details_str,
        ])
    from fastapi.responses import Response
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=audit-log.csv"},
    )


@router.get("/admin/health")
async def admin_health_dashboard(request: Request):
    """Aggregated health snapshot for the admin Health-Dashboard."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    from services.health_metrics import dashboard_snapshot
    return await dashboard_snapshot()


@router.get("/admin/health/ws")
async def admin_health_ws(request: Request):
    """Real-time WebSocket-auth metrics (rolling 5-min window).
    Surfaces cookie-on-upgrade regressions like the Chat-Call incident."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    from services.ws_metrics import snapshot
    return snapshot()


@router.get("/admin/health/mongo")
async def admin_health_mongo(request: Request):
    """Iter 261 — MongoDB Replica-Set Status. Liefert PRIMARY/SECONDARY/ARBITER
    Count plus die Roles aller Mitglieder. Bei Standalone-Deployment: status
    'standalone'. Bei aktivem RS: status 'replica_set' mit member-Liste.
    """
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        info = await db.client.admin.command("replSetGetStatus")
        members = info.get("members", [])
        state_names = {1: "PRIMARY", 2: "SECONDARY", 7: "ARBITER", 8: "DOWN", 9: "ROLLBACK", 10: "REMOVED"}
        breakdown = {"PRIMARY": 0, "SECONDARY": 0, "ARBITER": 0, "OTHER": 0}
        member_list = []
        for m in members:
            state = state_names.get(m.get("state"), "OTHER")
            breakdown[state if state in breakdown else "OTHER"] += 1
            member_list.append({
                "name": m.get("name"),
                "state": state,
                "health": m.get("health"),
                "uptime_s": m.get("uptime"),
                "self": bool(m.get("self")),
            })
        return {
            "status": "replica_set",
            "set_name": info.get("set"),
            "primary_count": breakdown["PRIMARY"],
            "secondary_count": breakdown["SECONDARY"],
            "arbiter_count": breakdown["ARBITER"],
            "members": member_list,
            "read_preference_active": "SECONDARY_PREFERRED (via read_db)",
        }
    except Exception as e:
        msg = str(e)
        if "not running with --replSet" in msg or "NoReplicationEnabled" in msg:
            return {
                "status": "standalone",
                "note": "MongoDB läuft im Standalone-Modus. read_db fällt transparent auf PRIMARY zurück. Für echte Read-Skalierung Replica-Set aufsetzen (siehe /app/docs/MONGO_REPLICA_SET.md).",
            }
        return {"status": "error", "error": msg[:200]}



@router.get("/admin/health/alerts/config")
async def health_alerts_get_config(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    from services.health_alerts import get_alert_config
    return await get_alert_config()


@router.put("/admin/health/alerts/config")
async def health_alerts_put_config(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    from services.health_alerts import set_alert_config
    return await set_alert_config(body or {})


@router.post("/admin/health/alerts/run")
async def health_alerts_run(request: Request):
    """Force-evaluate all alert rules and send any that would fire (bypasses
    cooldowns). Useful to debug and to test from the UI."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    from services.health_alerts import check_and_alert
    return await check_and_alert(force=True)


@router.post("/admin/health/alerts/test")
async def health_alerts_test(request: Request):
    """Send a test alert to the configured recipients."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    from services.health_alerts import get_alert_config, _dispatch_alert  # noqa: WPS450
    cfg = await get_alert_config()
    lines = [
        "Dies ist eine Test-Nachricht aus dem MeetFlow Health-Alerting.",
        f"Ausgeloest von {user.get('email','admin')}.",
        "Wenn Du diese Nachricht erhaelst, funktionieren die Alert-Kanaele korrekt.",
    ]
    res = await _dispatch_alert("Health-Alert TEST", lines, cfg, severity="ok")
    return res


@router.get("/admin/health/alerts/history")
async def health_alerts_history(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    from services.health_alerts import list_recent_alerts
    return {"items": await list_recent_alerts(limit=20)}


@router.get("/admin/email-config/dns-check")
async def email_dns_check(request: Request, domain: str = "", provider: str = ""):
    """Check MX/SPF/DKIM/DMARC for the given e-mail domain. If no domain is
    passed, the sender_email domain from email_config is used."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    from services.dns_check import check_domain
    target = domain.strip()
    prov = provider.strip().lower() or None
    if not target or not prov:
        cfg = await db.email_config.find_one({"config_id": "global"}, {"_id": 0}) or {}
        if not target:
            target = cfg.get("sender_email", "") or ""
        if not prov:
            prov = (cfg.get("provider") or "resend").lower()
    if not target:
        raise HTTPException(status_code=400, detail="No domain to check")
    return await check_domain(target, provider=prov or "resend")



@router.get("/admin/reminder-config")
async def get_reminder_config(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403)
    config = await db.reminder_config.find_one({"config_id": "global"}, {"_id": 0})
    return config or {"config_id": "global", "default_minutes": 15, "enabled": True}

@router.put("/admin/reminder-config")
async def update_reminder_config(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403)
    body = await request.json()
    updates = {"config_id": "global"}
    if "default_minutes" in body:
        updates["default_minutes"] = body["default_minutes"]
    if "enabled" in body:
        updates["enabled"] = body["enabled"]
    await db.reminder_config.update_one(
        {"config_id": "global"}, {"$set": updates}, upsert=True
    )
    return await db.reminder_config.find_one({"config_id": "global"}, {"_id": 0}) or updates



@router.get("/admin/api-config")
async def get_api_config(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    config = await db.api_config.find_one({"config_id": "global"}, {"_id": 0})
    if not config:
        config = {
            "config_id": "global",
            "llm_key": os.environ.get("EMERGENT_LLM_KEY", ""),
            "llm_model": "gpt-5.2",
            "llm_enabled": bool(os.environ.get("EMERGENT_LLM_KEY", "")),
        }
    def mask(key):
        if not key:
            return ""
        if len(key) > 10:
            return key[:4] + "***" + key[-4:]
        return "***"
    return {
        **config,
        "llm_key": mask(config.get("llm_key", "")),
        "llm_key_set": bool(config.get("llm_key", "")),
    }

@router.put("/admin/api-config")
async def update_api_config(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    allowed = ["llm_key", "llm_model", "llm_enabled"]
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields")
    key_changed = False
    if updates.get("llm_key", "").startswith("***") or updates.get("llm_key", "") == "":
        updates.pop("llm_key", None)
    elif "llm_key" in updates:
        key_changed = True
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.api_config.update_one({"config_id": "global"}, {"$set": updates}, upsert=True)
    await db.api_config.update_one({"config_id": "global"}, {"$setOnInsert": {"config_id": "global"}}, upsert=True)
    # Invalidate cached Object-Storage init so a freshly pasted key takes effect
    # on the next upload without requiring a backend restart.
    if key_changed:
        try:
            from services.storage import reset_storage
            reset_storage()
        except Exception:
            pass
    return {"message": "API config updated"}


@router.get("/admin/storage/health")
async def storage_health(request: Request):
    """Live-check whether Object Storage is actually reachable with the current
    Emergent key (ENV var or admin-saved DB key). The Admin → Integrationen
    panel uses this instead of merely mirroring the LLM-key-set boolean."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    import asyncio
    from services.storage import init_storage
    key = await asyncio.to_thread(init_storage)
    if key:
        # Indicate whether the key comes from ENV (preferred, immutable on
        # Emergent-managed deploys) or from the admin-saved DB row — useful so
        # the admin knows where to update the key if something breaks.
        source = "env" if os.environ.get("EMERGENT_LLM_KEY", "") else "db"
        return {"available": True, "source": source}
    return {"available": False, "source": None}


@router.post("/admin/storage/test")
async def storage_test(request: Request):
    """Round-trip test of Object Storage:
       1) PUT a tiny canary file with a known UUID
       2) GET it back
       3) Assert byte-level identity
    Lets the admin verify uploads work *before* a user reports a broken logo."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    import asyncio
    from services.storage import put_object, get_object, APP_STORAGE_PREFIX
    canary = f"meetflow-storage-test {uuid.uuid4()}".encode()
    path = f"{APP_STORAGE_PREFIX}/__storage_test/{uuid.uuid4().hex}.txt"
    try:
        await asyncio.to_thread(put_object, path, canary, "text/plain")
    except HTTPException as he:
        return {"ok": False, "step": "upload", "error": he.detail}
    except Exception as e:
        return {"ok": False, "step": "upload", "error": str(e)}
    try:
        got, _ = await asyncio.to_thread(get_object, path)
    except HTTPException as he:
        return {"ok": False, "step": "download", "error": he.detail}
    except Exception as e:
        return {"ok": False, "step": "download", "error": str(e)}
    if got != canary:
        return {"ok": False, "step": "verify", "error": "Inhalt stimmt nicht überein"}
    return {"ok": True, "bytes": len(canary), "path": path}

@router.post("/admin/api-config/test-llm")
async def test_llm_config(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    api_key = await _get_llm_key()
    if not api_key:
        return {"status": "error", "message": "Kein LLM-Key konfiguriert"}
    config = await db.api_config.find_one({"config_id": "global"}, {"_id": 0})
    model = config.get("llm_model", "gpt-5.2") if config else "gpt-5.2"
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=api_key, session_id="test_llm", system_message="You are a test assistant.")
        chat.with_model("openai", model)
        response = await chat.send_message(UserMessage(text="Antworte kurz: Was ist MeetFlow?"))
        return {"status": "ok", "model": model, "response": response[:200]}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}

async def _get_llm_key():
    """Get LLM key from DB config or env."""
    config = await db.api_config.find_one({"config_id": "global"}, {"_id": 0})
    if config and config.get("llm_enabled") and config.get("llm_key"):
        return config["llm_key"]
    return os.environ.get("EMERGENT_LLM_KEY", "")




@router.post("/admin/policies")
async def create_policy(req: MeetingPolicyRequest, request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    policy = {
        "policy_id": f"pol_{uuid.uuid4().hex[:10]}", "name": req.name,
        "max_duration": req.max_duration, "max_participants": req.max_participants,
        "allow_recording": req.allow_recording, "allow_guest": req.allow_guest,
        "require_lobby": req.require_lobby, "default_meeting_mode": req.default_meeting_mode,
        "auto_transcribe": req.auto_transcribe, "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.meeting_policies.insert_one(policy)
    return await db.meeting_policies.find_one({"policy_id": policy["policy_id"]}, {"_id": 0})

@router.get("/admin/policies")
async def list_policies(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return await db.meeting_policies.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)

@router.put("/admin/policies/{policy_id}")
async def update_policy(policy_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    allowed = ["name", "max_duration", "max_participants", "allow_recording", "allow_guest", "require_lobby", "default_meeting_mode", "auto_transcribe", "is_active"]
    updates = {k: v for k, v in body.items() if k in allowed}
    if updates:
        await db.meeting_policies.update_one({"policy_id": policy_id}, {"$set": updates})
    return await db.meeting_policies.find_one({"policy_id": policy_id}, {"_id": 0})

@router.delete("/admin/policies/{policy_id}")
async def delete_policy(policy_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    await db.meeting_policies.delete_one({"policy_id": policy_id})
    return {"message": "Policy deleted"}


@router.post("/admin/maintenance/cleanup")
async def run_maintenance_cleanup(request: Request):
    """Manually trigger the TEST_* test-data purge (admin only)."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    from services.maintenance import cleanup_test_data
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    min_age = int(body.get("min_age_days", 7)) if body else 7
    result = await cleanup_test_data(min_age_days=min_age)
    return result


# ============ Klinik-Branding: Offizieller Virtual Background (iter 191) ============
# Admins laden ein Klinik-Hintergrundbild hoch, das allen Mitarbeitern in der
# Virtual-Background-Auswahl als "Offizieller Klinik-Hintergrund" erscheint.

_BRANDING_DIR = "/app/backend/uploads/branding"


async def _get_branding_doc():
    return await db.app_settings.find_one({"key": "official_background"}, {"_id": 0})


@router.get("/branding/official-background")
async def get_official_background(request: Request):
    """Jeder eingeloggte User kann das offizielle Hintergrundbild abrufen.
    Wird bei jedem Meeting-Start beim Laden der Virtual-BG-Auswahl geholt."""
    await get_current_user(request)
    doc = await _get_branding_doc()
    if not doc or not doc.get("enabled"):
        return {"enabled": False, "url": None, "name": None}
    return {
        "enabled": True,
        "url": doc.get("url"),
        "name": doc.get("name") or "Klinik-Hintergrund",
        "uploaded_at": doc.get("uploaded_at"),
    }


@router.post("/admin/branding/background")
async def upload_official_background(request: Request):
    """Upload eines offiziellen Klinik-Hintergrundbildes (PNG/JPG/WebP)."""
    from fastapi import UploadFile
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    form = await request.form()
    file: UploadFile = form.get("file")
    if not file:
        raise HTTPException(status_code=400, detail="file required")
    name = (form.get("name") or "Klinik-Hintergrund").strip()

    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("png", "jpg", "jpeg", "webp"):
        raise HTTPException(status_code=400, detail="Nur PNG/JPG/WebP erlaubt")

    os.makedirs(_BRANDING_DIR, exist_ok=True)
    file_id = f"bg_{uuid.uuid4().hex[:10]}.{ext}"
    path = os.path.join(_BRANDING_DIR, file_id)
    content = await file.read()
    # 10 MB max
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Bild darf max. 10 MB gross sein")
    with open(path, "wb") as fh:
        fh.write(content)

    url = f"/api/branding/files/{file_id}"
    doc = {
        "key": "official_background",
        "url": url, "name": name, "file_id": file_id,
        "enabled": True,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "uploaded_by": user["user_id"],
    }
    # Cleanup previous file
    prev = await _get_branding_doc()
    if prev and prev.get("file_id"):
        try:
            os.remove(os.path.join(_BRANDING_DIR, prev["file_id"]))
        except Exception:
            pass

    await db.app_settings.update_one(
        {"key": "official_background"}, {"$set": doc}, upsert=True,
    )
    return {"enabled": True, "url": url, "name": name}


@router.delete("/admin/branding/background")
async def remove_official_background(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    prev = await _get_branding_doc()
    if prev and prev.get("file_id"):
        try:
            os.remove(os.path.join(_BRANDING_DIR, prev["file_id"]))
        except Exception:
            pass
    await db.app_settings.delete_one({"key": "official_background"})
    return {"ok": True}


@router.put("/admin/branding/background")
async def toggle_official_background(request: Request):
    """Body: {enabled: bool, name?: str}. Kein Upload noetig um nur an/aus
    zu schalten oder den Anzeigenamen zu aendern."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    updates = {}
    if "enabled" in body:
        updates["enabled"] = bool(body["enabled"])
    if "name" in body and body["name"]:
        updates["name"] = str(body["name"]).strip()
    if not updates:
        raise HTTPException(status_code=400, detail="Keine Änderungen")
    await db.app_settings.update_one(
        {"key": "official_background"}, {"$set": updates}, upsert=False,
    )
    doc = await _get_branding_doc()
    return doc or {"enabled": False}


@router.get("/branding/files/{file_id}")
async def serve_branding_file(file_id: str):
    """Serve das Hintergrundbild. Oeffentlich zugaenglich, damit das
    <canvas>-Compositing mit `crossOrigin='anonymous'` funktioniert — ein
    Branding-Asset ist ohnehin kein sensibles Dokument."""
    from fastapi.responses import FileResponse
    import mimetypes
    # Nur einfache Dateinamen zulassen (keine Path-Traversal)
    if "/" in file_id or ".." in file_id:
        raise HTTPException(status_code=400, detail="Invalid id")
    path = os.path.join(_BRANDING_DIR, file_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Not found")
    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)
