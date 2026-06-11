"""
News/comment sentiment analysis helpers — extracted from routes/news.py.
Uses the Emergent LLM Key for GPT-based classification with a safe fallback.
Optionally folds in extracted text from file attachments (PDF/TXT etc.).
"""
from __future__ import annotations

import os
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def _parse_json_payload(raw: str) -> List[Dict[str, Any]]:
    """Strip common markdown fences and parse the JSON list an LLM returned."""
    t = (raw or "").strip()
    if t.startswith("```"):
        t = t.split("```")[1].strip()
        if t.startswith("json"):
            t = t[4:].strip()
    return json.loads(t)


def _fallback_neutral(n: int, with_keywords: bool = False) -> List[Dict[str, Any]]:
    out = []
    for i in range(n):
        entry = {"index": i + 1, "sentiment": "neutral", "score": 0.5}
        if with_keywords:
            entry["keywords"] = []
        out.append(entry)
    return out


async def classify_sentiment(texts: List[str], *, with_keywords: bool = False,
                             max_items: int = 30) -> List[Dict[str, Any]]:
    """Return a per-item sentiment classification. Never raises — always returns
    a list of the same length as ``texts`` (padded with neutral on failure)."""
    if not texts:
        return []
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        api_key = os.environ.get("EMERGENT_LLM_KEY", "")
        chat = LlmChat(
            api_key=api_key,
            session_id=f"sentiment_{os.urandom(4).hex()}",
            system_message="Du bist ein Experte für Sentiment-Analyse. Antworte ausschliesslich mit einem JSON-Array wie vorgegeben."
        )
        chat.with_model("openai", "gpt-5.2")
        sample = texts[:max_items]
        combined = "\n---\n".join([f"[{i+1}] {t}" for i, t in enumerate(sample)])
        keyword_hint = ', "keywords": ["keyword1"]' if with_keywords else ""
        prompt = (
            f"Analysiere die Stimmung der folgenden Texte. Antworte NUR als JSON-Array mit Objekten: "
            f'[{{"index": 1, "sentiment": "positive|neutral|negative", "score": 0.0-1.0{keyword_hint}}}]\n\n'
            f"Texte:\n{combined}"
        )
        response_text = await chat.send_message(UserMessage(text=prompt))
        try:
            results = _parse_json_payload(response_text)
        except Exception:
            results = _fallback_neutral(len(texts), with_keywords)
        if not isinstance(results, list):
            results = _fallback_neutral(len(texts), with_keywords)
        # Pad / trim to match input length
        if len(results) < len(texts):
            results = list(results) + _fallback_neutral(len(texts) - len(results), with_keywords)
        return results[:len(texts)]
    except Exception as e:
        logger.error(f"Sentiment classification failed: {e}")
        return _fallback_neutral(len(texts), with_keywords)


async def enrich_texts_with_attachments(texts: List[str],
                                        attachments_per_text: Optional[List[List[str]]]) -> List[str]:
    """For each text, append extracted excerpts from its attachments (PDF/TXT)."""
    if not attachments_per_text:
        return list(texts)
    from services.attachment_text import enrich_with_attachment_text
    enriched = []
    for i, t in enumerate(texts):
        aids = attachments_per_text[i] if i < len(attachments_per_text) else []
        enriched.append(await enrich_with_attachment_text(t, aids or []))
    return enriched


def summarize_counts(results: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {"positive": 0, "neutral": 0, "negative": 0}
    for r in results:
        s = r.get("sentiment", "neutral")
        summary[s] = summary.get(s, 0) + 1
    return summary
