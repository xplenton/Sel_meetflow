"""
Audit logging for capability / permissions changes.
All cap changes flow through log_caps_change() for DSGVO-compliant auditability.
"""
from datetime import datetime, timezone
import uuid
from database import db


async def log_caps_change(
    actor: dict,
    target_user_id: str,
    action: str,
    details: dict,
    *,
    category: str = "capabilities",
    request=None,
):
    """
    action: one of:
      "set_caps"           — grants/denies explicitly set
      "apply_preset"       — preset applied to user/group
      "auto_assign"        — auto-rule engine assigned caps
      "create_preset"      — custom preset created
      "update_preset"      — custom preset edited
      "delete_preset"      — custom preset deleted
      "create_rule"        — auto-rule created
      "update_rule"        — auto-rule edited
      "delete_rule"        — auto-rule deleted
      "bulk_apply"         — bulk preset applied to multiple users
      "force_logout"       — admin invalidated a user's sessions
      "force_logout_all"   — admin invalidated everyone's sessions
      "health_alert"       — automated health alert fired
    category: "capabilities" (default), "session", "alert", etc. — used for UI filters.
    details: free-form dict.
    request: optional FastAPI Request — if provided, IP + User-Agent are captured.
    """
    ip = ua = None
    if request is not None:
        try:
            ip = request.client.host if request.client else None
            xff = request.headers.get("x-forwarded-for")
            if xff:
                ip = xff.split(",")[0].strip()
            ua = (request.headers.get("user-agent") or "")[:240]
        except Exception:
            pass
    entry = {
        "audit_id": f"audit_{uuid.uuid4().hex[:12]}",
        "actor_id": actor.get("user_id"),
        "actor_name": actor.get("name", ""),
        "actor_email": actor.get("email", ""),
        "target_user_id": target_user_id,
        "action": action,
        "category": category,
        "details": details,
        "ip": ip, "user_agent": ua,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.audit_logs.insert_one(entry)
    except Exception:
        # Never block caller on audit failure
        pass
    return entry
