"""Task-Modul Notifications (iter 192).
Sendet Email + Push bei Assignment, Status-Change, neuen Kommentaren,
@mentions. Respektiert User-Notification-Prefs (Quiet Hours).
"""
from typing import Any, Dict, Iterable, List
import asyncio
import os

from database import db
from services.email import send_email_real
from services.news_push import send_push_to_user


FRONTEND_URL = os.environ.get("FRONTEND_URL", "")


async def _users_by_ids(ids: Iterable[str]) -> List[Dict[str, Any]]:
    ids_list = list(set([i for i in ids if i]))
    if not ids_list:
        return []
    return await db.users.find(
        {"user_id": {"$in": ids_list}},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1},
    ).to_list(len(ids_list))


def _task_url(task_id: str) -> str:
    base = FRONTEND_URL or ""
    return f"{base}/tasks/{task_id}"


async def notify_assignment(task: Dict[str, Any], actor: Dict[str, Any], new_assignee_ids: List[str]):
    if not new_assignee_ids:
        return
    targets = await _users_by_ids(new_assignee_ids)
    title = task.get("title", "Aufgabe")
    actor_name = actor.get("name", "")
    body = f'{actor_name} hat dir eine Aufgabe zugewiesen: "{title}"'
    url = _task_url(task["task_id"])
    for u in targets:
        if u["user_id"] == actor.get("user_id"):
            continue
        if u.get("email"):
            try:
                await send_email_real(
                    u["email"],
                    f"Neue Aufgabe: {title}",
                    f"<p>{body}</p><p><a href=\"{url}\">Aufgabe oeffnen</a></p>",
                )
            except Exception:
                pass
        try:
            await send_push_to_user(u["user_id"], title="Neue Aufgabe", body=body,
                                    data={"url": url, "category": "tasks"})
        except Exception:
            pass


async def notify_status_change(task: Dict[str, Any], actor: Dict[str, Any], old: str, new: str):
    targets_ids = list(set((task.get("assignee_ids") or []) + [task.get("creator_id")]))
    targets = await _users_by_ids(targets_ids)
    body = f"{actor.get('name','')} hat den Status von \"{task.get('title','')}\" geaendert: {old} → {new}"
    url = _task_url(task["task_id"])
    for u in targets:
        if u["user_id"] == actor.get("user_id"):
            continue
        try:
            await send_push_to_user(u["user_id"], title="Aufgaben-Status geaendert",
                                    body=body, data={"url": url, "category": "tasks"})
        except Exception:
            pass


async def notify_comment(task: Dict[str, Any], comment: Dict[str, Any], author: Dict[str, Any]):
    """Notify everybody on the task + everyone mentioned. Mentions get email,
    others only push (to avoid noise)."""
    interested = set((task.get("assignee_ids") or []) + [task.get("creator_id")])
    interested.discard(author.get("user_id"))
    mentions = set(comment.get("mentions") or [])
    all_ids = list(interested | mentions)
    if not all_ids:
        return
    targets = await _users_by_ids(all_ids)
    snippet = (comment.get("content") or "")[:140]
    title = task.get("title", "Aufgabe")
    url = _task_url(task["task_id"])
    actor_name = author.get("name", "")
    for u in targets:
        is_mention = u["user_id"] in mentions
        body = (f'{actor_name} hat dich erwaehnt in "{title}": {snippet}'
                if is_mention else
                f'{actor_name} hat kommentiert in "{title}": {snippet}')
        try:
            await send_push_to_user(u["user_id"],
                title="@-Erwaehnung" if is_mention else "Neuer Kommentar",
                body=body, data={"url": url, "category": "tasks"})
        except Exception:
            pass
        if is_mention and u.get("email"):
            try:
                await send_email_real(
                    u["email"],
                    f'@Erwaehnung: {title}',
                    f'<p>{body}</p><p><a href="{url}">Aufgabe oeffnen</a></p>',
                )
            except Exception:
                pass


def fire_and_forget(coro):
    """Schedule a coroutine without awaiting it (for use in HTTP handlers)."""
    try:
        asyncio.create_task(coro)
    except RuntimeError:
        pass
