"""
Health-metrics helpers for the admin Health-Dashboard.

Three collections (created lazily, indexed with TTL to self-purge):
    email_send_log     {ts, to, provider, status, error, subject, fallback}
    auth_refresh_log   {ts, user_id, ip, ua}
    maintenance_runs   {ts, task, modified:int, took_ms:int}

All writes are fire-and-forget — a broken log must never break the caller.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from database import db, read_db

logger = logging.getLogger(__name__)

# TTL in seconds — logs auto-purge after 30 days
_LOG_TTL_SEC = 30 * 24 * 3600
_indexes_ensured = False


async def _ensure_indexes():
    """Create TTL + compound indexes on first access. Idempotent."""
    global _indexes_ensured
    if _indexes_ensured:
        return
    try:
        await db.email_send_log.create_index("ts", expireAfterSeconds=_LOG_TTL_SEC)
        await db.email_send_log.create_index([("provider", 1), ("status", 1)])
        await db.auth_refresh_log.create_index("ts", expireAfterSeconds=_LOG_TTL_SEC)
        await db.auth_refresh_log.create_index([("user_id", 1), ("ts", -1)])
        await db.maintenance_runs.create_index("ts", expireAfterSeconds=_LOG_TTL_SEC)
        _indexes_ensured = True
    except Exception as e:  # non-fatal
        logger.debug(f"[health_metrics] index ensure failed: {e}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============ Write side ============

async def log_email_send(to_email: str, subject: str, result: Dict[str, Any]) -> None:
    """Fire-and-forget email send logger. `result` follows send_email_real()."""
    try:
        await _ensure_indexes()
        await db.email_send_log.insert_one({
            "ts": datetime.now(timezone.utc),
            "to": to_email,
            "provider": (result or {}).get("provider", "unknown"),
            "status": (result or {}).get("status", "unknown"),
            "error": (result or {}).get("error"),
            "subject": (subject or "")[:120],
            "fallback": bool((result or {}).get("fallback")),
        })
    except Exception as e:
        logger.debug(f"[health_metrics] log_email_send failed: {e}")


async def log_auth_refresh(user_id: str, request=None) -> None:
    try:
        await _ensure_indexes()
        ip = ua = None
        if request is not None:
            ip = request.client.host if request.client else None
            ua = (request.headers.get("user-agent") or "")[:200]
        await db.auth_refresh_log.insert_one({
            "ts": datetime.now(timezone.utc),
            "user_id": user_id, "ip": ip, "ua": ua,
        })
    except Exception as e:
        logger.debug(f"[health_metrics] log_auth_refresh failed: {e}")


async def log_maintenance_run(task: str, modified: int, took_ms: int) -> None:
    try:
        await _ensure_indexes()
        await db.maintenance_runs.insert_one({
            "ts": datetime.now(timezone.utc),
            "task": task,
            "modified": int(modified or 0),
            "took_ms": int(took_ms or 0),
        })
    except Exception as e:
        logger.debug(f"[health_metrics] log_maintenance_run failed: {e}")


# ============ Read side (admin dashboard) ============

async def email_stats(days: int = 7) -> Dict[str, Any]:
    """Aggregates email_send_log for the last N days."""
    await _ensure_indexes()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    cursor = read_db.email_send_log.aggregate([
        {"$match": {"ts": {"$gte": since}}},
        {"$group": {
            "_id": {"provider": "$provider", "status": "$status"},
            "count": {"$sum": 1},
        }},
    ])
    rows = await cursor.to_list(500)
    total = sum(r["count"] for r in rows)
    sent = sum(r["count"] for r in rows if r["_id"].get("status") == "sent")
    failed = sum(r["count"] for r in rows if r["_id"].get("status") == "failed")
    simulated = sum(r["count"] for r in rows if r["_id"].get("status") in ("logged", "simulated"))
    by_provider = {}
    for r in rows:
        p = r["_id"].get("provider") or "unknown"
        by_provider.setdefault(p, {"sent": 0, "failed": 0, "simulated": 0})
        key = "simulated" if r["_id"].get("status") in ("logged", "simulated") else r["_id"].get("status") or "failed"
        by_provider[p].setdefault(key, 0)
        by_provider[p][key] += r["count"]
    success_rate = round(100 * sent / total, 1) if total else None

    # Daily bucket for sparkline (last 7 days)
    daily_cursor = read_db.email_send_log.aggregate([
        {"$match": {"ts": {"$gte": since}}},
        {"$project": {
            "day": {"$dateToString": {"format": "%Y-%m-%d", "date": "$ts"}},
            "status": 1,
        }},
        {"$group": {"_id": {"day": "$day", "status": "$status"}, "count": {"$sum": 1}}},
        {"$sort": {"_id.day": 1}},
    ])
    daily_rows = await daily_cursor.to_list(500)
    by_day: Dict[str, Dict[str, int]] = {}
    for r in daily_rows:
        day = r["_id"]["day"]
        st = r["_id"]["status"]
        by_day.setdefault(day, {"sent": 0, "failed": 0, "simulated": 0})
        key = "simulated" if st in ("logged", "simulated") else st or "failed"
        by_day[day].setdefault(key, 0)
        by_day[day][key] += r["count"]

    # Last failure sample (most recent failed send)
    last_failure = await read_db.email_send_log.find_one(
        {"status": "failed", "ts": {"$gte": since}},
        {"_id": 0, "ts": 1, "to": 1, "provider": 1, "error": 1, "subject": 1},
        sort=[("ts", -1)],
    )
    if last_failure and isinstance(last_failure.get("ts"), datetime):
        last_failure["ts"] = last_failure["ts"].isoformat()

    return {
        "days": days,
        "total": total, "sent": sent, "failed": failed, "simulated": simulated,
        "success_rate": success_rate,
        "by_provider": by_provider,
        "by_day": [{"day": d, **v} for d, v in sorted(by_day.items())],
        "last_failure": last_failure,
    }


async def auth_refresh_anomalies(hours: int = 24, threshold: int = 30) -> Dict[str, Any]:
    """Return users with more than `threshold` refresh attempts in the last
    `hours` — a strong hint at stuck tokens or looped clients."""
    await _ensure_indexes()
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    cursor = db.auth_refresh_log.aggregate([
        {"$match": {"ts": {"$gte": since}}},
        {"$group": {"_id": "$user_id", "count": {"$sum": 1}, "last": {"$max": "$ts"}}},
        {"$sort": {"count": -1}},
        {"$limit": 20},
    ])
    top = await cursor.to_list(20)
    anomalies = []
    total_refreshes = 0
    for r in top:
        total_refreshes += r["count"]
        if r["count"] >= threshold:
            uid = r["_id"]
            user = await db.users.find_one({"user_id": uid}, {"_id": 0, "email": 1, "name": 1})
            anomalies.append({
                "user_id": uid,
                "email": (user or {}).get("email"),
                "name": (user or {}).get("name"),
                "count": r["count"],
                "last": r["last"].isoformat() if isinstance(r["last"], datetime) else r["last"],
            })
    total = await db.auth_refresh_log.count_documents({"ts": {"$gte": since}})
    return {
        "hours": hours,
        "threshold": threshold,
        "total_refreshes": total,
        "top": [{
            "user_id": r["_id"],
            "count": r["count"],
            "last": r["last"].isoformat() if isinstance(r["last"], datetime) else r["last"],
        } for r in top[:10]],
        "anomalies": anomalies,
    }


async def maintenance_status() -> Dict[str, Any]:
    """Latest run timestamp + summary for each maintenance task."""
    await _ensure_indexes()
    cursor = db.maintenance_runs.aggregate([
        {"$sort": {"ts": -1}},
        {"$group": {
            "_id": "$task",
            "last_ts": {"$first": "$ts"},
            "last_modified": {"$first": "$modified"},
            "last_took_ms": {"$first": "$took_ms"},
            "runs_24h": {"$sum": {"$cond": [
                {"$gte": ["$ts", datetime.now(timezone.utc) - timedelta(hours=24)]}, 1, 0,
            ]}},
        }},
    ])
    rows = await cursor.to_list(20)
    out = []
    for r in rows:
        out.append({
            "task": r["_id"],
            "last_ts": r["last_ts"].isoformat() if isinstance(r["last_ts"], datetime) else r["last_ts"],
            "last_modified": r.get("last_modified", 0),
            "last_took_ms": r.get("last_took_ms", 0),
            "runs_24h": r.get("runs_24h", 0),
        })
    return {"tasks": out}


async def dashboard_snapshot() -> Dict[str, Any]:
    """Single aggregated payload for the Health-Dashboard UI."""
    emails = await email_stats(days=7)
    anomalies = await auth_refresh_anomalies(hours=24, threshold=30)
    mnt = await maintenance_status()
    from services.dns_check import check_domain
    dns = None
    try:
        cfg = await db.email_config.find_one({"config_id": "global"}, {"_id": 0}) or {}
        sender = cfg.get("sender_email") or ""
        if sender and "@" in sender:
            prov = (cfg.get("provider") or "resend").lower()
            dns = await check_domain(sender, provider=prov)
    except Exception as e:
        dns = {"error": str(e)}
    # Global snapshot
    total_users = await db.users.count_documents({})
    active_sessions_24h = await db.auth_refresh_log.distinct("user_id", {
        "ts": {"$gte": datetime.now(timezone.utc) - timedelta(hours=24)},
    })
    return {
        "generated_at": _now_iso(),
        "emails": emails,
        "auth_refresh": anomalies,
        "maintenance": mnt,
        "dns": dns,
        "users": {
            "total": total_users,
            "active_sessions_24h": len(active_sessions_24h),
        },
    }
