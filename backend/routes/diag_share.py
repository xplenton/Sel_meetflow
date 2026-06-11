"""Shareable device-diagnostic tokens — Admin creates a token, sends the QR
link to any user (no login needed). The user hits `/diag/shared/<token>`, runs
the diagnostics automatically, and submits the result back to the admin.

Routes:
  POST   /api/diag/shared         — admin: create new token + QR PNG
  GET    /api/diag/shared         — admin: list active tokens + submissions
  GET    /api/diag/shared/{token} — public: resolve token (no auth)
  POST   /api/diag/shared/{token}/submit — public: submit report (no auth)
"""
from __future__ import annotations

import base64
import io
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

from database import db, logger
from dependencies import get_current_user

router = APIRouter()

# ----- constants ------

SHARE_TOKEN_BYTES = 12          # → 16-char URL-safe token
DEFAULT_EXPIRY_DAYS = 7
MAX_SUBMISSIONS_PER_TOKEN = 10  # avoid abuse


# ----- helpers -------------------------------------------------------------

def _build_qr_png(url: str) -> str:
    """Return a data-URL PNG of the QR code encoding `url`."""
    import qrcode
    img = qrcode.make(url, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


async def _assert_admin(request: Request) -> dict:
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    return user


# ----- admin endpoints -----------------------------------------------------

@router.post("/diag/shared")
async def create_diag_token(request: Request):
    """Create a new shareable diag token. Body: {note?: str, days?: int}."""
    user = await _assert_admin(request)
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    note = (body.get("note") or "").strip()[:200]
    days = int(body.get("days") or DEFAULT_EXPIRY_DAYS)
    days = max(1, min(days, 30))
    token = secrets.token_urlsafe(SHARE_TOKEN_BYTES)
    now = datetime.now(timezone.utc)
    doc = {
        "token": token,
        "created_by": user["user_id"],
        "created_by_name": user.get("name", ""),
        "note": note,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=days)).isoformat(),
        "submissions": [],
    }
    await db.diag_share_tokens.insert_one(doc)
    doc.pop("_id", None)
    frontend_origin = request.headers.get("origin") or str(request.base_url).rstrip("/")
    # `origin` header is usually the frontend; base_url is the backend. Prefer origin.
    share_url = f"{frontend_origin}/diag/shared/{token}"
    return {**doc, "share_url": share_url, "qr_png": _build_qr_png(share_url)}


@router.get("/diag/shared")
async def list_diag_tokens(request: Request):
    """Admin list of all tokens + their submissions."""
    await _assert_admin(request)
    tokens = await db.diag_share_tokens.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return tokens


@router.get("/admin/quick-scans")
async def list_all_quick_scans(request: Request):
    """Admin-only: organisationsweite Liste aller Quick-Scan-Sessions mit
    Submissions — für den Moderations-Tab in der Verwaltung.

    Liefert nur Tokens mit `kind == "quick_scan"`, enriched mit Meeting-Titel.
    """
    await _assert_admin(request)
    tokens = await db.diag_share_tokens.find(
        {"kind": "quick_scan"}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)

    # Enrich mit meeting_title (Bulk-Lookup)
    meeting_ids = list({t.get("meeting_id") for t in tokens if t.get("meeting_id")})
    title_map = {}
    if meeting_ids:
        async for m in db.meetings.find(
            {"meeting_id": {"$in": meeting_ids}},
            {"_id": 0, "meeting_id": 1, "title": 1},
        ):
            title_map[m["meeting_id"]] = m.get("title") or ""
    for t in tokens:
        t["meeting_title"] = title_map.get(t.get("meeting_id"), "")

    # Aggregate-Kennzahlen für die Header-Row
    total = len(tokens)
    submitted = sum(1 for t in tokens if (t.get("submissions") or []))
    pending = total - submitted
    fails = 0
    for t in tokens:
        for s in (t.get("submissions") or []):
            res = s.get("results") or {}
            if any(isinstance(v, dict) and v.get("state") == "fail" for v in res.values()):
                fails += 1
                break

    return {
        "tokens": tokens,
        "stats": {
            "total": total,
            "submitted": submitted,
            "pending": pending,
            "with_failures": fails,
        },
    }


@router.delete("/diag/shared/{token}")
async def revoke_diag_token(token: str, request: Request):
    await _assert_admin(request)
    result = await db.diag_share_tokens.delete_one({"token": token})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Token not found")
    return {"revoked": True}


# ----- public endpoints (no auth) -----------------------------------------

@router.get("/diag/shared/{token}")
async def resolve_diag_token(token: str):
    """Validate token + return creator name/note (no auth required)."""
    doc = await db.diag_share_tokens.find_one({"token": token}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Link ungültig oder abgelaufen")
    try:
        exp = datetime.fromisoformat(doc["expires_at"].replace("Z", "+00:00"))
    except Exception:
        exp = datetime.now(timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Link abgelaufen")
    return {
        "token": token,
        "created_by_name": doc.get("created_by_name", ""),
        "note": doc.get("note", ""),
        "expires_at": doc.get("expires_at"),
    }


@router.post("/diag/shared/{token}/submit")
async def submit_diag_report(token: str, request: Request):
    """Public: user submits their device diagnostic report."""
    doc = await db.diag_share_tokens.find_one({"token": token}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Link ungültig")
    try:
        exp = datetime.fromisoformat(doc["expires_at"].replace("Z", "+00:00"))
    except Exception:
        exp = datetime.now(timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Link abgelaufen")
    max_subs = int(doc.get("max_submissions") or MAX_SUBMISSIONS_PER_TOKEN)
    if len(doc.get("submissions") or []) >= max_subs:
        raise HTTPException(status_code=429, detail="Zu viele Einreichungen für diesen Link")

    body = await request.json()
    reporter_name = (body.get("reporter_name") or "Anonym").strip()[:80]
    ua = (body.get("user_agent") or "")[:500]
    results = body.get("results") or {}
    logs = (body.get("logs") or [])[:80]
    submission = {
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "reporter_name": reporter_name,
        "user_agent": ua,
        "ip_last": (request.client.host if request.client else "") + "",
        "results": results,
        "logs": logs,
    }
    await db.diag_share_tokens.update_one({"token": token}, {"$push": {"submissions": submission}})
    logger.info(f"[diag-share] submission for token={token[:6]}… from {reporter_name}")

    # Quick-Scan token → broadcast result to the host's meeting room over WS
    if doc.get("kind") == "quick_scan":
        try:
            from services.meetings_quickscan import notify_host_of_result
            await notify_host_of_result(doc, submission)
        except Exception as e:
            logger.warning(f"[diag-share] quick-scan hook failed: {e}")

    # Notify the admin who created the token
    try:
        await db.notifications.insert_one({
            "notification_id": f"notif_{secrets.token_hex(5)}",
            "user_id": doc["created_by"],
            "type": "diag_report",
            "title": f"Diagnose empfangen: {reporter_name}",
            "body": _build_notif_body(results),
            "read": False,
            "diag_token": token,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.warning(f"[diag-share] admin notification failed: {e}")
    return {"ok": True, "message": "Vielen Dank — die Diagnose wurde übertragen."}


def _build_notif_body(results: dict) -> str:
    """Short readable summary for the admin notification."""
    if not isinstance(results, dict):
        return "Diagnose-Bericht eingetroffen"
    rows = []
    for key in ("secureCtx", "cam", "mic", "screen", "webrtc", "push", "vapid", "subscription"):
        v = results.get(key)
        if isinstance(v, dict) and v.get("state"):
            rows.append(f"{key}:{v['state']}")
    return " · ".join(rows) or "Diagnose-Bericht eingetroffen"
