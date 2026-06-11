"""
Extract readable text snippets from GridFS attachments (PDF / plain text / CSV / markdown).
Used by sentiment analysis so that uploaded documents are factored in alongside the
regular comment text.
"""
from typing import List, Dict
import io
import logging

from database import db

logger = logging.getLogger(__name__)

# Hard cap per-attachment to keep LLM prompts safe
MAX_CHARS_PER_ATTACHMENT = 2000
# Hard cap total combined across all attachments of one item
MAX_TOTAL_CHARS = 6000

_TEXT_MIMES = {
    "text/plain", "text/csv", "text/markdown", "text/html",
    "application/json", "application/xml",
}


async def _download_bytes(attachment_id: str) -> bytes:
    from motor.motor_asyncio import AsyncIOMotorGridFSBucket
    bucket = AsyncIOMotorGridFSBucket(db, bucket_name="attachments")
    try:
        gridout = await bucket.open_download_stream(attachment_id)
    except Exception:
        return b""
    chunks: List[bytes] = []
    total = 0
    while True:
        chunk = await gridout.readchunk()
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        # Don't bother downloading more than 5 MB per attachment for text extraction
        if total > 5 * 1024 * 1024:
            break
    return b"".join(chunks)


def _extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        parts: List[str] = []
        for page in reader.pages[:30]:  # Cap: first 30 pages
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(parts).strip()
    except Exception as e:
        logger.warning(f"PDF extraction failed: {e}")
        return ""


def _extract_plain_text(data: bytes) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return data.decode(enc, errors="ignore")
        except Exception:
            continue
    return ""


async def extract_attachment_text(attachment_id: str) -> str:
    """Return extracted plaintext from a single attachment, or "" if unsupported."""
    doc = await db["attachments.files"].find_one(
        {"_id": attachment_id}, {"filename": 1, "metadata": 1}
    )
    if not doc:
        return ""
    meta = doc.get("metadata", {}) or {}
    mime = (meta.get("mime") or "").lower()
    data = await _download_bytes(attachment_id)
    if not data:
        return ""
    text = ""
    if mime == "application/pdf":
        text = _extract_pdf_text(data)
    elif mime in _TEXT_MIMES:
        text = _extract_plain_text(data)
    else:
        return ""
    return text[:MAX_CHARS_PER_ATTACHMENT].strip()


async def extract_texts_for_attachments(attachment_ids: List[str]) -> Dict[str, str]:
    """Extract text for multiple attachments. Returns {attachment_id: text}."""
    out: Dict[str, str] = {}
    total = 0
    for aid in attachment_ids or []:
        if total >= MAX_TOTAL_CHARS:
            break
        try:
            t = await extract_attachment_text(aid)
        except Exception as e:
            logger.warning(f"Attachment extract failed {aid}: {e}")
            t = ""
        if t:
            out[aid] = t
            total += len(t)
    return out


async def enrich_with_attachment_text(comment_text: str, attachment_ids: List[str]) -> str:
    """Return a combined string: the comment content plus brief excerpts from its
    text-bearing attachments, formatted for inclusion in a sentiment-analysis prompt."""
    base = (comment_text or "").strip()
    if not attachment_ids:
        return base
    texts = await extract_texts_for_attachments(attachment_ids)
    if not texts:
        return base
    excerpts = []
    for aid, t in texts.items():
        snippet = t[:800].replace("\n", " ").strip()
        if snippet:
            excerpts.append(f"[Anhang-Auszug] {snippet}")
    if not excerpts:
        return base
    joined = "\n".join(excerpts)
    return f"{base}\n{joined}" if base else joined
