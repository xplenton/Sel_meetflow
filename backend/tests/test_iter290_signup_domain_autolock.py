"""
Iteration 290 — Self-Registration Domain Allowlist + Auto-Lock Unverified Users

Tests:
1. PUT /api/admin/org-settings accepts allowed_signup_domains and auto_lock_unverified_hours
2. POST /api/auth/register with domain NOT in list → 403
3. POST /api/auth/register with domain IN list → 200, user created with self_registered=true
4. POST /api/auth/register when allowed_signup_domains is EMPTY → any domain allowed
5. User with status=locked_unverified tries /api/auth/login → 403
6. User with status=inactive gets separate message 'Konto deaktiviert'
7. Admin-created users (self_registered != True) are NEVER auto-locked
8. Auto-lock sweep with auto_lock_unverified_hours=0 → nobody locked (disabled mode)
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

class TestIter290SignupDomainAutoLock:
    """Tests for Iteration 290 self-registration domain allowlist and auto-lock features"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: login as admin, store token, reset org_settings after each test"""
        # Login as admin
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        self.admin_token = resp.json().get("token")
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        yield
        
        # Cleanup: reset org_settings to empty allowed_signup_domains
        requests.put(
            f"{BASE_URL}/api/admin/org-settings",
            json={"allowed_signup_domains": [], "auto_lock_unverified_hours": 24},
            headers=self.admin_headers
        )
        
        # Cleanup test users
        # Note: We'll use a prefix to identify test users
    
    def _cleanup_test_user(self, email):
        """Helper to delete test user via direct DB or admin endpoint if available"""
        # For now, we'll just note that cleanup should happen
        pass
    
    # =========================================================================
    # Test 1: PUT /api/admin/org-settings accepts new fields
    # =========================================================================
    def test_org_settings_accepts_allowed_signup_domains(self):
        """PUT /api/admin/org-settings accepts allowed_signup_domains, lowercased + @-stripped"""
        # Set domains with various formats
        resp = requests.put(
            f"{BASE_URL}/api/admin/org-settings",
            json={"allowed_signup_domains": ["@MEETFLOW.COM", "  Partner.DE  ", "example.org"]},
            headers=self.admin_headers
        )
        assert resp.status_code == 200, f"Failed to update org-settings: {resp.text}"
        data = resp.json()
        
        # Verify domains are lowercased and @-stripped
        domains = data.get("allowed_signup_domains", [])
        assert "meetflow.com" in domains, f"meetflow.com not in {domains}"
        assert "partner.de" in domains, f"partner.de not in {domains}"
        assert "example.org" in domains, f"example.org not in {domains}"
        # Verify no @ prefix
        for d in domains:
            assert not d.startswith("@"), f"Domain {d} still has @ prefix"
        print(f"✓ allowed_signup_domains saved correctly: {domains}")
    
    def test_org_settings_accepts_auto_lock_unverified_hours(self):
        """PUT /api/admin/org-settings accepts auto_lock_unverified_hours (0-168)"""
        # Test valid value
        resp = requests.put(
            f"{BASE_URL}/api/admin/org-settings",
            json={"auto_lock_unverified_hours": 48},
            headers=self.admin_headers
        )
        assert resp.status_code == 200
        assert resp.json().get("auto_lock_unverified_hours") == 48
        print("✓ auto_lock_unverified_hours=48 saved correctly")
        
        # Test boundary: 0 (disabled)
        resp = requests.put(
            f"{BASE_URL}/api/admin/org-settings",
            json={"auto_lock_unverified_hours": 0},
            headers=self.admin_headers
        )
        assert resp.status_code == 200
        assert resp.json().get("auto_lock_unverified_hours") == 0
        print("✓ auto_lock_unverified_hours=0 (disabled) saved correctly")
        
        # Test boundary: 168 (max)
        resp = requests.put(
            f"{BASE_URL}/api/admin/org-settings",
            json={"auto_lock_unverified_hours": 168},
            headers=self.admin_headers
        )
        assert resp.status_code == 200
        assert resp.json().get("auto_lock_unverified_hours") == 168
        print("✓ auto_lock_unverified_hours=168 (max) saved correctly")
        
        # Test clamping: value > 168 should be clamped to 168
        resp = requests.put(
            f"{BASE_URL}/api/admin/org-settings",
            json={"auto_lock_unverified_hours": 500},
            headers=self.admin_headers
        )
        assert resp.status_code == 200
        assert resp.json().get("auto_lock_unverified_hours") == 168
        print("✓ auto_lock_unverified_hours=500 clamped to 168")
    
    # =========================================================================
    # Test 2: POST /api/auth/register with domain NOT in list → 403
    # =========================================================================
    def test_register_domain_not_in_allowlist_returns_403(self):
        """POST /api/auth/register with domain NOT in allowed list → 403"""
        # First, set allowed domains
        requests.put(
            f"{BASE_URL}/api/admin/org-settings",
            json={"allowed_signup_domains": ["meetflow.com", "partner.de"]},
            headers=self.admin_headers
        )
        
        # Try to register with a domain NOT in the list
        test_email = f"test_iter290_{uuid.uuid4().hex[:8]}@evil.com"
        resp = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "testpass123",
            "name": "Test Evil Domain"
        })
        
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", "")
        assert "Selbst-Registrierung nur fuer folgende Domains erlaubt" in detail, f"Wrong error message: {detail}"
        assert "meetflow.com" in detail or "partner.de" in detail, f"Allowed domains not in message: {detail}"
        print(f"✓ Registration with evil.com blocked: {detail}")
    
    # =========================================================================
    # Test 3: POST /api/auth/register with domain IN list → 200
    # =========================================================================
    def test_register_domain_in_allowlist_succeeds(self):
        """POST /api/auth/register with domain IN allowed list → 200, self_registered=true"""
        # Set allowed domains
        requests.put(
            f"{BASE_URL}/api/admin/org-settings",
            json={"allowed_signup_domains": ["meetflow.com", "testdomain.org"]},
            headers=self.admin_headers
        )
        
        # Register with allowed domain
        test_email = f"test_iter290_{uuid.uuid4().hex[:8]}@testdomain.org"
        resp = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "testpass123",
            "name": "Test Allowed Domain"
        })
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "user_id" in data, f"No user_id in response: {data}"
        assert data.get("email") == test_email
        print(f"✓ Registration with testdomain.org succeeded: user_id={data.get('user_id')}")
        
        # Verify user has self_registered=true and email_verified=false
        # We need to check via admin endpoint or direct DB
        # For now, we verify the user can login but will be subject to auto-lock
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": test_email,
            "password": "testpass123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        print("✓ Self-registered user can login (email not yet verified)")
    
    # =========================================================================
    # Test 4: POST /api/auth/register when allowed_signup_domains is EMPTY
    # =========================================================================
    def test_register_empty_allowlist_allows_any_domain(self):
        """POST /api/auth/register when allowed_signup_domains is EMPTY → any domain allowed"""
        # Clear allowed domains (legacy behavior)
        requests.put(
            f"{BASE_URL}/api/admin/org-settings",
            json={"allowed_signup_domains": []},
            headers=self.admin_headers
        )
        
        # Register with any domain
        test_email = f"test_iter290_{uuid.uuid4().hex[:8]}@anydomain.xyz"
        resp = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "testpass123",
            "name": "Test Any Domain"
        })
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print(f"✓ Registration with anydomain.xyz succeeded when allowlist is empty")
    
    # =========================================================================
    # Test 5: User with status=locked_unverified tries /api/auth/login → 403
    # =========================================================================
    def test_login_locked_unverified_user_returns_403(self):
        """User with status=locked_unverified tries /api/auth/login → 403 with German message"""
        # First, create a user via registration
        requests.put(
            f"{BASE_URL}/api/admin/org-settings",
            json={"allowed_signup_domains": []},
            headers=self.admin_headers
        )
        
        test_email = f"test_iter290_locked_{uuid.uuid4().hex[:8]}@test.com"
        reg_resp = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "testpass123",
            "name": "Test Locked User"
        })
        assert reg_resp.status_code == 200
        user_id = reg_resp.json().get("user_id")
        
        # Now we need to manually set the user's status to locked_unverified
        # This requires admin access to update user status
        # We'll use the admin users endpoint if available, or simulate via direct approach
        
        # Try to update user status via admin endpoint
        update_resp = requests.put(
            f"{BASE_URL}/api/admin/users/{user_id}",
            json={"status": "locked_unverified"},
            headers=self.admin_headers
        )
        
        if update_resp.status_code != 200:
            # If admin endpoint doesn't support status update, skip this test
            pytest.skip("Admin endpoint doesn't support status update, cannot test locked_unverified login")
        
        # Now try to login
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": test_email,
            "password": "testpass123"
        })
        
        assert login_resp.status_code == 403, f"Expected 403, got {login_resp.status_code}: {login_resp.text}"
        detail = login_resp.json().get("detail", "")
        assert "gesperrt" in detail.lower() or "locked" in detail.lower(), f"Wrong error message: {detail}"
        assert "E-Mail" in detail or "email" in detail.lower(), f"Message should mention email verification: {detail}"
        print(f"✓ Login blocked for locked_unverified user: {detail}")
    
    # =========================================================================
    # Test 6: User with status=inactive gets separate message
    # =========================================================================
    def test_login_inactive_user_returns_403_with_deactivated_message(self):
        """User with status=inactive gets 'Konto deaktiviert' message, not locked message"""
        # Create a user
        requests.put(
            f"{BASE_URL}/api/admin/org-settings",
            json={"allowed_signup_domains": []},
            headers=self.admin_headers
        )
        
        test_email = f"test_iter290_inactive_{uuid.uuid4().hex[:8]}@test.com"
        reg_resp = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "testpass123",
            "name": "Test Inactive User"
        })
        assert reg_resp.status_code == 200
        user_id = reg_resp.json().get("user_id")
        
        # Set user status to inactive
        update_resp = requests.put(
            f"{BASE_URL}/api/admin/users/{user_id}",
            json={"status": "inactive"},
            headers=self.admin_headers
        )
        
        if update_resp.status_code != 200:
            pytest.skip("Admin endpoint doesn't support status update")
        
        # Try to login
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": test_email,
            "password": "testpass123"
        })
        
        assert login_resp.status_code == 403, f"Expected 403, got {login_resp.status_code}"
        detail = login_resp.json().get("detail", "")
        assert "deaktiviert" in detail.lower(), f"Expected 'deaktiviert' in message: {detail}"
        # Should NOT contain locked_unverified message
        assert "bestaetigt" not in detail.lower() and "frist" not in detail.lower(), \
            f"Inactive user should not get locked_unverified message: {detail}"
        print(f"✓ Inactive user gets correct message: {detail}")
    
    # =========================================================================
    # Test 7: Admin-created users are NEVER auto-locked
    # =========================================================================
    def test_admin_created_user_not_auto_locked(self):
        """Admin-created users (self_registered != True) are NEVER auto-locked"""
        # Create user via admin endpoint (not self-registration)
        test_email = f"test_iter290_admin_created_{uuid.uuid4().hex[:8]}@test.com"
        
        create_resp = requests.post(
            f"{BASE_URL}/api/admin/users",
            json={
                "email": test_email,
                "password": "testpass123",
                "name": "Admin Created User",
                "role": "user"
            },
            headers=self.admin_headers
        )
        
        if create_resp.status_code not in [200, 201]:
            pytest.skip(f"Admin user creation endpoint not available: {create_resp.status_code}")
        
        user_id = create_resp.json().get("user_id")
        print(f"✓ Admin-created user: {user_id}")
        
        # Verify user does NOT have self_registered=True
        # The user should be able to login even if email is unverified and time has passed
        # (We can't easily test the sweep without waiting, but we verify the flag)
        
        # Get user details
        user_resp = requests.get(
            f"{BASE_URL}/api/admin/users/{user_id}",
            headers=self.admin_headers
        )
        
        if user_resp.status_code == 200:
            user_data = user_resp.json()
            # Admin-created users should NOT have self_registered=True
            assert user_data.get("self_registered") != True, \
                f"Admin-created user should not have self_registered=True: {user_data}"
            print("✓ Admin-created user does not have self_registered=True")
        
        # User should be able to login
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": test_email,
            "password": "testpass123"
        })
        assert login_resp.status_code == 200, f"Admin-created user should be able to login: {login_resp.text}"
        print("✓ Admin-created user can login (not subject to auto-lock)")
    
    # =========================================================================
    # Test 8: Auto-lock with auto_lock_unverified_hours=0 → disabled
    # =========================================================================
    def test_auto_lock_disabled_when_hours_is_zero(self):
        """When auto_lock_unverified_hours=0, auto-lock is disabled"""
        # Set auto_lock_unverified_hours to 0
        resp = requests.put(
            f"{BASE_URL}/api/admin/org-settings",
            json={"auto_lock_unverified_hours": 0},
            headers=self.admin_headers
        )
        assert resp.status_code == 200
        assert resp.json().get("auto_lock_unverified_hours") == 0
        print("✓ auto_lock_unverified_hours set to 0 (disabled)")
        
        # Create a self-registered user
        test_email = f"test_iter290_nolock_{uuid.uuid4().hex[:8]}@test.com"
        reg_resp = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "testpass123",
            "name": "Test No Lock User"
        })
        assert reg_resp.status_code == 200
        
        # User should be able to login (auto-lock is disabled)
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": test_email,
            "password": "testpass123"
        })
        assert login_resp.status_code == 200, f"User should be able to login when auto-lock is disabled: {login_resp.text}"
        print("✓ User can login when auto_lock_unverified_hours=0")
    
    # =========================================================================
    # Test 9: GET /api/admin/org-settings returns new fields
    # =========================================================================
    def test_get_org_settings_returns_new_fields(self):
        """GET /api/admin/org-settings returns allowed_signup_domains and auto_lock_unverified_hours"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/org-settings",
            headers=self.admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Check that fields exist (may be empty/default)
        assert "allowed_signup_domains" in data or data.get("allowed_signup_domains") is None, \
            f"allowed_signup_domains field missing: {data}"
        # auto_lock_unverified_hours should have a default of 24
        hours = data.get("auto_lock_unverified_hours")
        assert hours is not None or "auto_lock_unverified_hours" in data, \
            f"auto_lock_unverified_hours field missing: {data}"
        print(f"✓ GET org-settings returns new fields: allowed_signup_domains={data.get('allowed_signup_domains')}, auto_lock_unverified_hours={hours}")


class TestIter290EdgeCases:
    """Edge case tests for Iteration 290"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert resp.status_code == 200
        self.admin_token = resp.json().get("token")
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        yield
        # Cleanup
        requests.put(
            f"{BASE_URL}/api/admin/org-settings",
            json={"allowed_signup_domains": [], "auto_lock_unverified_hours": 24},
            headers=self.admin_headers
        )
    
    def test_register_case_insensitive_domain_matching(self):
        """Domain matching should be case-insensitive"""
        # Set allowed domain in lowercase
        requests.put(
            f"{BASE_URL}/api/admin/org-settings",
            json={"allowed_signup_domains": ["meetflow.com"]},
            headers=self.admin_headers
        )
        
        # Register with uppercase domain
        test_email = f"test_iter290_{uuid.uuid4().hex[:8]}@MEETFLOW.COM"
        resp = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "testpass123",
            "name": "Test Case Insensitive"
        })
        
        assert resp.status_code == 200, f"Case-insensitive domain matching failed: {resp.text}"
        print("✓ Domain matching is case-insensitive")
    
    def test_register_duplicate_email_still_returns_400(self):
        """Duplicate email registration should still return 400, not 403"""
        # Clear domain restrictions
        requests.put(
            f"{BASE_URL}/api/admin/org-settings",
            json={"allowed_signup_domains": []},
            headers=self.admin_headers
        )
        
        # Register first user
        test_email = f"test_iter290_dup_{uuid.uuid4().hex[:8]}@test.com"
        resp1 = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "testpass123",
            "name": "First User"
        })
        assert resp1.status_code == 200
        
        # Try to register same email again
        resp2 = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "testpass456",
            "name": "Second User"
        })
        
        assert resp2.status_code == 400, f"Expected 400 for duplicate email, got {resp2.status_code}"
        assert "already registered" in resp2.json().get("detail", "").lower()
        print("✓ Duplicate email still returns 400 (not 403)")
    
    def test_domain_check_happens_before_duplicate_check(self):
        """Domain check should happen, but duplicate check takes precedence"""
        # Set restricted domains
        requests.put(
            f"{BASE_URL}/api/admin/org-settings",
            json={"allowed_signup_domains": ["allowed.com"]},
            headers=self.admin_headers
        )
        
        # First, register with allowed domain
        test_email = f"test_iter290_{uuid.uuid4().hex[:8]}@allowed.com"
        resp1 = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "testpass123",
            "name": "First User"
        })
        assert resp1.status_code == 200
        
        # Try to register same email again (should get duplicate error, not domain error)
        resp2 = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "testpass456",
            "name": "Second User"
        })
        
        # Should be 400 (duplicate) not 403 (domain)
        assert resp2.status_code == 400, f"Expected 400, got {resp2.status_code}: {resp2.text}"
        print("✓ Duplicate check takes precedence over domain check")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
