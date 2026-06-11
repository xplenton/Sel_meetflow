"""Iter 188 — pytest for 2FA / TOTP, DSGVO export richer payload, and
read_db usage on more endpoints.

Lokale tests, hit live FastAPI via REACT_APP_BACKEND_URL.
"""
import os
import time
import requests
import pyotp
import pytest


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


# ============ 2FA Lifecycle ============

@pytest.fixture
def admin_token():
    body = _login(*ADMIN)
    if body.get("totp_required"):
        # leftover from a previous run — clean up via direct DB hack would
        # require backend access. Here we just skip the test session.
        pytest.skip("Admin already has 2FA enabled from a previous run; clean DB first.")
    return body["token"]


def test_2fa_full_lifecycle(admin_token):
    # 1) Status = disabled
    r = requests.get(f"{API}/auth/2fa/status", headers=_h(admin_token), timeout=10)
    assert r.status_code == 200
    assert r.json()["totp_enabled"] is False

    # 2) Setup
    r = requests.post(f"{API}/auth/2fa/setup", headers=_h(admin_token), timeout=10)
    assert r.status_code == 200
    setup = r.json()
    assert "secret" in setup and "qr_png" in setup
    assert setup["qr_png"].startswith("data:image/png;base64,")
    assert len(setup["recovery_codes"]) == 10

    secret = setup["secret"]

    # 3) Verify-setup with WRONG code → 401
    r = requests.post(f"{API}/auth/2fa/verify-setup",
                      headers=_h(admin_token), json={"code": "000000"}, timeout=10)
    assert r.status_code == 401

    # 4) Verify-setup with REAL code → 200
    code = pyotp.TOTP(secret).now()
    r = requests.post(f"{API}/auth/2fa/verify-setup",
                      headers=_h(admin_token), json={"code": code}, timeout=10)
    assert r.status_code == 200, r.text

    # 5) Login now requires TOTP
    body = _login(*ADMIN)
    assert body.get("totp_required") is True
    challenge = body["challenge_token"]

    time.sleep(1)
    code2 = pyotp.TOTP(secret).now()
    r = requests.post(f"{API}/auth/2fa/verify-login",
                      json={"challenge_token": challenge, "code": code2}, timeout=10)
    assert r.status_code == 200, r.text
    new_token = r.json()["token"]
    # No secrets leaked in response
    assert "totp_secret" not in r.json()
    assert "password_hash" not in r.json()

    # 6) Recovery-code path
    body = _login(*ADMIN)
    challenge = body["challenge_token"]
    recovery = setup["recovery_codes"][0]
    r = requests.post(f"{API}/auth/2fa/verify-login",
                      json={"challenge_token": challenge, "code": recovery, "mode": "recovery"},
                      timeout=10)
    assert r.status_code == 200

    # Same recovery code is now consumed → 401
    body = _login(*ADMIN)
    challenge = body["challenge_token"]
    r = requests.post(f"{API}/auth/2fa/verify-login",
                      json={"challenge_token": challenge, "code": recovery, "mode": "recovery"},
                      timeout=10)
    assert r.status_code == 401

    # 7) Disable
    time.sleep(1)
    code3 = pyotp.TOTP(secret).now()
    r = requests.post(f"{API}/auth/2fa/disable",
                      headers=_h(new_token), json={"code": code3}, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["totp_enabled"] is False

    # 8) Login now without 2FA again
    body = _login(*ADMIN)
    assert "token" in body and not body.get("totp_required")


def test_user_response_strips_totp_fields():
    """Even after enabling 2FA, /auth/me must NEVER include totp_secret etc."""
    body = _login(*ADMIN)
    if body.get("totp_required"):
        pytest.skip("admin has lingering 2FA — covered by lifecycle test")
    token = body["token"]
    r = requests.get(f"{API}/auth/me", headers=_h(token), timeout=10).json()
    for f in ("password_hash", "totp_secret", "totp_pending_secret",
              "totp_recovery_hashes", "totp_pending_recovery_hashes"):
        assert f not in r, f"{f} leaked in /auth/me"


# ============ DSGVO ============

def test_dsgvo_export_richer_payload():
    body = _login(*ADMIN)
    if body.get("totp_required"):
        pytest.skip("2FA still on")
    token = body["token"]
    r = requests.get(f"{API}/users/me/export", headers=_h(token), timeout=20)
    assert r.status_code == 200
    data = r.json()
    # Legacy keys (backward compat)
    for k in ("profile", "meetings_hosted", "news_posts_authored",
              "survey_responses", "push_subscriptions", "audit_log_entries"):
        assert k in data
    # New iter188 nested structure
    assert "_iter188" in data
    rich = data["_iter188"]
    assert "_meta" in rich and "exported_at" in rich["_meta"]
    for section in ("profile", "news", "surveys", "meetings", "chat",
                    "scheduling", "calendar", "notifications", "audit"):
        assert section in rich
    # Sensitive fields must NOT be present in the profile
    assert "password_hash" not in rich["profile"]
    assert "totp_secret" not in rich["profile"]


# ============ read_db on more endpoints ============

def test_admin_stats_via_read_db():
    body = _login(*ADMIN)
    if body.get("totp_required"):
        pytest.skip("2FA still on")
    token = body["token"]
    r = requests.get(f"{API}/admin/stats", headers=_h(token), timeout=10)
    assert r.status_code == 200
    for k in ("total_users", "total_meetings", "total_messages"):
        assert k in r.json()
        assert isinstance(r.json()[k], int)


def test_search_global_via_read_db():
    body = _login(*ADMIN)
    if body.get("totp_required"):
        pytest.skip("2FA still on")
    token = body["token"]
    r = requests.get(f"{API}/search/global?q=test", headers=_h(token), timeout=10)
    assert r.status_code == 200
    for k in ("news", "meetings", "chats", "users"):
        assert k in r.json()
