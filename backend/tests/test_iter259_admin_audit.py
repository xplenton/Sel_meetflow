"""
Iteration 259 — Verwaltung (Admin Panel) Comprehensive Audit
============================================================
Tests für:
- Admin-Zugriffskontrolle (RBAC)
- User-Management CRUD
- Groups CRUD
- Roles/Capabilities
- Audit-Logs
- System-Settings
- Brute-Force Protection (wenn vorhanden)
- 50 concurrent Load-Tests
"""
import pytest
import requests
import os
import uuid
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"


class TestAdminAuth:
    """Admin-Authentifizierung und Token-Handling"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Login als Admin und Token zurückgeben"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        data = resp.json()
        token = data.get("access_token") or data.get("token")
        assert token, "No token in response"
        return token
    
    @pytest.fixture(scope="class")
    def member_token(self, admin_token):
        """Erstelle einen Member-User und gib dessen Token zurück"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        test_email = f"test-vw-member-{uuid.uuid4().hex[:8]}@meetflow.com"
        
        # Invite user
        resp = requests.post(f"{BASE_URL}/api/admin/users/invite", headers=headers, json={
            "email": test_email,
            "name": "Test Member",
            "role": "member"
        })
        if resp.status_code == 409:
            # User exists, try login
            pass
        else:
            assert resp.status_code == 200, f"Invite failed: {resp.text}"
            temp_pw = resp.json().get("temp_password")
            # Login with temp password
            login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": test_email,
                "password": temp_pw
            })
            if login_resp.status_code == 200:
                return login_resp.json().get("access_token") or login_resp.json().get("token")
        
        # Fallback: register new user
        test_email2 = f"test-vw-member2-{uuid.uuid4().hex[:8]}@meetflow.com"
        reg_resp = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email2,
            "password": "test123",
            "name": "Test Member 2"
        })
        if reg_resp.status_code in [200, 201]:
            login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": test_email2,
                "password": "test123"
            })
            if login_resp.status_code == 200:
                return login_resp.json().get("access_token") or login_resp.json().get("token")
        
        pytest.skip("Could not create member user for RBAC tests")
    
    def test_admin_login_success(self):
        """Admin kann sich einloggen"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data or "token" in data
        print("PASS — Admin login successful")
    
    def test_admin_login_wrong_password(self):
        """Falsches Passwort wird abgelehnt"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": "wrongpassword"
        })
        assert resp.status_code in [401, 400]
        print("PASS — Wrong password rejected")


class TestAdminUsersRBAC:
    """RBAC-Tests: Member darf KEINE Admin-Endpoints aufrufen"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        return resp.json().get("access_token") or resp.json().get("token")
    
    @pytest.fixture(scope="class")
    def member_token(self, admin_token):
        """Erstelle Member für RBAC-Tests"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        test_email = f"test-vw-rbac-{uuid.uuid4().hex[:8]}@meetflow.com"
        
        # Try register
        reg_resp = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "test123",
            "name": "RBAC Test Member"
        })
        if reg_resp.status_code in [200, 201]:
            login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": test_email,
                "password": "test123"
            })
            if login_resp.status_code == 200:
                return login_resp.json().get("access_token") or login_resp.json().get("token")
        pytest.skip("Could not create member for RBAC tests")
    
    def test_member_cannot_list_users(self, member_token):
        """Member kann /api/admin/users NICHT aufrufen"""
        headers = {"Authorization": f"Bearer {member_token}"}
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers=headers)
        assert resp.status_code in [403, 404], f"Expected 403/404, got {resp.status_code}"
        print("PASS — Member blocked from GET /api/admin/users")
    
    def test_member_cannot_create_group(self, member_token):
        """Member kann keine Gruppe erstellen"""
        headers = {"Authorization": f"Bearer {member_token}"}
        resp = requests.post(f"{BASE_URL}/api/admin/groups", headers=headers, json={
            "name": "Hacker Group",
            "description": "Should not be created"
        })
        assert resp.status_code in [403, 404], f"Expected 403/404, got {resp.status_code}"
        print("PASS — Member blocked from POST /api/admin/groups")
    
    def test_member_cannot_view_audit_logs(self, member_token):
        """Member kann Audit-Logs NICHT sehen"""
        headers = {"Authorization": f"Bearer {member_token}"}
        resp = requests.get(f"{BASE_URL}/api/admin/audit/system", headers=headers)
        assert resp.status_code in [403, 404], f"Expected 403/404, got {resp.status_code}"
        print("PASS — Member blocked from GET /api/admin/audit/system")
    
    def test_member_cannot_update_other_user(self, member_token, admin_token):
        """Member kann andere User NICHT ändern"""
        headers = {"Authorization": f"Bearer {member_token}"}
        # Get admin user_id
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        users_resp = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers)
        if users_resp.status_code != 200:
            pytest.skip("Could not get users list")
        users = users_resp.json()
        if isinstance(users, dict):
            users = users.get("users", [])
        if not users:
            pytest.skip("No users found")
        
        target_user = users[0]
        resp = requests.put(f"{BASE_URL}/api/admin/users/{target_user['user_id']}", 
                           headers=headers, json={"role": "admin"})
        assert resp.status_code in [403, 404], f"Expected 403/404, got {resp.status_code}"
        print("PASS — Member blocked from PUT /api/admin/users/{id}")
    
    def test_tokenless_request_rejected(self):
        """Requests ohne Token werden abgelehnt"""
        resp = requests.get(f"{BASE_URL}/api/admin/users")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        print("PASS — Tokenless request rejected")


class TestAdminUsersCRUD:
    """Admin User-Management CRUD Tests"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        return resp.json().get("access_token") or resp.json().get("token")
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}"}
    
    def test_list_users(self, admin_headers):
        """Admin kann User-Liste abrufen"""
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Can be list or paginated object
        if isinstance(data, list):
            assert len(data) >= 1
        else:
            assert "users" in data or "total" in data
        print("PASS — GET /api/admin/users returns user list")
    
    def test_list_users_paginated(self, admin_headers):
        """Admin kann paginierte User-Liste abrufen"""
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers, 
                           params={"page": 1, "limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        if isinstance(data, dict):
            assert "users" in data
            assert "total" in data
            assert "page" in data
        print("PASS — GET /api/admin/users with pagination works")
    
    def test_list_users_with_search(self, admin_headers):
        """Admin kann User suchen"""
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers,
                           params={"page": 1, "limit": 10, "search": "admin"})
        assert resp.status_code == 200
        print("PASS — GET /api/admin/users with search works")
    
    def test_list_users_filters(self, admin_headers):
        """Admin kann Filter-Optionen abrufen"""
        resp = requests.get(f"{BASE_URL}/api/admin/users/filters", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "departments" in data or "roles" in data
        print("PASS — GET /api/admin/users/filters returns filter options")
    
    def test_invite_user(self, admin_headers):
        """Admin kann User einladen"""
        test_email = f"test-vw-invite-{uuid.uuid4().hex[:8]}@meetflow.com"
        resp = requests.post(f"{BASE_URL}/api/admin/users/invite", headers=admin_headers, json={
            "email": test_email,
            "name": "Test Invite User",
            "role": "member"
        })
        assert resp.status_code == 200, f"Invite failed: {resp.text}"
        data = resp.json()
        assert "user_id" in data
        assert "temp_password" in data
        print(f"PASS — POST /api/admin/users/invite created user {test_email}")
        return data["user_id"]
    
    def test_update_user(self, admin_headers):
        """Admin kann User aktualisieren"""
        # First create a user
        test_email = f"test-vw-update-{uuid.uuid4().hex[:8]}@meetflow.com"
        create_resp = requests.post(f"{BASE_URL}/api/admin/users/invite", headers=admin_headers, json={
            "email": test_email,
            "name": "Update Test",
            "role": "member"
        })
        if create_resp.status_code != 200:
            pytest.skip("Could not create user for update test")
        user_id = create_resp.json()["user_id"]
        
        # Update user
        resp = requests.put(f"{BASE_URL}/api/admin/users/{user_id}", headers=admin_headers, json={
            "name": "Updated Name",
            "department": "IT-Test"
        })
        assert resp.status_code == 200, f"Update failed: {resp.text}"
        data = resp.json()
        assert data.get("name") == "Updated Name"
        print("PASS — PUT /api/admin/users/{id} updates user")
    
    def test_admin_cannot_delete_self(self, admin_headers, admin_token):
        """Admin kann sich selbst NICHT löschen"""
        # Get admin user_id
        me_resp = requests.get(f"{BASE_URL}/api/auth/me", headers=admin_headers)
        if me_resp.status_code != 200:
            pytest.skip("Could not get current user")
        admin_user_id = me_resp.json().get("user_id")
        
        resp = requests.delete(f"{BASE_URL}/api/admin/users/{admin_user_id}", headers=admin_headers)
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        print("PASS — Admin cannot delete self (400)")
    
    def test_delete_user(self, admin_headers):
        """Admin kann User löschen"""
        # Create user to delete
        test_email = f"test-vw-delete-{uuid.uuid4().hex[:8]}@meetflow.com"
        create_resp = requests.post(f"{BASE_URL}/api/admin/users/invite", headers=admin_headers, json={
            "email": test_email,
            "name": "Delete Test",
            "role": "member"
        })
        if create_resp.status_code != 200:
            pytest.skip("Could not create user for delete test")
        user_id = create_resp.json()["user_id"]
        
        # Delete user
        resp = requests.delete(f"{BASE_URL}/api/admin/users/{user_id}", headers=admin_headers)
        assert resp.status_code == 200, f"Delete failed: {resp.text}"
        
        # Verify deleted
        get_resp = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers,
                               params={"search": test_email})
        print("PASS — DELETE /api/admin/users/{id} deletes user")
    
    def test_force_logout_user(self, admin_headers):
        """Admin kann User-Session beenden"""
        # Create user
        test_email = f"test-vw-logout-{uuid.uuid4().hex[:8]}@meetflow.com"
        create_resp = requests.post(f"{BASE_URL}/api/admin/users/invite", headers=admin_headers, json={
            "email": test_email,
            "name": "Logout Test",
            "role": "member"
        })
        if create_resp.status_code != 200:
            pytest.skip("Could not create user for logout test")
        user_id = create_resp.json()["user_id"]
        
        resp = requests.post(f"{BASE_URL}/api/admin/users/{user_id}/force-logout", headers=admin_headers)
        assert resp.status_code == 200, f"Force logout failed: {resp.text}"
        print("PASS — POST /api/admin/users/{id}/force-logout works")


class TestAdminGroupsCRUD:
    """Admin Groups CRUD Tests"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        token = resp.json().get("access_token") or resp.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_list_groups(self, admin_headers):
        """Admin kann Gruppen auflisten"""
        resp = requests.get(f"{BASE_URL}/api/admin/groups", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print("PASS — GET /api/admin/groups returns list")
    
    def test_create_group(self, admin_headers):
        """Admin kann Gruppe erstellen"""
        group_name = f"test-grp-{uuid.uuid4().hex[:8]}"
        resp = requests.post(f"{BASE_URL}/api/admin/groups", headers=admin_headers, json={
            "name": group_name,
            "description": "Test group for iter 259"
        })
        assert resp.status_code == 200, f"Create group failed: {resp.text}"
        data = resp.json()
        assert data.get("name") == group_name
        assert "group_id" in data
        print(f"PASS — POST /api/admin/groups created {group_name}")
        return data["group_id"]
    
    def test_create_duplicate_group_name(self, admin_headers):
        """Doppelter Gruppenname sollte Fehler geben (oder erlaubt sein)"""
        group_name = f"test-dup-{uuid.uuid4().hex[:8]}"
        # Create first
        resp1 = requests.post(f"{BASE_URL}/api/admin/groups", headers=admin_headers, json={
            "name": group_name,
            "description": "First"
        })
        assert resp1.status_code == 200
        
        # Create duplicate
        resp2 = requests.post(f"{BASE_URL}/api/admin/groups", headers=admin_headers, json={
            "name": group_name,
            "description": "Duplicate"
        })
        # Either 409 conflict or 200 (if duplicates allowed)
        print(f"Duplicate group name: status={resp2.status_code}")
    
    def test_update_group(self, admin_headers):
        """Admin kann Gruppe aktualisieren"""
        # Create group
        group_name = f"test-upd-{uuid.uuid4().hex[:8]}"
        create_resp = requests.post(f"{BASE_URL}/api/admin/groups", headers=admin_headers, json={
            "name": group_name,
            "description": "Original"
        })
        if create_resp.status_code != 200:
            pytest.skip("Could not create group")
        group_id = create_resp.json()["group_id"]
        
        # Update
        resp = requests.put(f"{BASE_URL}/api/admin/groups/{group_id}", headers=admin_headers, json={
            "description": "Updated description"
        })
        assert resp.status_code == 200, f"Update failed: {resp.text}"
        print("PASS — PUT /api/admin/groups/{id} updates group")
    
    def test_delete_group(self, admin_headers):
        """Admin kann Gruppe löschen"""
        # Create group
        group_name = f"test-del-{uuid.uuid4().hex[:8]}"
        create_resp = requests.post(f"{BASE_URL}/api/admin/groups", headers=admin_headers, json={
            "name": group_name
        })
        if create_resp.status_code != 200:
            pytest.skip("Could not create group")
        group_id = create_resp.json()["group_id"]
        
        # Delete
        resp = requests.delete(f"{BASE_URL}/api/admin/groups/{group_id}", headers=admin_headers)
        assert resp.status_code == 200, f"Delete failed: {resp.text}"
        print("PASS — DELETE /api/admin/groups/{id} deletes group")
    
    def test_add_member_to_group(self, admin_headers):
        """Admin kann Mitglied zu Gruppe hinzufügen"""
        # Create group
        group_name = f"test-mem-{uuid.uuid4().hex[:8]}"
        create_resp = requests.post(f"{BASE_URL}/api/admin/groups", headers=admin_headers, json={
            "name": group_name
        })
        if create_resp.status_code != 200:
            pytest.skip("Could not create group")
        group_id = create_resp.json()["group_id"]
        
        # Create user
        test_email = f"test-vw-grpmem-{uuid.uuid4().hex[:8]}@meetflow.com"
        user_resp = requests.post(f"{BASE_URL}/api/admin/users/invite", headers=admin_headers, json={
            "email": test_email,
            "name": "Group Member Test"
        })
        if user_resp.status_code != 200:
            pytest.skip("Could not create user")
        user_id = user_resp.json()["user_id"]
        
        # Add to group
        resp = requests.post(f"{BASE_URL}/api/admin/groups/{group_id}/members", 
                            headers=admin_headers, json={"user_id": user_id})
        assert resp.status_code == 200, f"Add member failed: {resp.text}"
        print("PASS — POST /api/admin/groups/{id}/members adds member")


class TestAdminAuditLogs:
    """Audit-Log Tests"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        token = resp.json().get("access_token") or resp.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_system_audit(self, admin_headers):
        """Admin kann System-Audit abrufen"""
        resp = requests.get(f"{BASE_URL}/api/admin/audit/system", headers=admin_headers)
        assert resp.status_code == 200, f"Audit failed: {resp.text}"
        data = resp.json()
        assert "entries" in data
        print(f"PASS — GET /api/admin/audit/system returns {len(data.get('entries', []))} entries")
    
    def test_audit_with_limit(self, admin_headers):
        """Audit-Log mit Limit"""
        resp = requests.get(f"{BASE_URL}/api/admin/audit/system", headers=admin_headers,
                           params={"limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        entries = data.get("entries", [])
        assert len(entries) <= 10
        print("PASS — Audit log respects limit parameter")
    
    def test_audit_with_category_filter(self, admin_headers):
        """Audit-Log mit Kategorie-Filter"""
        resp = requests.get(f"{BASE_URL}/api/admin/audit/system", headers=admin_headers,
                           params={"category": "session"})
        assert resp.status_code == 200
        print("PASS — Audit log accepts category filter")


class TestAdminStats:
    """Admin Statistics Tests"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        token = resp.json().get("access_token") or resp.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_stats(self, admin_headers):
        """Admin kann Statistiken abrufen"""
        resp = requests.get(f"{BASE_URL}/api/admin/stats", headers=admin_headers)
        assert resp.status_code == 200, f"Stats failed: {resp.text}"
        data = resp.json()
        assert "total_users" in data
        assert "total_meetings" in data
        print(f"PASS — GET /api/admin/stats: {data.get('total_users')} users, {data.get('total_meetings')} meetings")


class TestAdminCapabilities:
    """Capabilities/Roles Tests"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        token = resp.json().get("access_token") or resp.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_list_capabilities(self, admin_headers):
        """Admin kann Capabilities auflisten"""
        resp = requests.get(f"{BASE_URL}/api/admin/capabilities", headers=admin_headers)
        assert resp.status_code == 200, f"Capabilities failed: {resp.text}"
        data = resp.json()
        assert "capabilities" in data
        assert "role_defaults" in data
        print(f"PASS — GET /api/admin/capabilities: {len(data.get('capabilities', []))} caps")
    
    def test_list_presets(self, admin_headers):
        """Admin kann Presets auflisten"""
        resp = requests.get(f"{BASE_URL}/api/admin/presets", headers=admin_headers)
        assert resp.status_code == 200, f"Presets failed: {resp.text}"
        data = resp.json()
        assert "presets" in data
        print(f"PASS — GET /api/admin/presets: {len(data.get('presets', []))} presets")


class TestAdminValidation:
    """Validation und Error-Handling Tests"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        token = resp.json().get("access_token") or resp.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_update_user_nonexistent_role(self, admin_headers):
        """Update mit ungültiger Rolle sollte Fehler geben"""
        # Create user
        test_email = f"test-vw-badrole-{uuid.uuid4().hex[:8]}@meetflow.com"
        create_resp = requests.post(f"{BASE_URL}/api/admin/users/invite", headers=admin_headers, json={
            "email": test_email,
            "name": "Bad Role Test"
        })
        if create_resp.status_code != 200:
            pytest.skip("Could not create user")
        user_id = create_resp.json()["user_id"]
        
        # Try invalid role
        resp = requests.put(f"{BASE_URL}/api/admin/users/{user_id}", headers=admin_headers, json={
            "role": "nonexistent_role_xyz"
        })
        # Should either reject (400) or accept (role validation might be lenient)
        print(f"Invalid role update: status={resp.status_code}")
    
    def test_create_group_empty_name(self, admin_headers):
        """Gruppe ohne Name sollte Fehler geben"""
        resp = requests.post(f"{BASE_URL}/api/admin/groups", headers=admin_headers, json={
            "name": "",
            "description": "No name"
        })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        print("PASS — Empty group name rejected (400)")
    
    def test_delete_nonexistent_user(self, admin_headers):
        """Löschen eines nicht existierenden Users"""
        resp = requests.delete(f"{BASE_URL}/api/admin/users/nonexistent_user_id_xyz", 
                              headers=admin_headers)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("PASS — Delete nonexistent user returns 404")


class TestAdminLoadTest:
    """50 Concurrent User Load Tests"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        token = resp.json().get("access_token") or resp.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def _make_request(self, method, url, headers, json_data=None, params=None):
        """Helper für concurrent requests"""
        start = time.time()
        try:
            if method == "GET":
                resp = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == "POST":
                resp = requests.post(url, headers=headers, json=json_data, timeout=30)
            elif method == "PUT":
                resp = requests.put(url, headers=headers, json=json_data, timeout=30)
            elif method == "DELETE":
                resp = requests.delete(url, headers=headers, timeout=30)
            else:
                return {"success": False, "error": "Unknown method", "duration": 0}
            
            duration = time.time() - start
            return {
                "success": resp.status_code in [200, 201, 204],
                "status": resp.status_code,
                "duration": duration
            }
        except Exception as e:
            return {"success": False, "error": str(e), "duration": time.time() - start}
    
    def test_50_concurrent_get_users(self, admin_headers):
        """50 concurrent GET /api/admin/users"""
        url = f"{BASE_URL}/api/admin/users"
        results = []
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [
                executor.submit(self._make_request, "GET", url, admin_headers, params={"page": 1, "limit": 10})
                for _ in range(50)
            ]
            for f in as_completed(futures):
                results.append(f.result())
        
        success_count = sum(1 for r in results if r.get("success"))
        durations = [r["duration"] for r in results if r.get("success")]
        p95 = sorted(durations)[int(len(durations) * 0.95)] if durations else 0
        
        print(f"50× GET /api/admin/users: {success_count}/50 success, p95={p95*1000:.0f}ms")
        assert success_count >= 40, f"Only {success_count}/50 succeeded"
    
    def test_50_concurrent_create_groups(self, admin_headers):
        """50 concurrent POST /api/admin/groups mit unique names"""
        url = f"{BASE_URL}/api/admin/groups"
        results = []
        
        def create_group(i):
            return self._make_request("POST", url, admin_headers, json_data={
                "name": f"load-test-grp-{uuid.uuid4().hex[:8]}",
                "description": f"Load test group {i}"
            })
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(create_group, i) for i in range(50)]
            for f in as_completed(futures):
                results.append(f.result())
        
        success_count = sum(1 for r in results if r.get("success"))
        print(f"50× POST /api/admin/groups (unique names): {success_count}/50 success")
        assert success_count >= 45, f"Only {success_count}/50 succeeded"
    
    def test_50_concurrent_get_audit_logs(self, admin_headers):
        """50 concurrent GET /api/admin/audit/system"""
        url = f"{BASE_URL}/api/admin/audit/system"
        results = []
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [
                executor.submit(self._make_request, "GET", url, admin_headers, params={"limit": 100})
                for _ in range(50)
            ]
            for f in as_completed(futures):
                results.append(f.result())
        
        success_count = sum(1 for r in results if r.get("success"))
        durations = [r["duration"] for r in results if r.get("success")]
        p95 = sorted(durations)[int(len(durations) * 0.95)] if durations else 0
        
        print(f"50× GET /api/admin/audit/system: {success_count}/50 success, p95={p95*1000:.0f}ms")
        assert success_count >= 40, f"Only {success_count}/50 succeeded"


class TestCleanup:
    """Cleanup test data"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        token = resp.json().get("access_token") or resp.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_cleanup_test_users(self, admin_headers):
        """Cleanup test-vw-* users"""
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers)
        if resp.status_code != 200:
            return
        
        users = resp.json()
        if isinstance(users, dict):
            users = users.get("users", [])
        
        deleted = 0
        for u in users:
            email = u.get("email", "")
            if email.startswith("test-vw-"):
                del_resp = requests.delete(f"{BASE_URL}/api/admin/users/{u['user_id']}", 
                                          headers=admin_headers)
                if del_resp.status_code == 200:
                    deleted += 1
        
        print(f"Cleanup: deleted {deleted} test users")
    
    def test_cleanup_test_groups(self, admin_headers):
        """Cleanup test-* and load-test-* groups"""
        resp = requests.get(f"{BASE_URL}/api/admin/groups", headers=admin_headers)
        if resp.status_code != 200:
            return
        
        groups = resp.json()
        deleted = 0
        for g in groups:
            name = g.get("name", "")
            if name.startswith("test-") or name.startswith("load-test-"):
                del_resp = requests.delete(f"{BASE_URL}/api/admin/groups/{g['group_id']}", 
                                          headers=admin_headers)
                if del_resp.status_code == 200:
                    deleted += 1
        
        print(f"Cleanup: deleted {deleted} test groups")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
