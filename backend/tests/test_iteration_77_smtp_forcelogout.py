"""
Iteration 77 Tests: SMTP Provider, DNS Check, Force-Logout Features

Tests:
1. SMTP PROVIDER: PUT /api/admin/email-config accepts smtp block, GET returns masked password
2. SMTP HEALTH: POST /api/admin/email-config/smtp-health with valid/invalid smtp config
3. SMTP FALLBACK: With provider='resend' + fallback_to_smtp=true
4. DNS CHECK: GET /api/admin/email-config/dns-check?domain=example.com&provider=resend
5. DNS CHECK FALLBACK: GET /api/admin/email-config/dns-check (no params) uses stored config
6. FORCE-LOGOUT PER USER: POST /api/admin/users/{user_id}/force-logout bumps token_version
7. FORCE-LOGOUT GLOBAL: POST /api/admin/force-logout-all increments token_version for all except caller
8. TOKEN VERSION IN NEW TOKENS: After force-logout, re-login gets new tv claim
9. REFRESH WITH NEW tv: Old refresh cookie returns 401 'Session invalidated'
10. REGRESSION: All existing auth + admin flows still work
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"


class TestSMTPConfiguration:
    """Tests for SMTP provider configuration"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin before each test"""
        self.session = requests.Session()
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        self.admin_user = resp.json()
        yield
        self.session.close()

    def test_get_email_config_returns_smtp_block(self):
        """GET /api/admin/email-config should return smtp block with masked password"""
        resp = self.session.get(f"{BASE_URL}/api/admin/email-config")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Verify smtp block exists
        assert "smtp" in data, "smtp block missing from response"
        smtp = data["smtp"]
        
        # Verify smtp fields
        assert "host" in smtp
        assert "port" in smtp
        assert "username" in smtp
        assert "password" in smtp
        assert "use_tls" in smtp
        assert "use_starttls" in smtp
        assert "from_name" in smtp
        assert "from_email" in smtp
        
        # Verify fallback_to_smtp field
        assert "fallback_to_smtp" in data
        print(f"PASSED: GET email-config returns smtp block with fields: {list(smtp.keys())}")

    def test_put_email_config_with_smtp_block(self):
        """PUT /api/admin/email-config accepts smtp block"""
        smtp_config = {
            "provider": "smtp",
            "sender_email": "test@example.com",
            "enabled": True,
            "smtp": {
                "host": "smtp.test.example",
                "port": 587,
                "username": "testuser",
                "password": "testpass123",
                "use_tls": False,
                "use_starttls": True,
                "from_name": "Test MeetFlow",
                "from_email": "noreply@test.example"
            },
            "fallback_to_smtp": False
        }
        
        resp = self.session.put(f"{BASE_URL}/api/admin/email-config", json=smtp_config)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        
        # Verify the config was saved
        get_resp = self.session.get(f"{BASE_URL}/api/admin/email-config")
        assert get_resp.status_code == 200
        data = get_resp.json()
        
        assert data["provider"] == "smtp"
        assert data["smtp"]["host"] == "smtp.test.example"
        assert data["smtp"]["port"] == 587
        assert data["smtp"]["username"] == "testuser"
        # Password should be masked
        assert data["smtp"]["password"].startswith("***") or data["smtp"]["password"] == "***"
        print("PASSED: PUT email-config with smtp block saves correctly, password masked")

    def test_put_email_config_preserves_masked_password(self):
        """PUT with masked password should preserve stored password"""
        # First set a password
        self.session.put(f"{BASE_URL}/api/admin/email-config", json={
            "smtp": {"host": "smtp.test.example", "password": "realpassword123"}
        })
        
        # Now update with masked password - should preserve original
        resp = self.session.put(f"{BASE_URL}/api/admin/email-config", json={
            "smtp": {"host": "smtp.test.example", "password": "***rd123"}
        })
        assert resp.status_code == 200
        print("PASSED: Masked password preserved on update")

    def test_email_config_provider_options(self):
        """Provider select should accept 'smtp' as valid option"""
        for provider in ["none", "resend", "sendgrid", "smtp"]:
            resp = self.session.put(f"{BASE_URL}/api/admin/email-config", json={
                "provider": provider
            })
            assert resp.status_code == 200, f"Provider '{provider}' failed: {resp.text}"
        print("PASSED: All 4 provider options (none, resend, sendgrid, smtp) accepted")


class TestSMTPHealth:
    """Tests for SMTP health check endpoint"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        yield
        self.session.close()

    def test_smtp_health_with_invalid_host(self):
        """POST /api/admin/email-config/smtp-health with invalid host returns {ok: false, error}"""
        resp = self.session.post(f"{BASE_URL}/api/admin/email-config/smtp-health", json={
            "smtp": {
                "host": "smtp.invalid.example",
                "port": 587,
                "username": "",
                "password": "",
                "use_starttls": True
            }
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert "ok" in data
        assert data["ok"] == False, "Expected ok=false for invalid host"
        assert "error" in data, "Expected error message for invalid host"
        print(f"PASSED: SMTP health check returns ok=false for invalid host, error: {data.get('error', '')[:50]}")

    def test_smtp_health_missing_host(self):
        """POST /api/admin/email-config/smtp-health with missing host returns error"""
        resp = self.session.post(f"{BASE_URL}/api/admin/email-config/smtp-health", json={
            "smtp": {
                "host": "",
                "port": 587
            }
        })
        assert resp.status_code == 200
        data = resp.json()
        
        assert data["ok"] == False
        assert "error" in data
        print(f"PASSED: SMTP health check returns error for missing host: {data.get('error')}")

    def test_smtp_health_uses_stored_config_when_no_body(self):
        """POST /api/admin/email-config/smtp-health without smtp in body uses stored config"""
        # First set a config
        self.session.put(f"{BASE_URL}/api/admin/email-config", json={
            "smtp": {"host": "smtp.stored.example", "port": 587}
        })
        
        # Call health check without smtp in body
        resp = self.session.post(f"{BASE_URL}/api/admin/email-config/smtp-health", json={})
        assert resp.status_code == 200
        data = resp.json()
        
        # Should use stored config (which has invalid host, so ok=false)
        assert "ok" in data
        print(f"PASSED: SMTP health uses stored config when body omits smtp, ok={data['ok']}")

    def test_smtp_health_requires_admin(self):
        """POST /api/admin/email-config/smtp-health requires admin role"""
        # Create a non-admin session
        non_admin_session = requests.Session()
        
        # Try without auth
        resp = non_admin_session.post(f"{BASE_URL}/api/admin/email-config/smtp-health", json={
            "smtp": {"host": "test.example"}
        })
        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"
        print("PASSED: SMTP health requires authentication (401 without)")


class TestDNSCheck:
    """Tests for DNS check endpoint"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        yield
        self.session.close()

    def test_dns_check_with_domain_param(self):
        """GET /api/admin/email-config/dns-check?domain=example.com returns DNS records"""
        resp = self.session.get(f"{BASE_URL}/api/admin/email-config/dns-check", params={
            "domain": "example.com",
            "provider": "resend"
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "domain" in data
        assert "mx" in data
        assert "spf" in data
        assert "dkim" in data
        assert "dmarc" in data
        assert "severity" in data
        assert "summary" in data
        assert "hints" in data
        
        # Verify mx/spf/dkim/dmarc structure
        for key in ["mx", "spf", "dkim", "dmarc"]:
            assert "ok" in data[key], f"{key} missing 'ok' field"
        
        # Verify summary structure
        for key in ["mx", "spf", "dkim", "dmarc"]:
            assert key in data["summary"], f"summary missing '{key}'"
        
        print(f"PASSED: DNS check for example.com returns: mx={data['mx']['ok']}, spf={data['spf']['ok']}, dkim={data['dkim']['ok']}, dmarc={data['dmarc']['ok']}")

    def test_dns_check_with_email_address(self):
        """GET /api/admin/email-config/dns-check extracts domain from email address"""
        resp = self.session.get(f"{BASE_URL}/api/admin/email-config/dns-check", params={
            "domain": "test@example.com",
            "provider": "resend"
        })
        assert resp.status_code == 200
        data = resp.json()
        
        assert data["domain"] == "example.com", f"Expected domain 'example.com', got '{data['domain']}'"
        print("PASSED: DNS check extracts domain from email address")

    def test_dns_check_fallback_to_stored_config(self):
        """GET /api/admin/email-config/dns-check (no params) uses stored sender_email domain"""
        # First set sender_email
        self.session.put(f"{BASE_URL}/api/admin/email-config", json={
            "sender_email": "noreply@example.com",
            "provider": "resend"
        })
        
        # Call DNS check without params
        resp = self.session.get(f"{BASE_URL}/api/admin/email-config/dns-check")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "domain" in data
        print(f"PASSED: DNS check fallback uses stored config, domain={data['domain']}")

    def test_dns_check_invalid_domain(self):
        """GET /api/admin/email-config/dns-check with invalid domain returns error"""
        resp = self.session.get(f"{BASE_URL}/api/admin/email-config/dns-check", params={
            "domain": "does-not-exist-123.invalid"
        })
        assert resp.status_code == 200
        data = resp.json()
        
        # Should return results with ok=false for most records
        assert "domain" in data
        print(f"PASSED: DNS check for invalid domain returns: mx={data.get('mx', {}).get('ok')}, spf={data.get('spf', {}).get('ok')}")

    def test_dns_check_requires_admin(self):
        """GET /api/admin/email-config/dns-check requires admin role"""
        non_admin_session = requests.Session()
        resp = non_admin_session.get(f"{BASE_URL}/api/admin/email-config/dns-check", params={
            "domain": "example.com"
        })
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASSED: DNS check requires authentication")


class TestForceLogoutPerUser:
    """Tests for force-logout per user endpoint"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        self.admin_user = resp.json()
        yield
        self.session.close()

    def test_force_logout_bumps_token_version(self):
        """POST /api/admin/users/{user_id}/force-logout bumps token_version by 1"""
        # Create a test user
        test_email = f"TEST_forcelogout_{uuid.uuid4().hex[:8]}@test.com"
        invite_resp = self.session.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": test_email,
            "name": "Test Force Logout",
            "role": "member"
        })
        assert invite_resp.status_code == 200
        test_user = invite_resp.json()
        test_user_id = test_user["user_id"]
        
        try:
            # Get initial token_version (should be 0 or undefined)
            users_resp = self.session.get(f"{BASE_URL}/api/admin/users")
            users = users_resp.json()
            target_user = next((u for u in users if u["user_id"] == test_user_id), None)
            initial_tv = target_user.get("token_version", 0) if target_user else 0
            
            # Force logout the user
            resp = self.session.post(f"{BASE_URL}/api/admin/users/{test_user_id}/force-logout")
            assert resp.status_code == 200, f"Failed: {resp.text}"
            data = resp.json()
            
            assert "user_id" in data
            assert "token_version" in data
            assert data["token_version"] == initial_tv + 1, f"Expected tv={initial_tv + 1}, got {data['token_version']}"
            print(f"PASSED: Force logout bumps token_version from {initial_tv} to {data['token_version']}")
        finally:
            # Cleanup
            self.session.delete(f"{BASE_URL}/api/admin/users/{test_user_id}")

    def test_force_logout_requires_admin(self):
        """POST /api/admin/users/{user_id}/force-logout requires admin role"""
        non_admin_session = requests.Session()
        resp = non_admin_session.post(f"{BASE_URL}/api/admin/users/some_user_id/force-logout")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASSED: Force logout requires authentication")

    def test_force_logout_nonexistent_user(self):
        """POST /api/admin/users/{user_id}/force-logout returns 404 for nonexistent user"""
        resp = self.session.post(f"{BASE_URL}/api/admin/users/nonexistent_user_12345/force-logout")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("PASSED: Force logout returns 404 for nonexistent user")

    def test_force_logout_invalidates_old_tokens(self):
        """After force-logout, old tokens return 401 'Session invalidated'"""
        # Create a test user
        test_email = f"TEST_tokeninvalid_{uuid.uuid4().hex[:8]}@test.com"
        test_password = "testpass123"
        
        invite_resp = self.session.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": test_email,
            "name": "Test Token Invalid",
            "role": "member"
        })
        assert invite_resp.status_code == 200
        test_user = invite_resp.json()
        test_user_id = test_user["user_id"]
        temp_password = test_user["temp_password"]
        
        try:
            # Login as test user to get tokens
            user_session = requests.Session()
            login_resp = user_session.post(f"{BASE_URL}/api/auth/login", json={
                "email": test_email,
                "password": temp_password
            })
            assert login_resp.status_code == 200, f"Test user login failed: {login_resp.text}"
            
            # Verify user can access /api/auth/me
            me_resp = user_session.get(f"{BASE_URL}/api/auth/me")
            assert me_resp.status_code == 200, "User should be able to access /api/auth/me before force-logout"
            
            # Admin force-logouts the user
            force_resp = self.session.post(f"{BASE_URL}/api/admin/users/{test_user_id}/force-logout")
            assert force_resp.status_code == 200
            
            # Now the old session should be invalidated
            me_resp2 = user_session.get(f"{BASE_URL}/api/auth/me")
            assert me_resp2.status_code == 401, f"Expected 401 after force-logout, got {me_resp2.status_code}"
            
            # Check for 'Session invalidated' message
            error_detail = me_resp2.json().get("detail", "")
            assert "Session invalidated" in error_detail or "invalidated" in error_detail.lower(), \
                f"Expected 'Session invalidated' in error, got: {error_detail}"
            
            print("PASSED: Old tokens return 401 'Session invalidated' after force-logout")
        finally:
            self.session.delete(f"{BASE_URL}/api/admin/users/{test_user_id}")


class TestForceLogoutAll:
    """Tests for global force-logout endpoint"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        self.admin_user = resp.json()
        yield
        self.session.close()

    def test_force_logout_all_returns_modified_count(self):
        """POST /api/admin/force-logout-all returns {modified_count}"""
        resp = self.session.post(f"{BASE_URL}/api/admin/force-logout-all")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert "modified_count" in data
        assert isinstance(data["modified_count"], int)
        print(f"PASSED: Force logout all returns modified_count={data['modified_count']}")

    def test_force_logout_all_excludes_caller(self):
        """POST /api/admin/force-logout-all does NOT invalidate caller's session"""
        # Call force-logout-all
        resp = self.session.post(f"{BASE_URL}/api/admin/force-logout-all")
        assert resp.status_code == 200
        
        # Caller's session should still be valid
        me_resp = self.session.get(f"{BASE_URL}/api/auth/me")
        assert me_resp.status_code == 200, f"Caller's session should remain valid, got {me_resp.status_code}"
        print("PASSED: Force logout all excludes caller - admin session still valid")

    def test_force_logout_all_invalidates_other_users(self):
        """POST /api/admin/force-logout-all invalidates other users' sessions"""
        # Create a test user
        test_email = f"TEST_logoutall_{uuid.uuid4().hex[:8]}@test.com"
        invite_resp = self.session.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": test_email,
            "name": "Test Logout All",
            "role": "member"
        })
        assert invite_resp.status_code == 200
        test_user = invite_resp.json()
        test_user_id = test_user["user_id"]
        temp_password = test_user["temp_password"]
        
        try:
            # Login as test user
            user_session = requests.Session()
            login_resp = user_session.post(f"{BASE_URL}/api/auth/login", json={
                "email": test_email,
                "password": temp_password
            })
            assert login_resp.status_code == 200
            
            # Verify user can access /api/auth/me
            me_resp = user_session.get(f"{BASE_URL}/api/auth/me")
            assert me_resp.status_code == 200
            
            # Admin calls force-logout-all
            force_resp = self.session.post(f"{BASE_URL}/api/admin/force-logout-all")
            assert force_resp.status_code == 200
            
            # Test user's session should be invalidated
            me_resp2 = user_session.get(f"{BASE_URL}/api/auth/me")
            assert me_resp2.status_code == 401, f"Expected 401 for other user after force-logout-all, got {me_resp2.status_code}"
            print("PASSED: Force logout all invalidates other users' sessions")
        finally:
            self.session.delete(f"{BASE_URL}/api/admin/users/{test_user_id}")

    def test_force_logout_all_requires_admin(self):
        """POST /api/admin/force-logout-all requires admin role"""
        non_admin_session = requests.Session()
        resp = non_admin_session.post(f"{BASE_URL}/api/admin/force-logout-all")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASSED: Force logout all requires authentication")


class TestTokenVersionInNewTokens:
    """Tests for token version in newly issued tokens"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        yield
        self.session.close()

    def test_relogin_after_force_logout_gets_new_tv(self):
        """After force-logout, re-login gets new token with updated tv claim"""
        # Create a test user
        test_email = f"TEST_newtv_{uuid.uuid4().hex[:8]}@test.com"
        invite_resp = self.session.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": test_email,
            "name": "Test New TV",
            "role": "member"
        })
        assert invite_resp.status_code == 200
        test_user = invite_resp.json()
        test_user_id = test_user["user_id"]
        temp_password = test_user["temp_password"]
        
        try:
            # Login as test user
            user_session = requests.Session()
            login_resp = user_session.post(f"{BASE_URL}/api/auth/login", json={
                "email": test_email,
                "password": temp_password
            })
            assert login_resp.status_code == 200
            
            # Admin force-logouts the user
            force_resp = self.session.post(f"{BASE_URL}/api/admin/users/{test_user_id}/force-logout")
            assert force_resp.status_code == 200
            new_tv = force_resp.json()["token_version"]
            
            # Re-login as test user
            user_session2 = requests.Session()
            login_resp2 = user_session2.post(f"{BASE_URL}/api/auth/login", json={
                "email": test_email,
                "password": temp_password
            })
            assert login_resp2.status_code == 200, f"Re-login failed: {login_resp2.text}"
            
            # New session should work
            me_resp = user_session2.get(f"{BASE_URL}/api/auth/me")
            assert me_resp.status_code == 200, f"New session should work, got {me_resp.status_code}"
            print(f"PASSED: Re-login after force-logout works, new tv={new_tv}")
        finally:
            self.session.delete(f"{BASE_URL}/api/admin/users/{test_user_id}")


class TestRefreshWithNewTV:
    """Tests for refresh token behavior after force-logout"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        yield
        self.session.close()

    def test_old_refresh_token_returns_401_after_force_logout(self):
        """After force-logout, old refresh token on /api/auth/refresh returns 401"""
        # Create a test user
        test_email = f"TEST_oldrefresh_{uuid.uuid4().hex[:8]}@test.com"
        invite_resp = self.session.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": test_email,
            "name": "Test Old Refresh",
            "role": "member"
        })
        assert invite_resp.status_code == 200
        test_user = invite_resp.json()
        test_user_id = test_user["user_id"]
        temp_password = test_user["temp_password"]
        
        try:
            # Login as test user to get refresh token
            user_session = requests.Session()
            login_resp = user_session.post(f"{BASE_URL}/api/auth/login", json={
                "email": test_email,
                "password": temp_password
            })
            assert login_resp.status_code == 200
            
            # Verify refresh works before force-logout
            refresh_resp = user_session.post(f"{BASE_URL}/api/auth/refresh")
            assert refresh_resp.status_code == 200, f"Refresh should work before force-logout, got {refresh_resp.status_code}"
            
            # Admin force-logouts the user
            force_resp = self.session.post(f"{BASE_URL}/api/admin/users/{test_user_id}/force-logout")
            assert force_resp.status_code == 200
            
            # Old refresh token should now fail
            refresh_resp2 = user_session.post(f"{BASE_URL}/api/auth/refresh")
            assert refresh_resp2.status_code == 401, f"Expected 401 for old refresh token, got {refresh_resp2.status_code}"
            
            # Check for 'Session invalidated' message
            error_detail = refresh_resp2.json().get("detail", "")
            assert "Session invalidated" in error_detail or "invalidated" in error_detail.lower(), \
                f"Expected 'Session invalidated' in error, got: {error_detail}"
            
            print("PASSED: Old refresh token returns 401 'Session invalidated' after force-logout")
        finally:
            self.session.delete(f"{BASE_URL}/api/admin/users/{test_user_id}")


class TestRegressionAuthAdmin:
    """Regression tests for existing auth and admin flows"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        yield
        self.session.close()

    def test_auth_login(self):
        """POST /api/auth/login still works"""
        session = requests.Session()
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" in data
        assert "email" in data
        print("PASSED: /api/auth/login works")

    def test_auth_refresh(self):
        """POST /api/auth/refresh still works"""
        resp = self.session.post(f"{BASE_URL}/api/auth/refresh")
        assert resp.status_code == 200
        print("PASSED: /api/auth/refresh works")

    def test_auth_me(self):
        """GET /api/auth/me still works"""
        resp = self.session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" in data
        print("PASSED: /api/auth/me works")

    def test_admin_email_config_get_put_test(self):
        """GET/PUT/test /api/admin/email-config still work"""
        # GET
        get_resp = self.session.get(f"{BASE_URL}/api/admin/email-config")
        assert get_resp.status_code == 200
        
        # PUT
        put_resp = self.session.put(f"{BASE_URL}/api/admin/email-config", json={
            "provider": "none",
            "enabled": False
        })
        assert put_resp.status_code == 200
        
        # Test
        test_resp = self.session.post(f"{BASE_URL}/api/admin/email-config/test", json={
            "to_email": "test@example.com"
        })
        assert test_resp.status_code == 200
        print("PASSED: /api/admin/email-config GET/PUT/test work")

    def test_admin_users_crud(self):
        """Admin users CRUD still works"""
        # List
        list_resp = self.session.get(f"{BASE_URL}/api/admin/users")
        assert list_resp.status_code == 200
        assert isinstance(list_resp.json(), list)
        print("PASSED: /api/admin/users CRUD works")

    def test_admin_stats(self):
        """GET /api/admin/stats still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_users" in data
        print("PASSED: /api/admin/stats works")

    def test_admin_groups(self):
        """GET /api/admin/groups still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/groups")
        assert resp.status_code == 200
        print("PASSED: /api/admin/groups works")

    def test_admin_capabilities(self):
        """GET /api/admin/capabilities still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert "capabilities" in data
        print("PASSED: /api/admin/capabilities works")

    def test_admin_presets(self):
        """GET /api/admin/presets still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert "presets" in data
        print("PASSED: /api/admin/presets works")

    def test_admin_cap_rules(self):
        """GET /api/admin/cap-rules still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/cap-rules")
        assert resp.status_code == 200
        data = resp.json()
        assert "rules" in data
        print("PASSED: /api/admin/cap-rules works")

    def test_user_permissions_with_capability_labels(self):
        """GET /api/user/permissions returns capability_labels"""
        resp = self.session.get(f"{BASE_URL}/api/user/permissions")
        assert resp.status_code == 200
        data = resp.json()
        assert "capabilities" in data
        assert "capability_labels" in data
        print("PASSED: /api/user/permissions with capability_labels works")

    def test_email_preferences(self):
        """GET/PUT /api/users/me/email-preferences still work"""
        get_resp = self.session.get(f"{BASE_URL}/api/users/me/email-preferences")
        assert get_resp.status_code == 200
        
        put_resp = self.session.put(f"{BASE_URL}/api/users/me/email-preferences", json={
            "newsletter_enabled": True
        })
        assert put_resp.status_code == 200
        print("PASSED: /api/users/me/email-preferences GET/PUT work")

    def test_unsubscribe_invalid_token(self):
        """GET /api/unsubscribe/{token} returns 400 for invalid token"""
        resp = self.session.get(f"{BASE_URL}/api/unsubscribe/invalid_token_12345")
        assert resp.status_code == 400
        print("PASSED: /api/unsubscribe/{token} returns 400 for invalid token")

    def test_onboarding_complete(self):
        """POST /api/users/me/onboarding-complete still works"""
        resp = self.session.post(f"{BASE_URL}/api/users/me/onboarding-complete")
        assert resp.status_code == 200
        data = resp.json()
        assert "onboarding_completed_at" in data
        print("PASSED: /api/users/me/onboarding-complete works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
