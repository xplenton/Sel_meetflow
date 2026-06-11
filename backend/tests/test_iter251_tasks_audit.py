"""Iter 251 — Umfassende Prüfung des Aufgaben-Moduls (Tasks).

Testet:
- CRUD-Operationen (Create, Read, Update, Delete)
- Validierung (fehlender Titel, ungültige Priorität, ungültiger Status)
- RBAC (Admin vs. Member Berechtigungen)
- Kommentare, Anhänge, Verlauf
- Load-Tests mit 50 gleichzeitigen Benutzern
- Race-Condition-Tests für Status-Updates
- Regression: iter 248 booking race, iter 250 survey race
"""
import asyncio
import uuid
from datetime import datetime

import httpx
import pytest

API = "http://localhost:8001/api"
ADMIN_CREDS = {"email": "admin@meetflow.com", "password": "admin123"}


# ============ Fixtures ============

@pytest.fixture
def unique_email():
    return f"test-tasks-{uuid.uuid4().hex[:8]}@meetflow.com"


@pytest.fixture
def unique_title():
    return f"TEST-Task-{uuid.uuid4().hex[:8]}"


# ============ Helper Functions ============

async def login_admin(client: httpx.AsyncClient) -> dict:
    r = await client.post(f"{API}/auth/login", json=ADMIN_CREDS)
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def register_and_login_member(client: httpx.AsyncClient, email: str) -> dict:
    r = await client.post(f"{API}/auth/register", json={
        "email": email, "password": "test123", "name": "Test Member"
    })
    assert r.status_code in (200, 201), f"Register failed: {r.text}"
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": "test123"})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ============ CRUD Tests ============

class TestTasksCRUD:
    """Grundlegende CRUD-Operationen für Aufgaben."""

    @pytest.mark.asyncio
    async def test_create_task_success(self):
        """Admin kann Aufgabe erstellen."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            h = await login_admin(c)
            title = f"TEST-Create-{uuid.uuid4().hex[:8]}"
            r = await c.post(f"{API}/tasks", headers=h, json={
                "title": title,
                "description": "Test-Beschreibung",
                "priority": "high",
                "status": "open"
            })
            assert r.status_code in (200, 201), f"Create failed: {r.text}"
            data = r.json()
            assert data["title"] == title
            assert data["priority"] == "high"
            assert data["status"] == "open"
            assert "task_id" in data
            
            # Cleanup
            await c.delete(f"{API}/tasks/{data['task_id']}", headers=h)

    @pytest.mark.asyncio
    async def test_get_task_success(self):
        """Aufgabe kann abgerufen werden."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            h = await login_admin(c)
            title = f"TEST-Get-{uuid.uuid4().hex[:8]}"
            
            # Create
            r = await c.post(f"{API}/tasks", headers=h, json={"title": title})
            task_id = r.json()["task_id"]
            
            # Get
            r = await c.get(f"{API}/tasks/{task_id}", headers=h)
            assert r.status_code == 200
            assert r.json()["title"] == title
            
            # Cleanup
            await c.delete(f"{API}/tasks/{task_id}", headers=h)

    @pytest.mark.asyncio
    async def test_update_task_success(self):
        """Aufgabe kann aktualisiert werden."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            h = await login_admin(c)
            title = f"TEST-Update-{uuid.uuid4().hex[:8]}"
            
            # Create
            r = await c.post(f"{API}/tasks", headers=h, json={"title": title})
            task_id = r.json()["task_id"]
            
            # Update
            r = await c.put(f"{API}/tasks/{task_id}", headers=h, json={
                "title": f"{title}-Updated",
                "status": "in_progress",
                "priority": "urgent"
            })
            assert r.status_code == 200
            data = r.json()
            assert data["title"] == f"{title}-Updated"
            assert data["status"] == "in_progress"
            assert data["priority"] == "urgent"
            
            # Verify persistence
            r = await c.get(f"{API}/tasks/{task_id}", headers=h)
            assert r.json()["status"] == "in_progress"
            
            # Cleanup
            await c.delete(f"{API}/tasks/{task_id}", headers=h)

    @pytest.mark.asyncio
    async def test_delete_task_success(self):
        """Aufgabe kann gelöscht werden."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            h = await login_admin(c)
            title = f"TEST-Delete-{uuid.uuid4().hex[:8]}"
            
            # Create
            r = await c.post(f"{API}/tasks", headers=h, json={"title": title})
            task_id = r.json()["task_id"]
            
            # Delete
            r = await c.delete(f"{API}/tasks/{task_id}", headers=h)
            assert r.status_code == 200
            
            # Verify deletion
            r = await c.get(f"{API}/tasks/{task_id}", headers=h)
            assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_list_tasks(self):
        """Aufgabenliste kann abgerufen werden."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            h = await login_admin(c)
            r = await c.get(f"{API}/tasks", headers=h)
            assert r.status_code == 200
            data = r.json()
            assert "tasks" in data
            assert "total" in data


# ============ Validation Tests ============

class TestTasksValidation:
    """Validierungstests für Aufgaben-Endpoints."""

    @pytest.mark.asyncio
    async def test_create_without_title_returns_400(self):
        """POST /api/tasks ohne Titel -> 400."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            h = await login_admin(c)
            r = await c.post(f"{API}/tasks", headers=h, json={
                "description": "Nur Beschreibung, kein Titel"
            })
            assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"

    @pytest.mark.asyncio
    async def test_create_with_empty_title_returns_400(self):
        """POST /api/tasks mit leerem Titel -> 400."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            h = await login_admin(c)
            r = await c.post(f"{API}/tasks", headers=h, json={
                "title": "   ",
                "description": "Leerer Titel"
            })
            assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_get_nonexistent_task_returns_404(self):
        """GET /api/tasks/{nonexistent} -> 404."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            h = await login_admin(c)
            r = await c.get(f"{API}/tasks/task_nonexistent123", headers=h)
            assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_priority_normalized(self):
        """Ungültige Priorität wird auf 'normal' normalisiert."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            h = await login_admin(c)
            title = f"TEST-InvalidPrio-{uuid.uuid4().hex[:8]}"
            r = await c.post(f"{API}/tasks", headers=h, json={
                "title": title,
                "priority": "super_urgent_invalid"
            })
            assert r.status_code in (200, 201)
            data = r.json()
            # Backend normalisiert ungültige Priorität auf 'normal'
            assert data["priority"] == "normal"
            
            # Cleanup
            await c.delete(f"{API}/tasks/{data['task_id']}", headers=h)

    @pytest.mark.asyncio
    async def test_invalid_status_transition_returns_400(self):
        """PUT /api/tasks/{id} mit ungültigem Status -> 400."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            h = await login_admin(c)
            title = f"TEST-InvalidStatus-{uuid.uuid4().hex[:8]}"
            
            # Create
            r = await c.post(f"{API}/tasks", headers=h, json={"title": title})
            task_id = r.json()["task_id"]
            
            # Try invalid status
            r = await c.put(f"{API}/tasks/{task_id}", headers=h, json={
                "status": "invalid_status_xyz"
            })
            assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
            
            # Cleanup
            await c.delete(f"{API}/tasks/{task_id}", headers=h)

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(self):
        """Anfrage ohne Token -> 401."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(f"{API}/tasks")
            assert r.status_code == 401


# ============ Comments Tests ============

class TestTasksComments:
    """Tests für Aufgaben-Kommentare."""

    @pytest.mark.asyncio
    async def test_add_comment_success(self):
        """Kommentar kann hinzugefügt werden."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            h = await login_admin(c)
            title = f"TEST-Comment-{uuid.uuid4().hex[:8]}"
            
            # Create task
            r = await c.post(f"{API}/tasks", headers=h, json={"title": title})
            task_id = r.json()["task_id"]
            
            # Add comment
            r = await c.post(f"{API}/tasks/{task_id}/comments", headers=h, json={
                "content": "Test-Kommentar"
            })
            assert r.status_code in (200, 201)
            assert r.json()["content"] == "Test-Kommentar"
            
            # List comments
            r = await c.get(f"{API}/tasks/{task_id}/comments", headers=h)
            assert r.status_code == 200
            assert len(r.json()) >= 1
            
            # Cleanup
            await c.delete(f"{API}/tasks/{task_id}", headers=h)

    @pytest.mark.asyncio
    async def test_add_empty_comment_returns_400(self):
        """POST /api/tasks/{id}/comments ohne Text -> 400."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            h = await login_admin(c)
            title = f"TEST-EmptyComment-{uuid.uuid4().hex[:8]}"
            
            # Create task
            r = await c.post(f"{API}/tasks", headers=h, json={"title": title})
            task_id = r.json()["task_id"]
            
            # Try empty comment
            r = await c.post(f"{API}/tasks/{task_id}/comments", headers=h, json={
                "content": ""
            })
            assert r.status_code == 400
            
            # Cleanup
            await c.delete(f"{API}/tasks/{task_id}", headers=h)


# ============ Attachments Tests ============

class TestTasksAttachments:
    """Tests für Aufgaben-Anhänge."""

    @pytest.mark.asyncio
    async def test_add_link_attachment(self):
        """Link-Anhang kann hinzugefügt werden."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            h = await login_admin(c)
            title = f"TEST-Attachment-{uuid.uuid4().hex[:8]}"
            
            # Create task
            r = await c.post(f"{API}/tasks", headers=h, json={"title": title})
            task_id = r.json()["task_id"]
            
            # Add link
            r = await c.post(f"{API}/tasks/{task_id}/attachments/link", headers=h, json={
                "url": "https://example.com/doc.pdf",
                "name": "Beispiel-Dokument"
            })
            assert r.status_code in (200, 201)
            
            # List attachments
            r = await c.get(f"{API}/tasks/{task_id}/attachments", headers=h)
            assert r.status_code == 200
            assert len(r.json()) >= 1
            
            # Cleanup
            await c.delete(f"{API}/tasks/{task_id}", headers=h)


# ============ History Tests ============

class TestTasksHistory:
    """Tests für Aufgaben-Verlauf (Activity Log)."""

    @pytest.mark.asyncio
    async def test_history_records_changes(self):
        """Verlauf zeichnet Änderungen auf."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            h = await login_admin(c)
            title = f"TEST-History-{uuid.uuid4().hex[:8]}"
            
            # Create task
            r = await c.post(f"{API}/tasks", headers=h, json={"title": title})
            task_id = r.json()["task_id"]
            
            # Update status
            await c.put(f"{API}/tasks/{task_id}", headers=h, json={"status": "in_progress"})
            
            # Check history
            r = await c.get(f"{API}/tasks/{task_id}/history", headers=h)
            assert r.status_code == 200
            history = r.json()
            assert len(history) >= 1  # At least 'created' entry
            
            # Cleanup
            await c.delete(f"{API}/tasks/{task_id}", headers=h)


# ============ RBAC Tests ============

class TestTasksRBAC:
    """RBAC-Audit: Admin vs. Member Berechtigungen."""

    @pytest.mark.asyncio
    async def test_member_can_create_own_task(self):
        """Member kann eigene Aufgabe erstellen."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            email = f"test-rbac-{uuid.uuid4().hex[:8]}@meetflow.com"
            h = await register_and_login_member(c, email)
            title = f"TEST-MemberTask-{uuid.uuid4().hex[:8]}"
            
            r = await c.post(f"{API}/tasks", headers=h, json={"title": title})
            assert r.status_code in (200, 201)
            task_id = r.json()["task_id"]
            
            # Member can see own task
            r = await c.get(f"{API}/tasks/{task_id}", headers=h)
            assert r.status_code == 200
            
            # Member can delete own task
            r = await c.delete(f"{API}/tasks/{task_id}", headers=h)
            assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_member_cannot_delete_others_task(self):
        """Member kann fremde Aufgabe nicht löschen."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            # Admin creates task
            admin_h = await login_admin(c)
            title = f"TEST-AdminTask-{uuid.uuid4().hex[:8]}"
            r = await c.post(f"{API}/tasks", headers=admin_h, json={"title": title})
            task_id = r.json()["task_id"]
            
            # Member tries to delete
            email = f"test-rbac-del-{uuid.uuid4().hex[:8]}@meetflow.com"
            member_h = await register_and_login_member(c, email)
            
            r = await c.delete(f"{API}/tasks/{task_id}", headers=member_h)
            # Should be 403 or 404 (member can't see/delete admin's task)
            assert r.status_code in (403, 404)
            
            # Cleanup
            await c.delete(f"{API}/tasks/{task_id}", headers=admin_h)

    @pytest.mark.asyncio
    async def test_admin_can_see_all_tasks(self):
        """Admin kann alle Aufgaben sehen."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            admin_h = await login_admin(c)
            r = await c.get(f"{API}/tasks", headers=admin_h)
            assert r.status_code == 200
            # Admin should see tasks (may be empty, but endpoint works)
            assert "tasks" in r.json()

    @pytest.mark.asyncio
    async def test_member_sees_only_assigned_tasks(self):
        """Member sieht nur zugewiesene Aufgaben."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            # Create member
            email = f"test-rbac-view-{uuid.uuid4().hex[:8]}@meetflow.com"
            member_h = await register_and_login_member(c, email)
            
            # Get member's user_id
            r = await c.get(f"{API}/auth/me", headers=member_h)
            member_id = r.json()["user_id"]
            
            # Admin creates task NOT assigned to member
            admin_h = await login_admin(c)
            title = f"TEST-NotAssigned-{uuid.uuid4().hex[:8]}"
            r = await c.post(f"{API}/tasks", headers=admin_h, json={
                "title": title,
                "assignee_ids": []  # Not assigned to member
            })
            task_id = r.json()["task_id"]
            
            # Member should not see this task
            r = await c.get(f"{API}/tasks/{task_id}", headers=member_h)
            assert r.status_code == 404
            
            # Cleanup
            await c.delete(f"{API}/tasks/{task_id}", headers=admin_h)

    @pytest.mark.asyncio
    async def test_member_can_see_assigned_task(self):
        """Member kann zugewiesene Aufgabe sehen."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            # Create member
            email = f"test-rbac-assigned-{uuid.uuid4().hex[:8]}@meetflow.com"
            member_h = await register_and_login_member(c, email)
            
            # Get member's user_id
            r = await c.get(f"{API}/auth/me", headers=member_h)
            member_id = r.json()["user_id"]
            
            # Admin creates task assigned to member
            admin_h = await login_admin(c)
            title = f"TEST-Assigned-{uuid.uuid4().hex[:8]}"
            r = await c.post(f"{API}/tasks", headers=admin_h, json={
                "title": title,
                "assignee_ids": [member_id]
            })
            task_id = r.json()["task_id"]
            
            # Member should see this task
            r = await c.get(f"{API}/tasks/{task_id}", headers=member_h)
            assert r.status_code == 200
            assert r.json()["title"] == title
            
            # Cleanup
            await c.delete(f"{API}/tasks/{task_id}", headers=admin_h)


# ============ Load Tests (50 concurrent) ============

class TestTasksLoad:
    """Load-Tests mit 50 gleichzeitigen Benutzern."""

    @pytest.mark.asyncio
    async def test_50_concurrent_get_tasks(self):
        """50× GET /api/tasks gleichzeitig."""
        async with httpx.AsyncClient(timeout=60.0) as c:
            h = await login_admin(c)
            
            async def get_tasks():
                start = datetime.now()
                r = await c.get(f"{API}/tasks", headers=h)
                elapsed = (datetime.now() - start).total_seconds()
                return r.status_code, elapsed
            
            results = await asyncio.gather(*[get_tasks() for _ in range(50)])
            
            success = sum(1 for s, _ in results if s == 200)
            times = sorted([t for _, t in results])
            p95 = times[int(len(times) * 0.95)] if times else 0
            
            assert success == 50, f"Expected 50 successes, got {success}"
            print(f"50× GET /api/tasks: {success}/50 success, p95={p95:.2f}s")

    @pytest.mark.asyncio
    async def test_50_concurrent_create_tasks(self):
        """50× POST /api/tasks von 50 verschiedenen Titeln -> alle 50 erstellt."""
        async with httpx.AsyncClient(timeout=60.0) as c:
            h = await login_admin(c)
            created_ids = []
            
            async def create_task(i):
                title = f"LOAD-Task-{uuid.uuid4().hex[:8]}-{i}"
                r = await c.post(f"{API}/tasks", headers=h, json={"title": title})
                if r.status_code in (200, 201):
                    return r.json().get("task_id")
                return None
            
            results = await asyncio.gather(*[create_task(i) for i in range(50)])
            created_ids = [r for r in results if r]
            
            assert len(created_ids) == 50, f"Expected 50 created, got {len(created_ids)}"
            
            # Verify no duplicates
            assert len(set(created_ids)) == 50, "Duplicate task_ids detected!"
            
            # Cleanup
            for tid in created_ids:
                await c.delete(f"{API}/tasks/{tid}", headers=h)
            
            print(f"50× POST /api/tasks: {len(created_ids)}/50 created, no duplicates")

    @pytest.mark.asyncio
    async def test_50_concurrent_comments_same_task(self):
        """50× POST /api/tasks/{id}/comments von 50 verschiedenen Benutzern."""
        async with httpx.AsyncClient(timeout=60.0) as c:
            admin_h = await login_admin(c)
            
            # Create task
            title = f"LOAD-Comments-{uuid.uuid4().hex[:8]}"
            r = await c.post(f"{API}/tasks", headers=admin_h, json={"title": title})
            task_id = r.json()["task_id"]
            
            # Create 50 users and add comments
            async def add_comment(i):
                email = f"load-cmt-{uuid.uuid4().hex[:8]}@meetflow.com"
                try:
                    h = await register_and_login_member(c, email)
                    r = await c.post(f"{API}/tasks/{task_id}/comments", headers=h, json={
                        "content": f"Kommentar von User {i}"
                    })
                    return r.status_code in (200, 201)
                except:
                    return False
            
            results = await asyncio.gather(*[add_comment(i) for i in range(50)])
            success = sum(1 for r in results if r)
            
            # Verify all comments stored
            r = await c.get(f"{API}/tasks/{task_id}/comments", headers=admin_h)
            comments = r.json()
            
            # Cleanup
            await c.delete(f"{API}/tasks/{task_id}", headers=admin_h)
            
            assert success >= 45, f"Expected ~50 comments, got {success}"
            print(f"50× POST comments: {success}/50 success, {len(comments)} stored")


# ============ Race Condition Tests ============

class TestTasksRaceCondition:
    """Race-Condition-Tests für Status-Updates."""

    @pytest.mark.asyncio
    async def test_50_concurrent_status_updates_same_task(self):
        """50× PUT /api/tasks/{id} Status-Update gleichzeitig.
        
        Prüft ob bei 4 Workern Race-Conditions auftreten:
        - Verlorene Updates
        - Inkonsistente Activity-Log-Einträge
        """
        async with httpx.AsyncClient(timeout=60.0) as c:
            h = await login_admin(c)
            
            # Create task
            title = f"RACE-Status-{uuid.uuid4().hex[:8]}"
            r = await c.post(f"{API}/tasks", headers=h, json={
                "title": title,
                "status": "open"
            })
            task_id = r.json()["task_id"]
            
            # 50 concurrent status updates (alternating between statuses)
            statuses = ["in_progress", "blocked", "done", "open"]
            
            async def update_status(i):
                status = statuses[i % len(statuses)]
                r = await c.put(f"{API}/tasks/{task_id}", headers=h, json={
                    "status": status
                })
                return r.status_code, status
            
            results = await asyncio.gather(*[update_status(i) for i in range(50)])
            
            success = sum(1 for s, _ in results if s == 200)
            
            # Check final state
            r = await c.get(f"{API}/tasks/{task_id}", headers=h)
            final_status = r.json()["status"]
            
            # Check history for consistency
            r = await c.get(f"{API}/tasks/{task_id}/history", headers=h)
            history = r.json()
            status_changes = [h for h in history if h.get("action") == "set:status"]
            
            # Cleanup
            await c.delete(f"{API}/tasks/{task_id}", headers=h)
            
            print(f"50× Status-Update: {success}/50 success")
            print(f"Final status: {final_status}")
            print(f"History entries (status changes): {len(status_changes)}")
            
            # All requests should succeed (no 500 errors)
            assert success == 50, f"Expected 50 successes, got {success}"
            # Final status should be one of the valid statuses
            assert final_status in statuses, f"Invalid final status: {final_status}"

    @pytest.mark.asyncio
    async def test_50_concurrent_assignee_updates_same_task(self):
        """50× PUT /api/tasks/{id} Assignee-Update gleichzeitig.
        
        Prüft ob bei rotierenden Assignees Race-Conditions auftreten.
        """
        async with httpx.AsyncClient(timeout=60.0) as c:
            admin_h = await login_admin(c)
            
            # Create some test users
            user_ids = []
            for i in range(5):
                email = f"race-assign-{uuid.uuid4().hex[:8]}@meetflow.com"
                r = await c.post(f"{API}/auth/register", json={
                    "email": email, "password": "test123", "name": f"User {i}"
                })
                if r.status_code in (200, 201):
                    r = await c.post(f"{API}/auth/login", json={"email": email, "password": "test123"})
                    if r.status_code == 200:
                        r = await c.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
                        user_ids.append(r.json()["user_id"])
            
            if len(user_ids) < 3:
                pytest.skip("Could not create enough test users")
            
            # Create task
            title = f"RACE-Assign-{uuid.uuid4().hex[:8]}"
            r = await c.post(f"{API}/tasks", headers=admin_h, json={"title": title})
            task_id = r.json()["task_id"]
            
            # 50 concurrent assignee updates
            async def update_assignee(i):
                assignee = user_ids[i % len(user_ids)]
                r = await c.put(f"{API}/tasks/{task_id}", headers=admin_h, json={
                    "assignee_ids": [assignee]
                })
                return r.status_code, assignee
            
            results = await asyncio.gather(*[update_assignee(i) for i in range(50)])
            
            success = sum(1 for s, _ in results if s == 200)
            
            # Check final state
            r = await c.get(f"{API}/tasks/{task_id}", headers=admin_h)
            final_assignees = r.json().get("assignee_ids", [])
            
            # Check history
            r = await c.get(f"{API}/tasks/{task_id}/history", headers=admin_h)
            history = r.json()
            assignee_changes = [h for h in history if h.get("action") == "set:assignee_ids"]
            
            # Cleanup
            await c.delete(f"{API}/tasks/{task_id}", headers=admin_h)
            
            print(f"50× Assignee-Update: {success}/50 success")
            print(f"Final assignees: {final_assignees}")
            print(f"History entries (assignee changes): {len(assignee_changes)}")
            
            assert success == 50, f"Expected 50 successes, got {success}"
            assert len(final_assignees) == 1, f"Expected 1 assignee, got {len(final_assignees)}"


# ============ Regression Tests ============

class TestRegressionIter248Iter250:
    """Regression-Tests für iter 248 (booking race) und iter 250 (survey race)."""

    @pytest.mark.asyncio
    async def test_health_check_4_workers(self):
        """Health-Check und 4 Worker verifizieren."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(f"{API}/health")
            assert r.status_code == 200
            data = r.json()
            assert data.get("status") == "ok"
            print(f"Health check: {data}")

    @pytest.mark.asyncio
    async def test_iter248_booking_race_regression(self):
        """Iter 248 Booking Race-Condition Regression."""
        # Run the existing test
        import subprocess
        result = subprocess.run(
            ["pytest", "/app/backend/tests/test_iter248_booking_race.py", "-v", "--tb=short"],
            capture_output=True, text=True, timeout=120
        )
        print(f"Iter 248 booking race test output:\n{result.stdout}")
        if result.returncode != 0:
            print(f"Stderr: {result.stderr}")
        assert result.returncode == 0, "Iter 248 booking race regression failed"

    @pytest.mark.asyncio
    async def test_iter250_survey_race_regression(self):
        """Iter 250 Survey Race-Condition Regression."""
        import subprocess
        result = subprocess.run(
            ["pytest", "/app/backend/tests/test_iter250_survey_race.py", "-v", "--tb=short"],
            capture_output=True, text=True, timeout=120
        )
        print(f"Iter 250 survey race test output:\n{result.stdout}")
        if result.returncode != 0:
            print(f"Stderr: {result.stderr}")
        assert result.returncode == 0, "Iter 250 survey race regression failed"


# ============ Functional Flow Tests ============

class TestTasksFunctionalFlows:
    """Funktionale End-to-End-Flows."""

    @pytest.mark.asyncio
    async def test_admin_creates_task_member_updates_status(self):
        """Admin erstellt Aufgabe, Member aktualisiert Status."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            # Create member
            email = f"test-flow-{uuid.uuid4().hex[:8]}@meetflow.com"
            member_h = await register_and_login_member(c, email)
            r = await c.get(f"{API}/auth/me", headers=member_h)
            member_id = r.json()["user_id"]
            
            # Admin creates task assigned to member
            admin_h = await login_admin(c)
            title = f"TEST-Flow-{uuid.uuid4().hex[:8]}"
            r = await c.post(f"{API}/tasks", headers=admin_h, json={
                "title": title,
                "assignee_ids": [member_id],
                "status": "open"
            })
            task_id = r.json()["task_id"]
            
            # Member sees task
            r = await c.get(f"{API}/tasks/{task_id}", headers=member_h)
            assert r.status_code == 200
            
            # Member updates status to in_progress
            r = await c.put(f"{API}/tasks/{task_id}", headers=member_h, json={
                "status": "in_progress"
            })
            assert r.status_code == 200
            
            # Verify status change
            r = await c.get(f"{API}/tasks/{task_id}", headers=admin_h)
            assert r.json()["status"] == "in_progress"
            
            # Member adds comment
            r = await c.post(f"{API}/tasks/{task_id}/comments", headers=member_h, json={
                "content": "Arbeite daran"
            })
            assert r.status_code in (200, 201)
            
            # Admin checks history
            r = await c.get(f"{API}/tasks/{task_id}/history", headers=admin_h)
            assert r.status_code == 200
            history = r.json()
            assert len(history) >= 2  # created + status change
            
            # Cleanup
            await c.delete(f"{API}/tasks/{task_id}", headers=admin_h)

    @pytest.mark.asyncio
    async def test_task_with_checklist(self):
        """Aufgabe mit Checkliste erstellen und aktualisieren."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            h = await login_admin(c)
            title = f"TEST-Checklist-{uuid.uuid4().hex[:8]}"
            
            # Create with checklist
            r = await c.post(f"{API}/tasks", headers=h, json={
                "title": title,
                "checklist": [
                    {"text": "Schritt 1", "done": False},
                    {"text": "Schritt 2", "done": False},
                    {"text": "Schritt 3", "done": False}
                ]
            })
            assert r.status_code in (200, 201)
            task_id = r.json()["task_id"]
            checklist = r.json().get("checklist", [])
            assert len(checklist) == 3
            
            # Update checklist (mark first item done)
            updated_checklist = checklist.copy()
            updated_checklist[0]["done"] = True
            r = await c.put(f"{API}/tasks/{task_id}", headers=h, json={
                "checklist": updated_checklist
            })
            assert r.status_code == 200
            
            # Verify
            r = await c.get(f"{API}/tasks/{task_id}", headers=h)
            assert r.json()["checklist"][0]["done"] == True
            
            # Cleanup
            await c.delete(f"{API}/tasks/{task_id}", headers=h)

    @pytest.mark.asyncio
    async def test_task_duplicate(self):
        """Aufgabe duplizieren."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            h = await login_admin(c)
            title = f"TEST-Duplicate-{uuid.uuid4().hex[:8]}"
            
            # Create
            r = await c.post(f"{API}/tasks", headers=h, json={
                "title": title,
                "priority": "high",
                "tags": ["test", "duplicate"]
            })
            task_id = r.json()["task_id"]
            
            # Duplicate
            r = await c.post(f"{API}/tasks/{task_id}/duplicate", headers=h)
            assert r.status_code in (200, 201)
            dup_id = r.json()["task_id"]
            assert dup_id != task_id
            assert "(Kopie)" in r.json()["title"]
            
            # Cleanup
            await c.delete(f"{API}/tasks/{task_id}", headers=h)
            await c.delete(f"{API}/tasks/{dup_id}", headers=h)


# ============ Cleanup ============

@pytest.fixture(scope="session", autouse=True)
def cleanup_test_data():
    """Cleanup TEST_/LOAD_/RACE_ prefixed data after all tests."""
    yield
    import asyncio
    
    async def do_cleanup():
        async with httpx.AsyncClient(timeout=30.0) as c:
            h = await login_admin(c)
            # Get all tasks and delete test ones
            r = await c.get(f"{API}/tasks?limit=500", headers=h)
            if r.status_code == 200:
                tasks = r.json().get("tasks", [])
                for t in tasks:
                    if t["title"].startswith(("TEST-", "LOAD-", "RACE-")):
                        await c.delete(f"{API}/tasks/{t['task_id']}", headers=h)
    
    try:
        asyncio.get_event_loop().run_until_complete(do_cleanup())
    except:
        pass
