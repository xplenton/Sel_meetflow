"""
Advanced CSV + PDF exports for surveys and interactions.
PDFs use reportlab with matplotlib charts embedded.
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
import csv
import io
from datetime import datetime, timezone
from collections import Counter

# Configure matplotlib for headless PDF generation
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
)

from dependencies import get_current_user
from database import db

router = APIRouter()


def _require_editor(user):
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")


async def _user_dimensions(user_ids):
    """Fetch department/location/profession for the given users."""
    if not user_ids:
        return {}
    docs = await db.users.find(
        {"user_id": {"$in": list(user_ids)}},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1,
         "department": 1, "location": 1, "profession": 1, "role": 1},
    ).to_list(len(user_ids))
    return {d["user_id"]: d for d in docs}


def _chart_to_image(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _bar_chart(labels, values, title):
    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    colors_list = ["#4A5D4E", "#6B8E23", "#D4A373", "#C87967", "#9CA3AF",
                   "#8B9E4E", "#A87C5A", "#6B4E30"] * 5
    bars = ax.bar(range(len(labels)), values, color=colors_list[:len(labels)])
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels([str(lbl)[:18] for lbl in labels], rotation=25, ha="right", fontsize=8)
    ax.set_title(title, fontsize=10, loc="left", color="#1C1F1D")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="y", labelsize=7)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), str(v),
                ha="center", va="bottom", fontsize=7, color="#1C1F1D")
    fig.tight_layout()
    return _chart_to_image(fig)


def _pie_chart(labels, values, title):
    fig, ax = plt.subplots(figsize=(5.2, 3.2))
    colors_list = ["#4A5D4E", "#6B8E23", "#D4A373", "#C87967", "#9CA3AF"] * 5
    ax.pie(values, labels=[str(lbl)[:16] for lbl in labels], autopct="%1.0f%%",
           colors=colors_list[:len(labels)], textprops={"fontsize": 8})
    ax.set_title(title, fontsize=10, loc="left", color="#1C1F1D")
    fig.tight_layout()
    return _chart_to_image(fig)


def _base_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="H1Green", parent=styles["Heading1"],
                              textColor=colors.HexColor("#4A5D4E"), spaceAfter=8, fontSize=20))
    styles.add(ParagraphStyle(name="H2Green", parent=styles["Heading2"],
                              textColor=colors.HexColor("#4A5D4E"), spaceBefore=14, spaceAfter=6, fontSize=13))
    styles.add(ParagraphStyle(name="Meta", parent=styles["BodyText"],
                              textColor=colors.HexColor("#9CA3AF"), fontSize=9, spaceAfter=10))
    styles.add(ParagraphStyle(name="Cell", parent=styles["BodyText"], fontSize=9, leading=11))
    return styles


# ============ SURVEY EXPORTS ============

@router.get("/exports/surveys/{survey_id}/csv")
async def export_survey_extended_csv(survey_id: str, request: Request):
    """Extended CSV with demographics (department/location/profession) per respondent."""
    user = await get_current_user(request)
    _require_editor(user)
    survey = await db.surveys.find_one({"survey_id": survey_id}, {"_id": 0})
    if not survey:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    responses = await db.survey_responses.find({"survey_id": survey_id}, {"_id": 0}).to_list(10000)
    questions = survey.get("questions", [])

    user_ids = {r.get("user_id") for r in responses if r.get("user_id") and r.get("user_id") != "anonymous"}
    dims = await _user_dimensions(user_ids)

    output = io.StringIO()
    writer = csv.writer(output)
    header = ["Teilnehmer", "E-Mail", "Abteilung", "Standort", "Berufsgruppe", "Rolle", "Zeitpunkt"] + [q["text"] for q in questions]
    writer.writerow(header)

    # Iter 379 — Rollen-IDs in deutsche Bezeichner ueberfuehren fuer CSV-Export.
    ROLE_DE = {"admin": "Admin", "moderator": "Moderator", "member": "Mitarbeiter", "guest": "Gast"}

    for r in responses:
        uid = r.get("user_id")
        d = dims.get(uid, {}) if uid and uid != "anonymous" else {}
        row = [
            r.get("user_name", "Anonym"),
            d.get("email", ""),
            d.get("department", ""),
            d.get("location", ""),
            d.get("profession", ""),
            ROLE_DE.get(d.get("role", ""), d.get("role", "")),
            r.get("created_at", ""),
        ]
        for q in questions:
            ans = r.get("answers", {}).get(q["question_id"], "")
            if isinstance(ans, list):
                ans = "; ".join(str(a) for a in ans)
            row.append(str(ans))
        writer.writerow(row)

    output.seek(0)
    fname = f"survey_{survey_id}_extended.csv"
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


async def build_survey_pdf_bytes(survey_id: str) -> bytes:
    """Iter 253 — Reusable PDF builder, callable from both the sync endpoint
    and the arq background task. Returns the raw PDF bytes (caller decides
    how to deliver: StreamingResponse, GridFS, etc.).
    """
    survey = await db.surveys.find_one({"survey_id": survey_id}, {"_id": 0})
    if not survey:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    responses = await db.survey_responses.find({"survey_id": survey_id}, {"_id": 0}).to_list(10000)
    questions = survey.get("questions", [])
    total = len(responses)

    user_ids = {r.get("user_id") for r in responses if r.get("user_id") and r.get("user_id") != "anonymous"}
    dims = await _user_dimensions(user_ids)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.4 * cm, bottomMargin=1.2 * cm)
    styles = _base_styles()
    story = []

    story.append(Paragraph(survey.get("title", "Umfrage"), styles["H1Green"]))
    if survey.get("description"):
        story.append(Paragraph(survey["description"], styles["BodyText"]))
    story.append(Paragraph(
        f"Typ: {survey.get('type', 'survey')} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Teilnahmen: <b>{total}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Status: {survey.get('status', '-')} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Erstellt: {datetime.now(timezone.utc).strftime('%d.%m.%Y')}",
        styles["Meta"]))

    # Demographic breakdown
    dept_counter = Counter()
    loc_counter = Counter()
    prof_counter = Counter()
    for r in responses:
        uid = r.get("user_id")
        if uid and uid != "anonymous":
            d = dims.get(uid, {})
            if d.get("department"): dept_counter[d["department"]] += 1
            if d.get("location"): loc_counter[d["location"]] += 1
            if d.get("profession"): prof_counter[d["profession"]] += 1

    if dept_counter or loc_counter or prof_counter:
        story.append(Paragraph("Demografie der Teilnehmer", styles["H2Green"]))
        for counter, label in [(dept_counter, "Abteilung"),
                               (loc_counter, "Standort"),
                               (prof_counter, "Berufsgruppe")]:
            if not counter:
                continue
            top = counter.most_common(8)
            img = _bar_chart([k for k, _ in top], [v for _, v in top], f"Verteilung: {label}")
            story.append(Image(img, width=16 * cm, height=7 * cm))
            story.append(Spacer(1, 4))

    # Per-question analysis
    story.append(PageBreak())
    story.append(Paragraph("Auswertung nach Frage", styles["H2Green"]))

    for idx, q in enumerate(questions, 1):
        qid = q["question_id"]
        qtext = q.get("text", "")
        qtype = q.get("type", "free_text")
        story.append(Paragraph(f"{idx}. {qtext} <font color='#9CA3AF'>({qtype})</font>", styles["H2Green"]))

        if qtype in ("single_choice", "multiple_choice"):
            counts = Counter()
            for opt in q.get("options", []):
                counts[opt] = 0
            for r in responses:
                ans = r.get("answers", {}).get(qid)
                if isinstance(ans, list):
                    for a in ans:
                        counts[a] += 1
                elif ans:
                    counts[ans] += 1
            items = list(counts.items())
            if items:
                img = _bar_chart([k for k, _ in items], [v for _, v in items], "Antwortverteilung")
                story.append(Image(img, width=16 * cm, height=7 * cm))

        elif qtype == "scale":
            values = []
            for r in responses:
                ans = r.get("answers", {}).get(qid)
                try:
                    if ans is not None:
                        values.append(float(ans))
                except (ValueError, TypeError):
                    pass
            if values:
                avg = sum(values) / len(values)
                bins = Counter(int(v) for v in values)
                sorted_bins = sorted(bins.items())
                img = _bar_chart([str(k) for k, _ in sorted_bins],
                                 [v for _, v in sorted_bins],
                                 f"Verteilung (Durchschnitt: {avg:.1f})")
                story.append(Image(img, width=16 * cm, height=7 * cm))

        elif qtype == "free_text":
            texts = [r.get("answers", {}).get(qid) for r in responses]
            texts = [t for t in texts if t]
            if texts:
                rows = [[Paragraph(str(t)[:300], styles["Cell"])] for t in texts[:25]]
                table = Table(rows, colWidths=[16 * cm])
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F4F1")),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E4E0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]))
                story.append(table)
                if len(texts) > 25:
                    story.append(Paragraph(f"... und {len(texts) - 25} weitere Antworten", styles["Meta"]))
            else:
                story.append(Paragraph("Keine Freitext-Antworten", styles["Meta"]))

        story.append(Spacer(1, 8))

    doc.build(story)
    return buf.getvalue()


@router.get("/exports/surveys/{survey_id}/pdf")
async def export_survey_pdf(survey_id: str, request: Request):
    """PDF report with charts + demographic breakdown."""
    user = await get_current_user(request)
    _require_editor(user)
    pdf_bytes = await build_survey_pdf_bytes(survey_id)
    fname = f"survey_{survey_id}_report.pdf"
    return StreamingResponse(iter([pdf_bytes]), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.post("/exports/surveys/{survey_id}/pdf/async")
async def export_survey_pdf_async(survey_id: str, request: Request):
    """Iter 253 Phase 3 — enqueue PDF build as background job.
    Returns {job_id}. Poll GET /api/jobs/{job_id} until complete; result
    contains a download URL for /api/exports/surveys/jobs/{job_id}/pdf.
    """
    user = await get_current_user(request)
    _require_editor(user)
    survey = await db.surveys.find_one({"survey_id": survey_id}, {"_id": 0, "survey_id": 1})
    if not survey:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    from services.background_queue import enqueue
    job = await enqueue("build_survey_pdf", survey_id)
    job_id = getattr(job, "job_id", None) or "inline"
    return {"job_id": job_id, "survey_id": survey_id, "status": "queued",
            "download_url": f"/api/exports/surveys/jobs/{job_id}/pdf"}


@router.get("/exports/surveys/jobs/{job_id}/pdf")
async def download_survey_pdf_job(job_id: str, request: Request):
    """Download the PDF produced by a previously-enqueued build_survey_pdf job.
    Returns 202 if still processing, 200 + PDF when complete, 404 if expired."""
    user = await get_current_user(request)
    _require_editor(user)
    from services.background_queue import _get_pool, ENABLED
    if not ENABLED:
        raise HTTPException(404, "Background queue disabled — use /pdf instead")
    pool = await _get_pool()
    from arq.jobs import Job
    job = Job(job_id, pool)
    status = await job.status()
    status_str = status.value if hasattr(status, "value") else str(status)
    if status_str not in ("complete",):
        raise HTTPException(202, f"Job not ready (status={status_str})")
    pdf_bytes = await job.result(timeout=1)
    if not isinstance(pdf_bytes, (bytes, bytearray)):
        raise HTTPException(500, "Job did not produce a PDF")
    return StreamingResponse(iter([pdf_bytes]), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="survey_{job_id}.pdf"'})


# ============ INTERACTIONS DASHBOARD EXPORTS ============

async def _collect_interaction_stats():
    """Reuse core metrics that power the admin Interactions dashboard."""
    total_posts = await db.news_posts.count_documents({"status": "published"})
    total_comments = await db.news_comments.count_documents({"deleted": {"$ne": True}})
    total_reactions = await db.news_reactions.count_documents({})
    total_reads_pipeline = [
        {"$group": {"_id": None, "total": {"$sum": 1}}}
    ]
    reads_cursor = db.news_reads.aggregate(total_reads_pipeline)
    total_reads = 0
    async for doc in reads_cursor:
        total_reads = doc["total"]

    open_reports = await db.news_reports.count_documents({"status": "open"})
    mandatory_count = await db.news_posts.count_documents({"mandatory": True, "status": "published"})
    surveys_total = await db.surveys.count_documents({})
    surveys_published = await db.surveys.count_documents({"status": "published"})
    active_users = await db.users.count_documents({"status": {"$ne": "inactive"}})

    # Top engaged posts
    top_posts_agg = [
        {"$match": {"status": "published"}},
        {"$lookup": {"from": "news_comments", "localField": "post_id", "foreignField": "post_id", "as": "cmts"}},
        {"$lookup": {"from": "news_reactions", "localField": "post_id", "foreignField": "post_id", "as": "rxns"}},
        {"$project": {"_id": 0, "post_id": 1, "title": 1,
                      "comments": {"$size": "$cmts"}, "reactions": {"$size": "$rxns"}}},
        {"$addFields": {"engagement": {"$add": ["$comments", "$reactions"]}}},
        {"$sort": {"engagement": -1}}, {"$limit": 10},
    ]
    top_posts = []
    async for doc in db.news_posts.aggregate(top_posts_agg):
        top_posts.append(doc)

    # Popular tags
    tag_agg = [
        {"$match": {"status": "published"}},
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 15},
    ]
    popular_tags = []
    async for doc in db.news_posts.aggregate(tag_agg):
        popular_tags.append({"tag": doc["_id"], "count": doc["count"]})

    return {
        "totals": {
            "posts": total_posts, "comments": total_comments,
            "reactions": total_reactions, "reads": total_reads,
            "open_reports": open_reports, "mandatory": mandatory_count,
            "surveys_total": surveys_total, "surveys_published": surveys_published,
            "active_users": active_users,
        },
        "top_posts": top_posts,
        "popular_tags": popular_tags,
    }


@router.get("/exports/interactions/csv")
async def export_interactions_csv(request: Request):
    user = await get_current_user(request)
    _require_editor(user)
    stats = await _collect_interaction_stats()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Bereich", "Metrik", "Wert"])
    totals = stats["totals"]
    label_map = {
        "posts": "Veroeffentlichte Beitraege",
        "comments": "Kommentare",
        "reactions": "Reaktionen",
        "reads": "Lesebestaetigungen",
        "open_reports": "Offene Meldungen",
        "mandatory": "Pflicht-News",
        "surveys_total": "Umfragen (gesamt)",
        "surveys_published": "Umfragen (veroeffentlicht)",
        "active_users": "Aktive Nutzer",
    }
    for k, v in totals.items():
        writer.writerow(["Kennzahlen", label_map.get(k, k), v])
    writer.writerow([])
    writer.writerow(["Top Beitraege", "Titel", "Kommentare", "Reaktionen", "Engagement"])
    for p in stats["top_posts"]:
        writer.writerow(["", p.get("title", ""), p.get("comments", 0),
                         p.get("reactions", 0), p.get("engagement", 0)])
    writer.writerow([])
    writer.writerow(["Beliebte Tags", "Tag", "Anzahl"])
    for t in stats["popular_tags"]:
        writer.writerow(["", t["tag"], t["count"]])

    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="interactions_report.csv"'})


@router.get("/exports/interactions/pdf")
async def export_interactions_pdf(request: Request):
    user = await get_current_user(request)
    _require_editor(user)
    stats = await _collect_interaction_stats()
    totals = stats["totals"]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.4 * cm, bottomMargin=1.2 * cm)
    styles = _base_styles()
    story = []
    story.append(Paragraph("Interaktionen & Kennzahlen", styles["H1Green"]))
    story.append(Paragraph(
        f"Zeitpunkt: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')}",
        styles["Meta"]))

    # Kennzahlen table
    kpi_rows = [
        ["Veroeffentlichte Beitraege", totals["posts"]],
        ["Kommentare", totals["comments"]],
        ["Reaktionen", totals["reactions"]],
        ["Lesebestaetigungen", totals["reads"]],
        ["Offene Meldungen", totals["open_reports"]],
        ["Pflicht-News", totals["mandatory"]],
        ["Umfragen (veroeffentlicht / gesamt)", f"{totals['surveys_published']} / {totals['surveys_total']}"],
        ["Aktive Nutzer", totals["active_users"]],
    ]
    t = Table(kpi_rows, colWidths=[10 * cm, 6 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F9F9F8")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E4E0")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#4A5D4E")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))

    # Engagement chart
    if stats["top_posts"]:
        story.append(Paragraph("Top Beitraege nach Engagement", styles["H2Green"]))
        tp = stats["top_posts"][:8]
        img = _bar_chart([p["title"][:22] for p in tp],
                         [p["engagement"] for p in tp],
                         "Kommentare + Reaktionen")
        story.append(Image(img, width=16 * cm, height=7 * cm))

    # Tags chart
    if stats["popular_tags"]:
        story.append(Paragraph("Beliebte Tags", styles["H2Green"]))
        pt = stats["popular_tags"][:10]
        img = _bar_chart([t["tag"] for t in pt], [t["count"] for t in pt], "Tag-Haeufigkeit")
        story.append(Image(img, width=16 * cm, height=7 * cm))

    doc.build(story)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="application/pdf",
                             headers={"Content-Disposition": 'attachment; filename="interactions_report.pdf"'})
