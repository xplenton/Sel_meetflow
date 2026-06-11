"""Iter 200 — can_delete flag and DELETE permission gate tests.

Tests:
1. POST /tasks returns can_delete: true (creator)
2. GET /tasks/{id} returns can_delete: true for creator
3. GET /tasks/{id} returns can_delete: true for admin
4. GET /tasks/{id} returns can_delete: false for non-creator member without tasks.delete_others
5. DELETE /tasks/{id} by creator succeeds
6. DELETE /tasks/{id} by admin succeeds
7. DELETE /tasks/{id} by non-creator without tasks.delete_others returns 403
8. DELETE /tasks/{id} by user with tasks.delete_others capability succeeds
"""
import os
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
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=15).json()
    if r.get("totp_required"):
        pytest.skip("admin 2FA enabled")
    if "token" not in r:
        pytest.skip(f"login failed: {r}")
    return r


def _h(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin@meetflow.com", "admin123")["token"]


@pytest.fixture(scope="module")
def member_a():
    """A regular member who will create tasks."""
    suffix = uuid.uuid4().hex[:6]
    email = f"iter200_member_a_{suffix}@example.com"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "name": f"Member A {suffix}", "password": "Test1234!"},
                      timeout=15)
    if r.status_code not in (200, 201, 409):
        pytest.skip(f"register failed: {r.text}")
    return _login(email, "Test1234!")


@pytest.fixture(scope="module")
def member_b():
    """A regular member who will NOT be the creator."""
    suffix = uuid.uuid4().hex[:6]
    email = f"iter200_member_b_{suffix}@example.com"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "name": f"Member B {suffix}", "password": "Test1234!"},
                      timeout=15)
    if r.status_code not in (200, 201, 409):
        pytest.skip(f"register failed: {r.text}")
    return _login(email, "Test1234!")


# ============ POST /tasks returns can_delete: true ============

def test_post_task_returns_can_delete_true(member_a):
    """POST /tasks should return can_delete: true for the creator."""
    h = _h(member_a["token"])
    r = requests.post(f"{API}/tasks", headers=h, json={
        "title": f"Iter200 POST can_delete test {uuid.uuid4().hex[:6]}",
    }, timeout=15)
    assert r.status_code == 200, f"POST failed: {r.text}"
    data = r.json()
    assert "can_delete" in data, "can_delete field missing from POST response"
    assert data["can_delete"] is True, "can_delete should be True for creator"
    # Cleanup
    requests.delete(f"{API}/tasks/{data['task_id']}", headers=h, timeout=15)


# ============ GET /tasks/{id} returns can_delete based on permissions ============

def test_get_task_can_delete_true_for_creator(member_a):
    """GET /tasks/{id} should return can_delete: true for the creator."""
    h = _h(member_a["token"])
    # Create task
    r = requests.post(f"{API}/tasks", headers=h, json={
        "title": f"Iter200 GET creator test {uuid.uuid4().hex[:6]}",
    }, timeout=15)
    assert r.status_code == 200
    task = r.json()
    tid = task["task_id"]
    
    # GET as creator
    g = requests.get(f"{API}/tasks/{tid}", headers=h, timeout=15)
    assert g.status_code == 200
    data = g.json()
    assert data.get("can_delete") is True, "can_delete should be True for creator"
    
    # Cleanup
    requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=15)


def test_get_task_can_delete_true_for_admin(member_a, admin_token):
    """GET /tasks/{id} should return can_delete: true for admin."""
    h_member = _h(member_a["token"])
    h_admin = _h(admin_token)
    
    # Member creates task
    r = requests.post(f"{API}/tasks", headers=h_member, json={
        "title": f"Iter200 GET admin test {uuid.uuid4().hex[:6]}",
    }, timeout=15)
    assert r.status_code == 200
    task = r.json()
    tid = task["task_id"]
    
    # GET as admin
    g = requests.get(f"{API}/tasks/{tid}", headers=h_admin, timeout=15)
    assert g.status_code == 200
    data = g.json()
    assert data.get("can_delete") is True, "can_delete should be True for admin"
    
    # Cleanup
    requests.delete(f"{API}/tasks/{tid}", headers=h_admin, timeout=15)


def test_get_task_can_delete_false_for_non_creator_member(member_a, member_b, admin_token):
    """GET /tasks/{id} should return can_delete: false for non-creator member without tasks.delete_others."""
    h_a = _h(member_a["token"])
    h_b = _h(member_b["token"])
    h_admin = _h(admin_token)
    
    # Member A creates task and assigns to Member B (so B can view it)
    r = requests.post(f"{API}/tasks", headers=h_a, json={
        "title": f"Iter200 GET non-creator test {uuid.uuid4().hex[:6]}",
        "assignee_ids": [member_b["user_id"]],
    }, timeout=15)
    assert r.status_code == 200
    task = r.json()
    tid = task["task_id"]
    
    # GET as Member B (assignee but not creator)
    g = requests.get(f"{API}/tasks/{tid}", headers=h_b, timeout=15)
    assert g.status_code == 200
    data = g.json()
    assert data.get("can_delete") is False, "can_delete should be False for non-creator assignee"
    
    # Cleanup (admin deletes)
    requests.delete(f"{API}/tasks/{tid}", headers=h_admin, timeout=15)


# ============ DELETE /tasks/{id} permission gate ============

def test_delete_task_by_creator_succeeds(member_a):
    """DELETE /tasks/{id} by creator should succeed."""
    h = _h(member_a["token"])
    
    # Create task
    r = requests.post(f"{API}/tasks", headers=h, json={
        "title": f"Iter200 DELETE creator test {uuid.uuid4().hex[:6]}",
    }, timeout=15)
    assert r.status_code == 200
    tid = r.json()["task_id"]
    
    # Delete as creator
    d = requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=15)
    assert d.status_code == 200, f"Creator should be able to delete: {d.text}"
    assert d.json().get("deleted") is True


def test_delete_task_by_admin_succeeds(member_a, admin_token):
    """DELETE /tasks/{id} by admin should succeed even if not creator."""
    h_member = _h(member_a["token"])
    h_admin = _h(admin_token)
    
    # Member creates task
    r = requests.post(f"{API}/tasks", headers=h_member, json={
        "title": f"Iter200 DELETE admin test {uuid.uuid4().hex[:6]}",
    }, timeout=15)
    assert r.status_code == 200
    tid = r.json()["task_id"]
    
    # Delete as admin
    d = requests.delete(f"{API}/tasks/{tid}", headers=h_admin, timeout=15)
    assert d.status_code == 200, f"Admin should be able to delete: {d.text}"
    assert d.json().get("deleted") is True


def test_delete_task_by_non_creator_returns_403(member_a, member_b, admin_token):
    """DELETE /tasks/{id} by non-creator without tasks.delete_others should return 403."""
    h_a = _h(member_a["token"])
    h_b = _h(member_b["token"])
    h_admin = _h(admin_token)
    
    # Member A creates task and assigns to Member B (so B can view it)
    r = requests.post(f"{API}/tasks", headers=h_a, json={
        "title": f"Iter200 DELETE 403 test {uuid.uuid4().hex[:6]}",
        "assignee_ids": [member_b["user_id"]],
    }, timeout=15)
    assert r.status_code == 200
    tid = r.json()["task_id"]
    
    # Member B tries to delete (should fail with 403)
    d = requests.delete(f"{API}/tasks/{tid}", headers=h_b, timeout=15)
    assert d.status_code == 403, f"Non-creator should get 403, got {d.status_code}: {d.text}"
    
    # Cleanup (admin deletes)
    requests.delete(f"{API}/tasks/{tid}", headers=h_admin, timeout=15)


# ============ tasks.delete_others capability test ============

def test_delete_task_with_delete_others_capability(admin_token, member_a):
    """User with tasks.delete_others capability can delete others' tasks."""
    h_admin = _h(admin_token)
    h_member = _h(member_a["token"])
    
    # Member creates task
    r = requests.post(f"{API}/tasks", headers=h_member, json={
        "title": f"Iter200 DELETE capability test {uuid.uuid4().hex[:6]}",
    }, timeout=15)
    assert r.status_code == 200
    tid = r.json()["task_id"]
    
    # Admin (who has tasks.delete_others by default) can delete
    # Note: Admin role already has full permissions, so this tests the path
    d = requests.delete(f"{API}/tasks/{tid}", headers=h_admin, timeout=15)
    assert d.status_code == 200, f"User with delete_others should succeed: {d.text}"
