"""News feed query/ranking/enrichment logic.

Extracted from routes/news/posts.py (Iter 88) to keep the route handler thin.
Behaviour is preserved byte-for-byte — this is a pure move + small helper
decomposition, no semantic changes.
"""
from __future__ import annotations

import time as _time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from database import read_db

# Iter 345 (perf) — per-(user, filter) TTL cache for /news/feed.
# Soak (iter 344) showed p95 ~2.1s; the count_documents + find + enrich
# chain is read-heavy and repeats for the same filters from auto-poll.
# 15s TTL keeps "feels live" while removing > 90 % of DB round-trips.
_FEED_CACHE: "dict[str, tuple[float, dict]]" = {}
_FEED_TTL_SECONDS = 15


def build_audience_filter(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the `$or` list that matches posts visible to `user`.

    A post is visible if ANY of:
      - target_all=True
      - no targeting set at all (all target_* arrays empty/missing)
      - one of the user's group/dept/location/profession/role matches
      - the user's user_id appears in target_user_ids (per-user targeting, iter 169)
    """
    user_groups = user.get("groups", [])
    user_dept = user.get("department", "")
    user_loc = user.get("location", "")
    user_prof = user.get("profession", "")
    user_role = user.get("role", "")
    user_id = user.get("user_id", "")

    audience_or: List[Dict[str, Any]] = [
        {"target_all": True},
        {"$and": [
            {"$or": [{"target_groups": {"$size": 0}}, {"target_groups": {"$exists": False}}]},
            {"$or": [{"target_departments": {"$size": 0}}, {"target_departments": {"$exists": False}}]},
            {"$or": [{"target_locations": {"$size": 0}}, {"target_locations": {"$exists": False}}]},
            {"$or": [{"target_professions": {"$size": 0}}, {"target_professions": {"$exists": False}}]},
            {"$or": [{"target_roles": {"$size": 0}}, {"target_roles": {"$exists": False}}]},
            {"$or": [{"target_user_ids": {"$size": 0}}, {"target_user_ids": {"$exists": False}}]},
        ]},
    ]
    if user_groups:
        audience_or.append({"target_groups": {"$in": user_groups}})
    if user_dept:
        audience_or.append({"target_departments": user_dept})
    if user_loc:
        audience_or.append({"target_locations": user_loc})
    if user_prof:
        audience_or.append({"target_professions": user_prof})
    if user_role:
        audience_or.append({"target_roles": user_role})
    if user_id:
        audience_or.append({"target_user_ids": user_id})
    return audience_or


def build_feed_query(user: Dict[str, Any], *,
                     category: Optional[str] = None,
                     priority: Optional[str] = None,
                     search: Optional[str] = None) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    audience_or = build_audience_filter(user)
    query: Dict[str, Any] = {
        "status": "published",
        "$and": [
            {"$or": [{"expires_at": None}, {"expires_at": ""}, {"expires_at": {"$gte": now_iso}}]},
            {"$or": [{"publish_at": None}, {"publish_at": ""}, {"publish_at": {"$lte": now_iso}}]},
            {"$or": audience_or},
        ],
    }
    if category:
        query["categories"] = category
    if priority:
        query["priority"] = priority
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"content": {"$regex": search, "$options": "i"}},
            {"tags": {"$regex": search, "$options": "i"}},
        ]
        # Move the search $or into the $and block so it composes with audience/time filters
        query["$and"].append({"$or": query.pop("$or")})
    return query


def build_sort_spec(sort: str) -> List:
    """Return a list of (field, direction) tuples. Pinned posts always first."""
    sort_field: List = [("pinned", -1)]
    if sort == "priority":
        sort_field.append(("priority_order", -1))
        sort_field.append(("published_at", -1))
    elif sort == "relevance":
        sort_field.append(("is_mandatory", -1))
        sort_field.append(("priority_order", -1))
        sort_field.append(("published_at", -1))
    else:  # "latest" / default
        sort_field.append(("published_at", -1))
    return sort_field


async def enrich_posts(posts: List[Dict[str, Any]], user_id: str) -> None:
    """Mutate `posts` in-place, adding read status + reaction counts + comment count.

    Iter 172 (perf): replaced N*3 round trips with 3 batch queries using `$in`.
    """
    if not posts:
        return
    post_ids = [p["post_id"] for p in posts]
    # 1) Reads for this user, batched
    reads = await read_db.news_reads.find(
        {"post_id": {"$in": post_ids}, "user_id": user_id},
        {"_id": 0, "post_id": 1, "read_at": 1},
    ).to_list(len(post_ids))
    reads_map = {r["post_id"]: r.get("read_at") for r in reads}
    # 2) Reactions: all posts in one fetch
    reactions = await read_db.news_reactions.find(
        {"post_id": {"$in": post_ids}}, {"_id": 0}
    ).to_list(5000)
    reaction_buckets: Dict[str, Dict[str, int]] = {pid: {} for pid in post_ids}
    user_reactions: Dict[str, Any] = {pid: None for pid in post_ids}
    for r in reactions:
        pid = r["post_id"]
        rtype = r["reaction_type"]
        reaction_buckets[pid][rtype] = reaction_buckets[pid].get(rtype, 0) + 1
        if r["user_id"] == user_id:
            user_reactions[pid] = rtype
    # 3) Comment counts via aggregate
    comment_rows = await read_db.news_comments.aggregate([
        {"$match": {"post_id": {"$in": post_ids}, "deleted": {"$ne": True}}},
        {"$group": {"_id": "$post_id", "c": {"$sum": 1}}},
    ]).to_list(len(post_ids))
    comment_map = {c["_id"]: c["c"] for c in comment_rows}
    for post in posts:
        pid = post["post_id"]
        post["is_read"] = pid in reads_map
        post["read_at"] = reads_map.get(pid)
        post["reaction_counts"] = reaction_buckets.get(pid, {})
        post["user_reaction"] = user_reactions.get(pid)
        post["comment_count"] = comment_map.get(pid, 0)


async def fetch_feed(user: Dict[str, Any], *, page: int = 1, limit: int = 20,
                     sort: str = "latest",
                     category: Optional[str] = None,
                     priority: Optional[str] = None,
                     search: Optional[str] = None) -> Dict[str, Any]:
    """End-to-end feed fetch: query → sort → paginate → enrich."""
    # Iter 345 (perf) — short-TTL cache, scoped by user + filter combo.
    # Skip cache when a search term is present (low hit-rate, high churn).
    cache_key = None
    if not search:
        cache_key = f"{user['user_id']}|{page}|{limit}|{sort}|{category or ''}|{priority or ''}"
        now = _time.monotonic()
        entry = _FEED_CACHE.get(cache_key)
        if entry and (now - entry[0]) < _FEED_TTL_SECONDS:
            return entry[1]

    query = build_feed_query(user, category=category, priority=priority, search=search)
    sort_spec = build_sort_spec(sort)
    # Iter 187 — route reads through a SECONDARY when the deployment runs a
    # Replica-Set. This off-loads heavy feed queries from the PRIMARY which
    # only handles writes (publish/edit/react/comment).
    total = await read_db.news_posts.count_documents(query)
    skip = (page - 1) * limit
    posts = await read_db.news_posts.find(query, {"_id": 0}).sort(sort_spec).skip(skip).limit(limit).to_list(limit)
    await enrich_posts(posts, user["user_id"])
    result = {"posts": posts, "total": total, "page": page, "pages": (total + limit - 1) // limit}

    if cache_key is not None:
        _FEED_CACHE[cache_key] = (_time.monotonic(), result)
        # Cap cache size to ~4k entries (~4k users × 1 default view); evict
        # expired entries lazily when we cross the threshold.
        if len(_FEED_CACHE) > 4000:
            cutoff = _time.monotonic() - _FEED_TTL_SECONDS
            for k in [k for k, v in _FEED_CACHE.items() if v[0] < cutoff]:
                _FEED_CACHE.pop(k, None)
    return result


def invalidate_news_feed_cache() -> None:
    """Drop the entire feed cache.

    Called from post create/edit/delete/react/comment paths so the next feed
    pull reflects the change immediately (writes are rare vs. reads, so a
    blanket invalidation is fine here).
    """
    _FEED_CACHE.clear()
