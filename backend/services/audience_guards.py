"""
Audience visibility helpers (iter 186 — privacy hardening sweep).

Centralises the rules for "can user U see/interact with object O?"
across News, Surveys, Meetings. Mirrors the audience filter in
services/news_feed.py / surveys.py to keep the logic in ONE place.

All `assert_*` helpers raise HTTPException(404) on denial — a 404
prevents existence-leaks (BOLA/IDOR) compared to a bare 403.
"""
from typing import Dict, Any
from fastapi import HTTPException
from database import db


def _user_in_audience(user: Dict[str, Any], obj: Dict[str, Any]) -> bool:
    """Sync helper: does `obj`'s targeting include `user`?

    Mirrors `services.news_feed.build_audience_filter` semantics:
      * `target_all=True` → visible to everyone
      * Object listed via target_user_ids → visible
      * Any of user's groups in target_groups → visible
      * Targeted by department/location/profession/role → visible
      * No targeting set at all (legacy) → visible
    """
    if obj.get("target_all"):
        return True

    uid = user.get("user_id", "")
    user_role = user.get("role", "")
    user_groups = set(user.get("groups", []) or [])
    user_dept = (user.get("department") or "").strip()
    user_loc = (user.get("location") or "").strip()
    user_prof = (user.get("profession") or "").strip()

    target_users = set(obj.get("target_user_ids", []) or [])
    target_groups = set(obj.get("target_groups", []) or [])
    target_depts = set(obj.get("target_departments", []) or [])
    target_locs = set(obj.get("target_locations", []) or [])
    target_profs = set(obj.get("target_professions", []) or [])
    target_roles = set(obj.get("target_roles", []) or [])

    if uid and uid in target_users:
        return True
    if user_groups and (target_groups & user_groups):
        return True
    if user_dept and user_dept in target_depts:
        return True
    if user_loc and user_loc in target_locs:
        return True
    if user_prof and user_prof in target_profs:
        return True
    if user_role and user_role in target_roles:
        return True

    # No targeting set at all = visible to everyone (legacy behaviour for
    # very old objects that pre-date the audience feature).
    if (not target_users and not target_groups and not target_depts
            and not target_locs and not target_profs and not target_roles):
        return True
    return False


# ============ NEWS ============

async def can_view_news_post(user: Dict[str, Any], post: Dict[str, Any]) -> bool:
    """News rules:
      * Author / owner / moderator / admin → always
      * draft / review / approval / scheduled → only above
      * published / archived → audience targeting + status
    """
    if not post:
        return False
    if user.get("role") in ("admin", "moderator"):
        return True
    uid = user.get("user_id")
    if uid and (post.get("author_id") == uid or post.get("owner_id") == uid):
        return True
    if post.get("status") not in ("published", "archived"):
        return False
    return _user_in_audience(user, post)


async def assert_can_view_news_post(user: Dict[str, Any], post_id: str) -> Dict[str, Any]:
    """Fetches the post by id and raises 404 if missing OR user is not in audience."""
    post = await db.news_posts.find_one({"post_id": post_id}, {"_id": 0})
    if not post or not await can_view_news_post(user, post):
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    return post


# ============ SURVEYS ============

async def can_view_survey(user: Dict[str, Any], survey: Dict[str, Any]) -> bool:
    """Survey/feedback-form rules:
      * admin/moderator → always
      * Owner (created_by) → always
      * draft → only admin/moderator/owner
      * published / archived / closed → audience targeting
    """
    if not survey:
        return False
    if user.get("role") in ("admin", "moderator"):
        return True
    uid = user.get("user_id")
    if uid and survey.get("created_by") == uid:
        return True
    if survey.get("status") not in ("published", "archived", "closed"):
        return False
    return _user_in_audience(user, survey)


async def assert_can_view_survey(user: Dict[str, Any], survey_id: str) -> Dict[str, Any]:
    """Fetches the survey by id and raises 404 if missing OR user not in audience."""
    survey = await db.surveys.find_one({"survey_id": survey_id}, {"_id": 0})
    if not survey or not await can_view_survey(user, survey):
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    return survey


async def has_responded_to_survey(user_id: str, survey_id: str) -> bool:
    """Did this user submit a response to the given survey?"""
    if not user_id:
        return False
    found = await db.survey_responses.find_one(
        {"survey_id": survey_id, "user_id": user_id},
        {"_id": 1},
    )
    return found is not None


# ============ MEETINGS ============

async def can_view_meeting(user: Dict[str, Any], meeting: Dict[str, Any]) -> bool:
    """Meeting rules:
      * Admin → always
      * Host / co-host / creator → always
      * Listed participant (db.meeting_participants OR inline) → always
      * Email-invited (matches user's e-mail) → always
      * Otherwise → 404
    """
    if not meeting:
        return False
    if user.get("role") == "admin":
        return True
    uid = user.get("user_id", "")
    if uid and uid in (meeting.get("host_id"), meeting.get("created_by")):
        return True

    # Persistent participants table
    if uid:
        try:
            p = await db.meeting_participants.find_one(
                {"meeting_id": meeting.get("meeting_id"), "user_id": uid},
                {"_id": 0, "user_id": 1},
            )
            if p:
                return True
        except Exception:
            pass

    # Inline participants on the meeting doc (older schema)
    for p in meeting.get("participants", []) or []:
        if isinstance(p, dict) and p.get("user_id") == uid:
            return True
        if isinstance(p, str) and p == uid:
            return True

    # Email-based invitations (e.g. external participants registered post-hoc)
    em = (user.get("email") or "").lower()
    if em:
        for p in meeting.get("invited_emails", []) or []:
            if isinstance(p, str) and p.lower() == em:
                return True
        for p in meeting.get("optional_emails", []) or []:
            if isinstance(p, str) and p.lower() == em:
                return True

    return False


async def assert_can_view_meeting(
    user: Dict[str, Any],
    meeting_id: str,
    *,
    accept_code: bool = True,
) -> Dict[str, Any]:
    """Fetch a meeting by id (or meeting_code if `accept_code=True`) and raise
    HTTPException(404) if it doesn't exist or the user has no access.
    Returns the (sanitised) meeting dict on success.
    """
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting and accept_code:
        meeting = await db.meetings.find_one({"meeting_code": meeting_id}, {"_id": 0})
    if not meeting or not await can_view_meeting(user, meeting):
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting
