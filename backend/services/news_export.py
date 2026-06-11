"""Small export helpers for news data (read-receipts, posts, audit).

Extracted from routes/news/workflow.py (Iter 94). Returns plain strings /
lists that the route layer wraps in a StreamingResponse.
"""
from __future__ import annotations

import csv
import io
import json
from typing import List, Dict, Any


def read_receipts_csv(reads: List[Dict[str, Any]]) -> str:
    """Render a list of news_read documents as a German CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Benutzer", "Gelesen am"])
    for r in reads:
        writer.writerow([r.get("user_name", ""), r.get("read_at", "")])
    return output.getvalue()


def posts_export_csv(posts: List[Dict[str, Any]]) -> str:
    """Render a list of news_posts documents as CSV (admin-facing export)."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "post_id", "title", "status", "priority", "author", "published_at",
        "created_at", "pinned", "is_mandatory", "categories", "target_all",
    ])
    for p in posts:
        writer.writerow([
            p.get("post_id", ""), p.get("title", ""), p.get("status", ""),
            p.get("priority", ""), p.get("author_name", ""),
            p.get("published_at", ""), p.get("created_at", ""),
            "yes" if p.get("pinned") else "",
            "yes" if p.get("is_mandatory") else "",
            ", ".join(p.get("categories") or []),
            "yes" if p.get("target_all") else "",
        ])
    return output.getvalue()


def posts_export_json(posts: List[Dict[str, Any]]) -> str:
    """Render posts as pretty-printed JSON."""
    return json.dumps(posts, ensure_ascii=False, indent=2, default=str)
