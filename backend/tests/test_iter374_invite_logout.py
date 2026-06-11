"""
Iteration 374 — Regression Tests for:
1. InviteUserDialog with required fields validation (Pflichtfelder)
2. Logout bug fix (hard navigation + storage cleanup)

Required fields for invite: email, first_name, last_name, department, position, personnel_number
Optional: display_name, phone, location, profession, org_unit, language, role, group_ids, cap_grants, cap_denies
"""
import pytest
import requests
import os
import uuid
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestInviteUserRequiredFields:
    """Test POST /api/admin/users/invite with required field validation"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin before each test"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.admin_user = login_resp.json()
        yield
        self.session.close()
    
    def test_invite_email_only_returns_400_missing_fields(self):
        """POST /api/admin/users/invite with email-only → 400 'Pflichtfelder fehlen'"""
        resp = self.session.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": f"test_invite_{uuid.uuid4().hex[:8]}@example.com"
        })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "Pflichtfelder fehlen" in data.get("detail", ""), f"Expected 'Pflichtfelder fehlen' in detail: {data}"
        # Should mention all missing required fields
        detail = data.get("detail", "")
        assert "Vorname" in detail, f"Missing 'Vorname' in error: {detail}"
        assert "Nachname" in detail, f"Missing 'Nachname' in error: {detail}"
        assert "Abteilung" in detail, f"Missing 'Abteilung' in error: {detail}"
        assert "Position" in detail, f"Missing 'Position' in error: {detail}"
        assert "Personalnummer" in detail, f"Missing 'Personalnummer' in error: {detail}"
    
    def test_invite_with_all_required_fields_succeeds(self):
        """POST /api/admin/users/invite with all required fields → 200 with user_id and temp_password"""
        unique_id = uuid.uuid4().hex[:8]
        email = f"test_invite_full_{unique_id}@example.com"
        personnel_number = f"PN-{unique_id}"
        
        resp = self.session.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": email,
            "first_name": "Test",
            "last_name": "User",
            "department": "IT",
            "position": "Developer",
            "personnel_number": personnel_number,
            "cap_grants": ["news.create"],
            "cap_denies": ["view:chat"]
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "user_id" in data, f"Missing user_id in response: {data}"
        assert "temp_password" in data, f"Missing temp_password in response: {data}"
        assert data.get("email") == email, f"Email mismatch: {data}"
        
        # Verify user was created with correct data via /admin/users/{id}/simulate or direct lookup
        user_id = data["user_id"]
        # Cleanup: delete the test user
        cleanup_resp = self.session.delete(f"{BASE_URL}/api/admin/users/{user_id}")
        assert cleanup_resp.status_code in [200, 204], f"Cleanup failed: {cleanup_resp.text}"
    
    def test_invite_duplicate_personnel_number_returns_409(self):
        """POST /api/admin/users/invite with duplicate personnel_number → 409"""
        unique_id = uuid.uuid4().hex[:8]
        personnel_number = f"PN-DUP-{unique_id}"
        
        # Create first user
        resp1 = self.session.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": f"test_dup1_{unique_id}@example.com",
            "first_name": "First",
            "last_name": "User",
            "department": "IT",
            "position": "Dev",
            "personnel_number": personnel_number
        })
        assert resp1.status_code == 200, f"First invite failed: {resp1.text}"
        user1_id = resp1.json().get("user_id")
        
        # Try to create second user with same personnel_number
        resp2 = self.session.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": f"test_dup2_{unique_id}@example.com",
            "first_name": "Second",
            "last_name": "User",
            "department": "HR",
            "position": "Manager",
            "personnel_number": personnel_number
        })
        assert resp2.status_code == 409, f"Expected 409, got {resp2.status_code}: {resp2.text}"
        data = resp2.json()
        assert "Personalnummer bereits vergeben" in data.get("detail", ""), f"Expected 'Personalnummer bereits vergeben': {data}"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/users/{user1_id}")
    
    def test_invite_duplicate_email_returns_409(self):
        """POST /api/admin/users/invite with duplicate email → 409 'Benutzer existiert bereits'"""
        unique_id = uuid.uuid4().hex[:8]
        email = f"test_dup_email_{unique_id}@example.com"
        
        # Create first user
        resp1 = self.session.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": email,
            "first_name": "First",
            "last_name": "User",
            "department": "IT",
            "position": "Dev",
            "personnel_number": f"PN-E1-{unique_id}"
        })
        assert resp1.status_code == 200, f"First invite failed: {resp1.text}"
        user1_id = resp1.json().get("user_id")
        
        # Try to create second user with same email
        resp2 = self.session.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": email,
            "first_name": "Second",
            "last_name": "User",
            "department": "HR",
            "position": "Manager",
            "personnel_number": f"PN-E2-{unique_id}"
        })
        assert resp2.status_code == 409, f"Expected 409, got {resp2.status_code}: {resp2.text}"
        data = resp2.json()
        assert "Benutzer existiert bereits" in data.get("detail", ""), f"Expected 'Benutzer existiert bereits': {data}"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/users/{user1_id}")


class TestInviteUserNonAdmin:
    """Test that non-admin users cannot invite"""
    
    def test_member_cannot_invite_returns_403(self):
        """POST /api/admin/users/invite as member → 403"""
        session = requests.Session()
        # Login as qa_member
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "qa_member@meetflow.com",
            "password": "qa_member_pw_372"
        })
        assert login_resp.status_code == 200, f"Member login failed: {login_resp.text}"
        
        # Try to invite
        resp = session.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": "should_not_work@example.com",
            "first_name": "Should",
            "last_name": "Fail",
            "department": "IT",
            "position": "Dev",
            "personnel_number": "PN-FAIL-001"
        })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        session.close()


class TestLogoutBugFix:
    """Test that logout properly clears session and /auth/me returns 401"""
    
    def test_logout_clears_session(self):
        """After logout, /auth/me should return 401"""
        session = requests.Session()
        
        # Login as admin
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        
        # Verify logged in
        me_resp = session.get(f"{BASE_URL}/api/auth/me")
        assert me_resp.status_code == 200, f"Expected 200 for /auth/me while logged in: {me_resp.text}"
        assert me_resp.json().get("email") == "admin@meetflow.com"
        
        # Logout
        logout_resp = session.post(f"{BASE_URL}/api/auth/logout")
        assert logout_resp.status_code == 200, f"Logout failed: {logout_resp.text}"
        
        # Verify logged out - /auth/me should return 401
        me_after_logout = session.get(f"{BASE_URL}/api/auth/me")
        assert me_after_logout.status_code == 401, f"Expected 401 after logout, got {me_after_logout.status_code}: {me_after_logout.text}"
        
        session.close()
    
    def test_login_as_different_user_after_logout(self):
        """After logout and re-login as different user, /auth/me returns new user"""
        session = requests.Session()
        
        # Login as admin
        login1 = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login1.status_code == 200
        
        # Logout
        session.post(f"{BASE_URL}/api/auth/logout")
        
        # Login as qa_member
        login2 = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "qa_member@meetflow.com",
            "password": "qa_member_pw_372"
        })
        assert login2.status_code == 200, f"Second login failed: {login2.text}"
        
        # Verify /auth/me returns qa_member, not admin
        me_resp = session.get(f"{BASE_URL}/api/auth/me")
        assert me_resp.status_code == 200
        user_data = me_resp.json()
        assert user_data.get("email") == "qa_member@meetflow.com", f"Expected qa_member, got: {user_data}"
        assert "admin" not in user_data.get("email", ""), "Should not see admin email"
        
        session.close()


class TestInviteWithCapabilities:
    """Test invite with cap_grants and cap_denies"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        yield
        self.session.close()
    
    def test_invite_with_caps_stores_grants_and_denies(self):
        """Invite with cap_grants and cap_denies should store them on user"""
        unique_id = uuid.uuid4().hex[:8]
        email = f"test_caps_{unique_id}@example.com"
        
        resp = self.session.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": email,
            "first_name": "Caps",
            "last_name": "Test",
            "department": "IT",
            "position": "Tester",
            "personnel_number": f"PN-CAPS-{unique_id}",
            "cap_grants": ["news.create", "meetings.create"],
            "cap_denies": ["view:chat", "admin.access"]
        })
        assert resp.status_code == 200, f"Invite failed: {resp.text}"
        user_id = resp.json().get("user_id")
        
        # Verify user has the caps by fetching user list
        users_resp = self.session.get(f"{BASE_URL}/api/admin/users", params={"search": email})
        users_data = users_resp.json()
        users = users_data.get("users", users_data) if isinstance(users_data, dict) else users_data
        
        found_user = None
        for u in users:
            if u.get("email") == email:
                found_user = u
                break
        
        assert found_user is not None, f"Could not find created user {email}"
        assert "news.create" in (found_user.get("cap_grants") or []), f"Missing cap_grants: {found_user}"
        assert "view:chat" in (found_user.get("cap_denies") or []), f"Missing cap_denies: {found_user}"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/users/{user_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
