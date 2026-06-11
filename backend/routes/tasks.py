"""Task-Modul Routes (iter 192)."""
from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse
import asyncio
import os
import shutil
import uuid
from typing import Optional, Dict, Any

from database import db
from dependencies import get_current_user
from services import tasks_service as svc
from services import pending_count_cache
from services.permissions import require_cap
from services.task_notifs import (
    notify_assignment, notify_status_change, notify_comment, fire_and_forget,
)
from routes.chat._shared import chat_ws

router = APIRouter()

UPLOAD_DIR = "/app/backend/uploads/tasks"


def _serialize(t):
    return {k: v for k, v in t.items() if k != "_id"} if t else t


def _task_recipients(task: dict, *extra_user_ids: str) -> set[str]:
    """Iter 336 — Live-Update fan-out targets for a task event.

    Includes everyone with a stake in the task: current assignees, the
    creator, and any explicitly-passed user ids (e.g. former assignees on
    a re-assign so their lane updates too).
    """
    targets: set[str] = set()
    targets.update(task.get("assignee_ids") or [])
    if task.get("creator_id"):
        targets.add(task["creator_id"])
    for uid in extra_user_ids:
        if uid:
            targets.add(uid)
    return {u for u in targets if u}


def _broadcast_task_event(event: str, task: dict, *, actor_id: str | None = None, extra_uids: set[str] | None = None):
    """Fan-out a `task-<event>` payload to every stakeholder over the chat WS.

    Fire-and-forget — never block the request on socket I/O. Errors are
    swallowed (the HTTP response is the source of truth).
    """
    if not task:
        return
    targets = _task_recipients(task)
    if extra_uids:
        targets |= {u for u in extra_uids if u}
    payload = {
        "type": f"task-{event}",
        "task_id": task.get("task_id"),
        "task": _serialize(task),
        "actor_id": actor_id,
    }

    async def _send():
        await asyncio.gather(
            *(chat_ws.send_to_user(uid, payload) for uid in targets),
            return_exceptions=True,
        )
    fire_and_forget(_send())


# ============ Tasks CRUD ============

@router.get("/tasks")
async def list_tasks(
    request: Request,
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
):
    user = await get_current_user(request)
    return await svc.list_tasks_for_user(
        user, status=status, priority=priority, assignee_id=assignee_id,
        due_from=due_from, due_to=due_to, search=search,
        parent_task_id=parent_task_id, archived=archived,
        limit=min(limit, 500), skip=max(0, skip),
    )


@router.get("/tasks/search")
async def search_tasks(request: Request, q: str = "", limit: int = 30):
    user = await get_current_user(request)
    return await svc.search_full(user, q, limit=min(limit, 100))


@router.get("/tasks/pending-count")
async def my_pending_count(request: Request):
    """Number of open (non-done, non-archived) tasks where the current user
    is assignee. Used by Sidebar badge polling. Cheap query (indexed) and
    cached for 30s per user (iter 203)."""
    user = await get_current_user(request)
    uid = user["user_id"]
    cached = await pending_count_cache.get(uid)
    if cached is not None:
        return cached
    from database import read_db as _read
    count = await _read.tasks.count_documents({
        "assignee_ids": uid,
        "status": {"$ne": "done"},
        "archived": {"$ne": True},
    })
    overdue = await _read.tasks.count_documents({
        "assignee_ids": uid,
        "status": {"$ne": "done"},
        "archived": {"$ne": True},
        "due_date": {"$lt": _today_str(), "$ne": None},
    })
    payload = {"count": count, "overdue": overdue}
    await pending_count_cache.set(uid, payload)
    return payload


def _today_str() -> str:
    from datetime import date
    return date.today().isoformat()


@router.post("/tasks")
async def create_task(request: Request):
    user = await get_current_user(request)
    # Iter 372 — IAM-Audit Fix: enforce tasks.create cap (Guests dürfen nicht).
    await require_cap(user, "tasks.create", db)
    body = await request.json()
    try:
        task = await svc.create_task(user, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if task["assignee_ids"]:
        fire_and_forget(notify_assignment(task, user, task["assignee_ids"]))
    # iter 203 — invalidate badge cache for everyone whose count just changed.
    await pending_count_cache.invalidate_many(task.get("assignee_ids") or [])
    # iter 200 — creator can always delete their own task; surface flag for UI.
    task["can_delete"] = True
    # iter 336 — Live broadcast for Kanban-style realtime collab.
    _broadcast_task_event("created", task, actor_id=user["user_id"])
    return task


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, request: Request):
    user = await get_current_user(request)
    task = await db.tasks.find_one({"task_id": task_id}, {"_id": 0})
    if not task or not await svc.can_view_task(user, task):
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    # enrich with subtasks/comments/attachments preview
    subtasks = await db.tasks.find(
        {"parent_task_id": task_id, "archived": {"$ne": True}}, {"_id": 0},
    ).sort("created_at", 1).to_list(200)
    task["subtasks"] = subtasks
    # iter 200 — let the UI hide the delete button when not permitted.
    task["can_delete"] = await svc.can_delete_task(user, task)
    return task


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, request: Request):
    user = await get_current_user(request)
    task = await db.tasks.find_one({"task_id": task_id}, {"_id": 0})
    if not task or not await svc.can_view_task(user, task):
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    if not await svc.can_edit_task(user, task):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    body = await request.json()
    old_status = task.get("status")
    old_assignees = set(task.get("assignee_ids") or [])
    try:
        new_task = await svc.update_task(user, task_id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if new_task and new_task.get("status") != old_status:
        fire_and_forget(notify_status_change(new_task, user, old_status, new_task["status"]))
    new_assignees = set(new_task.get("assignee_ids") or []) if new_task else set()
    added = list(new_assignees - old_assignees)
    if added and new_task:
        fire_and_forget(notify_assignment(new_task, user, added))
    # iter 203 — invalidate badge cache for everyone whose pending-count may
    # have changed: previous + new assignees (covers status/archived/assignee
    # transitions and additions/removals).
    await pending_count_cache.invalidate_many(old_assignees | new_assignees)
    # iter 336 — Live broadcast. Include former assignees so their Kanban
    # column re-removes the task instantly when they're un-assigned.
    if new_task:
        _broadcast_task_event(
            "updated", new_task,
            actor_id=user["user_id"],
            extra_uids=(old_assignees - new_assignees),
        )
    return new_task


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, request: Request):
    user = await get_current_user(request)
    task = await db.tasks.find_one({"task_id": task_id}, {"_id": 0})
    if not task or not await svc.can_view_task(user, task):
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    if not await svc.can_delete_task(user, task):
        raise HTTPException(status_code=403, detail="Löschen nicht erlaubt")
    await svc.delete_task(task_id)
    # iter 203 — invalidate badge cache for all former assignees.
    await pending_count_cache.invalidate_many(task.get("assignee_ids") or [])
    # iter 336 — Live broadcast so other users see the row disappear from
    # their list/board without having to refresh.
    _broadcast_task_event("deleted", task, actor_id=user["user_id"])
    return {"deleted": True}


@router.post("/tasks/{task_id}/duplicate")
async def duplicate_task(task_id: str, request: Request):
    user = await get_current_user(request)
    task = await db.tasks.find_one({"task_id": task_id}, {"_id": 0})
    if not task or not await svc.can_view_task(user, task):
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    new = await svc.duplicate_task(task, user)
    # iter 203 — invalidate badge cache for every assignee of the new copy.
    if isinstance(new, dict):
        await pending_count_cache.invalidate_many(new.get("assignee_ids") or [])
    return new


# ============ Comments ============

@router.get("/tasks/{task_id}/comments")
async def list_comments(task_id: str, request: Request):
    user = await get_current_user(request)
    task = await db.tasks.find_one({"task_id": task_id}, {"_id": 0})
    if not task or not await svc.can_view_task(user, task):
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    return await svc.list_comments(task_id)


@router.post("/tasks/{task_id}/comments")
async def add_comment(task_id: str, request: Request):
    user = await get_current_user(request)
    task = await db.tasks.find_one({"task_id": task_id}, {"_id": 0})
    if not task or not await svc.can_view_task(user, task):
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    body = await request.json()
    try:
        cmt = await svc.add_comment(
            task_id, user,
            content=body.get("content", ""),
            parent_id=body.get("parent_id"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    fire_and_forget(notify_comment(task, cmt, user))
    return cmt


@router.put("/tasks/{task_id}/comments/{comment_id}")
async def edit_comment(task_id: str, comment_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    try:
        return await svc.edit_comment(comment_id, user, body.get("content", ""))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Nur Autor darf editieren")


@router.delete("/tasks/{task_id}/comments/{comment_id}")
async def delete_comment(task_id: str, comment_id: str, request: Request):
    user = await get_current_user(request)
    try:
        ok = await svc.delete_comment(comment_id, user)
        return {"deleted": ok}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Nicht erlaubt")


# ============ Attachments ============

@router.get("/tasks/{task_id}/attachments")
async def list_attachments(task_id: str, request: Request):
    user = await get_current_user(request)
    task = await db.tasks.find_one({"task_id": task_id}, {"_id": 0})
    if not task or not await svc.can_view_task(user, task):
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    return await svc.list_attachments(task_id)


@router.post("/tasks/{task_id}/attachments/link")
async def add_link(task_id: str, request: Request):
    user = await get_current_user(request)
    task = await db.tasks.find_one({"task_id": task_id}, {"_id": 0})
    if not task or not await svc.can_view_task(user, task):
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    body = await request.json()
    url = (body.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url required")
    return await svc.add_link_attachment(task_id, user, url, body.get("name", ""))


@router.post("/tasks/{task_id}/attachments/file")
async def upload_attachment(task_id: str, request: Request, file: UploadFile = File(...)):
    user = await get_current_user(request)
    task = await db.tasks.find_one({"task_id": task_id}, {"_id": 0})
    if not task or not await svc.can_view_task(user, task):
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "bin"
    file_id = f"taskf_{uuid.uuid4().hex[:10]}.{ext}"
    path = os.path.join(UPLOAD_DIR, file_id)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    size = os.path.getsize(path)
    if size > 25 * 1024 * 1024:  # 25 MB
        os.remove(path)
        raise HTTPException(status_code=413, detail="Datei zu gross (max 25 MB)")
    return await svc.add_file_attachment(
        task_id, user, file_id, file.filename or file_id, size, file.content_type or "application/octet-stream",
    )


@router.get("/tasks/files/{file_id}")
async def serve_attachment(file_id: str, request: Request):
    user = await get_current_user(request)
    if "/" in file_id or ".." in file_id:
        raise HTTPException(status_code=400, detail="Invalid id")
    # find the matching attachment + check task visibility
    att = await db.task_attachments.find_one({"file_id": file_id, "kind": "file"}, {"_id": 0})
    if not att:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    task = await db.tasks.find_one({"task_id": att["task_id"]}, {"_id": 0})
    if not task or not await svc.can_view_task(user, task):
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    path = os.path.join(UPLOAD_DIR, file_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Datei fehlt")
    return FileResponse(path, media_type=att.get("mime") or "application/octet-stream",
                        filename=att.get("name") or file_id)


@router.delete("/tasks/{task_id}/attachments/{attachment_id}")
async def delete_attachment(task_id: str, attachment_id: str, request: Request):
    user = await get_current_user(request)
    task = await db.tasks.find_one({"task_id": task_id}, {"_id": 0})
    if not task or not await svc.can_view_task(user, task):
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    att = await db.task_attachments.find_one({"attachment_id": attachment_id}, {"_id": 0})
    if att and att.get("kind") == "file" and att.get("file_id"):
        try:
            os.remove(os.path.join(UPLOAD_DIR, att["file_id"]))
        except Exception:
            pass
    try:
        ok = await svc.delete_attachment(attachment_id, user)
        return {"deleted": ok}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Nicht erlaubt")


# ============ Activity / History ============

@router.get("/tasks/{task_id}/history")
async def task_history(task_id: str, request: Request):
    """Return the audit trail for a task (created, status changes,
    assignee changes etc.). Visible to anyone who can view the task."""
    user = await get_current_user(request)
    task = await db.tasks.find_one({"task_id": task_id}, {"_id": 0})
    if not task or not await svc.can_view_task(user, task):
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    rows = await db.task_history.find(
        {"task_id": task_id}, {"_id": 0},
    ).sort("ts", -1).limit(200).to_list(200)
    # Enrich with actor names (one cheap aggregation)
    actor_ids = list({r.get("actor_id") for r in rows if r.get("actor_id")})
    if actor_ids:
        users = await db.users.find(
            {"user_id": {"$in": actor_ids}}, {"_id": 0, "user_id": 1, "name": 1, "email": 1},
        ).to_list(len(actor_ids))
        umap = {u["user_id"]: u for u in users}
        for r in rows:
            u = umap.get(r.get("actor_id"))
            r["actor_name"] = (u or {}).get("name") or (u or {}).get("email") or "?"
    return rows


# ============ Out-of-office (Vertretungsregelung) ============

@router.put("/users/me/out-of-office")
async def set_out_of_office(request: Request):
    """Body: {out_of_office: bool, delegate_user_id?: str, until?: ISO date}.
    Wenn `out_of_office=true`, werden zukuenftige Task-Zuweisungen automatisch
    auf `delegate_user_id` umgeleitet (siehe svc.resolve_delegations)."""
    user = await get_current_user(request)
    body = await request.json()
    updates = {
        "out_of_office": bool(body.get("out_of_office")),
        "delegate_user_id": body.get("delegate_user_id") or None,
        "out_of_office_until": body.get("until") or None,
    }
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": updates})
    return updates


@router.get("/users/me/out-of-office")
async def get_out_of_office(request: Request):
    user = await get_current_user(request)
    return {
        "out_of_office": bool(user.get("out_of_office")),
        "delegate_user_id": user.get("delegate_user_id"),
        "out_of_office_until": user.get("out_of_office_until"),
    }


# ============ Task Templates (iter 196) ============

@router.get("/task-templates")
async def list_templates(request: Request):
    user = await get_current_user(request)
    return await svc.list_templates(user)


@router.post("/task-templates")
async def create_template(request: Request):
    user = await get_current_user(request)
    body = await request.json()
    # Only admins, moderators or users with tasks.create may manage templates.
    from services.permissions import get_effective_capabilities
    caps = await get_effective_capabilities(user, db)
    if "tasks.create" not in caps and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Nicht erlaubt")
    try:
        return await svc.create_template(user, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/task-templates/{template_id}")
async def delete_template(template_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Nur Admin/Moderator")
    ok = await svc.delete_template(template_id)
    return {"deleted": ok}


@router.put("/task-templates/{template_id}")
async def update_template(template_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Nur Admin/Moderator")
    body = await request.json()
    tpl = await svc.update_template(template_id, body or {})
    if not tpl:
        raise HTTPException(status_code=404, detail="Vorlage nicht gefunden")
    return tpl


@router.post("/tasks/from-template/{template_id}")
async def create_from_template(template_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.body()
    overrides: Dict[str, Any] = {}
    if body:
        try:
            import json as _json
            overrides = _json.loads(body) or {}
        except Exception:
            overrides = {}
    try:
        new = await svc.apply_template(template_id, user, overrides)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(new, dict):
        await pending_count_cache.invalidate_many(new.get("assignee_ids") or [])
    return new
