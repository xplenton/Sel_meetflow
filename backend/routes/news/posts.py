from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from typing import Optional, List, Dict
from datetime import datetime, timezone, timedelta
from database import db, logger
from dependencies import get_current_user
import uuid
import os
import shutil

from ._helpers import _can_create, _can_moderate

router = APIRouter()


# ============ NEWS CATEGORIES ============

@router.get("/news/categories")
async def list_categories(request: Request):
    await get_current_user(request)
    cats = await db.news_categories.find({}, {"_id": 0}).sort("name", 1).to_list(100)
    return cats

@router.post("/news/categories")
async def create_category(request: Request):
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name erforderlich")
    cat_id = f"cat_{uuid.uuid4().hex[:10]}"
    cat = {
        "category_id": cat_id, "name": name,
        "color": body.get("color", "#4A5D4E"),
        "icon": body.get("icon", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.news_categories.insert_one(cat)
    cat.pop("_id", None)
    return cat

@router.delete("/news/categories/{cat_id}")
async def delete_category(cat_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin erforderlich")
    await db.news_categories.delete_one({"category_id": cat_id})
    return {"message": "Kategorie gelöscht"}

# ============ NEWS POSTS ============

_SIGNAGE_PROJECTION = {
    "_id": 0, "post_id": 1, "title": 1, "excerpt": 1, "content": 1,
    "priority": 1, "published_at": 1, "author_name": 1, "category": 1,
    "cover_image": 1,
}


@router.get("/news/digital-signage/feed")
async def get_digital_signage_feed(limit: int = 20):
    """Public pull feed for digital-signage displays (lobby/hall TVs).
    Returns only posts that were explicitly tagged for signage via the
    channel picker (`signage_eligible=True`). No auth — signage displays
    typically run unattended without user sessions (iter 130)."""
    posts = await db.news_posts.find(
        {
            "status": "published",
            "signage_eligible": True,
        },
        _SIGNAGE_PROJECTION,
    ).sort("published_at", -1).limit(min(limit, 50)).to_list(limit)
    return {"posts": posts, "count": len(posts)}


@router.get("/news/digital-signage/preview/{post_id}")
async def get_digital_signage_preview(post_id: str, request: Request):
    """Authenticated preview of a single post rendered as a signage frame.
    Used by the News-Editor's "Signage-Vorschau" button so editors can
    check how a post will look on lobby TVs BEFORE publishing — bypasses
    both `status=='published'` and `signage_eligible` filters (iter 132)."""
    user = await get_current_user(request)
    if not await _can_create(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    post = await db.news_posts.find_one({"post_id": post_id}, _SIGNAGE_PROJECTION)
    if not post:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    return {"posts": [post], "count": 1, "preview": True}


@router.get("/news/feed")
async def get_news_feed(request: Request, page: int = 1, limit: int = 20,
                        sort: str = "latest", category: Optional[str] = None,
                        priority: Optional[str] = None, search: Optional[str] = None):
    """Main feed endpoint - returns news filtered by user's groups/targeting."""
    from services.news_feed import fetch_feed
    user = await get_current_user(request)
    return await fetch_feed(
        user, page=page, limit=limit, sort=sort,
        category=category, priority=priority, search=search,
    )

@router.get("/news/posts/{post_id}")
async def get_news_post(post_id: str, request: Request):
    from services.audience_guards import assert_can_view_news_post
    user = await get_current_user(request)
    post = await assert_can_view_news_post(user, post_id)
    # Read status
    read = await db.news_reads.find_one({"post_id": post_id, "user_id": user["user_id"]})
    post["is_read"] = read is not None
    # Reactions
    reactions = await db.news_reactions.find({"post_id": post_id}, {"_id": 0}).to_list(500)
    post["reaction_counts"] = {}
    post["user_reaction"] = None
    for r in reactions:
        rtype = r["reaction_type"]
        post["reaction_counts"][rtype] = post["reaction_counts"].get(rtype, 0) + 1
        if r["user_id"] == user["user_id"]:
            post["user_reaction"] = rtype
    post["comment_count"] = await db.news_comments.count_documents({"post_id": post_id, "deleted": {"$ne": True}})
    return post

@router.post("/news/posts")
async def create_news_post(request: Request):
    from services.news_crud import create_news_post as _create
    user = await get_current_user(request)
    if not await _can_create(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    body = await request.json()
    try:
        return await _create(body, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/news/posts/{post_id}")
async def update_news_post(post_id: str, request: Request):
    from services.news_crud import update_news_post as _update
    user = await get_current_user(request)
    body = await request.json()
    return await _update(post_id, body, user)

@router.delete("/news/posts/{post_id}")
async def delete_news_post(post_id: str, request: Request):
    user = await get_current_user(request)
    post = await db.news_posts.find_one({"post_id": post_id}, {"_id": 0, "title": 1, "author_id": 1, "status": 1})
    if not post:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    is_owner = post.get("author_id") == user["user_id"]
    can_mod = await _can_moderate(user)
    can_create = await _can_create(user)
    if not can_mod:
        if not (is_owner and can_create and post.get("status") == "draft"):
            raise HTTPException(status_code=403, detail="Keine Berechtigung")
    await db.news_posts.delete_one({"post_id": post_id})
    await db.news_audit.insert_one({
        "action": "deleted", "post_id": post_id, "user_id": user["user_id"],
        "user_name": user.get("name", ""), "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": f"News '{post.get('title', '')}' gelöscht"
    })
    return {"message": "News gelöscht"}

@router.post("/news/posts/{post_id}/publish")
async def publish_news_post(post_id: str, request: Request):
    from services.news_crud import publish_news_post as _publish
    user = await get_current_user(request)
    return await _publish(post_id, user)


@router.post("/news/posts/{post_id}/send-newsletter")
async def manual_send_newsletter(post_id: str, request: Request):
    """Manually (re-)send the HTML newsletter e-mail for a published post.
    Runs in the background and returns immediately with the recipient count."""
    user = await get_current_user(request)
    if not await _can_moderate(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    post = await db.news_posts.find_one({"post_id": post_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    if post.get("status") != "published":
        raise HTTPException(status_code=400, detail="Nur veroeffentlichte Beitraege können als Newsletter verschickt werden")
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    force = bool((body or {}).get("force", True))
    from services.news_email_newsletter import dispatch_newsletter_for_post, _resolve_email_audience
    recipients = await _resolve_email_audience(post)
    if not recipients:
        return {"total": 0, "sent": 0, "failed": 0, "reason": "no_recipients"}
    async def _dispatch():
        try:
            await dispatch_newsletter_for_post(post, force=force)
        except Exception as e:
            logger.error(f"Newsletter manual dispatch failed: {e}")
    import asyncio as _aio
    _aio.create_task(_dispatch())
    return {"queued": True, "recipients": len(recipients), "message": "Versand läuft im Hintergrund"}


@router.get("/news/posts/{post_id}/newsletter-preview")
async def newsletter_preview(post_id: str, request: Request):
    """Return a preview of audience size + HTML for the post."""
    user = await get_current_user(request)
    if not await _can_moderate(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    post = await db.news_posts.find_one({"post_id": post_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    from services.news_email_newsletter import _resolve_email_audience, _build_newsletter_html
    recipients = await _resolve_email_audience(post)
    return {
        "post_id": post_id,
        "audience_count": len(recipients),
        "channels": post.get("channels") or ["intranet"],
        "email_dispatched_at": post.get("email_dispatched_at"),
        "email_dispatch_stats": post.get("email_dispatch_stats"),
        "preview_html": _build_newsletter_html(post, unsubscribe_url="#preview"),
    }


@router.get("/news/editorial-calendar")
async def editorial_calendar(request: Request, start: Optional[str] = None, end: Optional[str] = None):
    """Return all news posts (draft/review/approval/scheduled/published/archived) within the
    given time window, enriched with the effective `calendar_date` — the date at which the
    post is / was / will be visible. Used by the News-Editorial-Timeline UI."""
    user = await get_current_user(request)
    if not (await _can_create(user) or await _can_moderate(user)):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    now = datetime.now(timezone.utc)
    if not start:
        start = (now - timedelta(days=7)).isoformat()
    if not end:
        end = (now + timedelta(days=90)).isoformat()
    cursor = db.news_posts.find(
        {"status": {"$in": ["draft", "review", "approval", "scheduled", "published", "archived"]}},
        {"_id": 0, "post_id": 1, "title": 1, "status": 1, "priority": 1,
         "publish_at": 1, "expires_at": 1, "published_at": 1, "created_at": 1,
         "author_id": 1, "author_name": 1, "owner_id": 1, "owner_name": 1,
         "channels": 1, "target_all": 1, "target_departments": 1,
         "target_locations": 1, "target_professions": 1, "target_roles": 1,
         "is_mandatory": 1, "pinned": 1, "categories": 1}
    )
    items = await cursor.to_list(1000)
    enriched: List[Dict] = []
    for p in items:
        # Effective calendar date: published_at if set, else publish_at, else created_at
        cal_date = p.get("published_at") or p.get("publish_at") or p.get("created_at")
        if not cal_date:
            continue
        # Only include if within the window
        if cal_date < start or cal_date > end:
            continue
        p["calendar_date"] = cal_date
        enriched.append(p)
    enriched.sort(key=lambda x: x.get("calendar_date") or "")
    return {"start": start, "end": end, "total": len(enriched), "items": enriched}



async def transfer_news_owner(post_id: str, request: Request):
    """Transfer page-owner responsibility to another user (moderators or current owner only)."""
    user = await get_current_user(request)
    post = await db.news_posts.find_one({"post_id": post_id}, {"_id": 0, "owner_id": 1, "title": 1})
    if not post:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    if post.get("owner_id") != user["user_id"] and not await _can_moderate(user):
        raise HTTPException(status_code=403, detail="Nur der aktuelle Owner oder ein Moderator darf den Owner übertragen")
    body = await request.json()
    new_owner_id = (body or {}).get("owner_id")
    if not new_owner_id:
        raise HTTPException(status_code=400, detail="owner_id erforderlich")
    new_owner = await db.users.find_one({"user_id": new_owner_id}, {"_id": 0, "name": 1, "email": 1})
    if not new_owner:
        raise HTTPException(status_code=404, detail="Neuer Owner nicht gefunden")
    old_owner_id = post.get("owner_id")
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.news_posts.update_one(
        {"post_id": post_id},
        {"$set": {"owner_id": new_owner_id, "owner_name": new_owner.get("name", ""), "updated_at": now_iso}}
    )
    await db.news_audit.insert_one({
        "action": "owner_transferred", "post_id": post_id, "user_id": user["user_id"],
        "user_name": user.get("name", ""), "timestamp": now_iso,
        "details": f"Owner von '{post.get('title', '')}' übertragen ({old_owner_id} -> {new_owner_id})",
        "from_owner_id": old_owner_id, "to_owner_id": new_owner_id,
    })
    return {"message": "Owner übertragen", "owner_id": new_owner_id, "owner_name": new_owner.get("name", "")}


@router.get("/news/posts/{post_id}/governance")
async def get_news_governance(post_id: str, request: Request):
    """Return the governance footprint (owner, author, transfer history, channels) of a post."""
    user = await get_current_user(request)
    post = await db.news_posts.find_one(
        {"post_id": post_id},
        {"_id": 0, "post_id": 1, "title": 1, "author_id": 1, "author_name": 1,
         "owner_id": 1, "owner_name": 1, "channels": 1, "status": 1,
         "publish_at": 1, "expires_at": 1, "target_all": 1,
         "target_groups": 1, "target_departments": 1, "target_locations": 1,
         "target_professions": 1, "target_roles": 1}
    )
    if not post:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    # Only owner/author/moderator may see governance info
    if (post.get("owner_id") != user["user_id"]
            and post.get("author_id") != user["user_id"]
            and not await _can_moderate(user)):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    transfers = await db.news_audit.find(
        {"post_id": post_id, "action": {"$in": ["owner_transferred", "created", "published", "scheduled_publish"]}},
        {"_id": 0}
    ).sort("timestamp", 1).to_list(100)
    return {"post": post, "history": transfers}

@router.post("/news/posts/{post_id}/archive")
async def archive_news_post(post_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    await db.news_posts.update_one({"post_id": post_id}, {"$set": {
        "status": "archived", "updated_at": datetime.now(timezone.utc).isoformat()
    }})
    return {"message": "Archiviert"}

# ============ READ RECEIPTS ============

@router.post("/news/posts/{post_id}/read")
async def mark_as_read(post_id: str, request: Request):
    from services.audience_guards import assert_can_view_news_post
    user = await get_current_user(request)
    await assert_can_view_news_post(user, post_id)
    existing = await db.news_reads.find_one({"post_id": post_id, "user_id": user["user_id"]})
    if not existing:
        await db.news_reads.insert_one({
            "post_id": post_id, "user_id": user["user_id"],
            "user_name": user.get("name", ""),
            "read_at": datetime.now(timezone.utc).isoformat(),
        })
    return {"message": "Gelesen"}

@router.get("/news/posts/{post_id}/reads")
async def get_read_receipts(post_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    reads = await db.news_reads.find({"post_id": post_id}, {"_id": 0}).to_list(5000)
    total_target = await _count_target_users(post_id)
    return {"reads": reads, "read_count": len(reads), "total_target": total_target}

async def _count_target_users(post_id):
    post = await db.news_posts.find_one({"post_id": post_id}, {"_id": 0, "target_groups": 1, "target_all": 1})
    if not post:
        return 0
    if post.get("target_all"):
        return await db.users.count_documents({"status": {"$ne": "inactive"}})
    groups = post.get("target_groups", [])
    if not groups:
        return await db.users.count_documents({"status": {"$ne": "inactive"}})
    return await db.users.count_documents({"groups": {"$in": groups}, "status": {"$ne": "inactive"}})

# ============ REACTIONS ============

@router.post("/news/posts/{post_id}/reactions")
async def toggle_reaction(post_id: str, request: Request):
    from services.news_interactions import toggle_reaction as _toggle
    from services.audience_guards import assert_can_view_news_post
    user = await get_current_user(request)
    await assert_can_view_news_post(user, post_id)
    body = await request.json()
    reaction_type = body.get("reaction_type", "like")
    return await _toggle(post_id, reaction_type, user)

# ============ COMMENTS ============

@router.get("/news/posts/{post_id}/comments")
async def get_comments(post_id: str, request: Request):
    from services.news_interactions import list_comments
    from services.audience_guards import assert_can_view_news_post
    user = await get_current_user(request)
    await assert_can_view_news_post(user, post_id)
    return await list_comments(post_id)

@router.post("/news/posts/{post_id}/comments")
async def add_comment(post_id: str, request: Request):
    from services.news_interactions import add_comment as _add
    from services.audience_guards import assert_can_view_news_post
    user = await get_current_user(request)
    await assert_can_view_news_post(user, post_id)
    body = await request.json()
    return await _add(post_id, body, user)

@router.delete("/news/comments/{comment_id}")
async def delete_comment(comment_id: str, request: Request):
    user = await get_current_user(request)
    comment = await db.news_comments.find_one({"comment_id": comment_id})
    if not comment:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    if comment["user_id"] != user["user_id"] and user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    await db.news_comments.update_one({"comment_id": comment_id}, {"$set": {"deleted": True}})
    return {"message": "Kommentar gelöscht"}

# ============ FILE UPLOAD ============

@router.post("/news/upload")
async def upload_news_file(request: Request, file: UploadFile = File(...)):
    user = await get_current_user(request)
    if not await _can_create(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    os.makedirs("/app/backend/uploads/news", exist_ok=True)
    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    file_id = f"newsfile_{uuid.uuid4().hex[:8]}.{ext}"
    path = f"/app/backend/uploads/news/{file_id}"
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"url": f"/api/news/files/{file_id}", "filename": file.filename, "file_id": file_id}

@router.get("/news/files/{file_id}")
async def serve_news_file(file_id: str, request: Request):
    # Require authentication. News-files are embedded into posts (cover image,
    # inline attachments) and must not be accessible without a session.
    await get_current_user(request)
    from fastapi.responses import FileResponse
    import mimetypes
    path = f"/app/backend/uploads/news/{file_id}"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)

# ============ STATS (for dashboard) ============

@router.get("/news/stats")
async def get_news_stats(request: Request):
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    total = await db.news_posts.count_documents({})
    published = await db.news_posts.count_documents({"status": "published"})
    drafts = await db.news_posts.count_documents({"status": "draft"})
    archived = await db.news_posts.count_documents({"status": "archived"})
    mandatory = await db.news_posts.count_documents({"is_mandatory": True, "status": "published"})
    return {"total": total, "published": published, "drafts": drafts, "archived": archived, "mandatory": mandatory}

@router.get("/news/unread-count")
async def get_unread_count(request: Request):
    user = await get_current_user(request)
    uid = user["user_id"]
    user_groups = user.get("groups", [])
    now_iso = datetime.now(timezone.utc).isoformat()
    query = {
        "status": "published",
        "$and": [
            {"$or": [{"expires_at": None}, {"expires_at": ""}, {"expires_at": {"$gte": now_iso}}]},
            {"$or": [{"publish_at": None}, {"publish_at": ""}, {"publish_at": {"$lte": now_iso}}]},
            {"$or": [
                {"target_groups": {"$size": 0}}, {"target_groups": {"$exists": False}},
                {"target_groups": {"$in": user_groups}}, {"target_all": True},
            ]},
        ],
    }
    total = await db.news_posts.count_documents(query)
    read_post_ids = await db.news_reads.distinct("post_id", {"user_id": uid})
    query_unread = {**query, "post_id": {"$nin": read_post_ids}}
    unread = await db.news_posts.count_documents(query_unread)
    mandatory_unread = await db.news_posts.count_documents({**query_unread, "is_mandatory": True})
    return {"unread": unread, "total": total, "mandatory_unread": mandatory_unread}


# ============ PHASE 2: APPROVAL WORKFLOW ============
# (helpers moved to _helpers.py to avoid cross-module duplication)
