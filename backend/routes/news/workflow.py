from fastapi import APIRouter, Request, HTTPException
from typing import List, Dict, Any
from datetime import datetime, timezone
from database import db
from dependencies import get_current_user
import uuid

from ._helpers import _can_review, _can_approve

router = APIRouter()


@router.post("/news/posts/{post_id}/submit-review")
async def submit_for_review(post_id: str, request: Request):
    """Autor submits draft for review by Redakteur."""
    from services.news_workflow import submit_for_review as _submit
    user = await get_current_user(request)
    return await _submit(post_id, user)

@router.post("/news/posts/{post_id}/approve-review")
async def approve_review(post_id: str, request: Request):
    """Redakteur approves and forwards to Freigeber, or Admin/Freigeber publishes directly."""
    from services.news_workflow import approve_review as _approve
    user = await get_current_user(request)
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    comment = body.get("comment", "") if isinstance(body, dict) else ""
    return await _approve(post_id, user, comment=comment)

@router.post("/news/posts/{post_id}/reject")
async def reject_post(post_id: str, request: Request):
    """Redakteur/Freigeber rejects a post back to draft."""
    from services.news_workflow import reject_post as _reject
    user = await get_current_user(request)
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    reason = body.get("reason", "") if isinstance(body, dict) else ""
    return await _reject(post_id, user, reason=reason)

@router.get("/news/approval-queue")
async def get_approval_queue(request: Request):
    """Get posts pending review/approval."""
    user = await get_current_user(request)
    if not await _can_review(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    query = {}
    if await _can_approve(user):
        query["status"] = {"$in": ["review", "approval"]}
    else:
        query["status"] = "review"
    posts = await db.news_posts.find(query, {"_id": 0}).sort("updated_at", -1).to_list(100)
    return posts

@router.get("/news/interaction-stats")
async def interaction_stats(request: Request):
    """Aggregated interaction KPIs for the moderation/admin dashboard.

    Returns counts for comments, reactions, unique reactors, mandatory reads,
    Q&A, reports, and the top engaged posts.
    """
    user = await get_current_user(request)
    if not await _can_review(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")

    total_posts = await db.news_posts.count_documents({"status": "published"})
    total_comments = await db.news_comments.count_documents({"deleted": {"$ne": True}})
    total_reactions = await db.news_reactions.count_documents({})
    total_unique_reactors = len(await db.news_reactions.distinct("user_id"))
    total_reports = await db.news_reports.count_documents({})
    open_reports = await db.news_reports.count_documents({"status": "pending"})

    # Mandatory reads
    mandatory_posts = await db.news_posts.find(
        {"is_mandatory": True, "status": "published"}, {"_id": 0, "post_id": 1, "title": 1}
    ).to_list(200)
    total_active_users = await db.users.count_documents({"status": {"$ne": "inactive"}})
    mandatory_stats = []
    for p in mandatory_posts:
        read_count = await db.news_reads.count_documents({"post_id": p["post_id"]})
        rate = round((read_count / total_active_users) * 100, 1) if total_active_users else 0
        mandatory_stats.append({
            "post_id": p["post_id"], "title": p["title"],
            "read_count": read_count, "total_users": total_active_users, "rate": rate,
        })

    # Q&A
    total_questions = await db.news_questions.count_documents({})
    answered_questions = await db.news_questions.count_documents({"answer": {"$nin": [None, ""]}})

    # Top engaged posts (by comments + reactions)
    pipeline = [
        {"$match": {"status": "published"}},
        {"$project": {
            "_id": 0, "post_id": 1, "title": 1, "published_at": 1,
            "comment_count": {"$ifNull": ["$comment_count", 0]},
            "reaction_count": {"$add": [
                {"$ifNull": ["$reaction_counts.like", 0]},
                {"$ifNull": ["$reaction_counts.agree", 0]},
                {"$ifNull": ["$reaction_counts.helpful", 0]},
            ]},
        }},
        {"$addFields": {"engagement": {"$add": ["$comment_count", "$reaction_count"]}}},
        {"$sort": {"engagement": -1}},
        {"$limit": 5},
    ]
    top_posts = await db.news_posts.aggregate(pipeline).to_list(5)

    # Survey participation
    survey_total = await db.surveys.count_documents({"status": "published"})
    survey_responses = await db.survey_responses.count_documents({})
    survey_rate = round((survey_responses / (survey_total * total_active_users)) * 100, 1) if survey_total and total_active_users else 0

    # Tags popularity (top 10)
    tag_pipeline = [
        {"$match": {"status": "published"}},
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    tag_rows = await db.news_posts.aggregate(tag_pipeline).to_list(10)
    popular_tags = [{"tag": r["_id"], "count": r["count"]} for r in tag_rows if r.get("_id")]

    return {
        "posts": {"total": total_posts},
        "comments": {"total": total_comments},
        "reactions": {"total": total_reactions, "unique_users": total_unique_reactors,
                      "rate": round((total_unique_reactors / total_active_users) * 100, 1) if total_active_users else 0},
        "reports": {"total": total_reports, "open": open_reports},
        "mandatory": mandatory_stats,
        "questions": {"total": total_questions, "answered": answered_questions,
                      "answer_rate": round((answered_questions / total_questions) * 100, 1) if total_questions else 0},
        "surveys": {"published": survey_total, "total_responses": survey_responses, "participation_rate": survey_rate},
        "top_posts": top_posts,
        "popular_tags": popular_tags,
        "total_active_users": total_active_users,
    }


@router.get("/news/audit/{post_id}")
async def get_audit_trail(post_id: str, request: Request):
    user = await get_current_user(request)
    if not await _can_review(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    trail = await db.news_audit.find({"post_id": post_id}, {"_id": 0}).sort("timestamp", -1).to_list(100)
    return trail


@router.get("/news/audit")
async def list_all_audit(request: Request, limit: int = 200, user_id: str = "", action: str = ""):
    """Global audit log (admin-only). Filterable by user_id, action."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin erforderlich")
    q = {}
    if user_id: q["user_id"] = user_id
    if action: q["action"] = action
    limit = max(1, min(int(limit), 500))
    trail = await db.news_audit.find(q, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return trail


# ============ PHASE 4: Q&A FUNCTION ============

@router.post("/news/posts/{post_id}/questions")
async def ask_question(post_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Frage erforderlich")
    q_id = f"qa_{uuid.uuid4().hex[:10]}"
    question = {
        "question_id": q_id, "post_id": post_id,
        "user_id": user["user_id"], "user_name": user.get("name", ""),
        "text": text, "answer": None, "answered_by": None, "answered_at": None,
        "upvotes": [], "upvote_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.news_qa.insert_one(question)
    question.pop("_id", None)
    return question

@router.get("/news/posts/{post_id}/questions")
async def get_questions(post_id: str, request: Request):
    user = await get_current_user(request)
    questions = await db.news_qa.find({"post_id": post_id}, {"_id": 0}).sort("upvote_count", -1).to_list(200)
    for q in questions:
        q["user_upvoted"] = user["user_id"] in q.get("upvotes", [])
    return questions

@router.post("/news/questions/{q_id}/upvote")
async def upvote_question(q_id: str, request: Request):
    user = await get_current_user(request)
    q = await db.news_qa.find_one({"question_id": q_id})
    if not q:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    upvotes = q.get("upvotes", [])
    if user["user_id"] in upvotes:
        upvotes.remove(user["user_id"])
    else:
        upvotes.append(user["user_id"])
    await db.news_qa.update_one({"question_id": q_id}, {"$set": {"upvotes": upvotes, "upvote_count": len(upvotes)}})
    return {"upvote_count": len(upvotes), "user_upvoted": user["user_id"] in upvotes}

@router.post("/news/questions/{q_id}/answer")
async def answer_question(q_id: str, request: Request):
    user = await get_current_user(request)
    if not await _can_review(user):
        raise HTTPException(status_code=403, detail="Nur Redakteure können antworten")
    body = await request.json()
    answer = body.get("answer", "").strip()
    if not answer:
        raise HTTPException(status_code=400, detail="Antwort erforderlich")
    await db.news_qa.update_one({"question_id": q_id}, {"$set": {
        "answer": answer, "answered_by": user.get("name", ""), "answered_at": datetime.now(timezone.utc).isoformat()
    }})
    return {"message": "Beantwortet"}

@router.delete("/news/questions/{q_id}")
async def delete_question(q_id: str, request: Request):
    user = await get_current_user(request)
    q = await db.news_qa.find_one({"question_id": q_id})
    if not q:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    if q["user_id"] != user["user_id"] and not await _can_review(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    await db.news_qa.delete_one({"question_id": q_id})
    return {"message": "Gelöscht"}

# ============ PHASE 4: MULTILINGUAL NEWS ============

@router.put("/news/posts/{post_id}/translations")
async def set_translations(post_id: str, request: Request):
    user = await get_current_user(request)
    if not await _can_review(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    body = await request.json()
    translations = {}
    for lang_code in ["de", "en", "fr", "es", "tr"]:
        if lang_code in body:
            translations[lang_code] = {
                "title": body[lang_code].get("title", ""),
                "content": body[lang_code].get("content", ""),
                "excerpt": body[lang_code].get("excerpt", ""),
            }
    await db.news_posts.update_one({"post_id": post_id}, {"$set": {
        "translations": translations, "updated_at": datetime.now(timezone.utc).isoformat()
    }})
    return {"message": "Übersetzungen gespeichert", "languages": list(translations.keys())}

@router.get("/news/posts/{post_id}/localized")
async def get_localized_post(post_id: str, request: Request, lang: str = "de"):
    await get_current_user(request)
    post = await db.news_posts.find_one({"post_id": post_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    translations = post.get("translations", {})
    if lang in translations:
        t = translations[lang]
        if t.get("title"): post["title"] = t["title"]
        if t.get("content"): post["content"] = t["content"]
        if t.get("content"): post["content_html"] = t["content"]
        if t.get("excerpt"): post["excerpt"] = t["excerpt"]
    return post

# ============ PHASE 4: SENTIMENT ANALYSIS ============

@router.post("/news/analyze-sentiment")
async def analyze_sentiment(request: Request):
    user = await get_current_user(request)
    if not await _can_review(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    body = await request.json()
    texts = body.get("texts", [])
    # Optional: list of attachment-id arrays aligned with texts, so PDFs/TXT docs
    # attached to free-text answers are folded into the sentiment signal.
    attachments_per_text = body.get("attachments", [])
    if not texts:
        raise HTTPException(status_code=400, detail="Keine Texte")
    from services.news_sentiment import classify_sentiment, enrich_texts_with_attachments
    texts = await enrich_texts_with_attachments(texts, attachments_per_text)
    results = await classify_sentiment(texts, with_keywords=True, max_items=20)
    return {"results": results}

@router.get("/news/posts/{post_id}/sentiment")
async def get_post_sentiment(post_id: str, request: Request):
    user = await get_current_user(request)
    if not await _can_review(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    comments = await db.news_comments.find(
        {"post_id": post_id, "deleted": {"$ne": True}},
        {"_id": 0, "content": 1, "user_name": 1, "comment_id": 1, "attachments": 1}
    ).to_list(50)
    if not comments:
        return {"post_id": post_id, "comments": 0, "sentiment_summary": {"positive": 0, "neutral": 0, "negative": 0}, "details": []}
    from services.attachment_text import enrich_with_attachment_text
    from services.news_sentiment import classify_sentiment, summarize_counts
    texts: List[str] = []
    attachment_used_map: Dict[str, bool] = {}
    for c in comments:
        att_ids = c.get("attachments") or []
        enriched = await enrich_with_attachment_text(c.get("content", ""), att_ids)
        texts.append(enriched)
        attachment_used_map[c["comment_id"]] = bool(att_ids) and enriched != (c.get("content") or "").strip()
    results = await classify_sentiment(texts, with_keywords=False, max_items=30)
    summary = summarize_counts(results)
    details = []
    for i, c in enumerate(comments):
        r = results[i] if i < len(results) else {"sentiment": "neutral", "score": 0.5}
        details.append({
            "comment_id": c["comment_id"], "user_name": c["user_name"],
            "text": (c.get("content") or "")[:100],
            "sentiment": r.get("sentiment", "neutral"), "score": r.get("score", 0.5),
            "has_attachment_text": attachment_used_map.get(c["comment_id"], False),
        })
    return {"post_id": post_id, "comments": len(comments), "sentiment_summary": summary, "details": details}

# ============ PHASE 4: EXPORT READ RECEIPTS ============

@router.get("/news/posts/{post_id}/reads/export")
async def export_read_receipts(post_id: str, request: Request):
    from fastapi.responses import StreamingResponse
    from services.news_export import read_receipts_csv
    user = await get_current_user(request)
    if not await _can_review(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    reads = await db.news_reads.find({"post_id": post_id}, {"_id": 0}).to_list(5000)
    csv_str = read_receipts_csv(reads)
    return StreamingResponse(
        iter([csv_str]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="reads_{post_id}.csv"'},
    )


@router.get("/news/export/posts")
async def export_posts(request: Request, fmt: str = "csv", status: str = ""):
    """Admin-facing export of all news posts. Supports fmt=csv (default) or fmt=json.
    Optional `status` filter ('published', 'draft', 'review', …)."""
    from fastapi.responses import StreamingResponse
    from services.news_export import posts_export_csv, posts_export_json
    user = await get_current_user(request)
    if not await _can_review(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    posts = await db.news_posts.find(query, {"_id": 0}).sort("created_at", -1).to_list(5000)
    if fmt == "json":
        return StreamingResponse(
            iter([posts_export_json(posts)]),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="news_posts.json"'},
        )
    return StreamingResponse(
        iter([posts_export_csv(posts)]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="news_posts.csv"'},
    )


# ============ REPORT (MELDEN) ============

@router.post("/news/report")
async def report_content(request: Request):
    """Report inappropriate content (comments, posts, Q&A)."""
    user = await get_current_user(request)
    from services.rate_limit import enforce_rate_limit
    await enforce_rate_limit(request, key="news.report", limit=10, window_sec=600,
                             per_user_id=user["user_id"])
    body = await request.json()
    content_type = body.get("content_type", "")  # comment, post, question
    content_id = body.get("content_id", "")
    reason = body.get("reason", "")
    if not content_type or not content_id:
        raise HTTPException(status_code=400, detail="content_type und content_id erforderlich")
    report_id = f"rpt_{uuid.uuid4().hex[:10]}"
    report = {
        "report_id": report_id,
        "content_type": content_type,
        "content_id": content_id,
        "reason": reason,
        "reporter_id": user["user_id"],
        "reporter_name": user.get("name", ""),
        "status": "pending",  # pending, reviewed, dismissed
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.news_reports.insert_one(report)
    report.pop("_id", None)
    return report

@router.get("/news/reports")
async def list_reports(request: Request):
    user = await get_current_user(request)
    if not await _can_review(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    reports = await db.news_reports.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return reports

@router.get("/news/reports/pending-count")
async def pending_reports_count(request: Request):
    user = await get_current_user(request)
    if not await _can_review(user):
        # Non-reviewers just get 0 instead of 403 so sidebar never errors
        return {"count": 0}
    count = await db.news_reports.count_documents({"status": "pending"})
    return {"count": count}

@router.put("/news/reports/{report_id}")
async def update_report(report_id: str, request: Request):
    user = await get_current_user(request)
    if not await _can_review(user):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    body = await request.json()
    status = body.get("status", "reviewed")
    action = body.get("action", "")  # delete_content, warn_user, dismiss
    await db.news_reports.update_one({"report_id": report_id}, {"$set": {
        "status": status, "action": action,
        "reviewed_by": user.get("name", ""), "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }})
    # If action is delete_content, remove the reported content
    if action == "delete_content":
        report = await db.news_reports.find_one({"report_id": report_id}, {"_id": 0})
        if report:
            if report["content_type"] == "comment":
                await db.news_comments.update_one({"comment_id": report["content_id"]}, {"$set": {"deleted": True}})
            elif report["content_type"] == "question":
                await db.news_qa.delete_one({"question_id": report["content_id"]})
    return {"message": "Report aktualisiert"}

# ============ PUSH NOTIFICATIONS ============

