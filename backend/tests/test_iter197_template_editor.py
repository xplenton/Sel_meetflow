"""Iter 197 — Task Template Editor Tests.
Tests for:
1. PUT /api/task-templates/{id} — admin/moderator can update template
2. PUT /api/task-templates/{id} — member without role gets 403
3. PUT /api/task-templates/{id} — non-existent id returns 404
4. Regression: GET/POST/DELETE /api/task-templates still work
5. Regression: POST /api/tasks/from-template/{id} still works
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
    email = f"task_iter197_member_{suffix}@example.com"
    requests.post(f"{API}/auth/register",
                  json={"email": email, "name": f"Member197 {suffix}", "password": "Test1234!"},
                  timeout=10)
    return _login(email, "Test1234!")


def _h(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


# ============ TEST 1: PUT /api/task-templates/{id} ============

class TestUpdateTemplate:
    """Tests for PUT /api/task-templates/{id} endpoint."""

    def test_admin_can_update_template_name(self, admin_token):
        """Admin can update template name."""
        h = _h(admin_token)
        
        # Create template
        name = f"TEST_update_name_{uuid.uuid4().hex[:6]}"
        tpl = requests.post(f"{API}/task-templates", headers=h, json={
            "name": name,
            "title": "Original Title",
            "description": "Original Desc",
            "priority": "normal",
        }, timeout=10).json()
        
        # Update name
        new_name = f"TEST_updated_name_{uuid.uuid4().hex[:6]}"
        r = requests.put(f"{API}/task-templates/{tpl['template_id']}", headers=h, json={
            "name": new_name,
        }, timeout=10)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        updated = r.json()
        
        # Verify update
        assert updated["name"] == new_name
        assert updated["title"] == "Original Title"  # Unchanged
        assert updated["template_id"] == tpl["template_id"]
        
        # Cleanup
        requests.delete(f"{API}/task-templates/{tpl['template_id']}", headers=h, timeout=10)

    def test_admin_can_update_template_all_fields(self, admin_token):
        """Admin can update all template fields."""
        h = _h(admin_token)
        
        # Create template
        name = f"TEST_update_all_{uuid.uuid4().hex[:6]}"
        tpl = requests.post(f"{API}/task-templates", headers=h, json={
            "name": name,
            "title": "Original Title",
            "description": "Original Desc",
            "priority": "low",
            "tags": ["old-tag"],
            "checklist": [{"text": "Old Step"}],
        }, timeout=10).json()
        
        # Update all fields
        r = requests.put(f"{API}/task-templates/{tpl['template_id']}", headers=h, json={
            "name": f"TEST_updated_all_{uuid.uuid4().hex[:6]}",
            "title": "Updated Title",
            "description": "Updated Description",
            "priority": "urgent",
            "tags": ["new-tag", "another-tag"],
            "checklist": [{"text": "New Step 1"}, {"text": "New Step 2"}],
            "recurrence": {"pattern": "weekly", "interval": 2},
        }, timeout=10)
        assert r.status_code == 200
        updated = r.json()
        
        # Verify all updates
        assert updated["title"] == "Updated Title"
        assert updated["description"] == "Updated Description"
        assert updated["priority"] == "urgent"
        assert "new-tag" in updated["tags"]
        assert len(updated["checklist"]) == 2
        assert updated["recurrence"]["pattern"] == "weekly"
        assert updated["recurrence"]["interval"] == 2
        
        # Cleanup
        requests.delete(f"{API}/task-templates/{tpl['template_id']}", headers=h, timeout=10)

    def test_admin_can_update_template_assignees_and_groups(self, admin_token):
        """Admin can update template assignee_ids and group_ids."""
        h = _h(admin_token)
        
        # Get admin user_id
        me = requests.get(f"{API}/auth/me", headers=h, timeout=10).json()
        admin_uid = me["user_id"]
        
        # Create template
        name = f"TEST_update_assignees_{uuid.uuid4().hex[:6]}"
        tpl = requests.post(f"{API}/task-templates", headers=h, json={
            "name": name,
            "title": name,
        }, timeout=10).json()
        
        # Update with assignee_ids
        r = requests.put(f"{API}/task-templates/{tpl['template_id']}", headers=h, json={
            "assignee_ids": [admin_uid],
            "group_ids": ["test_group_1"],
        }, timeout=10)
        assert r.status_code == 200
        updated = r.json()
        
        # Verify updates
        assert admin_uid in updated["assignee_ids"]
        assert "test_group_1" in updated["group_ids"]
        
        # Cleanup
        requests.delete(f"{API}/task-templates/{tpl['template_id']}", headers=h, timeout=10)

    def test_member_cannot_update_template(self, admin_token, member):
        """Member without admin/moderator role gets 403."""
        ah = _h(admin_token)
        mh = _h(member["token"])
        
        # Admin creates template
        name = f"TEST_member_noupdate_{uuid.uuid4().hex[:6]}"
        tpl = requests.post(f"{API}/task-templates", headers=ah, json={
            "name": name,
            "title": name,
        }, timeout=10).json()
        
        # Member tries to update → 403
        r = requests.put(f"{API}/task-templates/{tpl['template_id']}", headers=mh, json={
            "name": "Hijacked Name",
        }, timeout=10)
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
        
        # Verify template unchanged
        templates = requests.get(f"{API}/task-templates", headers=ah, timeout=10).json()
        found = next((t for t in templates if t["template_id"] == tpl["template_id"]), None)
        assert found is not None
        assert found["name"] == name  # Unchanged
        
        # Cleanup
        requests.delete(f"{API}/task-templates/{tpl['template_id']}", headers=ah, timeout=10)

    def test_update_nonexistent_template_returns_404(self, admin_token):
        """PUT /api/task-templates/{id} with non-existent id returns 404."""
        h = _h(admin_token)
        
        r = requests.put(f"{API}/task-templates/nonexistent_tpl_xyz123", headers=h, json={
            "name": "Should Not Work",
        }, timeout=10)
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_update_template_checklist_regenerates_ids(self, admin_token):
        """Updating checklist regenerates checklist item IDs."""
        h = _h(admin_token)
        
        # Create template with checklist
        name = f"TEST_checklist_ids_{uuid.uuid4().hex[:6]}"
        tpl = requests.post(f"{API}/task-templates", headers=h, json={
            "name": name,
            "title": name,
            "checklist": [{"text": "Step 1"}],
        }, timeout=10).json()
        
        original_cl_id = tpl["checklist"][0]["id"]
        
        # Update checklist
        r = requests.put(f"{API}/task-templates/{tpl['template_id']}", headers=h, json={
            "checklist": [{"text": "New Step 1"}, {"text": "New Step 2"}],
        }, timeout=10)
        assert r.status_code == 200
        updated = r.json()
        
        # Verify new checklist
        assert len(updated["checklist"]) == 2
        assert updated["checklist"][0]["text"] == "New Step 1"
        # IDs should be generated (start with cl_)
        for cl in updated["checklist"]:
            assert cl["id"].startswith("cl_")
            assert cl["done"] is False
        
        # Cleanup
        requests.delete(f"{API}/task-templates/{tpl['template_id']}", headers=h, timeout=10)


# ============ TEST 2: Regression Tests ============

class TestTemplateRegression:
    """Regression tests for iter196 template functionality."""

    def test_get_templates_still_works(self, admin_token):
        """GET /api/task-templates still works."""
        h = _h(admin_token)
        r = requests.get(f"{API}/task-templates", headers=h, timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_post_templates_still_works(self, admin_token):
        """POST /api/task-templates still works."""
        h = _h(admin_token)
        name = f"TEST_regression_post_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/task-templates", headers=h, json={
            "name": name,
            "title": name,
        }, timeout=10)
        assert r.status_code == 200
        tpl = r.json()
        assert tpl["name"] == name
        
        # Cleanup
        requests.delete(f"{API}/task-templates/{tpl['template_id']}", headers=h, timeout=10)

    def test_delete_templates_still_works(self, admin_token):
        """DELETE /api/task-templates/{id} still works."""
        h = _h(admin_token)
        
        # Create
        name = f"TEST_regression_delete_{uuid.uuid4().hex[:6]}"
        tpl = requests.post(f"{API}/task-templates", headers=h, json={
            "name": name, "title": name,
        }, timeout=10).json()
        
        # Delete
        r = requests.delete(f"{API}/task-templates/{tpl['template_id']}", headers=h, timeout=10)
        assert r.status_code == 200
        assert r.json()["deleted"] is True

    def test_create_from_template_still_works(self, admin_token):
        """POST /api/tasks/from-template/{id} still works."""
        h = _h(admin_token)
        
        # Create template
        name = f"TEST_regression_apply_{uuid.uuid4().hex[:6]}"
        tpl = requests.post(f"{API}/task-templates", headers=h, json={
            "name": name,
            "title": "Regression Test Task",
            "priority": "high",
        }, timeout=10).json()
        
        # Apply template
        r = requests.post(f"{API}/tasks/from-template/{tpl['template_id']}", headers=h, json={}, timeout=10)
        assert r.status_code == 200
        task = r.json()
        assert task["title"] == "Regression Test Task"
        assert task["priority"] == "high"
        
        # Cleanup
        requests.delete(f"{API}/tasks/{task['task_id']}", headers=h, timeout=10)
        requests.delete(f"{API}/task-templates/{tpl['template_id']}", headers=h, timeout=10)
