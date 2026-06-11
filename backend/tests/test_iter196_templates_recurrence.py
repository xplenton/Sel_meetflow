"""Iter 196 — Task Templates + Recurring Tasks Tests.
Tests for:
1. POST /api/task-templates creates a template
2. GET /api/task-templates lists templates
3. DELETE /api/task-templates/{id} removes template (admin/moderator only)
4. POST /api/tasks/from-template/{id} creates task from template
5. Recurring tasks: daily, weekly, monthly patterns
6. Recurrence respects end_date
7. Member cannot delete templates (403)
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
    email = f"task_iter196_member_{suffix}@example.com"
    requests.post(f"{API}/auth/register",
                  json={"email": email, "name": f"Member196 {suffix}", "password": "Test1234!"},
                  timeout=10)
    return _login(email, "Test1234!")


def _h(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


# ============ TEST 1: Task Templates CRUD ============

class TestTaskTemplates:
    """Tests for task template endpoints."""

    def test_create_template(self, admin_token):
        """POST /api/task-templates creates a template."""
        h = _h(admin_token)
        name = f"TEST_tpl_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/task-templates", headers=h, json={
            "name": name,
            "title": "Template Task Title",
            "description": "Template description",
            "priority": "high",
            "tags": ["template", "test"],
            "checklist": [{"text": "Step 1"}, {"text": "Step 2"}],
        }, timeout=10)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data["name"] == name
        assert data["title"] == "Template Task Title"
        assert data["priority"] == "high"
        assert len(data["checklist"]) == 2
        assert "template_id" in data
        
        # Cleanup
        requests.delete(f"{API}/task-templates/{data['template_id']}", headers=h, timeout=10)

    def test_list_templates(self, admin_token):
        """GET /api/task-templates lists templates."""
        h = _h(admin_token)
        
        # Create a template first
        name = f"TEST_list_tpl_{uuid.uuid4().hex[:6]}"
        tpl = requests.post(f"{API}/task-templates", headers=h, json={
            "name": name, "title": name,
        }, timeout=10).json()
        
        # List templates
        r = requests.get(f"{API}/task-templates", headers=h, timeout=10)
        assert r.status_code == 200
        templates = r.json()
        assert isinstance(templates, list)
        assert any(t["template_id"] == tpl["template_id"] for t in templates)
        
        # Cleanup
        requests.delete(f"{API}/task-templates/{tpl['template_id']}", headers=h, timeout=10)

    def test_delete_template_admin(self, admin_token):
        """DELETE /api/task-templates/{id} works for admin."""
        h = _h(admin_token)
        
        # Create template
        name = f"TEST_del_tpl_{uuid.uuid4().hex[:6]}"
        tpl = requests.post(f"{API}/task-templates", headers=h, json={
            "name": name, "title": name,
        }, timeout=10).json()
        
        # Delete
        r = requests.delete(f"{API}/task-templates/{tpl['template_id']}", headers=h, timeout=10)
        assert r.status_code == 200
        assert r.json()["deleted"] is True
        
        # Verify deleted
        templates = requests.get(f"{API}/task-templates", headers=h, timeout=10).json()
        assert not any(t["template_id"] == tpl["template_id"] for t in templates)

    def test_member_cannot_delete_template(self, admin_token, member):
        """Member cannot delete templates (403)."""
        ah = _h(admin_token)
        mh = _h(member["token"])
        
        # Admin creates template
        name = f"TEST_nodelete_tpl_{uuid.uuid4().hex[:6]}"
        tpl = requests.post(f"{API}/task-templates", headers=ah, json={
            "name": name, "title": name,
        }, timeout=10).json()
        
        # Member tries to delete → 403
        r = requests.delete(f"{API}/task-templates/{tpl['template_id']}", headers=mh, timeout=10)
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"
        
        # Cleanup
        requests.delete(f"{API}/task-templates/{tpl['template_id']}", headers=ah, timeout=10)


# ============ TEST 2: Create Task from Template ============

class TestCreateFromTemplate:
    """Tests for POST /api/tasks/from-template/{id}."""

    def test_create_task_from_template(self, admin_token):
        """POST /api/tasks/from-template/{id} creates a task with template data."""
        h = _h(admin_token)
        
        # Create template with checklist and tags
        name = f"TEST_apply_tpl_{uuid.uuid4().hex[:6]}"
        tpl = requests.post(f"{API}/task-templates", headers=h, json={
            "name": name,
            "title": "Template Title",
            "description": "Template Desc",
            "priority": "urgent",
            "tags": ["from-template", "test"],
            "checklist": [{"text": "Check 1"}, {"text": "Check 2"}],
        }, timeout=10).json()
        
        # Create task from template
        r = requests.post(f"{API}/tasks/from-template/{tpl['template_id']}", headers=h, json={}, timeout=10)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        task = r.json()
        
        # Verify task has template data
        assert task["title"] == "Template Title"
        assert task["description"] == "Template Desc"
        assert task["priority"] == "urgent"
        assert "from-template" in task["tags"]
        assert len(task["checklist"]) == 2
        assert task["status"] == "open"  # Fresh task starts as open
        
        # Verify IDs are fresh (not same as template)
        for cl in task["checklist"]:
            assert cl["id"].startswith("cl_")
            assert cl["done"] is False
        
        # Cleanup
        requests.delete(f"{API}/tasks/{task['task_id']}", headers=h, timeout=10)
        requests.delete(f"{API}/task-templates/{tpl['template_id']}", headers=h, timeout=10)

    def test_create_from_template_with_overrides(self, admin_token):
        """POST /api/tasks/from-template/{id} with overrides body."""
        h = _h(admin_token)
        
        # Create template
        name = f"TEST_override_tpl_{uuid.uuid4().hex[:6]}"
        tpl = requests.post(f"{API}/task-templates", headers=h, json={
            "name": name,
            "title": "Original Title",
            "priority": "low",
        }, timeout=10).json()
        
        # Create task with overrides
        r = requests.post(f"{API}/tasks/from-template/{tpl['template_id']}", headers=h, json={
            "title": "Overridden Title",
            "due_date": "2026-12-25",
        }, timeout=10)
        assert r.status_code == 200
        task = r.json()
        
        # Verify overrides applied
        assert task["title"] == "Overridden Title"
        assert task["due_date"] == "2026-12-25"
        assert task["priority"] == "low"  # From template
        
        # Cleanup
        requests.delete(f"{API}/tasks/{task['task_id']}", headers=h, timeout=10)
        requests.delete(f"{API}/task-templates/{tpl['template_id']}", headers=h, timeout=10)

    def test_create_from_nonexistent_template(self, admin_token):
        """POST /api/tasks/from-template/{id} with invalid id returns 404."""
        h = _h(admin_token)
        r = requests.post(f"{API}/tasks/from-template/nonexistent_tpl_123", headers=h, json={}, timeout=10)
        assert r.status_code == 404


# ============ TEST 3: Recurring Tasks ============

class TestRecurringTasks:
    """Tests for recurring task functionality."""

    def test_create_task_with_recurrence(self, admin_token):
        """POST /api/tasks with recurrence metadata."""
        h = _h(admin_token)
        
        r = requests.post(f"{API}/tasks", headers=h, json={
            "title": f"TEST_recur_{uuid.uuid4().hex[:6]}",
            "due_date": "2026-01-15",
            "recurrence": {
                "pattern": "weekly",
                "interval": 1,
            },
        }, timeout=10)
        assert r.status_code == 200
        task = r.json()
        
        assert task["recurrence"] is not None
        assert task["recurrence"]["pattern"] == "weekly"
        assert task["recurrence"]["interval"] == 1
        
        # Cleanup
        requests.delete(f"{API}/tasks/{task['task_id']}", headers=h, timeout=10)

    def test_weekly_recurrence_spawns_next_task(self, admin_token):
        """Setting status='done' on weekly recurring task spawns new task +7 days."""
        h = _h(admin_token)
        
        # Create recurring task
        title = f"TEST_weekly_recur_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/tasks", headers=h, json={
            "title": title,
            "due_date": "2026-01-15",
            "recurrence": {
                "pattern": "weekly",
                "interval": 1,
            },
        }, timeout=10)
        task = r.json()
        tid = task["task_id"]
        
        # Mark as done
        r = requests.put(f"{API}/tasks/{tid}", headers=h, json={"status": "done"}, timeout=10)
        assert r.status_code == 200
        
        # Search for the spawned task
        tasks = requests.get(f"{API}/tasks?search={title}", headers=h, timeout=10).json()["tasks"]
        
        # Should have 2 tasks with same title (original done + new open)
        matching = [t for t in tasks if title in t["title"]]
        assert len(matching) >= 2, f"Expected at least 2 tasks, got {len(matching)}"
        
        # Find the new one (status=open, due_date=2026-01-22)
        new_tasks = [t for t in matching if t["status"] == "open"]
        assert len(new_tasks) >= 1, "No new open task spawned"
        new_task = new_tasks[0]
        assert new_task["due_date"] == "2026-01-22", f"Expected 2026-01-22, got {new_task['due_date']}"
        assert new_task["recurrence"]["pattern"] == "weekly"
        
        # Cleanup
        for t in matching:
            requests.delete(f"{API}/tasks/{t['task_id']}", headers=h, timeout=10)

    def test_daily_recurrence(self, admin_token):
        """Daily recurrence shifts due_date by interval days."""
        h = _h(admin_token)
        
        title = f"TEST_daily_recur_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/tasks", headers=h, json={
            "title": title,
            "due_date": "2026-02-10",
            "recurrence": {"pattern": "daily", "interval": 3},
        }, timeout=10)
        task = r.json()
        tid = task["task_id"]
        
        # Mark done
        requests.put(f"{API}/tasks/{tid}", headers=h, json={"status": "done"}, timeout=10)
        
        # Find spawned task
        tasks = requests.get(f"{API}/tasks?search={title}", headers=h, timeout=10).json()["tasks"]
        new_tasks = [t for t in tasks if t["status"] == "open"]
        assert len(new_tasks) >= 1
        assert new_tasks[0]["due_date"] == "2026-02-13"  # +3 days
        
        # Cleanup
        for t in tasks:
            if title in t["title"]:
                requests.delete(f"{API}/tasks/{t['task_id']}", headers=h, timeout=10)

    def test_monthly_recurrence(self, admin_token):
        """Monthly recurrence shifts due_date by interval months."""
        h = _h(admin_token)
        
        title = f"TEST_monthly_recur_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/tasks", headers=h, json={
            "title": title,
            "due_date": "2026-03-15",
            "recurrence": {"pattern": "monthly", "interval": 2},
        }, timeout=10)
        task = r.json()
        tid = task["task_id"]
        
        # Mark done
        requests.put(f"{API}/tasks/{tid}", headers=h, json={"status": "done"}, timeout=10)
        
        # Find spawned task
        tasks = requests.get(f"{API}/tasks?search={title}", headers=h, timeout=10).json()["tasks"]
        new_tasks = [t for t in tasks if t["status"] == "open"]
        assert len(new_tasks) >= 1
        assert new_tasks[0]["due_date"] == "2026-05-15"  # +2 months
        
        # Cleanup
        for t in tasks:
            if title in t["title"]:
                requests.delete(f"{API}/tasks/{t['task_id']}", headers=h, timeout=10)

    def test_monthly_recurrence_end_of_month_fallback(self, admin_token):
        """Monthly recurrence handles Jan 31 -> Feb 28 fallback."""
        h = _h(admin_token)
        
        title = f"TEST_month_fallback_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/tasks", headers=h, json={
            "title": title,
            "due_date": "2026-01-31",
            "recurrence": {"pattern": "monthly", "interval": 1},
        }, timeout=10)
        task = r.json()
        tid = task["task_id"]
        
        # Mark done
        requests.put(f"{API}/tasks/{tid}", headers=h, json={"status": "done"}, timeout=10)
        
        # Find spawned task
        tasks = requests.get(f"{API}/tasks?search={title}", headers=h, timeout=10).json()["tasks"]
        new_tasks = [t for t in tasks if t["status"] == "open"]
        assert len(new_tasks) >= 1
        # Feb 2026 has 28 days, so should fallback to Feb 28
        assert new_tasks[0]["due_date"] == "2026-02-28", f"Expected 2026-02-28, got {new_tasks[0]['due_date']}"
        
        # Cleanup
        for t in tasks:
            if title in t["title"]:
                requests.delete(f"{API}/tasks/{t['task_id']}", headers=h, timeout=10)

    def test_recurrence_respects_end_date(self, admin_token):
        """Recurrence does NOT spawn if next_due > end_date."""
        h = _h(admin_token)
        
        title = f"TEST_recur_end_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/tasks", headers=h, json={
            "title": title,
            "due_date": "2026-01-20",
            "recurrence": {
                "pattern": "weekly",
                "interval": 1,
                "end_date": "2026-01-25",  # Next would be Jan 27, past end_date
            },
        }, timeout=10)
        task = r.json()
        tid = task["task_id"]
        
        # Mark done
        requests.put(f"{API}/tasks/{tid}", headers=h, json={"status": "done"}, timeout=10)
        
        # Search for tasks
        tasks = requests.get(f"{API}/tasks?search={title}", headers=h, timeout=10).json()["tasks"]
        matching = [t for t in tasks if title in t["title"]]
        
        # Should only have 1 task (the original, now done) - no new spawn
        open_tasks = [t for t in matching if t["status"] == "open"]
        assert len(open_tasks) == 0, f"Expected 0 open tasks (end_date passed), got {len(open_tasks)}"
        
        # Cleanup
        for t in matching:
            requests.delete(f"{API}/tasks/{t['task_id']}", headers=h, timeout=10)

    def test_recurrence_only_on_status_transition_to_done(self, admin_token):
        """Recurrence only spawns when status transitions TO done, not when created as done."""
        h = _h(admin_token)
        
        title = f"TEST_recur_create_done_{uuid.uuid4().hex[:6]}"
        # Create task directly with status=done (should NOT spawn)
        r = requests.post(f"{API}/tasks", headers=h, json={
            "title": title,
            "due_date": "2026-01-15",
            "status": "done",  # Created as done
            "recurrence": {"pattern": "weekly", "interval": 1},
        }, timeout=10)
        task = r.json()
        tid = task["task_id"]
        
        # Search for tasks
        tasks = requests.get(f"{API}/tasks?search={title}", headers=h, timeout=10).json()["tasks"]
        matching = [t for t in tasks if title in t["title"]]
        
        # Should only have 1 task (the original)
        assert len(matching) == 1, f"Expected 1 task (no spawn on create), got {len(matching)}"
        
        # Cleanup
        requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=10)


# ============ TEST 4: Template with Recurrence ============

class TestTemplateWithRecurrence:
    """Tests for templates that include recurrence settings."""

    def test_template_with_recurrence_creates_recurring_task(self, admin_token):
        """Template with recurrence creates a recurring task."""
        h = _h(admin_token)
        
        # Create template with recurrence
        name = f"TEST_tpl_recur_{uuid.uuid4().hex[:6]}"
        tpl = requests.post(f"{API}/task-templates", headers=h, json={
            "name": name,
            "title": "Recurring Template Task",
            "recurrence": {"pattern": "daily", "interval": 1},
        }, timeout=10).json()
        
        # Create task from template
        task = requests.post(f"{API}/tasks/from-template/{tpl['template_id']}", headers=h, json={
            "due_date": "2026-03-01",
        }, timeout=10).json()
        
        # Verify recurrence is set
        assert task["recurrence"] is not None
        assert task["recurrence"]["pattern"] == "daily"
        
        # Cleanup
        requests.delete(f"{API}/tasks/{task['task_id']}", headers=h, timeout=10)
        requests.delete(f"{API}/task-templates/{tpl['template_id']}", headers=h, timeout=10)
