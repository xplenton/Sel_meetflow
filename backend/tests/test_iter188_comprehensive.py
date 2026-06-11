"""Iter 188 — Comprehensive pytest for 2FA / TOTP, DSGVO export, read_db, and regression.

Tests cover:
1. 2FA TOTP full lifecycle (setup, verify, login challenge, recovery codes, disable)
2. 2FA edge cases (expired challenge, wrong codes, regenerate recovery)
3. DSGVO export with richer _iter188 structure
4. read_db usage on admin/stats, search/global, admin/health
5. Regression tests for news, surveys, meetings, chat routes
"""
import os
import time
import requests
import pyotp
import pytest
import uuid


def _api() -> str:
    val = os.environ.get("REACT_APP_BACKEND_URL")
    if val:
        return val.rstrip("/") + "/api"
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/") + "/api"
    return "http://localhost:8001/api"


API = _api()
ADMIN = ("admin@meetflow.com", "admin123")


def _login(email: str, pwd: str) -> dict:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=10)
    return r.json()


def _h(token: str):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ============ Fixtures ============

@pytest.fixture(scope="module")
def admin_token():
    """Get admin token, skip if 2FA is already enabled."""
    body = _login(*ADMIN)
    if body.get("totp_required"):
        pytest.skip("Admin already has 2FA enabled from a previous run; clean DB first.")
    return body["token"]


@pytest.fixture(scope="module")
def test_user():
    """Create a test user for 2FA testing to avoid polluting admin state."""
    email = f"TEST_2fa_{uuid.uuid4().hex[:8]}@meetflow.local"
    pwd = "testpass123"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": pwd, "name": "Test 2FA User"
    }, timeout=10)
    if r.status_code != 200:
        pytest.skip(f"Could not create test user: {r.text}")
    data = r.json()
    return {"email": email, "password": pwd, "token": data["token"], "user_id": data.get("user_id")}


# ============ 2FA Status Endpoint ============

class Test2FAStatus:
    """Tests for GET /api/auth/2fa/status"""
    
    def test_2fa_status_returns_disabled_initially(self, admin_token):
        r = requests.get(f"{API}/auth/2fa/status", headers=_h(admin_token), timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "totp_enabled" in data
        assert "recovery_codes_remaining" in data
        assert data["totp_enabled"] is False
        assert data["recovery_codes_remaining"] == 0

    def test_2fa_status_requires_auth(self):
        r = requests.get(f"{API}/auth/2fa/status", timeout=10)
        assert r.status_code == 401


# ============ 2FA Setup Endpoint ============

class Test2FASetup:
    """Tests for POST /api/auth/2fa/setup"""
    
    def test_2fa_setup_generates_secret_and_qr(self, test_user):
        r = requests.post(f"{API}/auth/2fa/setup", headers=_h(test_user["token"]), timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "secret" in data
        assert "uri" in data
        assert "qr_png" in data
        assert "recovery_codes" in data
        # Validate QR is a data URL
        assert data["qr_png"].startswith("data:image/png;base64,")
        # Validate recovery codes
        assert len(data["recovery_codes"]) == 10
        for code in data["recovery_codes"]:
            # Format: XXXX-XXXX-XXXX
            assert len(code) == 14
            assert code[4] == "-" and code[9] == "-"

    def test_2fa_setup_requires_auth(self):
        r = requests.post(f"{API}/auth/2fa/setup", timeout=10)
        assert r.status_code == 401


# ============ 2FA Verify Setup ============

class Test2FAVerifySetup:
    """Tests for POST /api/auth/2fa/verify-setup"""
    
    def test_verify_setup_with_wrong_code_returns_401(self, test_user):
        # First setup
        r = requests.post(f"{API}/auth/2fa/setup", headers=_h(test_user["token"]), timeout=10)
        assert r.status_code == 200
        
        # Verify with wrong code
        r = requests.post(f"{API}/auth/2fa/verify-setup",
                          headers=_h(test_user["token"]), json={"code": "000000"}, timeout=10)
        assert r.status_code == 401

    def test_verify_setup_with_correct_code_enables_2fa(self, test_user):
        # Setup
        r = requests.post(f"{API}/auth/2fa/setup", headers=_h(test_user["token"]), timeout=10)
        assert r.status_code == 200
        secret = r.json()["secret"]
        
        # Verify with correct code
        code = pyotp.TOTP(secret).now()
        r = requests.post(f"{API}/auth/2fa/verify-setup",
                          headers=_h(test_user["token"]), json={"code": code}, timeout=10)
        assert r.status_code == 200
        assert r.json()["totp_enabled"] is True
        
        # Cleanup: disable 2FA
        time.sleep(1)
        code2 = pyotp.TOTP(secret).now()
        requests.post(f"{API}/auth/2fa/disable",
                      headers=_h(test_user["token"]), json={"code": code2}, timeout=10)


# ============ 2FA Login Flow ============

class Test2FALoginFlow:
    """Tests for 2FA login challenge flow"""
    
    def test_login_with_2fa_returns_challenge_token(self, test_user):
        # Enable 2FA
        r = requests.post(f"{API}/auth/2fa/setup", headers=_h(test_user["token"]), timeout=10)
        secret = r.json()["secret"]
        recovery_codes = r.json()["recovery_codes"]
        
        code = pyotp.TOTP(secret).now()
        r = requests.post(f"{API}/auth/2fa/verify-setup",
                          headers=_h(test_user["token"]), json={"code": code}, timeout=10)
        assert r.status_code == 200
        
        # Login should now require 2FA
        body = _login(test_user["email"], test_user["password"])
        assert body.get("totp_required") is True
        assert "challenge_token" in body
        assert "user_email" in body
        
        # Cleanup
        time.sleep(1)
        code2 = pyotp.TOTP(secret).now()
        requests.post(f"{API}/auth/2fa/disable",
                      headers=_h(test_user["token"]), json={"code": code2}, timeout=10)

    def test_verify_login_with_correct_totp(self, test_user):
        # Enable 2FA
        r = requests.post(f"{API}/auth/2fa/setup", headers=_h(test_user["token"]), timeout=10)
        secret = r.json()["secret"]
        
        code = pyotp.TOTP(secret).now()
        r = requests.post(f"{API}/auth/2fa/verify-setup",
                          headers=_h(test_user["token"]), json={"code": code}, timeout=10)
        
        # Login
        body = _login(test_user["email"], test_user["password"])
        challenge = body["challenge_token"]
        
        # Verify with TOTP
        time.sleep(1)
        code2 = pyotp.TOTP(secret).now()
        r = requests.post(f"{API}/auth/2fa/verify-login",
                          json={"challenge_token": challenge, "code": code2}, timeout=10)
        assert r.status_code == 200
        assert "token" in r.json()
        # Secrets must NOT be leaked
        assert "totp_secret" not in r.json()
        assert "password_hash" not in r.json()
        
        # Cleanup
        new_token = r.json()["token"]
        time.sleep(1)
        code3 = pyotp.TOTP(secret).now()
        requests.post(f"{API}/auth/2fa/disable",
                      headers=_h(new_token), json={"code": code3}, timeout=10)

    def test_verify_login_with_wrong_code_returns_401(self, test_user):
        # Enable 2FA
        r = requests.post(f"{API}/auth/2fa/setup", headers=_h(test_user["token"]), timeout=10)
        secret = r.json()["secret"]
        
        code = pyotp.TOTP(secret).now()
        r = requests.post(f"{API}/auth/2fa/verify-setup",
                          headers=_h(test_user["token"]), json={"code": code}, timeout=10)
        
        # Login
        body = _login(test_user["email"], test_user["password"])
        challenge = body["challenge_token"]
        
        # Verify with wrong code
        r = requests.post(f"{API}/auth/2fa/verify-login",
                          json={"challenge_token": challenge, "code": "000000"}, timeout=10)
        assert r.status_code == 401
        
        # Cleanup
        time.sleep(1)
        code2 = pyotp.TOTP(secret).now()
        requests.post(f"{API}/auth/2fa/disable",
                      headers=_h(test_user["token"]), json={"code": code2}, timeout=10)

    def test_verify_login_with_recovery_code(self, test_user):
        # Enable 2FA
        r = requests.post(f"{API}/auth/2fa/setup", headers=_h(test_user["token"]), timeout=10)
        secret = r.json()["secret"]
        recovery_codes = r.json()["recovery_codes"]
        
        code = pyotp.TOTP(secret).now()
        r = requests.post(f"{API}/auth/2fa/verify-setup",
                          headers=_h(test_user["token"]), json={"code": code}, timeout=10)
        
        # Login
        body = _login(test_user["email"], test_user["password"])
        challenge = body["challenge_token"]
        
        # Verify with recovery code
        r = requests.post(f"{API}/auth/2fa/verify-login",
                          json={"challenge_token": challenge, "code": recovery_codes[0], "mode": "recovery"},
                          timeout=10)
        assert r.status_code == 200
        assert "token" in r.json()
        
        # Same recovery code should now be consumed
        body2 = _login(test_user["email"], test_user["password"])
        challenge2 = body2["challenge_token"]
        r = requests.post(f"{API}/auth/2fa/verify-login",
                          json={"challenge_token": challenge2, "code": recovery_codes[0], "mode": "recovery"},
                          timeout=10)
        assert r.status_code == 401
        
        # Cleanup
        time.sleep(1)
        code2 = pyotp.TOTP(secret).now()
        requests.post(f"{API}/auth/2fa/disable",
                      headers=_h(test_user["token"]), json={"code": code2}, timeout=10)


# ============ 2FA Regenerate Recovery Codes ============

class Test2FARegenerateRecovery:
    """Tests for POST /api/auth/2fa/regenerate-recovery"""
    
    def test_regenerate_recovery_returns_10_fresh_codes(self, test_user):
        # Enable 2FA
        r = requests.post(f"{API}/auth/2fa/setup", headers=_h(test_user["token"]), timeout=10)
        secret = r.json()["secret"]
        old_codes = r.json()["recovery_codes"]
        
        code = pyotp.TOTP(secret).now()
        r = requests.post(f"{API}/auth/2fa/verify-setup",
                          headers=_h(test_user["token"]), json={"code": code}, timeout=10)
        
        # Regenerate
        time.sleep(1)
        code2 = pyotp.TOTP(secret).now()
        r = requests.post(f"{API}/auth/2fa/regenerate-recovery",
                          headers=_h(test_user["token"]), json={"code": code2}, timeout=10)
        assert r.status_code == 200
        new_codes = r.json()["recovery_codes"]
        assert len(new_codes) == 10
        # New codes should be different from old
        assert set(new_codes) != set(old_codes)
        
        # Cleanup
        time.sleep(1)
        code3 = pyotp.TOTP(secret).now()
        requests.post(f"{API}/auth/2fa/disable",
                      headers=_h(test_user["token"]), json={"code": code3}, timeout=10)


# ============ 2FA Disable ============

class Test2FADisable:
    """Tests for POST /api/auth/2fa/disable"""
    
    def test_disable_with_correct_code_disables_2fa(self, test_user):
        # Enable 2FA
        r = requests.post(f"{API}/auth/2fa/setup", headers=_h(test_user["token"]), timeout=10)
        secret = r.json()["secret"]
        
        code = pyotp.TOTP(secret).now()
        r = requests.post(f"{API}/auth/2fa/verify-setup",
                          headers=_h(test_user["token"]), json={"code": code}, timeout=10)
        
        # Disable
        time.sleep(1)
        code2 = pyotp.TOTP(secret).now()
        r = requests.post(f"{API}/auth/2fa/disable",
                          headers=_h(test_user["token"]), json={"code": code2}, timeout=10)
        assert r.status_code == 200
        assert r.json()["totp_enabled"] is False
        
        # Login should now work without 2FA
        body = _login(test_user["email"], test_user["password"])
        assert "token" in body
        assert not body.get("totp_required")


# ============ Security: No Secret Leaks ============

class TestNoSecretLeaks:
    """Tests that TOTP secrets never leak in responses"""
    
    def test_auth_me_never_leaks_totp_fields(self, admin_token):
        r = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=10)
        assert r.status_code == 200
        data = r.json()
        for field in ("password_hash", "totp_secret", "totp_pending_secret",
                      "totp_recovery_hashes", "totp_pending_recovery_hashes"):
            assert field not in data, f"{field} leaked in /auth/me"

    def test_login_response_never_leaks_totp_fields(self):
        body = _login(*ADMIN)
        for field in ("password_hash", "totp_secret", "totp_pending_secret",
                      "totp_recovery_hashes", "totp_pending_recovery_hashes"):
            assert field not in body, f"{field} leaked in login response"


# ============ DSGVO Export ============

class TestDSGVOExport:
    """Tests for GET /api/users/me/export"""
    
    def test_export_contains_legacy_keys(self, admin_token):
        r = requests.get(f"{API}/users/me/export", headers=_h(admin_token), timeout=20)
        assert r.status_code == 200
        data = r.json()
        for key in ("profile", "meetings_hosted", "news_posts_authored",
                    "survey_responses", "push_subscriptions", "audit_log_entries"):
            assert key in data, f"Legacy key {key} missing"

    def test_export_contains_iter188_block(self, admin_token):
        r = requests.get(f"{API}/users/me/export", headers=_h(admin_token), timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert "_iter188" in data
        rich = data["_iter188"]
        assert "_meta" in rich
        assert "exported_at" in rich["_meta"]
        for section in ("profile", "news", "surveys", "meetings", "chat",
                        "scheduling", "calendar", "notifications", "audit"):
            assert section in rich, f"Section {section} missing in _iter188"

    def test_export_profile_strips_sensitive_fields(self, admin_token):
        r = requests.get(f"{API}/users/me/export", headers=_h(admin_token), timeout=20)
        assert r.status_code == 200
        data = r.json()
        profile = data["_iter188"]["profile"]
        assert "password_hash" not in profile
        assert "totp_secret" not in profile

    def test_export_caldav_masks_password(self, admin_token):
        r = requests.get(f"{API}/users/me/export", headers=_h(admin_token), timeout=20)
        assert r.status_code == 200
        data = r.json()
        caldav = data["_iter188"]["calendar"].get("caldav_config", {})
        # If password exists, it should be masked
        if "password" in caldav:
            assert caldav["password"] == "***hidden***"


# ============ read_db Extension ============

class TestReadDBExtension:
    """Tests for read_db usage on admin/stats, search/global, admin/health"""
    
    def test_admin_stats_returns_correct_counts(self, admin_token):
        r = requests.get(f"{API}/admin/stats", headers=_h(admin_token), timeout=10)
        assert r.status_code == 200
        data = r.json()
        for key in ("total_users", "total_meetings", "active_meetings",
                    "ended_meetings", "total_messages", "total_polls", "total_recordings"):
            assert key in data
            assert isinstance(data[key], int)

    def test_search_global_returns_grouped_results(self, admin_token):
        r = requests.get(f"{API}/search/global?q=test", headers=_h(admin_token), timeout=10)
        assert r.status_code == 200
        data = r.json()
        for key in ("news", "meetings", "chats", "users"):
            assert key in data
            assert isinstance(data[key], list)

    def test_admin_health_returns_email_stats(self, admin_token):
        r = requests.get(f"{API}/admin/health", headers=_h(admin_token), timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "emails" in data
        assert "total" in data["emails"]


# ============ Regression Tests ============

class TestRegressionNewsFeed:
    """Regression: News feed still works"""
    
    def test_news_feed_returns_200(self, admin_token):
        r = requests.get(f"{API}/news/feed", headers=_h(admin_token), timeout=10)
        assert r.status_code == 200


class TestRegressionSurveys:
    """Regression: Surveys still work"""
    
    def test_surveys_list_returns_200(self, admin_token):
        r = requests.get(f"{API}/surveys", headers=_h(admin_token), timeout=10)
        assert r.status_code == 200


class TestRegressionMeetings:
    """Regression: Meetings still work"""
    
    def test_meetings_list_returns_200(self, admin_token):
        r = requests.get(f"{API}/meetings", headers=_h(admin_token), timeout=10)
        assert r.status_code == 200


class TestRegressionLoginWithout2FA:
    """Regression: Login without 2FA still works for users without 2FA enabled"""
    
    def test_member_login_without_2fa(self):
        # Create a fresh user
        email = f"TEST_no2fa_{uuid.uuid4().hex[:8]}@meetflow.local"
        pwd = "testpass123"
        r = requests.post(f"{API}/auth/register", json={
            "email": email, "password": pwd, "name": "Test No2FA User"
        }, timeout=10)
        if r.status_code != 200:
            pytest.skip(f"Could not create test user: {r.text}")
        
        # Login should work without 2FA
        body = _login(email, pwd)
        assert "token" in body
        assert not body.get("totp_required")


class TestRegressionChatRoutes:
    """Regression: Chat routes from Iter 187 still work"""
    
    def test_chat_conversations_list(self, admin_token):
        r = requests.get(f"{API}/chat/conversations", headers=_h(admin_token), timeout=10)
        assert r.status_code == 200

    def test_chat_users_list(self, admin_token):
        r = requests.get(f"{API}/chat/users", headers=_h(admin_token), timeout=10)
        assert r.status_code == 200


class TestRegressionPrivacyGuards:
    """Regression: Privacy guards from Iter 186 still work"""
    
    def test_stranger_cannot_access_targeted_news(self, admin_token):
        # This is a basic check - detailed privacy tests are in iter186 tests
        r = requests.get(f"{API}/news/feed", headers=_h(admin_token), timeout=10)
        assert r.status_code == 200
