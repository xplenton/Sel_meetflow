"""Task-Management-Modul (iter 192).

Zentrale Service-Funktionen für Aufgaben, Subtasks, Kommentare,
Anhänge, Suche und Vertretungsregelung.

Alle Endpoints leben in `routes/tasks.py`. Dieser Service kapselt
Mongo-Aggregations, Audience-Checks und Notification-Triggers.

Datenmodell (kompakt, keine ORM):
  tasks:
    task_id, title, description, status, priority, due_date,
    assignee_ids:[], group_ids:[], creator_id, parent_task_id|None,
    checklist:[{id,text,done,order}], tags:[], status_workflow:[..],
    meeting_id?, created_at, updated_at, archived
  task_comments:
    comment_id, task_id, parent_id|None, author_id, content,
    mentions:[user_ids], created_at, edited_at, deleted
  task_attachments:
    attachment_id, task_id, kind:'file'|'link', file_id|url,
    name, size, mime, uploaded_by, created_at
  task_history:
    history_id, task_id, actor_id, action, old, new, ts
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
import re
import uuid

from database import db, read_db


PRIORITIES = ("low", "normal", "high", "urgent")
DEFAULT_STATUSES = ("open", "in_progress", "blocked", "done")
TERMINAL = {"done"}

_MENTION_RE = re.compile(r"@\[([^\]]+)\]\(([a-zA-Z0-9_-]+)\)")


# ============ Helpers ============

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _strip(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Drop Mongo-internal fields."""
    return {k: v for k, v in doc.items() if k != "_id"}


async def _user_groups(user: Dict[str, Any]) -> Set[str]:
    return set(user.get("groups", []) or [])


# ============ Visibility ============

async def can_view_task(user: Dict[str, Any], task: Dict[str, Any]) -> bool:
    if not task:
        return False
    if user.get("role") in ("admin", "moderator"):
        return True
    uid = user.get("user_id")
    if uid and (task.get("creator_id") == uid or uid in (task.get("assignee_ids") or [])):
        return True
    user_groups = await _user_groups(user)
    if user_groups & set(task.get("group_ids") or []):
        return True
    return False


async def can_edit_task(user: Dict[str, Any], task: Dict[str, Any]) -> bool:
    """Edit = author + assignees + admin/moderator."""
    if not task:
        return False
    if user.get("role") in ("admin", "moderator"):
        return True
    uid = user.get("user_id")
    if uid and (task.get("creator_id") == uid or uid in (task.get("assignee_ids") or [])):
        return True
    return False


async def can_delete_task(user: Dict[str, Any], task: Dict[str, Any]) -> bool:
    """Delete = creator OR admin OR has tasks.delete_others capability.
    Stricter than edit: assignees alone may NOT delete a task they didn't create.
    """
    if not task:
        return False
    if user.get("role") == "admin":
        return True
    uid = user.get("user_id")
    if uid and task.get("creator_id") == uid:
        return True
    # Capability check (lazy import to avoid circular deps)
    from services.permissions import get_effective_capabilities
    from database import db as _db
    try:
        caps = await get_effective_capabilities(user, _db)
        if "tasks.delete_others" in caps:
            return True
    except Exception:
        pass
    return False


# ============ Audit history ============

async def _log(task_id: str, actor_id: str, action: str, old=None, new=None):
    await db.task_history.insert_one({
        "history_id": _new_id("th"),
        "task_id": task_id, "actor_id": actor_id,
        "action": action, "old": old, "new": new,
        "ts": _now(),
    })


# ============ Mention parsing ============

def extract_mentions(content: str) -> List[str]:
    """Find all @[Name](user_id) tokens and return unique user_ids."""
    return list({m.group(2) for m in _MENTION_RE.finditer(content or "")})


# ============ Task CRUD ============

def normalize_assignees(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve absent users to their delegate (Vertretungsregelung)."""
    return payload


async def resolve_delegations(user_ids: List[str]) -> List[str]:
    """If a user has `out_of_office=true` AND a `delegate_user_id`, replace."""
    if not user_ids:
        return []
    rows = await db.users.find(
        {"user_id": {"$in": user_ids}},
        {"_id": 0, "user_id": 1, "out_of_office": 1, "delegate_user_id": 1},
    ).to_list(len(user_ids))
    by_id = {r["user_id"]: r for r in rows}
    resolved: List[str] = []
    for uid in user_ids:
        u = by_id.get(uid)
        if u and u.get("out_of_office") and u.get("delegate_user_id"):
            resolved.append(u["delegate_user_id"])
        else:
            resolved.append(uid)
    # de-duplicate while preserving order
    seen, out = set(), []
    for uid in resolved:
        if uid not in seen:
            seen.add(uid); out.append(uid)
    return out


async def create_task(creator: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")
    raw_assignees = data.get("assignee_ids") or []
    assignees = await resolve_delegations(raw_assignees)
    doc = {
        "task_id": _new_id("task"),
        "title": title,
        "description": (data.get("description") or "").strip(),
        "status": data.get("status") or "open",
        "priority": data.get("priority") or "normal",
        "due_date": data.get("due_date") or None,
        "assignee_ids": assignees,
        "original_assignee_ids": raw_assignees,  # Audit trail for delegations
        "group_ids": data.get("group_ids") or [],
        "creator_id": creator["user_id"],
        "parent_task_id": data.get("parent_task_id") or None,
        "checklist": data.get("checklist") or [],
        "tags": data.get("tags") or [],
        "status_workflow": data.get("status_workflow") or list(DEFAULT_STATUSES),
        "meeting_id": data.get("meeting_id") or None,
        "recurrence": data.get("recurrence") or None,  # {pattern,interval,weekdays,end_date}
        "created_at": _now(),
        "updated_at": _now(),
        "archived": False,
    }
    if doc["priority"] not in PRIORITIES:
        doc["priority"] = "normal"
    if doc["status"] not in doc["status_workflow"]:
        doc["status_workflow"] = list(DEFAULT_STATUSES)
    await db.tasks.insert_one(doc)
    await _log(doc["task_id"], creator["user_id"], "created")
    return _strip(doc)


async def update_task(actor: Dict[str, Any], task_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    task = await db.tasks.find_one({"task_id": task_id}, {"_id": 0})
    if not task:
        return None
    allowed = {
        "title", "description", "status", "priority", "due_date",
        "assignee_ids", "group_ids", "checklist", "tags",
        "status_workflow", "archived", "recurrence",
    }
    patch = {k: v for k, v in updates.items() if k in allowed}
    if not patch:
        return task
    if "priority" in patch and patch["priority"] not in PRIORITIES:
        patch.pop("priority")
    if "assignee_ids" in patch and patch["assignee_ids"] != task.get("assignee_ids"):
        # Resolve delegations on re-assign
        patch["original_assignee_ids"] = patch["assignee_ids"]
        patch["assignee_ids"] = await resolve_delegations(patch["assignee_ids"])
    if "status" in patch and patch["status"] not in (task.get("status_workflow") or list(DEFAULT_STATUSES)):
        raise ValueError(f"Invalid status '{patch['status']}'")
    patch["updated_at"] = _now()
    await db.tasks.update_one({"task_id": task_id}, {"$set": patch})
    new = await db.tasks.find_one({"task_id": task_id}, {"_id": 0})
    # log diffs
    for k, v in patch.items():
        if task.get(k) != v and k not in ("updated_at", "original_assignee_ids"):
            await _log(task_id, actor["user_id"], f"set:{k}", task.get(k), v)
    # Recurrence (iter 196): when a recurring task moves to 'done', spawn the
    # next occurrence with a shifted due_date. The original is marked done and
    # keeps its recurrence metadata for the audit trail.
    if patch.get("status") == "done" and task.get("status") != "done":
        rec = new.get("recurrence")
        if rec and rec.get("pattern") in ("daily", "weekly", "monthly"):
            next_due = _compute_next_due(new.get("due_date"), rec)
            if next_due and (not rec.get("end_date") or next_due <= rec["end_date"]):
                next_payload = {
                    "title": new["title"],
                    "description": new.get("description", ""),
                    "priority": new.get("priority", "normal"),
                    "due_date": next_due,
                    "assignee_ids": new.get("original_assignee_ids") or new.get("assignee_ids") or [],
                    "group_ids": new.get("group_ids") or [],
                    "checklist": [{**c, "done": False, "id": _new_id("cl")} for c in new.get("checklist") or []],
                    "tags": new.get("tags") or [],
                    "recurrence": rec,  # chain onwards
                }
                await create_task(actor, next_payload)
    return new


def _compute_next_due(current_due: Optional[str], rec: Dict[str, Any]) -> Optional[str]:
    """Shift a YYYY-MM-DD due_date forward by `interval` units of `pattern`."""
    from datetime import date, timedelta
    if not current_due:
        base = date.today()
    else:
        try:
            base = date.fromisoformat(current_due)
        except Exception:
            return None
    interval = max(int(rec.get("interval") or 1), 1)
    p = rec.get("pattern")
    if p == "daily":
        nxt = base + timedelta(days=interval)
    elif p == "weekly":
        nxt = base + timedelta(weeks=interval)
    elif p == "monthly":
        m = base.month + interval
        y = base.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        try:
            nxt = base.replace(year=y, month=m)
        except ValueError:
            # Day of month doesn't exist in target month (e.g. Jan 31 -> Feb)
            nxt = date(y, m, 28)
    else:
        return None
    return nxt.isoformat()


async def delete_task(task_id: str, cascade: bool = True) -> int:
    """Hard-delete a task plus optional children/comments/attachments."""
    n = await db.tasks.delete_one({"task_id": task_id})
    if cascade:
        await db.tasks.delete_many({"parent_task_id": task_id})
        await db.task_comments.delete_many({"task_id": task_id})
        await db.task_attachments.delete_many({"task_id": task_id})
        await db.task_history.delete_many({"task_id": task_id})
    return n.deleted_count


async def duplicate_task(task: Dict[str, Any], creator: Dict[str, Any]) -> Dict[str, Any]:
    """Clone the task (title gets " (Kopie)" suffix) without comments/history."""
    payload = {
        "title": f"{task['title']} (Kopie)",
        "description": task.get("description", ""),
        "status": "open",
        "priority": task.get("priority", "normal"),
        "due_date": task.get("due_date"),
        "assignee_ids": task.get("original_assignee_ids") or task.get("assignee_ids") or [],
        "group_ids": task.get("group_ids") or [],
        "parent_task_id": task.get("parent_task_id"),
        "checklist": [{**c, "done": False, "id": _new_id("cl")} for c in task.get("checklist") or []],
        "tags": task.get("tags") or [],
        "status_workflow": task.get("status_workflow") or list(DEFAULT_STATUSES),
    }
    return await create_task(creator, payload)


# ============ Listing & Search ============

async def list_tasks_for_user(
    user: Dict[str, Any],
    *,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assignee_id: Optional[str] = None,
    due_from: Optional[str] = None,
    due_to: Optional[str] = None,
    search: Optional[str] = None,
    parent_task_id: Optional[str] = None,
    archived: bool = False,
    limit: int = 200,
    skip: int = 0,
) -> Dict[str, Any]:
    uid = user["user_id"]
    role = user.get("role")
    user_groups = list(await _user_groups(user))

    # Iter 377 — Department-Scope: ist die Cap `tasks.view_department` aktiv,
    # darf der User auch alle Aufgaben sehen, deren Creator oder Assignees
    # in derselben Abteilung sind. Das ist schwaecher als `view_all` und
    # genau passend fuer Team-/Stations-/Kuechen-Mitarbeiter.
    department_user_ids: Set[str] = set()
    try:
        from services.permissions import has_cap
        if role not in ("admin", "moderator") and await has_cap(user, "tasks.view_department", db):
            dept = (user.get("department") or "").strip()
            if dept:
                async for u in db.users.find(
                    {"department": dept}, {"_id": 0, "user_id": 1},
                ):
                    department_user_ids.add(u["user_id"])
    except Exception:
        pass

    if role in ("admin", "moderator"):
        query: Dict[str, Any] = {}
    else:
        clauses: List[Dict[str, Any]] = [
            {"creator_id": uid},
            {"assignee_ids": uid},
        ]
        if user_groups:
            clauses.append({"group_ids": {"$in": user_groups}})
        if department_user_ids:
            ids = list(department_user_ids)
            clauses.append({"creator_id": {"$in": ids}})
            clauses.append({"assignee_ids": {"$in": ids}})
        query = {"$or": clauses}

    if status:
        query["status"] = status
    if priority:
        query["priority"] = priority
    if assignee_id:
        query["assignee_ids"] = assignee_id
    if parent_task_id is not None:
        query["parent_task_id"] = parent_task_id if parent_task_id else None
    if archived is False:
        query["archived"] = {"$ne": True}
    if due_from or due_to:
        rng: Dict[str, Any] = {}
        if due_from: rng["$gte"] = due_from
        if due_to: rng["$lte"] = due_to
        query["due_date"] = rng
    if search:
        regex = {"$regex": re.escape(search), "$options": "i"}
        query["$and"] = query.get("$and", []) + [{"$or": [
            {"title": regex}, {"description": regex}, {"tags": regex},
        ]}]
    total = await read_db.tasks.count_documents(query)
    cur = read_db.tasks.find(query, {"_id": 0}).sort([
        ("priority", -1), ("due_date", 1), ("created_at", -1),
    ]).skip(skip).limit(limit)
    tasks = await cur.to_list(limit)
    # Attach quick counts
    if tasks:
        ids = [t["task_id"] for t in tasks]
        comm_rows = await read_db.task_comments.aggregate([
            {"$match": {"task_id": {"$in": ids}, "deleted": {"$ne": True}}},
            {"$group": {"_id": "$task_id", "c": {"$sum": 1}}},
        ]).to_list(len(ids))
        cmap = {r["_id"]: r["c"] for r in comm_rows}
        att_rows = await read_db.task_attachments.aggregate([
            {"$match": {"task_id": {"$in": ids}}},
            {"$group": {"_id": "$task_id", "c": {"$sum": 1}}},
        ]).to_list(len(ids))
        amap = {r["_id"]: r["c"] for r in att_rows}
        sub_rows = await read_db.tasks.aggregate([
            {"$match": {"parent_task_id": {"$in": ids}, "archived": {"$ne": True}}},
            {"$group": {"_id": "$parent_task_id", "total": {"$sum": 1},
                         "done": {"$sum": {"$cond": [{"$eq": ["$status", "done"]}, 1, 0]}}}},
        ]).to_list(len(ids))
        smap = {r["_id"]: r for r in sub_rows}
        for t in tasks:
            t["comment_count"] = cmap.get(t["task_id"], 0)
            t["attachment_count"] = amap.get(t["task_id"], 0)
            sub = smap.get(t["task_id"], {"total": 0, "done": 0})
            t["subtask_count"] = sub["total"]
            t["subtask_done"] = sub["done"]
    return {"tasks": tasks, "total": total, "skip": skip, "limit": limit}


async def search_full(user: Dict[str, Any], q: str, *, limit: int = 30) -> Dict[str, Any]:
    """Full-text-ish search across tasks AND comments."""
    if not q:
        return {"tasks": [], "comments": []}
    res = await list_tasks_for_user(user, search=q, limit=limit, archived=True)

    # comment search — cross-check task visibility via author/assignee/admin
    uid = user["user_id"]
    role = user.get("role")
    user_groups = list(await _user_groups(user))
    visible_filter: Dict[str, Any] = {} if role in ("admin", "moderator") else {
        "$or": [
            {"creator_id": uid},
            {"assignee_ids": uid},
            {"group_ids": {"$in": user_groups}} if user_groups else {"creator_id": uid},
        ]
    }
    visible_ids = await read_db.tasks.distinct("task_id", visible_filter)
    regex = {"$regex": re.escape(q), "$options": "i"}
    cmts = await read_db.task_comments.find(
        {"task_id": {"$in": visible_ids}, "content": regex, "deleted": {"$ne": True}},
        {"_id": 0},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"tasks": res["tasks"], "comments": cmts}


# ============ Comments ============

async def add_comment(task_id: str, author: Dict[str, Any], content: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
    if not content or not content.strip():
        raise ValueError("Comment cannot be empty")
    doc = {
        "comment_id": _new_id("tc"),
        "task_id": task_id,
        "parent_id": parent_id or None,
        "author_id": author["user_id"],
        "author_name": author.get("name", ""),
        "content": content.strip(),
        "mentions": extract_mentions(content),
        "created_at": _now(),
        "edited_at": None,
        "deleted": False,
    }
    await db.task_comments.insert_one(doc)
    await db.tasks.update_one({"task_id": task_id}, {"$set": {"updated_at": _now()}})
    return _strip(doc)


async def list_comments(task_id: str) -> List[Dict[str, Any]]:
    rows = await read_db.task_comments.find(
        {"task_id": task_id, "deleted": {"$ne": True}}, {"_id": 0},
    ).sort("created_at", 1).to_list(2000)
    return rows


async def edit_comment(comment_id: str, actor: Dict[str, Any], content: str) -> Optional[Dict[str, Any]]:
    cmt = await db.task_comments.find_one({"comment_id": comment_id}, {"_id": 0})
    if not cmt:
        return None
    if cmt["author_id"] != actor["user_id"] and actor.get("role") not in ("admin", "moderator"):
        raise PermissionError("Only the author can edit")
    await db.task_comments.update_one(
        {"comment_id": comment_id},
        {"$set": {
            "content": content.strip(),
            "mentions": extract_mentions(content),
            "edited_at": _now(),
        }},
    )
    return await db.task_comments.find_one({"comment_id": comment_id}, {"_id": 0})


async def delete_comment(comment_id: str, actor: Dict[str, Any]) -> bool:
    cmt = await db.task_comments.find_one({"comment_id": comment_id}, {"_id": 0})
    if not cmt:
        return False
    if cmt["author_id"] != actor["user_id"] and actor.get("role") not in ("admin", "moderator"):
        raise PermissionError("Only the author can delete")
    await db.task_comments.update_one({"comment_id": comment_id}, {"$set": {"deleted": True, "content": ""}})
    return True


# ============ Attachments ============

async def add_link_attachment(task_id: str, user: Dict[str, Any], url: str, name: str = "") -> Dict[str, Any]:
    doc = {
        "attachment_id": _new_id("ta"),
        "task_id": task_id, "kind": "link",
        "url": url, "name": name or url,
        "uploaded_by": user["user_id"],
        "created_at": _now(),
    }
    await db.task_attachments.insert_one(doc)
    return _strip(doc)


async def add_file_attachment(task_id: str, user: Dict[str, Any], file_id: str, name: str, size: int, mime: str) -> Dict[str, Any]:
    doc = {
        "attachment_id": _new_id("ta"),
        "task_id": task_id, "kind": "file",
        "file_id": file_id, "name": name,
        "size": size, "mime": mime,
        "uploaded_by": user["user_id"],
        "created_at": _now(),
    }
    await db.task_attachments.insert_one(doc)
    return _strip(doc)


async def list_attachments(task_id: str) -> List[Dict[str, Any]]:
    return await read_db.task_attachments.find({"task_id": task_id}, {"_id": 0}).sort("created_at", -1).to_list(500)


async def delete_attachment(attachment_id: str, actor: Dict[str, Any]) -> bool:
    att = await db.task_attachments.find_one({"attachment_id": attachment_id}, {"_id": 0})
    if not att:
        return False
    if att.get("uploaded_by") != actor["user_id"] and actor.get("role") not in ("admin", "moderator"):
        raise PermissionError("not allowed")
    await db.task_attachments.delete_one({"attachment_id": attachment_id})
    return True


# ============ Calendar Integration helper ============

async def tasks_for_calendar(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return upcoming due tasks where the user is creator or assignee
    (or admin sees everything). Used by build_calendar_events.

    iter 202 — filter to upcoming (today or later) and recent past 30 days,
    so the 500-row limit never drops valid current entries.
    """
    from datetime import date, timedelta
    uid = user["user_id"]
    role = user.get("role")
    today = date.today()
    earliest = (today - timedelta(days=30)).isoformat()
    if role in ("admin", "moderator"):
        q: Dict[str, Any] = {"due_date": {"$ne": None, "$gte": earliest}}
    else:
        q = {"due_date": {"$ne": None, "$gte": earliest},
             "$or": [{"creator_id": uid}, {"assignee_ids": uid}]}
    q["archived"] = {"$ne": True}
    return await read_db.tasks.find(q, {"_id": 0,
        "task_id": 1, "title": 1, "due_date": 1, "priority": 1, "status": 1,
        "assignee_ids": 1, "creator_id": 1,
    }).sort("due_date", 1).limit(500).to_list(500)


# ============ Task Templates (iter 196) ============

async def list_templates(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    """List all templates visible to the user. Currently org-wide — anyone
    with view:tasks can see them. Templates themselves are not private."""
    return await read_db.task_templates.find({}, {"_id": 0}).sort("name", 1).to_list(500)


async def create_template(creator: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("name required")
    doc = {
        "template_id": _new_id("tpl"),
        "name": name,
        "description": (data.get("description") or "").strip(),
        "title": (data.get("title") or name).strip(),
        "priority": data.get("priority") or "normal",
        "tags": data.get("tags") or [],
        "checklist": [{**c, "id": _new_id("cl"), "done": False} for c in data.get("checklist") or []],
        "group_ids": data.get("group_ids") or [],
        "assignee_ids": data.get("assignee_ids") or [],
        "recurrence": data.get("recurrence") or None,
        "creator_id": creator["user_id"],
        "created_at": _now(),
    }
    await db.task_templates.insert_one(doc)
    return _strip(doc)


async def delete_template(template_id: str) -> bool:
    r = await db.task_templates.delete_one({"template_id": template_id})
    return r.deleted_count > 0


async def apply_template(template_id: str, creator: Dict[str, Any],
                         overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    tpl = await db.task_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not tpl:
        raise ValueError("template not found")
    payload = {
        "title": tpl["title"],
        "description": tpl.get("description", ""),
        "priority": tpl.get("priority", "normal"),
        "tags": tpl.get("tags") or [],
        "checklist": [{**c, "id": _new_id("cl"), "done": False} for c in tpl.get("checklist") or []],
        "group_ids": tpl.get("group_ids") or [],
        "assignee_ids": tpl.get("assignee_ids") or [],
        "recurrence": tpl.get("recurrence"),
    }
    if overrides:
        payload.update({k: v for k, v in overrides.items() if v is not None})
    return await create_task(creator, payload)


async def update_template(template_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Patch a template. Regenerates checklist ids when checklist provided."""
    allowed = {"name", "description", "title", "priority", "tags",
               "checklist", "group_ids", "assignee_ids", "recurrence"}
    patch = {k: v for k, v in data.items() if k in allowed}
    if "checklist" in patch:
        patch["checklist"] = [
            {**c, "id": c.get("id") or _new_id("cl"), "done": False}
            for c in (patch["checklist"] or [])
        ]
    if not patch:
        return await db.task_templates.find_one({"template_id": template_id}, {"_id": 0})
    await db.task_templates.update_one({"template_id": template_id}, {"$set": patch})
    return await db.task_templates.find_one({"template_id": template_id}, {"_id": 0})
