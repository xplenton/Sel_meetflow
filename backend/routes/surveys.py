from fastapi import APIRouter, Request, HTTPException
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from database import db, read_db, logger
from dependencies import get_current_user
import uuid

router = APIRouter()

# ============ SURVEYS ============


# Surveys targeting filter helper. Mirrors news_feed.build_audience_filter to
# support target_all / target_groups / target_user_ids (and future per-dept etc.).
def _survey_audience_or(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    user_groups = user.get("groups", [])
    user_id = user.get("user_id", "")
    conds: List[Dict[str, Any]] = [
        {"target_all": True},
        # Legacy: no targeting whatsoever → visible to all
        {"$and": [
            {"$or": [{"target_groups": {"$size": 0}}, {"target_groups": {"$exists": False}}]},
            {"$or": [{"target_user_ids": {"$size": 0}}, {"target_user_ids": {"$exists": False}}]},
        ]},
    ]
    if user_groups:
        conds.append({"target_groups": {"$in": user_groups}})
    if user_id:
        conds.append({"target_user_ids": user_id})
    return conds


@router.get("/surveys")
async def list_surveys(request: Request, status: Optional[str] = None):
    user = await get_current_user(request)
    query = {"survey_type": {"$in": ["survey", "feedback_form", None]}}
    if status:
        query["status"] = status
    now_iso = datetime.now(timezone.utc).isoformat()
    query["$and"] = [
        {"$or": [{"expires_at": None}, {"expires_at": ""}, {"expires_at": {"$gte": now_iso}}]},
        {"$or": _survey_audience_or(user)},
    ]
    surveys = await read_db.surveys.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    if not surveys:
        return surveys
    # Iter 172 (perf): batch-fetch participation + counts instead of N*2 round trips
    sids = [s["survey_id"] for s in surveys]
    my_resp_docs = await read_db.survey_responses.find(
        {"survey_id": {"$in": sids}, "user_id": user["user_id"]},
        {"_id": 0, "survey_id": 1},
    ).to_list(len(sids))
    my_resp_set = {d["survey_id"] for d in my_resp_docs}
    count_rows = await read_db.survey_responses.aggregate([
        {"$match": {"survey_id": {"$in": sids}}},
        {"$group": {"_id": "$survey_id", "c": {"$sum": 1}}},
    ]).to_list(len(sids))
    count_map = {r["_id"]: r["c"] for r in count_rows}
    for s in surveys:
        s["participated"] = s["survey_id"] in my_resp_set
        s["response_count"] = count_map.get(s["survey_id"], 0)
    return surveys

@router.get("/surveys/pending-count")
async def surveys_pending_count(request: Request):
    """Count of published surveys the user has not yet responded to (scoped by target)."""
    user = await get_current_user(request)
    now_iso = datetime.now(timezone.utc).isoformat()
    query = {
        "status": "published",
        "$and": [
            {"$or": [{"expires_at": None}, {"expires_at": ""}, {"expires_at": {"$gte": now_iso}}]},
            {"$or": _survey_audience_or(user)},
        ],
    }
    surveys = await db.surveys.find(query, {"_id": 0, "survey_id": 1}).to_list(500)
    if not surveys:
        return {"count": 0, "total": 0}
    # Iter 172 (perf): single query instead of N
    sids = [s["survey_id"] for s in surveys]
    responded = await db.survey_responses.distinct(
        "survey_id",
        {"survey_id": {"$in": sids}, "user_id": user["user_id"]},
    )
    return {"count": len(sids) - len(responded), "total": len(sids)}


@router.post("/surveys")
async def create_survey(request: Request):
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    body = await request.json()
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Titel erforderlich")
    survey_id = f"srv_{uuid.uuid4().hex[:10]}"
    survey = {
        "survey_id": survey_id,
        "title": title,
        "description": body.get("description", ""),
        "survey_type": body.get("survey_type", "survey"),  # survey, pulse_check, feedback_form
        "questions": body.get("questions", []),
        # Each question: {question_id, text, type: single_choice|multiple_choice|free_text|scale, options: [], scale_min, scale_max, required}
        "anonymous": body.get("anonymous", False),
        "status": body.get("status", "draft"),
        "target_all": body.get("target_all", True),
        "target_groups": body.get("target_groups", []),
        "target_user_ids": body.get("target_user_ids", []),
        "expires_at": body.get("expires_at", ""),
        "author_id": user["user_id"],
        "author_name": user.get("name", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.surveys.insert_one(survey)
    survey.pop("_id", None)
    # Notify all target users when directly published
    if survey.get("status") == "published":
        await _notify_new_survey(survey, user)
    return survey


async def _notify_new_survey(survey: dict, actor: dict):
    """Create in-app notifications for target users about a new published survey."""
    target_groups = survey.get("target_groups", [])
    target_user_ids = survey.get("target_user_ids", [])
    q = {"status": {"$ne": "inactive"}, "user_id": {"$ne": actor["user_id"]}}
    if not survey.get("target_all"):
        conds: List[Dict[str, Any]] = []
        if target_groups:
            conds.append({"groups": {"$in": target_groups}})
        if target_user_ids:
            conds.append({"user_id": {"$in": target_user_ids}})
        if conds:
            q["$or"] = conds
        else:
            return  # no-target survey → skip notification fan-out
    users = await db.users.find(q, {"_id": 0, "user_id": 1}).to_list(5000)
    now_iso = datetime.now(timezone.utc).isoformat()
    for u in users:
        await db.notifications.insert_one({
            "notification_id": f"notif_{uuid.uuid4().hex[:10]}",
            "user_id": u["user_id"],
            "type": "new_survey",
            "title": f"Neue Umfrage: {survey.get('title','')}",
            "body": survey.get("description", "")[:160],
            "survey_id": survey.get("survey_id"),
            "from_user_id": actor["user_id"],
            "from_user_name": actor.get("name", ""),
            "read": False,
            "created_at": now_iso,
        })

@router.get("/surveys/{survey_id}")
async def get_survey(survey_id: str, request: Request):
    from services.audience_guards import assert_can_view_survey
    user = await get_current_user(request)
    survey = await assert_can_view_survey(user, survey_id)
    resp = await db.survey_responses.find_one({"survey_id": survey_id, "user_id": user["user_id"]})
    survey["participated"] = resp is not None
    survey["my_response"] = {k: v for k, v in resp.items() if k != "_id"} if resp else None
    survey["response_count"] = await db.survey_responses.count_documents({"survey_id": survey_id})
    return survey

@router.put("/surveys/{survey_id}")
async def update_survey(survey_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    body = await request.json()
    prev = await db.surveys.find_one({"survey_id": survey_id}, {"_id": 0})
    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    for k in ["title", "description", "questions", "anonymous", "status", "target_all", "target_groups", "target_user_ids", "expires_at", "survey_type"]:
        if k in body:
            updates[k] = body[k]
    await db.surveys.update_one({"survey_id": survey_id}, {"$set": updates})
    updated = await db.surveys.find_one({"survey_id": survey_id}, {"_id": 0})
    # Notify on status transition to published
    if prev and updated and prev.get("status") != "published" and updated.get("status") == "published":
        await _notify_new_survey(updated, user)
    return updated

@router.delete("/surveys/{survey_id}")
async def delete_survey(survey_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    await db.surveys.delete_one({"survey_id": survey_id})
    await db.survey_responses.delete_many({"survey_id": survey_id})
    return {"message": "Umfrage gelöscht"}


@router.post("/surveys/{survey_id}/archive")
async def archive_survey(survey_id: str, request: Request):
    """Manually archive a survey (admin/moderator)."""
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    from services.surveys_archive import set_archive_state
    updated = await set_archive_state(survey_id, True, actor_id=user["user_id"])
    if not updated:
        raise HTTPException(status_code=404, detail="Umfrage nicht gefunden")
    return updated


@router.post("/surveys/{survey_id}/restore")
async def restore_survey(survey_id: str, request: Request):
    """Restore an archived survey back to status='published' (admin/moderator)."""
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    from services.surveys_archive import set_archive_state
    updated = await set_archive_state(survey_id, False, actor_id=user["user_id"])
    if not updated:
        raise HTTPException(status_code=404, detail="Umfrage nicht gefunden")
    return updated


@router.post("/surveys/archive/run")
async def run_survey_auto_archive(request: Request):
    """Manually trigger the auto-archive pass (admin only). Helpful for tests
    and for clinic-admins that want to clear the pending-count immediately."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json() if request.headers.get("content-length") else {}
    grace = int((body or {}).get("grace_days", 14) or 14)
    from services.surveys_archive import auto_archive_expired_surveys
    return await auto_archive_expired_surveys(grace_days=grace)

@router.post("/surveys/{survey_id}/respond")
async def submit_response(survey_id: str, request: Request):
    from services.audience_guards import assert_can_view_survey
    user = await get_current_user(request)
    survey = await assert_can_view_survey(user, survey_id)
    if survey.get("status") != "published":
        raise HTTPException(status_code=400, detail="Umfrage nicht aktiv")
    # Check if already responded
    existing = await db.survey_responses.find_one({"survey_id": survey_id, "user_id": user["user_id"]})
    if existing:
        raise HTTPException(status_code=400, detail="Bereits teilgenommen")
    body = await request.json()
    answers = body.get("answers", {})  # {question_id: answer_value}
    attachment_map = body.get("attachment_map", {})  # {question_id: [attachment_ids]}
    # sanitize attachment_map
    clean_attachment_map = {}
    if isinstance(attachment_map, dict):
        for qid, att_list in attachment_map.items():
            if isinstance(att_list, list):
                ids = [str(a) for a in att_list if isinstance(a, str)][:5]
                if ids:
                    clean_attachment_map[qid] = ids
    response_id = f"resp_{uuid.uuid4().hex[:10]}"
    response = {
        "response_id": response_id,
        "survey_id": survey_id,
        "user_id": user["user_id"] if not survey.get("anonymous") else "anonymous",
        "user_name": user.get("name", "") if not survey.get("anonymous") else "Anonym",
        "answers": answers,
        "attachment_map": clean_attachment_map,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # Iter 250 — synthetic dedup key (set only for non-anonymous) drives the
    # unique partial index that catches concurrent double-submits across
    # uvicorn workers.
    if not survey.get("anonymous"):
        response["_user_dedup"] = user["user_id"]
    try:
        await db.survey_responses.insert_one(response)
    except Exception as e:
        # Iter 250 — partial unique index catches the race-condition double-submit.
        msg = str(e).lower()
        if "duplicate" in msg or "e11000" in msg or "11000" in msg:
            raise HTTPException(status_code=400, detail="Bereits teilgenommen")
        raise
    response.pop("_id", None)
    return response


@router.get("/surveys/{survey_id}/results")
async def get_survey_results(survey_id: str, request: Request):
    from services.audience_guards import assert_can_view_survey, has_responded_to_survey
    user = await get_current_user(request)
    survey = await assert_can_view_survey(user, survey_id)
    # Only editors (admin/moderator/owner) OR participants who already responded
    # may see aggregated results — keeps individual answers private from spectators.
    is_editor = (
        user.get("role") in ("admin", "moderator")
        or survey.get("created_by") == user.get("user_id")
    )
    if not is_editor:
        if not await has_responded_to_survey(user["user_id"], survey_id):
            raise HTTPException(status_code=403, detail="Erst nach Teilnahme einsehbar")
    responses = await db.survey_responses.find({"survey_id": survey_id}, {"_id": 0}).to_list(5000)
    total = len(responses)
    # Aggregate results per question
    results = {}
    for q in survey.get("questions", []):
        qid = q["question_id"]
        qtype = q.get("type", "free_text")
        results[qid] = {"question": q["text"], "type": qtype, "total": total, "answers": {}}
        if qtype in ("single_choice", "multiple_choice"):
            for opt in q.get("options", []):
                results[qid]["answers"][opt] = 0
            for r in responses:
                ans = r.get("answers", {}).get(qid)
                if isinstance(ans, list):
                    for a in ans:
                        results[qid]["answers"][a] = results[qid]["answers"].get(a, 0) + 1
                elif ans:
                    results[qid]["answers"][ans] = results[qid]["answers"].get(ans, 0) + 1
        elif qtype == "scale":
            values = []
            for r in responses:
                ans = r.get("answers", {}).get(qid)
                if ans is not None:
                    try:
                        values.append(float(ans))
                    except (ValueError, TypeError):
                        pass
            results[qid]["values"] = values
            results[qid]["average"] = round(sum(values) / len(values), 1) if values else 0
        elif qtype == "free_text":
            texts = []
            from routes.attachments import fetch_attachments_meta
            for r in responses:
                ans = r.get("answers", {}).get(qid)
                att_ids = (r.get("attachment_map") or {}).get(qid) or []
                att_meta = await fetch_attachments_meta(att_ids) if att_ids else []
                if ans or att_meta:
                    texts.append({"text": ans or "", "user": r.get("user_name", "Anonym"), "attachments": att_meta})
            results[qid]["texts"] = texts
    return {"survey": survey, "total_responses": total, "results": results}

# ============ PULSE CHECKS ============

@router.get("/pulse-checks")
async def list_pulse_checks(request: Request):
    user = await get_current_user(request)
    return await list_surveys_by_type(user, "pulse_check")

async def list_surveys_by_type(user, stype):
    now_iso = datetime.now(timezone.utc).isoformat()
    query = {
        "survey_type": stype, "status": "published",
        "$and": [
            {"$or": [{"expires_at": None}, {"expires_at": ""}, {"expires_at": {"$gte": now_iso}}]},
            {"$or": _survey_audience_or(user)},
        ],
    }
    surveys = await db.surveys.find(query, {"_id": 0}).sort("created_at", -1).to_list(50)
    for s in surveys:
        resp = await db.survey_responses.find_one({"survey_id": s["survey_id"], "user_id": user["user_id"]})
        s["participated"] = resp is not None
        s["response_count"] = await db.survey_responses.count_documents({"survey_id": s["survey_id"]})
    return surveys

# ============ ANONYMOUS FEEDBACK ============

@router.get("/feedback-forms")
async def list_feedback_forms(request: Request):
    user = await get_current_user(request)
    return await list_surveys_by_type(user, "feedback_form")

@router.post("/feedback/submit")
async def submit_anonymous_feedback(request: Request):
    """Submit feedback. If the body has `anonymous: false`, the submitter's
    user_id + name are stored so the user can view their own feedback under
    Profil → Mein Feedback. Default = anonymous for backward compatibility.

    Anonymous submissions receive a unique `tracking_code` the user can store
    and later use with `POST /feedback/track` to check admin replies — without
    exposing their identity in the DB."""
    user = await get_current_user(request)
    from services.rate_limit import enforce_rate_limit
    await enforce_rate_limit(request, key="feedback.submit", limit=5, window_sec=300,
                             per_user_id=user["user_id"])
    body = await request.json()
    feedback_id = f"fb_{uuid.uuid4().hex[:10]}"
    category = body.get("category", "general")  # ideas, complaints, improvements, questions
    is_anonymous = bool(body.get("anonymous", True))
    feedback = {
        "feedback_id": feedback_id,
        "category": category,
        "subject": body.get("subject", ""),
        "content": body.get("content", ""),
        "anonymous": is_anonymous,
        "status": "new",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if not is_anonymous:
        feedback["user_id"] = user["user_id"]
        feedback["user_name"] = user.get("name", "")
    else:
        # Short (11 chars), prefixed, URL-safe tracking code. NOT linked to the
        # user — if the user loses it, the feedback truly stays anonymous.
        # Length chosen to stay readable (e.g. "FB-7K2N9X4M1P").
        import secrets
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/l
        code = "FB-" + "".join(secrets.choice(alphabet) for _ in range(11))
        feedback["tracking_code"] = code
    await db.feedback_entries.insert_one(feedback)
    feedback.pop("_id", None)
    return feedback


@router.post("/feedback/track")
async def track_anonymous_feedback(request: Request):
    """Look up an anonymous feedback by its tracking code. Returns status +
    admin reply, NOT the original content (caller already knows it) and never
    any user identifier (even if something was stored — defensive projection).

    Rate-limited to protect against code-guessing."""
    user = await get_current_user(request)
    from services.rate_limit import enforce_rate_limit
    await enforce_rate_limit(request, key="feedback.track", limit=20, window_sec=300,
                             per_user_id=user["user_id"])
    body = await request.json()
    code = (body.get("tracking_code") or "").strip().upper()
    if not code or len(code) < 5 or len(code) > 64:
        raise HTTPException(status_code=400, detail="Invalid tracking code")
    fb = await db.feedback_entries.find_one(
        {"tracking_code": code, "anonymous": True},
        {"_id": 0, "user_id": 0, "user_name": 0},
    )
    if not fb:
        raise HTTPException(status_code=404, detail="Keine Rückmeldung unter diesem Code")
    return {
        "tracking_code": fb.get("tracking_code"),
        "subject": fb.get("subject", ""),
        "category": fb.get("category"),
        "status": fb.get("status"),
        "created_at": fb.get("created_at"),
        "admin_response": fb.get("admin_response") or None,
        "responded_by": fb.get("responded_by") or None,
        "responded_at": fb.get("responded_at") or None,
    }


@router.get("/feedback/my")
async def list_my_feedback(request: Request):
    """Return non-anonymous feedback submitted by the current user.
    Anonymous submissions are intentionally not tracked back to the user."""
    user = await get_current_user(request)
    entries = await db.feedback_entries.find(
        {"user_id": user["user_id"], "anonymous": False}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return entries

@router.get("/feedback/entries")
async def list_feedback_entries(request: Request, category: Optional[str] = None, status: Optional[str] = None):
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    query = {}
    if category:
        query["category"] = category
    if status:
        query["status"] = status
    entries = await db.feedback_entries.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return entries

@router.put("/feedback/entries/{feedback_id}")
async def update_feedback_status(feedback_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    body = await request.json()
    updates = {}
    if "status" in body:
        updates["status"] = body["status"]
    response_added = False
    if "response" in body:
        updates["admin_response"] = body["response"]
        updates["responded_by"] = user.get("name", "")
        updates["responded_at"] = datetime.now(timezone.utc).isoformat()
        response_added = True
    if updates:
        await db.feedback_entries.update_one({"feedback_id": feedback_id}, {"$set": updates})
    fb = await db.feedback_entries.find_one({"feedback_id": feedback_id}, {"_id": 0})
    # iter 166: notify signed submitters when admin replies (anonymous feedback
    # intentionally cannot be notified back)
    if response_added and fb and fb.get("anonymous") is False and fb.get("user_id"):
        target_uid = fb["user_id"]
        subject = fb.get("subject") or "Feedback"
        try:
            await db.notifications.insert_one({
                "notification_id": f"notif_{uuid.uuid4().hex[:10]}",
                "user_id": target_uid,
                "type": "feedback_reply",
                "title": f"{user.get('name', 'Admin')} hat auf dein Feedback geantwortet",
                "body": (body.get("response") or "")[:120],
                "feedback_id": feedback_id,
                "subject": subject,
                "from_user_id": user["user_id"],
                "read": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "link": "/profile#my-feedback",
            })
        except Exception as e:
            logger.warning(f"feedback notification insert failed: {e}")
        try:
            from services.news_push import send_push_to_user
            await send_push_to_user(
                target_uid,
                title="💬 Antwort auf dein Feedback",
                body=f'"{subject}" wurde von {user.get("name", "Admin")} beantwortet',
                data={
                    "type": "feedback_reply",
                    "feedback_id": feedback_id,
                    "url": "/profile#my-feedback",
                    "tag": f"feedback-{feedback_id}",
                },
                category="feedback",
            )
        except Exception as e:
            logger.warning(f"feedback push failed: {e}")
    return fb

# ============ INTERACTION DASHBOARD ============

@router.get("/interaction-stats")
async def get_interaction_stats(request: Request):
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    # News stats
    total_posts = await db.news_posts.count_documents({"status": "published"})
    total_comments = await db.news_comments.count_documents({"deleted": {"$ne": True}})
    total_reactions = await db.news_reactions.count_documents({})
    total_reads = await db.news_reads.count_documents({})
    # Survey stats
    total_surveys = await db.surveys.count_documents({"status": "published"})
    total_responses = await db.survey_responses.count_documents({})
    # Feedback stats
    total_feedback = await db.feedback_entries.count_documents({})
    new_feedback = await db.feedback_entries.count_documents({"status": "new"})
    # Approval queue
    pending_review = await db.news_posts.count_documents({"status": {"$in": ["review", "approval"]}})
    return {
        "news": {"posts": total_posts, "comments": total_comments, "reactions": total_reactions, "reads": total_reads},
        "surveys": {"total": total_surveys, "responses": total_responses},
        "feedback": {"total": total_feedback, "new": new_feedback},
        "approval_queue": pending_review,
    }


# ============ EXPORT FUNCTIONS ============

@router.get("/surveys/{survey_id}/export")
async def export_survey_results(survey_id: str, request: Request):
    """Export survey results as CSV."""
    from fastapi.responses import StreamingResponse
    import csv
    import io
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    survey = await db.surveys.find_one({"survey_id": survey_id}, {"_id": 0})
    if not survey:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    responses = await db.survey_responses.find({"survey_id": survey_id}, {"_id": 0}).to_list(5000)
    questions = survey.get("questions", [])
    output = io.StringIO()
    writer = csv.writer(output)
    header = ["Teilnehmer", "Zeitpunkt"] + [q["text"] for q in questions]
    writer.writerow(header)
    for r in responses:
        row = [r.get("user_name", "Anonym"), r.get("created_at", "")]
        for q in questions:
            ans = r.get("answers", {}).get(q["question_id"], "")
            if isinstance(ans, list):
                ans = "; ".join(str(a) for a in ans)
            row.append(str(ans))
        writer.writerow(row)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="survey_{survey_id}.csv"'}
    )

@router.get("/feedback/export")
async def export_feedback(request: Request):
    """Export all feedback as CSV."""
    from fastapi.responses import StreamingResponse
    import csv
    import io
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    entries = await db.feedback_entries.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Kategorie", "Betreff", "Inhalt", "Status", "Antwort", "Erstellt"])
    for e in entries:
        writer.writerow([e.get("feedback_id"), e.get("category"), e.get("subject"), e.get("content"), e.get("status"), e.get("admin_response", ""), e.get("created_at")])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="feedback_export.csv"'}
    )
