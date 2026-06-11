"""Iter 192 — Task-Modul End-to-End-Tests.
CRUD, Subtasks, Comments mit @mention, Attachments, Filter, Suche,
Calendar-Integration, Out-of-office Delegation.
"""
import os
import io
import uuid
import requests
import pytest


def _api():
    val = os.environ.get("REACT_APP_BACKEND_URL")
    if val:
        return val.rstrip("/") + "/api"
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/") + "/api"
    return "http://localhost:8001/api"


API = _api()


def _login(email, pwd):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=10).json()
    if r.get("totp_required"):
        pytest.skip("admin 2FA enabled")
    if "token" not in r:
        pytest.skip(f"login failed: {r}")
    return r


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin@meetflow.com", "admin123")["token"]


@pytest.fixture(scope="module")
def member(admin_token):
    suffix = uuid.uuid4().hex[:6]
    email = f"task_member_{suffix}@example.com"
    requests.post(f"{API}/auth/register",
                  json={"email": email, "name": f"Member {suffix}", "password": "Test1234!"},
                  timeout=10)
    return _login(email, "Test1234!")


def _h(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


# ============ CRUD ============

def test_task_full_crud(admin_token):
    h = _h(admin_token)
    r = requests.post(f"{API}/tasks", headers=h, json={
        "title": f"Task CRUD {uuid.uuid4().hex[:6]}",
        "description": "Test description",
        "priority": "high",
        "due_date": "2026-12-15",
        "checklist": [{"id": "c1", "text": "Step 1", "done": False}],
        "tags": ["test", "crud"],
    }, timeout=10)
    assert r.status_code == 200
    t = r.json()
    tid = t["task_id"]
    assert t["priority"] == "high"
    assert len(t["checklist"]) == 1

    # Get
    g = requests.get(f"{API}/tasks/{tid}", headers=h, timeout=10).json()
    assert g["task_id"] == tid

    # Update status (done changes status workflow)
    r = requests.put(f"{API}/tasks/{tid}", headers=h, json={"status": "in_progress", "priority": "urgent"}, timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"
    assert r.json()["priority"] == "urgent"

    # Invalid status → 400
    r = requests.put(f"{API}/tasks/{tid}", headers=h, json={"status": "qux"}, timeout=10)
    assert r.status_code == 400

    # Duplicate
    d = requests.post(f"{API}/tasks/{tid}/duplicate", headers=h, timeout=10).json()
    assert d["task_id"] != tid
    assert "(Kopie)" in d["title"]

    # Delete
    r = requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=10)
    assert r.status_code == 200
    assert requests.get(f"{API}/tasks/{tid}", headers=h, timeout=10).status_code == 404
    requests.delete(f"{API}/tasks/{d['task_id']}", headers=h, timeout=10)


# ============ Subtasks + Filter ============

def test_subtasks_and_filter(admin_token):
    h = _h(admin_token)
    parent = requests.post(f"{API}/tasks", headers=h, json={"title": "Parent task X"}, timeout=10).json()
    tid = parent["task_id"]
    sub = requests.post(f"{API}/tasks", headers=h, json={
        "title": "Subtask 1", "parent_task_id": tid, "status": "open",
    }, timeout=10).json()
    assert sub["parent_task_id"] == tid

    # Get parent should show subtasks
    g = requests.get(f"{API}/tasks/{tid}", headers=h, timeout=10).json()
    assert len(g["subtasks"]) >= 1

    # Filter by parent_task_id
    r = requests.get(f"{API}/tasks?parent_task_id={tid}", headers=h, timeout=10).json()
    assert any(t["task_id"] == sub["task_id"] for t in r["tasks"])

    requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=10)


# ============ Comments + @mentions ============

def test_comments_and_mentions(admin_token, member):
    h = _h(admin_token)
    me = requests.get(f"{API}/auth/me", headers=h, timeout=10).json()
    mtok = member["token"]
    muid = member["user_id"]

    # admin creates task assigned to member
    t = requests.post(f"{API}/tasks", headers=h, json={
        "title": "Comment Test", "assignee_ids": [muid],
    }, timeout=10).json()
    tid = t["task_id"]

    # member can comment
    c = requests.post(f"{API}/tasks/{tid}/comments", headers=_h(mtok),
                      json={"content": f"Hallo @[Admin]({me['user_id']})!"}, timeout=10).json()
    assert me["user_id"] in c["mentions"]

    # admin replies (threaded)
    r = requests.post(f"{API}/tasks/{tid}/comments", headers=h,
                      json={"content": "Antwort", "parent_id": c["comment_id"]}, timeout=10).json()
    assert r["parent_id"] == c["comment_id"]

    # Both visible
    cs = requests.get(f"{API}/tasks/{tid}/comments", headers=h, timeout=10).json()
    assert len(cs) == 2

    # Edit own comment
    e = requests.put(f"{API}/tasks/{tid}/comments/{c['comment_id']}", headers=_h(mtok),
                     json={"content": "Aktualisierter Text"}, timeout=10).json()
    assert e["content"] == "Aktualisierter Text"

    # Delete own
    requests.delete(f"{API}/tasks/{tid}/comments/{c['comment_id']}", headers=_h(mtok), timeout=10)

    requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=10)


# ============ Attachments ============

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de00000008494441540878636400000000000000017d0dd7000000004944"
    "41454ae426820000000049454e44ae426082"
)


def test_attachments_file_and_link(admin_token):
    h = _h(admin_token)
    t = requests.post(f"{API}/tasks", headers=h, json={"title": "Att Test"}, timeout=10).json()
    tid = t["task_id"]

    # link
    a = requests.post(f"{API}/tasks/{tid}/attachments/link", headers=h,
                      json={"url": "https://example.com", "name": "Beispiel"}, timeout=10).json()
    assert a["kind"] == "link"

    # file
    files = {"file": ("test.png", io.BytesIO(PNG_BYTES), "image/png")}
    r = requests.post(f"{API}/tasks/{tid}/attachments/file",
                      headers={"Authorization": h["Authorization"]},
                      files=files, timeout=15)
    assert r.status_code == 200
    fa = r.json()
    assert fa["kind"] == "file"
    assert fa["mime"] == "image/png"

    # list
    al = requests.get(f"{API}/tasks/{tid}/attachments", headers=h, timeout=10).json()
    assert len(al) == 2

    # serve
    fr = requests.get(f"{API}/tasks/files/{fa['file_id']}", headers=h, timeout=10)
    assert fr.status_code == 200

    # delete
    requests.delete(f"{API}/tasks/{tid}/attachments/{fa['attachment_id']}", headers=h, timeout=10)
    requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=10)


# ============ Search ============

def test_full_text_search(admin_token):
    h = _h(admin_token)
    marker = uuid.uuid4().hex[:8]
    t = requests.post(f"{API}/tasks", headers=h, json={
        "title": f"Search marker {marker}",
        "description": "needle in haystack",
    }, timeout=10).json()
    tid = t["task_id"]
    requests.post(f"{API}/tasks/{tid}/comments", headers=h,
                  json={"content": f"comment-marker-{marker}"}, timeout=10)

    # Title search
    r = requests.get(f"{API}/tasks/search?q={marker}", headers=h, timeout=10).json()
    assert len(r["tasks"]) >= 1

    # Comment search
    r2 = requests.get(f"{API}/tasks/search?q=comment-marker-{marker}", headers=h, timeout=10).json()
    assert len(r2["comments"]) >= 1

    requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=10)


# ============ Calendar Integration ============

def test_due_date_appears_in_calendar(admin_token):
    h = _h(admin_token)
    title = f"CalTask iter192 {uuid.uuid4().hex[:6]}"
    t = requests.post(f"{API}/tasks", headers=h, json={
        "title": title, "due_date": "2026-12-15",
    }, timeout=10).json()
    tid = t["task_id"]

    events = requests.get(f"{API}/calendar/events", headers=h, timeout=10).json()
    matches = [e for e in events if e.get("title", "").endswith(title)]
    assert len(matches) == 1
    e = matches[0]
    assert e["meeting_type"] == "task"
    assert e["no_room"] is True
    assert e["scheduled_at"].startswith("2026-12-15")

    requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=10)


# ============ Visibility / Permissions ============

def test_visibility_isolation(admin_token, member):
    """Non-member must not see a task it's not assigned to."""
    ah = _h(admin_token)
    mh = _h(member["token"])

    me_admin = requests.get(f"{API}/auth/me", headers=ah, timeout=10).json()
    private = requests.post(f"{API}/tasks", headers=ah, json={
        "title": "Private admin task", "assignee_ids": [me_admin["user_id"]],
    }, timeout=10).json()

    # Member cannot fetch
    r = requests.get(f"{API}/tasks/{private['task_id']}", headers=mh, timeout=10)
    assert r.status_code == 404

    # Member's list does not contain it
    ml = requests.get(f"{API}/tasks", headers=mh, timeout=10).json()
    assert not any(t["task_id"] == private["task_id"] for t in ml["tasks"])

    # Member cannot edit
    r = requests.put(f"{API}/tasks/{private['task_id']}", headers=mh, json={"title": "hijacked"}, timeout=10)
    assert r.status_code == 404

    requests.delete(f"{API}/tasks/{private['task_id']}", headers=ah, timeout=10)


# ============ Out-of-office Delegation ============

def test_out_of_office_delegation(admin_token):
    """Member B sets out_of_office with delegate=A. A new task assigned to B
    should auto-route to A (resolved at create time)."""
    h = _h(admin_token)
    me = requests.get(f"{API}/auth/me", headers=h, timeout=10).json()
    admin_uid = me["user_id"]

    # Create two members
    suffix = uuid.uuid4().hex[:6]
    a_email = f"deleg_a_{suffix}@example.com"
    b_email = f"deleg_b_{suffix}@example.com"
    requests.post(f"{API}/auth/register", json={"email": a_email, "name": "Deleg A", "password": "Test1234!"}, timeout=10)
    requests.post(f"{API}/auth/register", json={"email": b_email, "name": "Deleg B", "password": "Test1234!"}, timeout=10)
    a = _login(a_email, "Test1234!")
    b = _login(b_email, "Test1234!")

    # B sets out_of_office with delegate = A
    r = requests.put(f"{API}/users/me/out-of-office", headers=_h(b["token"]),
                     json={"out_of_office": True, "delegate_user_id": a["user_id"]}, timeout=10)
    assert r.status_code == 200

    # Admin assigns task to B
    t = requests.post(f"{API}/tasks", headers=h, json={
        "title": "Delegated Task", "assignee_ids": [b["user_id"]],
    }, timeout=10).json()
    # Should be routed to A
    assert a["user_id"] in t["assignee_ids"]
    assert b["user_id"] not in t["assignee_ids"]
    # Original assignee preserved for audit
    assert b["user_id"] in t.get("original_assignee_ids", [])

    # Cleanup: turn off OoO and delete
    requests.put(f"{API}/users/me/out-of-office", headers=_h(b["token"]),
                 json={"out_of_office": False}, timeout=10)
    requests.delete(f"{API}/tasks/{t['task_id']}", headers=h, timeout=10)
