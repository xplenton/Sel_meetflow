"""Iter 194 — Tasks View All Capability + Calendar Integration Tests.
Tests for:
1. GET /api/user/permissions returns 'tasks.view_all' for admin/moderator but NOT for member
2. GET /api/calendar/events includes task events with correct fields
3. Status label 'Wartend' (blocked key kept in DB for back-compat)
4. Regression: iter192 baseline still passes
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
    email = f"task_iter194_member_{suffix}@example.com"
    requests.post(f"{API}/auth/register",
                  json={"email": email, "name": f"Member194 {suffix}", "password": "Test1234!"},
                  timeout=10)
    return _login(email, "Test1234!")


def _h(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


# ============ TEST 1: tasks.view_all capability ============

class TestTasksViewAllCapability:
    """Tests for tasks.view_all capability in permissions response."""

    def test_admin_has_tasks_view_all(self, admin_token):
        """Verify admin has tasks.view_all capability."""
        h = _h(admin_token)
        r = requests.get(f"{API}/user/permissions", headers=h, timeout=10)
        assert r.status_code == 200
        data = r.json()
        
        caps = data.get("capabilities", [])
        assert "tasks.view_all" in caps, "Admin should have tasks.view_all capability"

    def test_member_does_not_have_tasks_view_all(self, member):
        """Verify regular member does NOT have tasks.view_all capability."""
        h = _h(member["token"])
        r = requests.get(f"{API}/user/permissions", headers=h, timeout=10)
        assert r.status_code == 200
        data = r.json()
        
        caps = data.get("capabilities", [])
        assert "tasks.view_all" not in caps, "Member should NOT have tasks.view_all capability"
        # But member should still have basic task capabilities
        assert "tasks.create" in caps, "Member should have tasks.create"
        assert "tasks.assign_others" in caps, "Member should have tasks.assign_others"


# ============ TEST 2: Calendar events include tasks ============

class TestCalendarTaskEvents:
    """Tests for task events in calendar."""

    def test_calendar_events_include_tasks(self, admin_token):
        """Verify GET /api/calendar/events includes task events."""
        h = _h(admin_token)
        
        # Create a task with due date
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        t = requests.post(f"{API}/tasks", headers=h, json={
            "title": f"TEST_cal_iter194_{uuid.uuid4().hex[:6]}",
            "due_date": tomorrow,
            "priority": "high",
            "status": "open",
        }, timeout=10).json()
        tid = t["task_id"]
        
        # Get calendar events
        events = requests.get(f"{API}/calendar/events", headers=h, timeout=10).json()
        
        # Find our task in events
        task_events = [e for e in events if e.get("from_task") == tid]
        assert len(task_events) == 1, "Task should appear in calendar events"
        
        ev = task_events[0]
        # Verify required fields
        assert ev["meeting_type"] == "task"
        assert ev["from_task"] == tid
        assert "task_status" in ev
        assert "task_priority" in ev
        assert ev["title"].startswith("📋")
        assert ev["no_room"] is True
        
        # Cleanup
        requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=10)

    def test_task_event_has_correct_scheduled_at(self, admin_token):
        """Verify task event scheduled_at matches due_date."""
        h = _h(admin_token)
        
        due = "2026-12-20"
        t = requests.post(f"{API}/tasks", headers=h, json={
            "title": f"TEST_due_iter194_{uuid.uuid4().hex[:6]}",
            "due_date": due,
        }, timeout=10).json()
        tid = t["task_id"]
        
        events = requests.get(f"{API}/calendar/events", headers=h, timeout=10).json()
        task_events = [e for e in events if e.get("from_task") == tid]
        assert len(task_events) == 1
        
        # scheduled_at should start with the due_date
        assert task_events[0]["scheduled_at"].startswith(due)
        
        requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=10)


# ============ TEST 3: Status 'blocked' key preserved, label is 'Wartend' ============

class TestBlockedStatusLabel:
    """Tests for blocked status (DB key preserved, label changed to Wartend)."""

    def test_blocked_status_accepted_in_api(self, admin_token):
        """Verify 'blocked' status is still accepted by API."""
        h = _h(admin_token)
        
        t = requests.post(f"{API}/tasks", headers=h, json={
            "title": f"TEST_blocked_iter194_{uuid.uuid4().hex[:6]}",
            "status": "blocked",
        }, timeout=10)
        assert t.status_code == 200
        data = t.json()
        assert data["status"] == "blocked"
        
        requests.delete(f"{API}/tasks/{data['task_id']}", headers=h, timeout=10)

    def test_update_to_blocked_status(self, admin_token):
        """Verify task can be updated to 'blocked' status."""
        h = _h(admin_token)
        
        t = requests.post(f"{API}/tasks", headers=h, json={
            "title": f"TEST_update_blocked_{uuid.uuid4().hex[:6]}",
            "status": "open",
        }, timeout=10).json()
        tid = t["task_id"]
        
        # Update to blocked
        r = requests.put(f"{API}/tasks/{tid}", headers=h, json={"status": "blocked"}, timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == "blocked"
        
        requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=10)


# ============ TEST 4: Regression - iter192 baseline ============

class TestRegression:
    """Quick regression tests to ensure iter192 features still work."""

    def test_task_crud_still_works(self, admin_token):
        """Basic CRUD still functional."""
        h = _h(admin_token)
        
        # Create
        t = requests.post(f"{API}/tasks", headers=h, json={
            "title": f"TEST_regression_194_{uuid.uuid4().hex[:6]}",
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

    def test_pending_count_still_works(self, admin_token, member):
        """Pending count endpoint still functional."""
        h = _h(member["token"])
        r = requests.get(f"{API}/tasks/pending-count", headers=h, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "count" in data
        assert "overdue" in data

    def test_history_still_works(self, admin_token):
        """History endpoint still functional."""
        h = _h(admin_token)
        
        t = requests.post(f"{API}/tasks", headers=h, json={
            "title": f"TEST_history_194_{uuid.uuid4().hex[:6]}",
        }, timeout=10).json()
        tid = t["task_id"]
        
        r = requests.get(f"{API}/tasks/{tid}/history", headers=h, timeout=10)
        assert r.status_code == 200
        
        requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=10)
