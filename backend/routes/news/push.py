from fastapi import APIRouter, Request, HTTPException
from datetime import datetime, timezone
from database import db
from dependencies import get_current_user

from ._helpers import _can_review, _dispatch_push_for_post

router = APIRouter()


@router.get("/news/push/vapid-public-key")
async def get_vapid_key(request: Request):
    await get_current_user(request)
    from services.push import get_vapid_public_key
    key = get_vapid_public_key()
    return {"public_key": key}

@router.post("/news/push/subscribe")
async def push_subscribe(request: Request):
    """Store push subscription for a user."""
    user = await get_current_user(request)
    from services.rate_limit import enforce_rate_limit
    await enforce_rate_limit(request, key="push.subscribe", limit=20, window_sec=60,
                             per_user_id=user["user_id"])
    body = await request.json()
    subscription = body.get("subscription", {})
    if not subscription or not subscription.get("endpoint"):
        raise HTTPException(status_code=400, detail="Subscription erforderlich")
    # iter 152 — Validate the p256dh/auth keys *before* persisting.
    # Previously some browsers (iOS Safari pre-16.4, certain Android
    # configurations) would call `pushManager.subscribe()` and return
    # a PushSubscription whose `.toJSON()` lacked proper keys. The
    # backend happily stored those and then every web-push attempt
    # failed with "Invalid p256dh key specified" — the user sees no
    # notification and the logs fill up with errors. Rejecting the
    # malformed subscription here surfaces the issue to the user
    # immediately (they'll retry / re-install the PWA) instead of
    # silently burying it.
    keys = (subscription.get("keys") or {})
    p256 = keys.get("p256dh") or ""
    auth = keys.get("auth") or ""
    # A valid P-256 public key is 65 bytes → 87-char url-safe base64.
    # Auth secret is 16 bytes → 22-char url-safe base64. We accept a
    # small tolerance for padding (±4). Shorter values are guaranteed
    # broken.
    if len(p256) < 80 or len(auth) < 16:
        raise HTTPException(
            status_code=400,
            detail="Ungültige Push-Subscription — bitte PWA neu installieren oder Berechtigung erneut erteilen.",
        )
    await db.push_subscriptions.update_one(
        {"user_id": user["user_id"], "endpoint": subscription.get("endpoint")},
        {"$set": {
            "user_id": user["user_id"], "user_name": user.get("name", ""),
            "endpoint": subscription.get("endpoint"),
            "subscription": subscription,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return {"message": "Push-Subscription gespeichert"}

@router.delete("/news/push/subscribe")
async def push_unsubscribe(request: Request):
    user = await get_current_user(request)
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    endpoint = body.get("endpoint")
    q = {"user_id": user["user_id"]}
    if endpoint:
        q["endpoint"] = endpoint
    await db.push_subscriptions.delete_many(q)
    return {"message": "Push-Subscription entfernt"}







@router.post("/news/push/send")
async def send_push_notification(request: Request):
    """Send push notification for a specific post (admin/moderator)."""
    user = await get_current_user(request)
    if not await _can_review(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    body = await request.json()
    post_id = body.get("post_id", "")
    post = await db.news_posts.find_one({"post_id": post_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    result = await _dispatch_push_for_post(post, sent_by=user.get("name", ""))
    return {"message": "Push-Benachrichtigung gesendet", **result}


# Iter 253 — async variant: enqueue + return job_id immediately.
@router.post("/news/push/send/async")
async def send_push_notification_async(request: Request):
    """Enqueue a push-dispatch as a background job; returns {job_id}.

    Use this for large recipient lists. Poll GET /api/jobs/{job_id} for status.
    """
    user = await get_current_user(request)
    if not await _can_review(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    body = await request.json()
    post_id = body.get("post_id", "")
    post = await db.news_posts.find_one({"post_id": post_id}, {"_id": 0, "post_id": 1})
    if not post:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    from services.background_queue import enqueue
    job = await enqueue("send_bulk_push", post_id, user.get("name", "system"))
    job_id = getattr(job, "job_id", None) or "inline"
    return {"job_id": job_id, "post_id": post_id, "status": "queued"}

@router.get("/news/push/notifications")
async def list_push_notifications(request: Request):
    user = await get_current_user(request)
    if not await _can_review(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    notifs = await db.push_notifications.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return notifs

@router.get("/news/push/status")
async def push_status(request: Request):
    """Check if current user has an active push subscription."""
    user = await get_current_user(request)
    count = await db.push_subscriptions.count_documents({"user_id": user["user_id"]})
    return {"subscribed": count > 0, "count": count}


@router.post("/news/push/test")
async def push_self_test(request: Request):
    """Fire a test push notification to the CURRENT user's registered devices.
    Used by the /diag page so admins can verify push end-to-end on their iPhone."""
    from services.news_push import send_push_to_user
    user = await get_current_user(request)
    subs = await db.push_subscriptions.count_documents({"user_id": user["user_id"]})
    if subs == 0:
        raise HTTPException(status_code=400, detail="Kein Gerät registriert. Bitte erst Push aktivieren.")
    try:
        result = await send_push_to_user(
            user["user_id"],
            title="MeetFlow Test-Push",
            body=f"Hallo {user.get('name', '')}! Wenn du das siehst, funktioniert Push auf diesem Gerät.",
            data={"tag": "diag-test", "url": "/diag"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Push-Versand fehlgeschlagen: {e}")
    return {"message": "Test-Push versendet", "subscriptions": subs, "result": result}
