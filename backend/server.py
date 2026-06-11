from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware
import os
import uuid
import asyncio
from datetime import datetime, timezone, timedelta

from database import db, client, logger
from dependencies import hash_password, verify_password
from services.storage import init_storage
from services.email import send_email_real

# Import route modules
from routes.auth import router as auth_router
from routes.sso_azure import router as sso_azure_router
from routes.meetings import router as meetings_router
from routes.admin import router as admin_router
from routes.scheduling import router as scheduling_router
from routes.documents import router as documents_router
from routes.whiteboard import router as whiteboard_router
from routes.websocket import router as websocket_router
from routes.chat import router as chat_router
from routes.news import router as news_router
from routes.surveys import router as surveys_router
from routes.search import router as search_router
from routes.attachments import router as attachments_router
from routes.exports import router as exports_router
from routes.diag_share import router as diag_share_router
from routes.org_onboarding import router as org_onboarding_router, ensure_default_groups
from routes.user_settings import router as user_settings_router
from routes.calendar_sync import router as calendar_sync_router
from routes.livekit import router as livekit_router
from routes.tasks import router as tasks_router
from routes.resources import router as resources_router
from routes.jobs import router as jobs_router
from routes.drivers_license import router as drivers_license_router
from routes.analytics_catering import router as analytics_catering_router
from routes.filetransfer import router as filetransfer_router
# Iter 369 — License-Server-Stub: Router + Guard-Middleware + Heartbeat.
from routes.admin.license import router as license_router, LicenseGuardMiddleware
from services.license import start_heartbeat as start_license_heartbeat

app = FastAPI(title="MeetFlow API")
api_router = APIRouter(prefix="/api")

# Include all route modules into the api_router
api_router.include_router(auth_router)
api_router.include_router(sso_azure_router)
api_router.include_router(meetings_router)
api_router.include_router(admin_router)
api_router.include_router(scheduling_router)
api_router.include_router(documents_router)
api_router.include_router(whiteboard_router)

# Chat has both API routes and WebSocket - include in both
api_router.include_router(chat_router)
api_router.include_router(news_router)
api_router.include_router(surveys_router)
api_router.include_router(search_router)
api_router.include_router(attachments_router)
api_router.include_router(exports_router)
api_router.include_router(diag_share_router)
api_router.include_router(org_onboarding_router)
api_router.include_router(user_settings_router)
api_router.include_router(calendar_sync_router)
api_router.include_router(livekit_router)
api_router.include_router(tasks_router)
api_router.include_router(resources_router)
api_router.include_router(jobs_router)
api_router.include_router(drivers_license_router)
api_router.include_router(analytics_catering_router)
api_router.include_router(filetransfer_router)
# Iter 369 — Lizenz-Status + Recheck-Endpoints unter /api/license/* + /api/admin/license/*
api_router.include_router(license_router)

# Include api_router in app
app.include_router(api_router)

# SECURITY/ORDERING: the chat WS is at `/api/ws/chat/{user_id}` but the
# meetings WS is the broader `/api/ws/{meeting_id}/{user_id}`. FastAPI matches
# routes in include-order, so register the narrower chat router FIRST,
# otherwise the meetings handler would treat `chat` as a meeting_id and every
# chat WS connection would be rejected by _authenticate_ws (see iter 101/110).
app.include_router(chat_router, include_in_schema=False)
app.include_router(websocket_router)

# Install production-readiness extensions (JSON logs, request-id, health
# endpoint, ETag caching, rate-limiter). MUST be after routers so the
# health route lands on api_router; MUST be before CORS so CORS remains
# the outermost middleware (iter 113).
from services.prod_ops import install_production_extensions  # noqa: E402
install_production_extensions(app, api_router)

# WebSocket routers go directly on app (not under api_router prefix)


# ============ STARTUP ============

@app.on_event("startup")
async def startup():
    # Iter 386b — Filetransfer collections + sweep
    await db.file_transfers.create_index([("owner_user_id", 1), ("created_at", -1)])
    await db.file_transfers.create_index("recipient_user_ids")
    await db.file_transfers.create_index("expires_at")
    await db.file_transfer_files.create_index("transfer_id")
    await db.file_transfer_shares.create_index("token", unique=True)
    await db.file_transfer_shares.create_index("transfer_id")
    await db.file_transfer_downloads.create_index([("transfer_id", 1), ("created_at", -1)])
    await db.file_transfer_audit.create_index([("transfer_id", 1), ("created_at", -1)])
    try:
        from routes.filetransfer import expire_outdated as _ft_expire
        await _ft_expire()
    except Exception as _e:
        logger.warning(f"filetransfer initial expire sweep failed: {_e}")

    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.meetings.create_index("meeting_id", unique=True)
    await db.meetings.create_index("meeting_code")
    await db.meeting_participants.create_index([("meeting_id", 1), ("user_id", 1)])
    await db.chat_messages.create_index("meeting_id")
    await db.login_attempts.create_index("identifier")
    await db.password_reset_tokens.create_index("token")
    await db.polls.create_index("meeting_id")
    await db.questions.create_index("meeting_id")
    await db.breakout_rooms.create_index("meeting_id")
    await db.recordings.create_index("meeting_id")
    await db.transcripts.create_index("meeting_id")
    await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
    await db.meeting_files.create_index("meeting_id")
    await db.meeting_documents.create_index("meeting_id")
    await db.meeting_documents.create_index("sign_token")
    await db.document_audit_logs.create_index([("doc_id", 1), ("timestamp", -1)])
    await db.document_audit_logs.create_index("meeting_id")
    await db.whiteboard_strokes.create_index("meeting_id")
    await db.whiteboard_notes.create_index("meeting_id")
    await db.meeting_templates.create_index("created_by")
    await db.attendance_events.create_index("meeting_id")
    await db.ai_insights.create_index("meeting_id")
    await db.action_items.create_index("meeting_id")
    await db.meeting_policies.create_index("policy_id")
    await db.conversations.create_index("members.user_id")
    await db.conversations.create_index("conversation_id", unique=True)
    await db.messages.create_index([("conversation_id", 1), ("created_at", -1)])
    await db.messages.create_index("message_id", unique=True)
    # d1/d5 (iter 113): compound index to speed up the "unread count" query
    # in `list_conversations` + a scoped index for missed-call watcher lookups
    await db.messages.create_index([("conversation_id", 1), ("sender_id", 1), ("created_at", -1)])
    await db.messages.create_index([("meeting_id", 1), ("created_at", -1)])
    await db.focus_times.create_index([("user_id", 1), ("start_time", 1), ("end_time", 1)])
    await db.meetings.create_index([("status", 1), ("scheduled_at", 1), ("reminder_sent", 1)])
    await db.meeting_participants.create_index("meeting_id")
    await db.meeting_participants.create_index([("user_id", 1), ("joined_at", -1)])
    await db.login_attempts.create_index([("identifier", 1), ("timestamp", -1)])
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    # Iter 172 (perf): indexes for /api/surveys, news feed enrichment
    await db.surveys.create_index([("status", 1), ("survey_type", 1), ("expires_at", 1)])
    await db.surveys.create_index("target_groups")
    await db.surveys.create_index("target_user_ids")
    await db.survey_responses.create_index([("survey_id", 1), ("user_id", 1)])
    # Iter 250 — partial unique index to prevent race-condition double-submits.
    # MongoDB partial index does not support $ne, so we set a synthetic
    # "_user_dedup" field only for non-anonymous responses; the index has a
    # `_user_dedup: {$exists: true}` partial filter.
    try:
        await db.survey_responses.create_index(
            [("survey_id", 1), ("_user_dedup", 1)],
            unique=True,
            partialFilterExpression={"_user_dedup": {"$exists": True}},
            name="uniq_survey_user_dedup",
        )
    except Exception as _e:
        logger.warning(f"uniq survey_responses index could not be created: {_e}")
    await db.survey_responses.create_index("survey_id")
    await db.news_reads.create_index([("user_id", 1), ("post_id", 1)])
    await db.news_reactions.create_index("post_id")
    await db.news_comments.create_index([("post_id", 1), ("deleted", 1)])
    await db.news_posts.create_index([("status", 1), ("published_at", -1)])

    # Resources & Bookings (iter 223)
    await db.resources.create_index("resource_id", unique=True)
    await db.resources.create_index("type")
    await db.resources.create_index("parent_resource_id")
    await db.resource_bookings.create_index("booking_id", unique=True)
    await db.resource_bookings.create_index([("resource_id", 1), ("start_at", 1), ("end_at", 1)])
    await db.resource_bookings.create_index([("user_id", 1), ("start_at", -1)])
    # Iter 248 — Index for $or query on booked_for_user_id (List "Meine Buchungen")
    await db.resource_bookings.create_index([("booked_for_user_id", 1), ("start_at", -1)])
    await db.resource_bookings.create_index("status")
    await db.catering_items.create_index("item_id", unique=True)
    await db.catering_requests.create_index("request_id", unique=True)
    await db.catering_requests.create_index([("booking_id", 1)])
    await db.catering_requests.create_index([("status", 1), ("created_at", -1)])

    # Iter 253 — Unique index on news_reactions to prevent race-condition
    # double-reactions (TOCTOU between find_one + insert_one).
    try:
        await db.news_reactions.create_index(
            [("post_id", 1), ("user_id", 1)],
            unique=True,
            name="uniq_news_reaction_per_user",
        )
    except Exception as _e:
        logger.warning(f"uniq news_reactions index could not be created: {_e}")

    # Iter 228 — new collections for audit gap-closing
    await db.blackout_periods.create_index([("resource_id", 1), ("start_at", 1), ("end_at", 1)])
    await db.cost_centers.create_index("cost_center_id", unique=True)
    await db.cost_centers.create_index("code")
    await db.accounting_accounts.create_index("account_id", unique=True)
    await db.user_favorites.create_index("user_id", unique=True)

    # Iter 345 — Performance indexes for hotspots identified in soak test
    # (see /app/test_reports/perf_iter344/REPORT.md).
    # - `bookings` is queried by host_id+status in build_calendar_events;
    #   p95 of /calendar/events was 5.1s due to a collection scan there.
    # - `bookings.meeting_id` is the join key from meetings → booking.
    # - `invoice_master_data` is queried by (type, active) for cost-center
    #   and accounts dropdowns; the in-process cache absorbs most reads
    #   but cold cache + admin writes still hit Mongo.
    try:
        await db.bookings.create_index([("host_id", 1), ("status", 1)])
        await db.bookings.create_index("meeting_id")
        await db.invoice_master_data.create_index([("type", 1), ("active", 1), ("code", 1)])
        await db.invoice_master_data.create_index("item_id", unique=True)
    except Exception as _e:
        logger.warning(f"iter-345 perf indexes could not be created: {_e}")

    # Iter 119: ensure the 'Gast' default group exists + org_settings doc
    try:
        await ensure_default_groups(db)
    except Exception as e:
        logger.warning(f"ensure_default_groups failed: {e}")

    try:
        init_storage()
    except Exception as e:
        logger.warning(f"Storage init skipped: {e}")

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@meetflow.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    # Loud warning when the built-in default password is still in use. This
    # is fine for preview environments (our E2E tests rely on it) but must
    # be overridden for production deployments via ADMIN_PASSWORD env var.
    if admin_password == "admin123":
        logger.warning(
            "[security] ADMIN_PASSWORD is still the built-in default. "
            "Set ADMIN_PASSWORD in your production environment!"
        )
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "user_id": f"user_{uuid.uuid4().hex[:12]}", "email": admin_email,
            "password_hash": hash_password(admin_password), "name": "Admin",
            "role": "admin", "avatar": "", "language": "en",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"Admin created: {admin_email}")
    elif not verify_password(admin_password, existing.get("password_hash", "")):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})

    os.makedirs("/app/memory", exist_ok=True)
    with open("/app/memory/test_credentials.md", "w") as f:
        f.write(f"# Test Credentials\n\n## Admin\n- Email: {admin_email}\n- Password: {admin_password}\n- Role: admin\n\n")
        f.write("## Endpoints\n- POST /api/auth/register\n- POST /api/auth/login\n- GET /api/auth/me\n- POST /api/auth/google-session\n")

    # Auto-migrate legacy roles (idempotent)
    try:
        from services.permissions import migrate_role, extra_grants_for_legacy, PRESETS
        legacy_count = 0
        async for u in db.users.find(
            {"role": {"$in": ["redakteur", "freigeber", "autor", "manager", "user"]}},
            {"_id": 0, "user_id": 1, "role": 1, "cap_grants": 1},
        ):
            old_role = u.get("role", "member")
            new_role = migrate_role(old_role)
            extra = set(u.get("cap_grants", []) or []) | set(extra_grants_for_legacy(old_role))
            await db.users.update_one({"user_id": u["user_id"]}, {"$set": {
                "role": new_role, "legacy_role": old_role,
                "cap_grants": sorted(list(extra)),
                "migrated_at": datetime.now(timezone.utc).isoformat(),
            }})
            legacy_count += 1
        if legacy_count:
            logger.info(f"Migrated {legacy_count} users from legacy roles to new 4-role system")

        # Seed / re-sync built-in capability presets.
        # Sprint 4 (iter 226): always upsert built-ins so newly added caps (e.g.
        # the resources/* family) propagate to existing deployments. Custom
        # presets (builtin != True) are never touched.
        synced = 0
        for p in PRESETS:
            doc = {**p, "builtin": True}
            existing = await db.presets.find_one({"preset_id": p["preset_id"]}, {"_id": 0})
            if existing and existing.get("builtin"):
                # Only mutate the builtin fields; leave `created_at` intact.
                await db.presets.update_one(
                    {"preset_id": p["preset_id"]},
                    {"$set": {"label": p["label"], "description": p["description"],
                              "capabilities": p["capabilities"], "builtin": True,
                              "updated_at": datetime.now(timezone.utc).isoformat()}},
                )
                synced += 1
            elif not existing:
                doc["created_at"] = datetime.now(timezone.utc).isoformat()
                await db.presets.insert_one(doc)
                synced += 1
        if synced:
            logger.info(f"Synced {synced} built-in capability presets (incl. resource roles)")
    except Exception as e:
        logger.warning(f"Role migration / preset seeding skipped: {e}")

    # Iter 324 — One-shot cleanup of test-data leftovers in the invoices /
    # invoice_templates collections. Earlier automated tests inserted rows
    # but never tore them down, polluting the admin UI ("Vorlagen, die ich
    # nicht kenne"). Runs exactly once per DB; marker stored in `migrations`.
    try:
        marker = await db.migrations.find_one({"_id": "iter324_test_data_cleanup"}, {"_id": 1})
        if not marker:
            test_patterns = [
                r"^BugFixTest[\s_]",
                r"^E2E[\s_]",
                r"^TEST_",
                r"^Test-(None|Templated|Plain)[\s_]",
            ]
            name_q = {"$or": [{"name": {"$regex": p, "$options": "i"}} for p in test_patterns]}
            title_q = {"$or": [{"title": {"$regex": p, "$options": "i"}} for p in test_patterns]}
            t_res = await db.invoice_templates.delete_many(name_q)
            i_res = await db.invoices.delete_many(title_q)
            await db.migrations.insert_one({
                "_id": "iter324_test_data_cleanup",
                "deleted_templates": t_res.deleted_count,
                "deleted_invoices": i_res.deleted_count,
                "ran_at": datetime.now(timezone.utc).isoformat(),
            })
            if t_res.deleted_count or i_res.deleted_count:
                logger.info(
                    f"[migration iter324] cleaned up "
                    f"{t_res.deleted_count} test invoice templates + "
                    f"{i_res.deleted_count} test invoices"
                )
    except Exception as e:
        logger.warning(f"iter324 cleanup migration skipped: {e}")

    logger.info("MeetFlow API started")

    # Iter 176: Redis Pub/Sub WebSocket broker — enables cross-pod fan-out
    # when running horizontally. Degrades to single-pod mode if REDIS_URL
    # isn't set or Redis is unreachable.
    try:
        from services.ws_broker import ws_broker
        await ws_broker.start()
        # iter 211 — register the meetings WS dispatcher so cross-pod
        # broadcasts (hand-raise, reactions, chat, whiteboard, subtitles, …)
        # reach participants connected to other FastAPI workers.
        try:
            from services.ws_manager import _meeting_dispatcher
            ws_broker.register_dispatcher(_meeting_dispatcher)
        except Exception as e:
            logger.warning(f"meeting dispatcher register skipped: {e}")
    except Exception as e:
        logger.warning(f"ws_broker start skipped: {e}")

    # Iter 204: cross-pod cache-invalidation broker (permissions / user /
    # pending_count caches). Same Redis instance as ws_broker. No-op when
    # REDIS_URL is unset.
    try:
        from services.cache_broker import cache_broker
        await cache_broker.start()
    except Exception as e:
        logger.warning(f"cache_broker start skipped: {e}")

    asyncio.create_task(_reminder_loop())
    # Iter 369 — License heartbeat: initial check + 6h-Loop.
    try:
        await start_license_heartbeat()
    except Exception as e:
        logger.warning(f"License heartbeat start skipped: {e}")
    # Scheduled-news + cleanup background loop
    try:
        from services.maintenance import start as start_maintenance
        start_maintenance()
    except Exception as e:
        logger.warning(f"Maintenance loop start skipped: {e}")


async def _reminder_loop():
    while True:
        try:
            config = await db.reminder_config.find_one({"config_id": "global"}, {"_id": 0})
            if not config or config.get("enabled", True) is False:
                await asyncio.sleep(60)
                continue
            now = datetime.now(timezone.utc)
            scheduled = await db.meetings.find({
                "status": "scheduled", "scheduled_at": {"$ne": None},
                "reminder_sent": {"$ne": True}, "reminder_minutes": {"$gt": 0},
            }, {"_id": 0}).to_list(50)
            for m in scheduled:
                try:
                    from dateutil import parser as dtparser
                    sched_time = dtparser.isoparse(m["scheduled_at"])
                    if sched_time.tzinfo is None:
                        sched_time = sched_time.replace(tzinfo=timezone.utc)
                    remind_mins = m.get("reminder_minutes", 15)
                    remind_at = sched_time - timedelta(minutes=remind_mins)
                    if now >= remind_at and now < sched_time:
                        participants = await db.meeting_participants.find(
                            {"meeting_id": m["meeting_id"]}, {"_id": 0}
                        ).to_list(100)
                        frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
                        join_url = f"{frontend_url}/meetings/{m['meeting_id']}/join"
                        time_str = sched_time.strftime("%d.%m.%Y %H:%M") + " UTC"
                        for p in participants:
                            email = p.get("email", "")
                            if email:
                                await send_email_real(email, f"Erinnerung: {m.get('title', 'Meeting')} in {remind_mins} Min.",
                                    f"<div style='font-family:Arial;padding:24px;'>"
                                    f"<h2 style='color:#4A5D4E;'>Meeting-Erinnerung</h2>"
                                    f"<p><b>{m.get('title','Meeting')}</b></p>"
                                    f"<p>Startet um: {time_str}</p>"
                                    f"<a href='{join_url}' style='display:inline-block;background:#4A5D4E;color:white;padding:10px 24px;border-radius:8px;text-decoration:none;margin-top:12px;'>Jetzt beitreten</a></div>"
                                )
                        host_email = ""
                        host = await db.users.find_one({"user_id": m.get("host_id")}, {"_id": 0})
                        if host:
                            host_email = host.get("email", "")
                        if host_email and host_email not in [p.get("email") for p in participants]:
                            await send_email_real(host_email, f"Erinnerung: {m.get('title', 'Meeting')} in {remind_mins} Min.",
                                f"<div style='font-family:Arial;padding:24px;'>"
                                f"<h2 style='color:#4A5D4E;'>Meeting-Erinnerung (Host)</h2>"
                                f"<p><b>{m.get('title','Meeting')}</b></p>"
                                f"<p>Startet um: {time_str}</p>"
                                f"<a href='{join_url}' style='display:inline-block;background:#4A5D4E;color:white;padding:10px 24px;border-radius:8px;text-decoration:none;margin-top:12px;'>Jetzt beitreten</a></div>"
                            )
                        await db.meetings.update_one({"meeting_id": m["meeting_id"]}, {"$set": {"reminder_sent": True}})
                        logger.info(f"[REMINDER] Sent for {m['meeting_id']}: {m.get('title')}")
                except Exception as e:
                    logger.error(f"[REMINDER] Error for {m.get('meeting_id')}: {e}")

            # Resource booking reminders (Sprint 4 P1 #10): notify owner 30 min ahead.
            booking_window_end = now + timedelta(minutes=30)
            # Iter 228 P2 — multiple reminder stages: 24h + 30min
            stage_24h_end = now + timedelta(hours=24)
            stage_24h_start = now + timedelta(hours=23, minutes=55)
            bookings_24h = await db.resource_bookings.find({
                "status": "confirmed",
                "reminder_24h_sent": {"$ne": True},
                "start_at": {"$lte": stage_24h_end, "$gt": stage_24h_start},
            }, {"_id": 0}).to_list(100)
            for b in bookings_24h:
                try:
                    await db.resource_bookings.update_one(
                        {"booking_id": b["booking_id"]},
                        {"$set": {"reminder_24h_sent": True}},
                    )
                    try:
                        from services.news_push import send_push_to_user
                        await send_push_to_user(
                            b["user_id"], title="Buchung morgen",
                            body=f"{b.get('title','Buchung')} startet in 24 Stunden",
                            data={"type": "booking_reminder_24h", "booking_id": b["booking_id"]},
                        )
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"[24H-REMINDER] {b.get('booking_id')}: {e}")

            bookings_to_remind = await db.resource_bookings.find({
                "status": {"$in": ["confirmed"]},
                "reminder_sent": {"$ne": True},
                "start_at": {"$lte": booking_window_end, "$gt": now},
            }, {"_id": 0}).to_list(100)
            for b in bookings_to_remind:
                try:
                    bk_user = await db.users.find_one({"user_id": b["user_id"]}, {"_id": 0, "email": 1, "name": 1})
                    res_doc = await db.resources.find_one({"resource_id": b["resource_id"]}, {"_id": 0, "name": 1, "type": 1})
                    start_at = b["start_at"]
                    if isinstance(start_at, str):
                        from dateutil import parser as _p
                        start_at = _p.isoparse(start_at)
                    if start_at.tzinfo is None:
                        start_at = start_at.replace(tzinfo=timezone.utc)
                    minutes_to = max(1, int((start_at - now).total_seconds() / 60))
                    if bk_user and bk_user.get("email"):
                        from services.email_templates import render_email, render_kv_list
                        body_html = (
                            "<p>Hallo {name},</p>"
                            "<p>nur ein kurzer Hinweis &mdash; eine deiner Buchungen startet in {min} Minuten:</p>"
                            "{kv}"
                            "<p>Wir wuenschen einen produktiven Termin!</p>"
                        ).format(
                            name=bk_user.get("name") or "",
                            min=minutes_to,
                            kv=render_kv_list([
                                ("Titel", b.get("title", "Buchung")),
                                ("Ressource", (res_doc or {}).get("name", "")),
                                ("Beginn", start_at.strftime("%d.%m.%Y %H:%M")),
                            ]),
                        )
                        front_url = os.environ.get("FRONTEND_URL", "")
                        html = render_email(
                            title="Buchungs-Erinnerung",
                            preheader=f"{b.get('title','Buchung')} startet in {minutes_to} Min.",
                            body_html=body_html,
                            cta_label="Buchung oeffnen",
                            cta_url=f"{front_url}/resources?tab=mine" if front_url else None,
                        )
                        await send_email_real(
                            bk_user["email"],
                            f"Erinnerung: {b.get('title', 'Buchung')} in {minutes_to} Min.",
                            html,
                        )
                    # In-app + push
                    try:
                        from services.news_push import send_push_to_user
                        await send_push_to_user(
                            b["user_id"], title="Buchungs-Erinnerung",
                            body=f"{b.get('title','Buchung')} in {minutes_to} Min ({(res_doc or {}).get('name','')})",
                            data={"type": "booking_reminder", "booking_id": b["booking_id"], "url": "/resources?tab=mine"},
                        )
                    except Exception:
                        pass
                    await db.resource_bookings.update_one(
                        {"booking_id": b["booking_id"]}, {"$set": {"reminder_sent": True}}
                    )
                    logger.info(f"[BOOKING-REMINDER] Sent for {b['booking_id']}: {b.get('title')}")
                except Exception as e:
                    logger.error(f"[BOOKING-REMINDER] Error for {b.get('booking_id')}: {e}")

            # Iter 228 P1 #14 — auto-release no-shows (grace 15 min)
            try:
                from datetime import timedelta as _td
                cutoff_ns = now - _td(minutes=15)
                ns_result = await db.resource_bookings.update_many({
                    "status": "confirmed",
                    "checked_in_at": None,
                    "start_at": {"$lt": cutoff_ns},
                    "end_at": {"$gt": now},
                }, {"$set": {"status": "no_show", "updated_at": now}})
                if ns_result.modified_count:
                    logger.info(f"[NO-SHOW] auto-released {ns_result.modified_count} bookings")
            except Exception as e:
                logger.error(f"[NO-SHOW] {e}")

            # Iter 283 — Check-in reminder (per-user configurable, default 15 min before start)
            # Iterate bookings starting within next 4h (covers any reasonable user setting up to 240 min)
            try:
                from datetime import timedelta as _td_290
                grace_doc = await db.org_settings.find_one({"_id_key": "org_settings_singleton"}, {"_id": 0}) or {}
                lock_hours = int(grace_doc.get("auto_lock_unverified_hours", 24) or 0)
                if lock_hours > 0:
                    cutoff_290 = now - _td_290(hours=lock_hours)
                    # Self-registered users whose mail is still unverified
                    # AFTER the grace window are locked out. Admin-created or
                    # invited accounts are exempt (`self_registered != True`).
                    result_290 = await db.users.update_many({
                        "self_registered": True,
                        "email_verified": {"$ne": True},
                        "status": {"$nin": ["locked_unverified", "inactive"]},
                        "$or": [
                            {"created_at": {"$lte": cutoff_290.isoformat()}},
                            {"created_at": {"$lte": cutoff_290}},
                        ],
                    }, {"$set": {
                        "status": "locked_unverified",
                        "locked_at": now,
                        "locked_reason": "email_unverified_grace_expired",
                    }})
                    if result_290.modified_count:
                        logger.info("[AUTO-LOCK] %s self-registered accounts locked (unverified > %sh)",
                                    result_290.modified_count, lock_hours)
                        # Bust user-cache so any active session is rejected
                        try:
                            from services.user_cache import invalidate_all as _inv_all
                            await _inv_all()
                        except Exception:
                            pass
            except Exception as _e290:
                logger.error("[AUTO-LOCK-UNVERIFIED] %s", _e290)

            try:
                from datetime import timedelta as _td2
                from services.notification_prefs import get_prefs as _get_prefs
                from services.news_push import send_push_to_user as _push
                checkin_candidates = await db.resource_bookings.find({
                    "status": "confirmed",
                    "checked_in_at": None,
                    "checkin_reminder_sent": {"$ne": True},
                    "start_at": {"$gt": now, "$lte": now + _td2(hours=4)},
                }, {"_id": 0}).to_list(200)
                for b in checkin_candidates:
                    try:
                        start_at = b["start_at"]
                        if isinstance(start_at, str):
                            from dateutil import parser as _p
                            start_at = _p.isoparse(start_at)
                        if start_at.tzinfo is None:
                            start_at = start_at.replace(tzinfo=timezone.utc)
                        # Determine which user(s) should receive the reminder.
                        recipients = []
                        if b.get("booked_for_user_id"):
                            recipients.append(b["booked_for_user_id"])
                        else:
                            recipients.append(b["user_id"])
                        for uid in recipients:
                            prefs = await _get_prefs(uid)
                            mins = int(prefs.get("checkin_reminder_minutes", 15) or 0)
                            if mins <= 0:
                                continue
                            remind_at = start_at - _td2(minutes=mins)
                            if now >= remind_at:
                                res_doc = await db.resources.find_one({"resource_id": b["resource_id"]}, {"_id": 0, "name": 1})
                                try:
                                    await _push(
                                        uid,
                                        title="Bitte einchecken",
                                        body=f"{b.get('title','Buchung')} beginnt in {mins} Min — {(res_doc or {}).get('name','')}",
                                        data={"type": "booking_checkin_reminder",
                                              "booking_id": b["booking_id"],
                                              "url": "/resources?tab=mine"},
                                    )
                                except Exception:
                                    pass
                        await db.resource_bookings.update_one(
                            {"booking_id": b["booking_id"]},
                            {"$set": {"checkin_reminder_sent": True}},
                        )
                    except Exception as e:
                        logger.error(f"[CHECKIN-REMINDER] {b.get('booking_id')}: {e}")
            except Exception as e:
                logger.error(f"[CHECKIN-REMINDER-STAGE] {e}")

            # Iter 283 — Check-out reminder + auto-checkout grace
            # When end_at has passed and the user is still checked-in without
            # check-out: send a push (once); auto-checkout after 30min grace.
            try:
                from datetime import timedelta as _td3
                from services.notification_prefs import get_prefs as _get_prefs2
                from services.news_push import send_push_to_user as _push2
                checkout_candidates = await db.resource_bookings.find({
                    "checked_in_at": {"$ne": None},
                    "checked_out_at": None,
                    "checkout_reminder_sent": {"$ne": True},
                    "end_at": {"$lt": now},
                }, {"_id": 0}).to_list(200)
                for b in checkout_candidates:
                    try:
                        recipients = []
                        if b.get("booked_for_user_id"):
                            recipients.append(b["booked_for_user_id"])
                        else:
                            recipients.append(b["user_id"])
                        for uid in recipients:
                            prefs = await _get_prefs2(uid)
                            if not prefs.get("checkout_reminder_enabled", True):
                                continue
                            res_doc = await db.resources.find_one({"resource_id": b["resource_id"]}, {"_id": 0, "name": 1})
                            try:
                                await _push2(
                                    uid,
                                    title="Bitte auschecken",
                                    body=f"{b.get('title','Buchung')} ist beendet — bitte auschecken ({(res_doc or {}).get('name','')})",
                                    data={"type": "booking_checkout_reminder",
                                          "booking_id": b["booking_id"],
                                          "url": "/resources?tab=mine"},
                                )
                            except Exception:
                                pass
                        await db.resource_bookings.update_one(
                            {"booking_id": b["booking_id"]},
                            {"$set": {"checkout_reminder_sent": True}},
                        )
                    except Exception as e:
                        logger.error(f"[CHECKOUT-REMINDER] {b.get('booking_id')}: {e}")
                # Auto-checkout after 30min grace (status -> completed)
                grace_cut = now - _td3(minutes=30)
                ac_result = await db.resource_bookings.update_many({
                    "checked_in_at": {"$ne": None},
                    "checked_out_at": None,
                    "end_at": {"$lt": grace_cut},
                }, {"$set": {
                    "checked_out_at": now,
                    "status": "completed",
                    "auto_checked_out": True,
                    "updated_at": now,
                }})
                if ac_result.modified_count:
                    logger.info(f"[AUTO-CHECKOUT] {ac_result.modified_count} bookings closed automatically")
            except Exception as e:
                logger.error(f"[CHECKOUT-STAGE] {e}")
        except Exception as e:
            logger.error(f"[REMINDER-LOOP] Error: {e}")
        await asyncio.sleep(60)


@app.on_event("shutdown")
async def shutdown():
    try:
        from services.ws_broker import ws_broker
        await ws_broker.stop()
    except Exception:
        pass
    try:
        from services.cache_broker import cache_broker
        await cache_broker.stop()
    except Exception:
        pass
    client.close()


cors_origins_env = os.environ.get("CORS_ORIGINS", "*").strip()
if cors_origins_env == "*":
    # Allow any origin but still support credentials (wildcard + credentials is forbidden by CORS spec,
    # so we use a regex that matches every origin instead).
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    allowed_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def security_headers(request, call_next):
    """Defense-in-depth security headers (iter 101 audit fix).
    HSTS handled by the ingress; we add the defaults that FastAPI does not."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: blob: https:; "
        "media-src 'self' blob: https:; "
        "connect-src 'self' https: wss: ws:; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self' data: https:; "
        "frame-ancestors 'none'"
    )
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response



# Iter 369 — License-Guard: muss als LETZTES registriert werden, damit es
# bei FastAPI's reverse-stack als ERSTES (vor allem anderen) ausgeführt wird
# und 503-Responses sofort zurückgibt, ohne CORS/Sec-Header-Overhead.
app.add_middleware(LicenseGuardMiddleware)
