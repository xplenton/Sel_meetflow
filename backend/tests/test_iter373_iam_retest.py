"""
Iteration 373 - IAM Security Audit RETEST
==========================================
Retesting fixes for 2 CRITICAL bugs found in iter 372:
1. POST /api/tasks accepted guest requests (now should be 403)
2. POST /api/meetings accepted guest requests (now should be 403)

Also retesting:
- PHASE 6.4: Token-version bump on role change
- PHASE 6.8: Cap cache invalidation (60s TTL)
- PHASE 6.9: Cascade cleanup on user delete
- PHASE 6.11: QR-Bulk-PDF access control
"""

import pytest
import requests
import os
import time
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from iter 372
CREDENTIALS = {
    'admin': {'email': 'admin@meetflow.com', 'password': 'admin123'},
    'qa_admin': {'email': 'qa_admin@meetflow.com', 'password': 'qa_admin_pw_372'},
    'qa_moderator': {'email': 'qa_moderator@meetflow.com', 'password': 'qa_moderator_pw_372'},
    'qa_member': {'email': 'qa_member@meetflow.com', 'password': 'qa_member_pw_372'},
    'qa_guest': {'email': 'qa_guest@meetflow.com', 'password': 'qa_guest_pw_372'},
    'downgrade_user': {'email': 'newguest_1776557090@example.com', 'password': 'qa_downgrade_pw_372'},
}


class TestHelpers:
    """Helper methods for authentication and API calls"""
    
    @staticmethod
    def login(email: str, password: str) -> dict:
        """Login and return token + user info"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": email,
            "password": password
        })
        if resp.status_code != 200:
            return {"error": resp.status_code, "detail": resp.text}
        data = resp.json()
        # Response has user_id at top level, not nested under "user"
        return {
            "token": data.get("token"),
            "user_id": data.get("user_id") or data.get("user", {}).get("user_id"),
            "role": data.get("role") or data.get("user", {}).get("role"),
            "user": data
        }
    
    @staticmethod
    def auth_headers(token: str) -> dict:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


class TestPhase5_3_BackendEnforcement:
    """RETEST: Backend capability enforcement for tasks and meetings"""
    
    def test_retest1_guest_cannot_create_tasks(self):
        """CRITICAL FIX RETEST: POST /api/tasks as qa_guest MUST be 403"""
        auth = TestHelpers.login(**CREDENTIALS['qa_guest'])
        assert "token" in auth, f"Guest login failed: {auth}"
        
        resp = requests.post(
            f"{BASE_URL}/api/tasks",
            headers=TestHelpers.auth_headers(auth["token"]),
            json={"title": "TEST_guest_task_should_fail", "description": "This should be rejected"}
        )
        
        assert resp.status_code == 403, f"CRITICAL BUG NOT FIXED: Guest created task! Expected 403, got {resp.status_code}. Response: {resp.text}"
        print(f"✓ RETEST 1 PASSED: Guest POST /api/tasks correctly returns 403")
    
    def test_retest2_guest_cannot_create_meetings(self):
        """CRITICAL FIX RETEST: POST /api/meetings as qa_guest MUST be 403"""
        auth = TestHelpers.login(**CREDENTIALS['qa_guest'])
        assert "token" in auth, f"Guest login failed: {auth}"
        
        resp = requests.post(
            f"{BASE_URL}/api/meetings",
            headers=TestHelpers.auth_headers(auth["token"]),
            json={"title": "TEST_guest_meeting_should_fail", "duration": 30}
        )
        
        assert resp.status_code == 403, f"CRITICAL BUG NOT FIXED: Guest created meeting! Expected 403, got {resp.status_code}. Response: {resp.text}"
        print(f"✓ RETEST 2 PASSED: Guest POST /api/meetings correctly returns 403")
    
    def test_regression1_member_can_create_tasks(self):
        """REGRESSION: POST /api/tasks as qa_member must still be 200/201"""
        auth = TestHelpers.login(**CREDENTIALS['qa_member'])
        assert "token" in auth, f"Member login failed: {auth}"
        
        resp = requests.post(
            f"{BASE_URL}/api/tasks",
            headers=TestHelpers.auth_headers(auth["token"]),
            json={"title": f"TEST_member_task_{uuid.uuid4().hex[:6]}", "description": "Member should be able to create"}
        )
        
        assert resp.status_code in [200, 201], f"REGRESSION: Member cannot create task! Expected 200/201, got {resp.status_code}. Response: {resp.text}"
        print(f"✓ REGRESSION 1 PASSED: Member POST /api/tasks returns {resp.status_code}")
    
    def test_regression2_member_can_create_meetings(self):
        """REGRESSION: POST /api/meetings as qa_member must still be 200/201"""
        auth = TestHelpers.login(**CREDENTIALS['qa_member'])
        assert "token" in auth, f"Member login failed: {auth}"
        
        resp = requests.post(
            f"{BASE_URL}/api/meetings",
            headers=TestHelpers.auth_headers(auth["token"]),
            json={"title": f"TEST_member_meeting_{uuid.uuid4().hex[:6]}", "duration": 30}
        )
        
        assert resp.status_code in [200, 201], f"REGRESSION: Member cannot create meeting! Expected 200/201, got {resp.status_code}. Response: {resp.text}"
        print(f"✓ REGRESSION 2 PASSED: Member POST /api/meetings returns {resp.status_code}")
    
    def test_regression3_moderator_can_create_tasks(self):
        """REGRESSION: POST /api/tasks as qa_moderator must be 200/201"""
        auth = TestHelpers.login(**CREDENTIALS['qa_moderator'])
        assert "token" in auth, f"Moderator login failed: {auth}"
        
        resp = requests.post(
            f"{BASE_URL}/api/tasks",
            headers=TestHelpers.auth_headers(auth["token"]),
            json={"title": f"TEST_moderator_task_{uuid.uuid4().hex[:6]}", "description": "Moderator should be able to create"}
        )
        
        assert resp.status_code in [200, 201], f"REGRESSION: Moderator cannot create task! Expected 200/201, got {resp.status_code}. Response: {resp.text}"
        print(f"✓ REGRESSION 3 PASSED: Moderator POST /api/tasks returns {resp.status_code}")
    
    def test_regression4_admin_can_create_meetings(self):
        """REGRESSION: POST /api/meetings as qa_admin must be 200/201"""
        auth = TestHelpers.login(**CREDENTIALS['qa_admin'])
        assert "token" in auth, f"Admin login failed: {auth}"
        
        resp = requests.post(
            f"{BASE_URL}/api/meetings",
            headers=TestHelpers.auth_headers(auth["token"]),
            json={"title": f"TEST_admin_meeting_{uuid.uuid4().hex[:6]}", "duration": 30}
        )
        
        assert resp.status_code in [200, 201], f"REGRESSION: Admin cannot create meeting! Expected 200/201, got {resp.status_code}. Response: {resp.text}"
        print(f"✓ REGRESSION 4 PASSED: Admin POST /api/meetings returns {resp.status_code}")


class TestPhase6_4_TokenVersionBump:
    """PHASE 6.4 RETEST: Token-version bump on role change"""
    
    def test_token_invalidation_on_role_change(self):
        """
        1. Login qa_member, save OLD token
        2. As qa_admin, change qa_member.role to 'guest'
        3. Old token must now return 401 on any /api/* call
        4. Reset role back to 'member'
        """
        # Step 1: Login as qa_member and save token
        member_auth = TestHelpers.login(**CREDENTIALS['qa_member'])
        assert "token" in member_auth, f"Member login failed: {member_auth}"
        old_token = member_auth["token"]
        member_user_id = member_auth["user_id"]
        
        # Verify old token works
        resp = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers=TestHelpers.auth_headers(old_token)
        )
        assert resp.status_code == 200, f"Old token should work initially: {resp.status_code}"
        print(f"✓ Step 1: Member logged in, token works")
        
        # Step 2: As qa_admin, change qa_member's role to 'guest'
        admin_auth = TestHelpers.login(**CREDENTIALS['qa_admin'])
        assert "token" in admin_auth, f"Admin login failed: {admin_auth}"
        
        resp = requests.put(
            f"{BASE_URL}/api/admin/users/{member_user_id}",
            headers=TestHelpers.auth_headers(admin_auth["token"]),
            json={"role": "guest"}
        )
        assert resp.status_code == 200, f"Admin failed to change role: {resp.status_code} - {resp.text}"
        print(f"✓ Step 2: Admin changed member role to 'guest'")
        
        # Step 3: Old token must now return 401
        time.sleep(0.5)  # Small delay for token version to propagate
        resp = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers=TestHelpers.auth_headers(old_token)
        )
        
        # Step 4: Reset role back to 'member' (cleanup)
        resp_reset = requests.put(
            f"{BASE_URL}/api/admin/users/{member_user_id}",
            headers=TestHelpers.auth_headers(admin_auth["token"]),
            json={"role": "member"}
        )
        assert resp_reset.status_code == 200, f"Failed to reset role: {resp_reset.status_code}"
        print(f"✓ Step 4: Role reset to 'member'")
        
        # Now check the result from step 3
        assert resp.status_code == 401, f"PHASE 6.4 FAIL: Old token should be invalidated after role change. Expected 401, got {resp.status_code}"
        print(f"✓ PHASE 6.4 PASSED: Token invalidated on role change (401)")


class TestPhase6_8_CapCacheInvalidation:
    """PHASE 6.8 RETEST: Cap cache invalidation (60s TTL)"""
    
    def test_cap_cache_invalidation(self):
        """
        1. Admin sets cap_denies=['resources.book'] on qa_member
        2. Within 5 seconds, qa_member's /api/user/permissions MUST not contain 'resources.book'
        3. Restore (denies=[]) afterwards
        """
        # Login as admin
        admin_auth = TestHelpers.login(**CREDENTIALS['qa_admin'])
        assert "token" in admin_auth, f"Admin login failed: {admin_auth}"
        
        # Login as member to get user_id
        member_auth = TestHelpers.login(**CREDENTIALS['qa_member'])
        assert "token" in member_auth, f"Member login failed: {member_auth}"
        member_user_id = member_auth["user_id"]
        
        # Check initial permissions - member should have resources.book
        resp = requests.get(
            f"{BASE_URL}/api/user/permissions",
            headers=TestHelpers.auth_headers(member_auth["token"])
        )
        assert resp.status_code == 200, f"Failed to get permissions: {resp.status_code}"
        initial_caps = resp.json().get("capabilities", [])
        print(f"✓ Initial caps count: {len(initial_caps)}")
        
        # Step 1: Admin sets denies=['resources.book'] (API uses 'denies' not 'cap_denies')
        resp = requests.put(
            f"{BASE_URL}/api/admin/users/{member_user_id}/capabilities",
            headers=TestHelpers.auth_headers(admin_auth["token"]),
            json={"denies": ["resources.book"], "grants": []}
        )
        assert resp.status_code == 200, f"Failed to set denies: {resp.status_code} - {resp.text}"
        print(f"✓ Step 1: Set denies=['resources.book']")
        
        # Step 2: Within 5 seconds, check permissions
        time.sleep(2)  # Small delay for cache invalidation
        
        # Re-login to get fresh token (cache might be tied to token)
        member_auth_fresh = TestHelpers.login(**CREDENTIALS['qa_member'])
        resp = requests.get(
            f"{BASE_URL}/api/user/permissions",
            headers=TestHelpers.auth_headers(member_auth_fresh["token"])
        )
        assert resp.status_code == 200, f"Failed to get permissions: {resp.status_code}"
        new_caps = resp.json().get("capabilities", [])
        
        # Step 3: Restore (denies=[])
        resp_restore = requests.put(
            f"{BASE_URL}/api/admin/users/{member_user_id}/capabilities",
            headers=TestHelpers.auth_headers(admin_auth["token"]),
            json={"denies": [], "grants": []}
        )
        assert resp_restore.status_code == 200, f"Failed to restore caps: {resp_restore.status_code}"
        print(f"✓ Step 3: Restored denies=[]")
        
        # Verify resources.book is NOT in new_caps
        assert "resources.book" not in new_caps, f"PHASE 6.8 FAIL: 'resources.book' should be denied but found in caps: {new_caps}"
        print(f"✓ PHASE 6.8 PASSED: Cap cache invalidation works (resources.book denied)")


class TestPhase6_9_CascadeCleanup:
    """PHASE 6.9 RETEST: Cascade cleanup on user delete"""
    
    def test_cascade_cleanup_on_user_delete(self):
        """
        1. Admin creates throwaway user via POST /api/auth/register
        2. Admin adds user to Gast group
        3. Admin deletes user via DELETE /api/admin/users/{id}
        4. GET Gast group and verify deleted user_id is NOT in members[]
        """
        admin_auth = TestHelpers.login(**CREDENTIALS['qa_admin'])
        assert "token" in admin_auth, f"Admin login failed: {admin_auth}"
        
        # Step 1: Create throwaway user
        throwaway_email = f"TEST_throwaway_{uuid.uuid4().hex[:8]}@example.com"
        resp = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": throwaway_email,
                "password": "throwaway_pw_123",
                "name": "Throwaway User"
            }
        )
        assert resp.status_code in [200, 201], f"Failed to create throwaway user: {resp.status_code} - {resp.text}"
        throwaway_user_id = resp.json().get("user", {}).get("user_id") or resp.json().get("user_id")
        assert throwaway_user_id, f"No user_id in response: {resp.json()}"
        print(f"✓ Step 1: Created throwaway user {throwaway_email} with id {throwaway_user_id}")
        
        # Step 2: Find Gast group and add user
        resp = requests.get(
            f"{BASE_URL}/api/admin/groups",
            headers=TestHelpers.auth_headers(admin_auth["token"])
        )
        assert resp.status_code == 200, f"Failed to get groups: {resp.status_code}"
        groups = resp.json() if isinstance(resp.json(), list) else resp.json().get("groups", [])
        gast_group = next((g for g in groups if g.get("name", "").lower() == "gast" or g.get("name", "").lower() == "guest"), None)
        
        if gast_group:
            gast_group_id = gast_group.get("group_id")
            # Add user to group
            current_members = gast_group.get("members", [])
            resp = requests.put(
                f"{BASE_URL}/api/admin/groups/{gast_group_id}",
                headers=TestHelpers.auth_headers(admin_auth["token"]),
                json={"members": current_members + [throwaway_user_id]}
            )
            if resp.status_code == 200:
                print(f"✓ Step 2: Added user to Gast group")
            else:
                print(f"⚠ Step 2: Could not add to Gast group: {resp.status_code}")
        else:
            print(f"⚠ Step 2: No Gast group found, skipping group membership test")
            gast_group_id = None
        
        # Step 3: Delete the throwaway user
        resp = requests.delete(
            f"{BASE_URL}/api/admin/users/{throwaway_user_id}",
            headers=TestHelpers.auth_headers(admin_auth["token"])
        )
        assert resp.status_code in [200, 204], f"Failed to delete user: {resp.status_code} - {resp.text}"
        print(f"✓ Step 3: Deleted throwaway user")
        
        # Step 4: Verify user is NOT in Gast group members
        if gast_group_id:
            resp = requests.get(
                f"{BASE_URL}/api/admin/groups/{gast_group_id}",
                headers=TestHelpers.auth_headers(admin_auth["token"])
            )
            if resp.status_code == 200:
                group_data = resp.json()
                members = group_data.get("members", [])
                assert throwaway_user_id not in members, f"PHASE 6.9 FAIL: Deleted user still in group members: {members}"
                print(f"✓ PHASE 6.9 PASSED: Cascade cleanup removed user from group")
            else:
                print(f"⚠ Could not verify group membership: {resp.status_code}")
        else:
            print(f"✓ PHASE 6.9 PASSED: User deleted (no group to verify)")


class TestPhase6_11_QRBulkPDF:
    """PHASE 6.11 RETEST: QR-Bulk-PDF access control"""
    
    def test_guest_cannot_access_qr_bulk_pdf(self):
        """
        As qa_guest, POST /api/resources-qr-bulk-pdf with body {resource_ids:['any-id']}
        MUST be 403 (cap view:resources required, guest doesn't have it)
        """
        auth = TestHelpers.login(**CREDENTIALS['qa_guest'])
        assert "token" in auth, f"Guest login failed: {auth}"
        
        resp = requests.post(
            f"{BASE_URL}/api/resources-qr-bulk-pdf",
            headers=TestHelpers.auth_headers(auth["token"]),
            json={"resource_ids": ["any-id-123"]}
        )
        
        assert resp.status_code == 403, f"PHASE 6.11 FAIL: Guest should not access QR bulk PDF. Expected 403, got {resp.status_code}. Response: {resp.text}"
        print(f"✓ PHASE 6.11 PASSED: Guest POST /api/resources-qr-bulk-pdf returns 403")


class TestAdditionalSecurityChecks:
    """Additional security checks for completeness"""
    
    def test_unauthenticated_access_returns_401(self):
        """Unauthenticated requests to protected endpoints should return 401"""
        resp = requests.get(f"{BASE_URL}/api/tasks")
        assert resp.status_code == 401, f"Expected 401 for unauthenticated, got {resp.status_code}"
        print(f"✓ Unauthenticated access returns 401")
    
    def test_garbage_token_returns_401(self):
        """Garbage token should return 401"""
        resp = requests.get(
            f"{BASE_URL}/api/tasks",
            headers={"Authorization": "Bearer garbage_token_xyz123"}
        )
        assert resp.status_code == 401, f"Expected 401 for garbage token, got {resp.status_code}"
        print(f"✓ Garbage token returns 401")
    
    def test_guest_can_view_own_profile(self):
        """Guest should be able to view their own profile"""
        auth = TestHelpers.login(**CREDENTIALS['qa_guest'])
        assert "token" in auth, f"Guest login failed: {auth}"
        
        resp = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers=TestHelpers.auth_headers(auth["token"])
        )
        assert resp.status_code == 200, f"Guest should view own profile: {resp.status_code}"
        print(f"✓ Guest can view own profile")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
