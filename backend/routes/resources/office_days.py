"""
Resources package — sub-module office_days.
Split out from bookings.py in iter 260 to keep modules under ~750 lines.

Covers:
- Recurring office-day configuration (weekdays + preferred desk)
- Sync + async generation of desk bookings for the next N weeks
- Skip / cancel an individual office day with reason
- Team-Office-Week widget (Mo–Fr, presence + absence visualisation)
- Slack/Team-Chat announcement helpers
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta, date as _date, time as _time
import uuid

from database import db
from dependencies import get_current_user
from services.permissions import has_cap

from ._common import _check_conflicts, _audit_booking

router = APIRouter(tags=["resources-office-days"])

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

SKIP_REASONS = {
    "krank": {"emoji": "🤒", "label_de": "Krank", "label_en": "Sick"},
    "homeoffice": {"emoji": "🏠", "label_de": "Homeoffice", "label_en": "Remote"},
    "urlaub": {"emoji": "🌴", "label_de": "Urlaub", "label_en": "Vacation"},
    "sonstiges": {"emoji": "❔", "label_de": "Sonstiges", "label_en": "Other"},
}


# ---------------------------------------------------------------------------
# Config: GET / PUT user's recurring office-days settings
# ---------------------------------------------------------------------------

@router.get("/users/me/office-days")
async def get_office_days(user=Depends(get_current_user)):
    """Liefert die gespeicherten Standard-Bürotage des Users."""
    cfg = user.get("recurring_office_days") or {}
    has_slack = bool(cfg.get("slack_webhook_url"))
    return {
        "weekdays": cfg.get("weekdays", []),
        "preferred_desk_id": cfg.get("preferred_desk_id"),
        "start_time": cfg.get("start_time", "08:00"),
        "end_time": cfg.get("end_time", "17:00"),
        "title": cfg.get("title", "Bürotag"),
        "announce_to_conversation_id": cfg.get("announce_to_conversation_id"),
        # Iter 244 — Slack: bool nach aussen, nicht die URL selbst (Privacy)
        "slack_webhook_configured": has_slack,
    }


@router.put("/users/me/office-days")
async def set_office_days(payload: dict, user=Depends(get_current_user)):
    """Speichert Standard-Bürotage. Validiert weekdays und Zeit-Format."""
    weekdays = payload.get("weekdays") or []
    if not isinstance(weekdays, list):
        raise HTTPException(400, "weekdays muss eine Liste sein")
    invalid = [w for w in weekdays if w not in WEEKDAYS]
    if invalid:
        raise HTTPException(400, f"Ungültige Wochentage: {invalid}")

    desk_id = payload.get("preferred_desk_id")
    if desk_id:
        desk = await db.resources.find_one({"resource_id": desk_id, "type": "desk"}, {"_id": 0})
        if not desk:
            raise HTTPException(404, "Bevorzugter Arbeitsplatz nicht gefunden")

    def _parse_hhmm(s: str, default: str) -> str:
        if not s:
            return default
        if len(s) != 5 or s[2] != ":":
            raise HTTPException(400, f"Zeit-Format HH:MM erwartet (war: {s})")
        try:
            h, m = int(s[:2]), int(s[3:])
            if not (0 <= h < 24 and 0 <= m < 60):
                raise ValueError
        except ValueError:
            raise HTTPException(400, f"Ungültige Zeit: {s}")
        return s

    cfg = {
        "weekdays": weekdays,
        "preferred_desk_id": desk_id or None,
        "start_time": _parse_hhmm(payload.get("start_time"), "08:00"),
        "end_time": _parse_hhmm(payload.get("end_time"), "17:00"),
        "title": (payload.get("title") or "Bürotag")[:120],
        # Iter 242 — optional: Team-Chat-Konversation fuer Auto-Announce
        "announce_to_conversation_id": payload.get("announce_to_conversation_id") or None,
        # Iter 244 — optional: Slack-Webhook-URL fuer externe Notification
        "slack_webhook_url": (payload.get("slack_webhook_url") or "").strip()[:500] or None,
    }
    if cfg["end_time"] <= cfg["start_time"]:
        raise HTTPException(400, "Endzeit muss nach Startzeit liegen")

    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"recurring_office_days": cfg}},
    )
    from services import user_cache as ucache
    await ucache.invalidate(user["user_id"])
    return {"message": "Standard-Bürotage gespeichert", **cfg}


# ---------------------------------------------------------------------------
# Generate desk bookings from config — sync + async
# ---------------------------------------------------------------------------

@router.post("/users/me/office-days/generate")
async def generate_office_day_bookings(payload: dict = None, user=Depends(get_current_user)):
    """Erzeugt Desk-Buchungen fuer die naechsten N Wochen (default 4).

    Skipt:
    - Tage, an denen User bereits eine eigene Desk-Buchung hat
    - Slots, an denen der bevorzugte Desk belegt ist (kein automatisches Ausweichen)
    """
    if not await has_cap(user, "resources.book", db):
        raise HTTPException(403, "Keine Berechtigung zum Buchen von Ressourcen")
    payload = payload or {}
    weeks = int(payload.get("weeks") or 4)
    weeks = max(1, min(weeks, 8))

    cfg = user.get("recurring_office_days") or {}
    weekdays: list = cfg.get("weekdays") or []
    desk_id = cfg.get("preferred_desk_id")
    if not weekdays:
        raise HTTPException(400, "Keine Standard-Bürotage konfiguriert")
    if not desk_id:
        raise HTTPException(400, "Bitte zuerst einen bevorzugten Arbeitsplatz wählen")

    desk = await db.resources.find_one({"resource_id": desk_id, "type": "desk"}, {"_id": 0})
    if not desk or desk.get("status") != "active":
        raise HTTPException(404, "Bevorzugter Arbeitsplatz nicht verfügbar")

    start_hhmm = cfg.get("start_time", "08:00")
    end_hhmm = cfg.get("end_time", "17:00")
    title = cfg.get("title", "Bürotag")

    today = datetime.now(timezone.utc).date()

    # Build target dates
    weekday_idx = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    wanted_idx = {weekday_idx[w] for w in weekdays}

    created: list = []
    skipped_owned: list = []
    skipped_conflict: list = []

    for offset in range(weeks * 7):
        day = today + timedelta(days=offset)
        if day.weekday() not in wanted_idx:
            continue
        sh, sm = map(int, start_hhmm.split(":"))
        eh, em = map(int, end_hhmm.split(":"))
        start_dt = datetime.combine(day, _time(sh, sm, tzinfo=timezone.utc))
        end_dt = datetime.combine(day, _time(eh, em, tzinfo=timezone.utc))

        # 1. Skip if user already has any desk booking on this day
        own_today = await db.resource_bookings.find_one({
            "user_id": user["user_id"],
            "status": {"$in": ["confirmed", "pending_approval"]},
            "start_at": {"$gte": start_dt.replace(hour=0, minute=0)},
            "end_at":   {"$lt": start_dt.replace(hour=0, minute=0) + timedelta(days=1)},
        }, {"_id": 0, "booking_id": 1})
        if own_today:
            skipped_owned.append(day.isoformat())
            continue

        # 2. Conflict on the preferred desk?
        conflicts = await _check_conflicts(desk_id, start_dt, end_dt)
        if conflicts:
            skipped_conflict.append(day.isoformat())
            continue

        bk = {
            "booking_id": f"bk_{uuid.uuid4().hex[:12]}",
            "resource_id": desk_id,
            "user_id": user["user_id"],
            "title": title,
            "description": "Automatisch erzeugt aus Standard-Bürotagen",
            "start_at": start_dt,
            "end_at": end_dt,
            "status": "confirmed",
            "auto_generated": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        await db.resource_bookings.insert_one(bk)
        created.append({"booking_id": bk["booking_id"], "date": day.isoformat()})
        await _audit_booking(user, bk["booking_id"], "office_day_autogen", {
            "desk_id": desk_id, "date": day.isoformat(),
        })

    return {
        "created": created,
        "created_count": len(created),
        "skipped_already_booked": skipped_owned,
        "skipped_desk_conflict": skipped_conflict,
        "weeks": weeks,
        "announced": await _announce_office_days(user, cfg, created),
        "slack_notified": await _slack_announce_office_days(user, cfg, created),
    }


@router.post("/users/me/office-days/generate/async")
async def generate_office_day_bookings_async(payload: dict = None,
                                              user=Depends(get_current_user)):
    """Iter 253 — Background variant: queue a generation job for up to 26 weeks
    ahead. Returns {job_id} immediately. Poll GET /api/jobs/{job_id} for status.
    """
    if not await has_cap(user, "resources.book", db):
        raise HTTPException(403, "Keine Berechtigung zum Buchen von Ressourcen")
    payload = payload or {}
    weeks = max(1, min(int(payload.get("weeks") or 8), 26))
    from services.background_queue import enqueue
    job = await enqueue("generate_recurring_bookings", user["user_id"], weeks)
    job_id = getattr(job, "job_id", None) or "inline"
    return {"job_id": job_id, "weeks": weeks, "status": "queued"}


# ---------------------------------------------------------------------------
# Slack / Team-Chat announcement helpers
# ---------------------------------------------------------------------------

@router.post("/users/me/office-days/slack/test")
async def slack_test_message(user=Depends(get_current_user)):
    """Iter 245 — Schickt eine Test-Nachricht an den konfigurierten Slack-Webhook.
    Hilft dem User zu verifizieren, dass die URL funktioniert, ohne dass er
    erst Buchungen generieren muss.
    """
    cfg = user.get("recurring_office_days") or {}
    url = (cfg.get("slack_webhook_url") or "").strip()
    if not url:
        raise HTTPException(400, "Kein Slack-Webhook konfiguriert")
    if not url.startswith("https://hooks.slack.com/"):
        return {"success": False, "error": "URL beginnt nicht mit https://hooks.slack.com/"}
    try:
        import httpx
        text = (
            f":wave: *MeetFlow Test* — Hallo {user.get('name') or user.get('email', '?')}! "
            f"Dein Slack-Webhook ist korrekt konfiguriert."
        )
        async with httpx.AsyncClient(timeout=5.0) as cli:
            r = await cli.post(url, json={"text": text})
            if 200 <= r.status_code < 300:
                return {"success": True}
            return {"success": False, "error": f"HTTP {r.status_code}: {r.text[:120]}"}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


async def _slack_announce_office_days(user, cfg, created) -> bool:
    """Iter 244 — Postet eine Message an einen externen Slack-Webhook (Incoming
    Webhook URL). Failure-tolerant — returnt False bei Fehler.

    Slack-Webhook-Format: https://hooks.slack.com/services/XXX/YYY/ZZZ
    User pasted die URL aus Slack im Profil ein. Wir senden nur, wenn
    `slack_webhook_url` gesetzt + Bookings neu erstellt.
    """
    url = (cfg.get("slack_webhook_url") or "").strip()
    if not url or not url.startswith("https://hooks.slack.com/"):
        return False
    if not created:
        return False
    try:
        import httpx
        weekday_en = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        days_used = sorted({weekday_en[_date.fromisoformat(c["date"]).weekday()]
                            for c in created})
        date_range = f"{created[0]['date']} – {created[-1]['date']}"
        text = (
            f":office: *{user.get('name') or user.get('email', '?')}* will be in "
            f"the office on: {' · '.join(days_used)} "
            f"({len(created)} days, {date_range})."
        )
        async with httpx.AsyncClient(timeout=5.0) as cli:
            r = await cli.post(url, json={"text": text})
            return 200 <= r.status_code < 300
    except Exception:
        return False


async def _announce_office_days(user, cfg, created) -> bool:
    """Iter 242 — postet eine System-Message im konfigurierten Team-Chat, wenn
    `announce_to_conversation_id` gesetzt ist und mindestens eine Buchung neu
    erstellt wurde. Failure-tolerant: wirft niemals — Logging only.
    """
    conv_id = cfg.get("announce_to_conversation_id")
    if not conv_id or not created:
        return False
    try:
        conv = await db.conversations.find_one(
            {"conversation_id": conv_id, "members.user_id": user["user_id"]},
            {"_id": 0, "conversation_id": 1},
        )
        if not conv:
            return False  # User ist nicht (mehr) Mitglied
        # Aggregiere die Wochentage aus created-Liste
        weekday_de = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        days_used = sorted({weekday_de[_date.fromisoformat(c["date"]).weekday()]
                            for c in created})
        date_range = f"{created[0]['date']} – {created[-1]['date']}"
        text = (
            f"\U0001F3E2 {user.get('name') or user.get('email', '?')} kommt "
            f"an folgenden Tagen ins Büro: {' · '.join(days_used)} "
            f"({len(created)} Tage, {date_range})."
        )
        msg = {
            "message_id": f"msg_{uuid.uuid4().hex[:12]}",
            "conversation_id": conv_id,
            "sender_id": user["user_id"],
            "sender_name": user.get("name") or user.get("email", "System"),
            "body": text,
            "type": "system",
            "system_event": "office_days_announce",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.messages.insert_one(msg)
        await db.conversations.update_one(
            {"conversation_id": conv_id},
            {"$set": {
                "last_message": {"body": text, "sender_id": user["user_id"],
                                  "created_at": msg["created_at"]},
                "updated_at": msg["created_at"],
            }},
        )
        # Broadcast via WebSocket (best-effort)
        try:
            from realtime import chat_ws  # type: ignore
            await chat_ws.broadcast_to_conversation(conv_id, {
                "type": "new-message", "message": {**msg, "_id": None},
            })
        except Exception:
            pass
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Skip / list reasons / upcoming / team office-week
# ---------------------------------------------------------------------------

@router.post("/users/me/office-days/skip")
async def skip_office_day(payload: dict, user=Depends(get_current_user)):
    """Iter 243 — Überspringt einen einzelnen Bürotag mit optionalem Grund.

    Verhalten:
    - Mit reason in {krank, homeoffice, urlaub, sonstiges}: setzt status='cancelled'
      und speichert skip_reason + cancelled_at. Booking bleibt fuer Team-Transparenz
      sichtbar (OfficeWeek-Widget zeigt z.B. "Anna · 🏠 Homeoffice").
    - Ohne reason (None/empty): Hard-Delete wie bisher.
    """
    booking_id = payload.get("booking_id")
    reason = (payload.get("reason") or "").strip().lower() or None
    if not booking_id:
        raise HTTPException(400, "booking_id fehlt")
    if reason and reason not in SKIP_REASONS:
        raise HTTPException(400, f"Ungültiger Grund. Erlaubt: {list(SKIP_REASONS.keys())}")

    bk = await db.resource_bookings.find_one(
        {"booking_id": booking_id, "user_id": user["user_id"]},
        {"_id": 0},
    )
    if not bk:
        raise HTTPException(404, "Buchung nicht gefunden")

    if reason is None:
        await db.resource_bookings.delete_one({"booking_id": booking_id})
        await _audit_booking(user, booking_id, "office_day_skip_deleted", {})
        return {"booking_id": booking_id, "action": "deleted"}

    now = datetime.now(timezone.utc)
    note = (payload.get("note") or "").strip()[:200] or None
    await db.resource_bookings.update_one(
        {"booking_id": booking_id},
        {"$set": {
            "status": "cancelled",
            "skip_reason": reason,
            "skip_note": note,
            "cancelled_at": now,
            "cancelled_by": user["user_id"],
            "updated_at": now,
        }},
    )
    await _audit_booking(user, booking_id, "office_day_skipped", {"reason": reason})
    return {
        "booking_id": booking_id,
        "action": "cancelled",
        "reason": reason,
        "emoji": SKIP_REASONS[reason]["emoji"],
        "label": SKIP_REASONS[reason]["label_de"],
    }


@router.get("/office-days/skip-reasons")
async def list_skip_reasons():
    """Statische Liste der gültigen Skip-Gruende (für Frontend-Dropdown)."""
    return {"reasons": [
        {"id": k, **v} for k, v in SKIP_REASONS.items()
    ]}


@router.get("/users/me/office-days/upcoming")
async def upcoming_office_day_bookings(user=Depends(get_current_user)):
    """Iter 242 — liefert die naechsten 4 Wochen an auto-generated Buchungen
    des Users (zum Ad-hoc-Skip im UI)."""
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=28)
    bks = await db.resource_bookings.find({
        "user_id": user["user_id"],
        "auto_generated": True,
        "status": {"$in": ["confirmed", "pending_approval"]},
        "start_at": {"$gte": now, "$lt": horizon},
    }, {"_id": 0, "booking_id": 1, "resource_id": 1, "start_at": 1, "end_at": 1, "title": 1}).sort("start_at", 1).to_list(200)
    # Enrich mit Desk-Namen
    rids = list({b["resource_id"] for b in bks})
    resources = await db.resources.find(
        {"resource_id": {"$in": rids}},
        {"_id": 0, "resource_id": 1, "name": 1, "desk_number": 1, "floor": 1},
    ).to_list(200)
    rmap = {r["resource_id"]: r for r in resources}
    out = []
    for b in bks:
        r = rmap.get(b["resource_id"], {})
        s = b["start_at"]
        e = b["end_at"]
        if isinstance(s, datetime) and s.tzinfo is None:
            s = s.replace(tzinfo=timezone.utc)
        if isinstance(e, datetime) and e.tzinfo is None:
            e = e.replace(tzinfo=timezone.utc)
        out.append({
            "booking_id": b["booking_id"],
            "date": s.date().isoformat(),
            "title": b.get("title", "Bürotag"),
            "desk_name": r.get("name"),
            "desk_number": r.get("desk_number"),
            "floor": r.get("floor"),
            "start_at": s.isoformat(),
            "end_at": e.isoformat(),
        })
    return {"upcoming": out, "count": len(out)}


@router.get("/resources-office-week")
async def office_week(user=Depends(get_current_user)):
    """Iter 242 — Team-Office-Days-Visualisierung: liefert Mo–Fr der aktuellen
    Woche mit allen Personen, die jeweils ueber eine confirmed Desk-Buchung
    verfuegen. Respektiert `hide_from_office_widget` Opt-Out.
    """
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    now = datetime.now(timezone.utc)
    # Iter 242 — am Wochenende (Sat=5, Sun=6) auf die KOMMENDE Woche springen,
    # damit das Dashboard-Widget nicht leer wirkt. Mo–Fr aktuell sonst.
    if now.weekday() >= 5:
        days_to_next_monday = 7 - now.weekday()
        monday = (now + timedelta(days=days_to_next_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    friday_end = monday + timedelta(days=5)

    # 1. Confirmed Desk-Buchungen UND cancelled Bookings mit skip_reason
    bookings = await db.resource_bookings.find({
        "$or": [
            {"status": "confirmed"},
            {"status": "cancelled", "skip_reason": {"$exists": True, "$ne": None}},
        ],
        "start_at": {"$gte": monday, "$lt": friday_end},
    }, {"_id": 0, "user_id": 1, "resource_id": 1, "start_at": 1, "end_at": 1,
        "status": 1, "skip_reason": 1, "skip_note": 1}).to_list(5000)
    if not bookings:
        return {"week_start": monday.date().isoformat(), "days": []}

    rids = list({b["resource_id"] for b in bookings})
    desks = await db.resources.find(
        {"resource_id": {"$in": rids}, "type": "desk"},
        {"_id": 0, "resource_id": 1, "desk_number": 1, "floor": 1, "name": 1},
    ).to_list(1000)
    desk_map = {d["resource_id"]: d for d in desks}
    desk_bks = [b for b in bookings if b["resource_id"] in desk_map]

    uids = list({b["user_id"] for b in desk_bks if b.get("user_id")})
    users_docs = await db.users.find(
        {"user_id": {"$in": uids}},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "avatar": 1,
         "department": 1, "hide_from_office_widget": 1},
    ).to_list(2000)
    user_map = {u["user_id"]: u for u in users_docs}

    # 2. Buckets pro Wochentag (0=Mo, 4=Fr)
    days: list = []
    weekday_de = ["Mo", "Di", "Mi", "Do", "Fr"]
    for i in range(5):
        day_start = monday + timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        seen_users: dict = {}
        absent_users: dict = {}
        for b in desk_bks:
            s = b["start_at"]
            if isinstance(s, datetime) and s.tzinfo is None:
                s = s.replace(tzinfo=timezone.utc)
            if not (day_start <= s < day_end):
                continue
            uid = b.get("user_id")
            u = user_map.get(uid)
            if not u or u.get("hide_from_office_widget"):
                continue
            d = desk_map[b["resource_id"]]
            if b.get("status") == "cancelled" and b.get("skip_reason"):
                # Iter 243 — Abwesenheit mit Grund (Krank/Homeoffice/Urlaub/Sonstiges)
                if uid in seen_users:
                    continue
                if uid in absent_users:
                    continue
                meta = SKIP_REASONS.get(b["skip_reason"], {})
                absent_users[uid] = {
                    "user_id": uid,
                    "name": u.get("name") or u.get("email", "?").split("@")[0],
                    "avatar_url": u.get("avatar") or None,
                    "reason": b["skip_reason"],
                    "reason_label": meta.get("label_de", b["skip_reason"]),
                    "emoji": meta.get("emoji", "❔"),
                    "note": b.get("skip_note") or None,
                }
            else:
                # confirmed = anwesend
                if uid in seen_users:
                    continue
                # Falls user vorher als absent gelistet (z.B. eine cancelled
                # und eine confirmed): anwesend ueberschreibt abwesend.
                absent_users.pop(uid, None)
                seen_users[uid] = {
                    "user_id": uid,
                    "name": u.get("name") or u.get("email", "?").split("@")[0],
                    "avatar_url": u.get("avatar") or None,
                    "department": u.get("department"),
                    "desk_number": d.get("desk_number") or d.get("name"),
                    "floor": d.get("floor"),
                }
        days.append({
            "weekday": weekday_de[i],
            "date": day_start.date().isoformat(),
            "people": list(seen_users.values()),
            "count": len(seen_users),
            "absent": list(absent_users.values()),
            "absent_count": len(absent_users),
        })
    return {"week_start": monday.date().isoformat(), "days": days}
