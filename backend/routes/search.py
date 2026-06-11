"""Global search API aggregating News, Chat, Meetings, and Users."""
from fastapi import APIRouter, Request
from dependencies import get_current_user
from database import db, read_db

router = APIRouter()


@router.get("/search/global")
async def global_search(request: Request, q: str = "", limit: int = 5):
    """Cross-module search for the Cmd/Ctrl+K palette.

    Returns grouped results: news, meetings, chats, users.
    """
    user = await get_current_user(request)
    q = (q or "").strip()
    if len(q) < 2:
        return {"news": [], "meetings": [], "chats": [], "users": []}
    limit = max(1, min(int(limit), 20))
    regex = {"$regex": q, "$options": "i"}
    user_groups = user.get("groups", [])

    # News (filtered by target)
    news_query = {
        "status": "published",
        "$and": [
            {"$or": [
                {"title": regex}, {"content": regex},
                {"excerpt": regex}, {"tags": regex},
            ]},
            {"$or": [
                {"target_groups": {"$size": 0}}, {"target_groups": {"$exists": False}},
                {"target_groups": {"$in": user_groups}}, {"target_all": True},
            ]},
        ],
    }
    news = await read_db.news_posts.find(
        news_query, {"_id": 0, "post_id": 1, "title": 1, "excerpt": 1, "priority": 1, "published_at": 1}
    ).sort("published_at", -1).limit(limit).to_list(limit)

    # Meetings user is part of
    user_participant_meetings = await read_db.meeting_participants.find(
        {"user_id": user["user_id"]}, {"_id": 0, "meeting_id": 1}
    ).to_list(5000)
    meeting_ids = [p["meeting_id"] for p in user_participant_meetings]
    meetings = await read_db.meetings.find(
        {"meeting_id": {"$in": meeting_ids},
         "$or": [{"title": regex}, {"description": regex}, {"meeting_code": regex}]},
        {"_id": 0, "meeting_id": 1, "meeting_code": 1, "title": 1, "scheduled_at": 1, "status": 1}
    ).sort("scheduled_at", -1).limit(limit).to_list(limit)

    # Chats - only conversations user is a member of
    user_convs = await read_db.conversations.find(
        {"members.user_id": user["user_id"]}, {"_id": 0, "conversation_id": 1}
    ).to_list(500)
    conv_ids = [c["conversation_id"] for c in user_convs]
    chats = await read_db.chat_messages.find(
        {"conversation_id": {"$in": conv_ids}, "content": regex},
        {"_id": 0, "message_id": 1, "conversation_id": 1, "content": 1, "sender_name": 1, "created_at": 1}
    ).sort("created_at", -1).limit(limit).to_list(limit)

    # Users (guests don't see other users — iter 154)
    from services.guest_visibility import is_guest_user
    if await is_guest_user(user):
        users = []
    else:
        users = await read_db.users.find(
            {"$or": [{"name": regex}, {"email": regex}], "status": {"$ne": "inactive"}},
            {"_id": 0, "user_id": 1, "name": 1, "email": 1, "avatar": 1, "role": 1, "online": 1, "status_mode": 1}
        ).limit(limit).to_list(limit)

    return {"news": news, "meetings": meetings, "chats": chats, "users": users}


@router.get("/search/mentions")
async def mention_search(request: Request, q: str = "", limit: int = 6):
    """Lightweight user search for @mention autocomplete.

    Supports 0+ characters (shows recent active users when empty) and is
    intentionally separate from /search/global so the 2-char minimum there
    doesn't block inline mention suggestions.

    Guests (members of the "Gast" group) receive an empty list — they
    cannot @-mention users they aren't already talking to (iter 154).
    """
    user = await get_current_user(request)
    from services.guest_visibility import is_guest_user
    if await is_guest_user(user):
        return {"users": []}
    q = (q or "").strip()
    limit = max(1, min(int(limit), 20))
    base = {"status": {"$ne": "inactive"}}
    if q:
        regex = {"$regex": q, "$options": "i"}
        base["$or"] = [{"name": regex}, {"email": regex}]
    users = await db.users.find(
        base,
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "avatar": 1, "role": 1},
    ).sort("name", 1).limit(limit).to_list(limit)
    return {"users": users}

