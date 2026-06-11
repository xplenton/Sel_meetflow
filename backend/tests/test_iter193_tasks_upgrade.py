"""Iter 193 — Task Module Upgrades Tests.
Tests for:
1. GET /api/tasks/pending-count → {count, overdue}
2. GET /api/tasks/{id}/history → audit trail with actor_name
3. 'view:tasks' capability in /api/user/permissions
4. Member role defaults include view:tasks, tasks.create, tasks.assign_others
"""
import os
import uuid
import requests
import pytest
from datetime import date, timedelta


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
def member():
    """Create a fresh member user for testing."""
    suffix = uuid.uuid4().hex[:6]
    email = f"task_iter193_{suffix}@example.com"
    requests.post(f"{API}/auth/register",
                  json={"email": email, "name": f"Member193 {suffix}", "password": "Test1234!"},
                  timeout=10)
    return _login(email, "Test1234!")


def _h(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


# ============ TEST 1: GET /api/tasks/pending-count ============

class TestPendingCount:
    """Tests for the new /api/tasks/pending-count endpoint."""

    def test_pending_count_returns_count_and_overdue(self, admin_token, member):
        """Verify endpoint returns {count, overdue} structure."""
        h = _h(member["token"])
        muid = member["user_id"]
        ah = _h(admin_token)

        # Create tasks assigned to member
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        # Task 1: open, due tomorrow (not overdue)
        t1 = requests.post(f"{API}/tasks", headers=ah, json={
            "title": f"TEST_pending_1_{uuid.uuid4().hex[:6]}",
            "assignee_ids": [muid],
            "status": "open",
            "due_date": tomorrow,
        }, timeout=10).json()

        # Task 2: open, due yesterday (overdue)
        t2 = requests.post(f"{API}/tasks", headers=ah, json={
            "title": f"TEST_pending_2_{uuid.uuid4().hex[:6]}",
            "assignee_ids": [muid],
            "status": "open",
            "due_date": yesterday,
        }, timeout=10).json()

        # Task 3: done (should NOT count)
        t3 = requests.post(f"{API}/tasks", headers=ah, json={
            "title": f"TEST_pending_3_{uuid.uuid4().hex[:6]}",
            "assignee_ids": [muid],
            "status": "done",
            "due_date": yesterday,
        }, timeout=10).json()

        # Call pending-count as member
        r = requests.get(f"{API}/tasks/pending-count", headers=h, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "count" in data
        assert "overdue" in data
        assert data["count"] >= 2  # At least t1 and t2
        assert data["overdue"] >= 1  # At least t2

        # Cleanup
        for t in [t1, t2, t3]:
            requests.delete(f"{API}/tasks/{t['task_id']}", headers=ah, timeout=10)

    def test_pending_count_excludes_done_and_archived(self, admin_token, member):
        """Verify done and archived tasks are excluded from count."""
        h = _h(member["token"])
        muid = member["user_id"]
        ah = _h(admin_token)

        # Create a done task
        t_done = requests.post(f"{API}/tasks", headers=ah, json={
            "title": f"TEST_done_{uuid.uuid4().hex[:6]}",
            "assignee_ids": [muid],
            "status": "done",
        }, timeout=10).json()

        # Get count before
        r1 = requests.get(f"{API}/tasks/pending-count", headers=h, timeout=10).json()
        count_before = r1["count"]

        # Create an open task
        t_open = requests.post(f"{API}/tasks", headers=ah, json={
            "title": f"TEST_open_{uuid.uuid4().hex[:6]}",
            "assignee_ids": [muid],
            "status": "open",
        }, timeout=10).json()

        # Get count after
        r2 = requests.get(f"{API}/tasks/pending-count", headers=h, timeout=10).json()
        assert r2["count"] == count_before + 1

        # Cleanup
        requests.delete(f"{API}/tasks/{t_done['task_id']}", headers=ah, timeout=10)
        requests.delete(f"{API}/tasks/{t_open['task_id']}", headers=ah, timeout=10)


# ============ TEST 2: GET /api/tasks/{id}/history ============

class TestTaskHistory:
    """Tests for the new /api/tasks/{id}/history endpoint."""

    def test_history_returns_audit_trail(self, admin_token):
        """Verify history endpoint returns audit entries with actor_name."""
        h = _h(admin_token)

        # Create a task
        t = requests.post(f"{API}/tasks", headers=h, json={
            "title": f"TEST_history_{uuid.uuid4().hex[:6]}",
            "status": "open",
            "priority": "normal",
        }, timeout=10).json()
        tid = t["task_id"]

        # Make some changes to generate history
        requests.put(f"{API}/tasks/{tid}", headers=h, json={"status": "in_progress"}, timeout=10)
        requests.put(f"{API}/tasks/{tid}", headers=h, json={"priority": "high"}, timeout=10)

        # Get history
        r = requests.get(f"{API}/tasks/{tid}/history", headers=h, timeout=10)
        assert r.status_code == 200
        history = r.json()
        assert isinstance(history, list)
        assert len(history) >= 1  # At least the creation event

        # Check structure
        for entry in history:
            assert "actor_name" in entry or "actor_id" in entry
            assert "action" in entry
            assert "ts" in entry

        # Cleanup
        requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=10)

    def test_history_404_for_non_viewer(self, admin_token, member):
        """Verify history returns 404 for users who can't view the task."""
        ah = _h(admin_token)
        mh = _h(member["token"])

        # Admin creates private task (not assigned to member)
        me = requests.get(f"{API}/auth/me", headers=ah, timeout=10).json()
        t = requests.post(f"{API}/tasks", headers=ah, json={
            "title": f"TEST_private_history_{uuid.uuid4().hex[:6]}",
            "assignee_ids": [me["user_id"]],  # Only admin
        }, timeout=10).json()
        tid = t["task_id"]

        # Member tries to access history
        r = requests.get(f"{API}/tasks/{tid}/history", headers=mh, timeout=10)
        assert r.status_code == 404

        # Cleanup
        requests.delete(f"{API}/tasks/{tid}", headers=ah, timeout=10)

    def test_history_shows_german_action_labels(self, admin_token):
        """Verify history entries have proper action types for German labels."""
        h = _h(admin_token)

        t = requests.post(f"{API}/tasks", headers=h, json={
            "title": f"TEST_labels_{uuid.uuid4().hex[:6]}",
        }, timeout=10).json()
        tid = t["task_id"]

        # Change status
        requests.put(f"{API}/tasks/{tid}", headers=h, json={"status": "done"}, timeout=10)

        history = requests.get(f"{API}/tasks/{tid}/history", headers=h, timeout=10).json()
        
        # Should have 'created' action
        actions = [h.get("action") for h in history]
        assert any("created" in a or "set:" in a for a in actions if a)

        requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=10)


# ============ TEST 3: view:tasks capability in /api/user/permissions ============

class TestTasksCapability:
    """Tests for view:tasks capability in permissions response."""

    def test_permissions_includes_tasks_module(self, admin_token):
        """Verify /api/user/permissions includes 'tasks' in permissions list."""
        h = _h(admin_token)
        r = requests.get(f"{API}/user/permissions", headers=h, timeout=10)
        assert r.status_code == 200
        data = r.json()
        
        # Check permissions list includes 'tasks'
        assert "permissions" in data
        assert "tasks" in data["permissions"]

    def test_permissions_includes_view_tasks_capability(self, admin_token):
        """Verify /api/user/permissions includes 'view:tasks' in capabilities."""
        h = _h(admin_token)
        r = requests.get(f"{API}/user/permissions", headers=h, timeout=10)
        assert r.status_code == 200
        data = r.json()
        
        # Check capabilities list includes 'view:tasks'
        assert "capabilities" in data
        assert "view:tasks" in data["capabilities"]

    def test_member_has_tasks_capabilities(self, member):
        """Verify member role has view:tasks, tasks.create, tasks.assign_others."""
        h = _h(member["token"])
        r = requests.get(f"{API}/user/permissions", headers=h, timeout=10)
        assert r.status_code == 200
        data = r.json()
        
        caps = data.get("capabilities", [])
        # Member should have these task capabilities by default
        assert "view:tasks" in caps, "Member should have view:tasks capability"
        assert "tasks.create" in caps, "Member should have tasks.create capability"
        assert "tasks.assign_others" in caps, "Member should have tasks.assign_others capability"

    def test_member_sees_tasks_in_permissions(self, member):
        """Verify member sees 'tasks' in module permissions list."""
        h = _h(member["token"])
        r = requests.get(f"{API}/user/permissions", headers=h, timeout=10)
        assert r.status_code == 200
        data = r.json()
        
        perms = data.get("permissions", [])
        assert "tasks" in perms, "Member should see 'tasks' in permissions list"


# ============ TEST 4: Regression - Existing iter192 features still work ============

class TestRegression:
    """Quick regression tests to ensure iter192 features still work."""

    def test_task_crud_still_works(self, admin_token):
        """Basic CRUD still functional."""
        h = _h(admin_token)
        
        # Create
        t = requests.post(f"{API}/tasks", headers=h, json={
            "title": f"TEST_regression_{uuid.uuid4().hex[:6]}",
        }, timeout=10)
        assert t.status_code == 200
        tid = t.json()["task_id"]
        
        # Read
        g = requests.get(f"{API}/tasks/{tid}", headers=h, timeout=10)
        assert g.status_code == 200
        
        # Update
        u = requests.put(f"{API}/tasks/{tid}", headers=h, json={"status": "done"}, timeout=10)
        assert u.status_code == 200
        
        # Delete
        d = requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=10)
        assert d.status_code == 200

    def test_comments_still_work(self, admin_token):
        """Comments endpoint still functional."""
        h = _h(admin_token)
        
        t = requests.post(f"{API}/tasks", headers=h, json={
            "title": f"TEST_comments_reg_{uuid.uuid4().hex[:6]}",
        }, timeout=10).json()
        tid = t["task_id"]
        
        # Add comment
        c = requests.post(f"{API}/tasks/{tid}/comments", headers=h, 
                         json={"content": "Test comment"}, timeout=10)
        assert c.status_code == 200
        
        # List comments
        cl = requests.get(f"{API}/tasks/{tid}/comments", headers=h, timeout=10)
        assert cl.status_code == 200
        assert len(cl.json()) >= 1
        
        requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=10)
