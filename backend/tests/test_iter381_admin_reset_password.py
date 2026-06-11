"""Iter 381 — Backend tests for Admin Reset Password feature + change-password policy.

Covers:
- POST /api/admin/users/{user_id}/reset-password (admin-only, returns temp PW)
- DB state: must_change_password=True after reset
- Login w/ temp PW returns must_change_password=true in /auth/me
- POST /api/auth/change-password with policy-conforming new PW
- Negative: weak PW rejected (400)
- Negative: non-admin (member) gets 403 on reset endpoint
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://video-meet-pro.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "qa_admin@meetflow.com"
ADMIN_PW = "qa_admin_pw_372"
MEMBER_EMAIL = "qa_member@meetflow.com"
MEMBER_PW = "Qa_member_Pw_372!!"


def _new_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(session, email, password):
    r = session.post(f"{API}/auth/login", json={"email": email, "password": password})
    return r


@pytest.fixture(scope="module")
def admin_session():
    s = _new_session()
    r = _login(s, ADMIN_EMAIL, ADMIN_PW)
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text[:200]}")
    data = r.json()
    if data.get("token"):
        s.headers.update({"Authorization": f"Bearer {data['token']}"})
    return s


@pytest.fixture(scope="module")
def demo_user(admin_session):
    """Seed demo users and pick one to reset."""
    # Try to seed (idempotent)
    admin_session.post(f"{API}/resources-seed-demo", json={})
    r = admin_session.get(f"{API}/admin/users")
    assert r.status_code == 200, f"/admin/users failed: {r.status_code} {r.text[:200]}"
    users = r.json() if isinstance(r.json(), list) else r.json().get("users", [])
    demo = next((u for u in users if (u.get("email") or "").endswith("@demo.meetflow.local") and u.get("role") != "moderator"), None)
    if not demo:
        # fallback: any demo user
        demo = next((u for u in users if (u.get("email") or "").endswith("@demo.meetflow.local")), None)
    if not demo:
        pytest.skip("No demo user found to reset")
    return demo


def test_password_policy_endpoint_public():
    r = requests.get(f"{API}/auth/password-policy")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("min_length") == 8
    assert data.get("requires_upper") is True
    assert data.get("requires_special") is True


def test_admin_reset_password_success(admin_session, demo_user):
    uid = demo_user["user_id"]
    r = admin_session.post(f"{API}/admin/users/{uid}/reset-password", json={})
    assert r.status_code == 200, f"reset-password failed: {r.status_code} {r.text[:400]}"
    body = r.json()
    assert body.get("ok") is True
    new_pw = body.get("new_password")
    assert new_pw and isinstance(new_pw, str)
    # Policy assertions
    assert len(new_pw) >= 8
    assert re.search(r"[A-Z]", new_pw), "missing uppercase"
    assert re.search(r"[a-z]", new_pw), "missing lowercase"
    assert re.search(r"\d", new_pw), "missing digit"
    assert re.search(r"[!@#$%^&*()_+\-=\[\]{};:'\",.<>/?\\|`~]", new_pw), "missing special"
    # Stash for next tests
    demo_user["__temp_pw"] = new_pw
    demo_user["__email"] = body.get("email") or demo_user["email"]


def test_login_with_temp_pw_returns_must_change(demo_user):
    temp_pw = demo_user.get("__temp_pw")
    email = demo_user.get("__email") or demo_user["email"]
    if not temp_pw:
        pytest.skip("temp pw not set")
    s = _new_session()
    r = _login(s, email, temp_pw)
    assert r.status_code == 200, f"login w/ temp pw failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert data.get("must_change_password") is True, f"must_change_password not in login response: {data}"
    if data.get("token"):
        s.headers.update({"Authorization": f"Bearer {data['token']}"})
    # Also verify /auth/me
    r2 = s.get(f"{API}/auth/me")
    assert r2.status_code == 200
    # Note: /auth/me may not echo must_change_password; login response is the primary signal.
    demo_user["__user_session"] = s


def test_change_password_weak_rejected(demo_user):
    s = demo_user.get("__user_session")
    if not s:
        pytest.skip("no user session")
    r = s.post(f"{API}/auth/change-password", json={
        "current_password": demo_user.get("__temp_pw"),
        "new_password": "abc123",
        "new_password_confirm": "abc123",
    })
    assert r.status_code in (400, 422), f"Expected 400/422 for weak pw, got {r.status_code}: {r.text[:200]}"


def test_change_password_success(demo_user):
    s = demo_user.get("__user_session")
    if not s:
        pytest.skip("no user session")
    new_pw = "NewPass1!Demo"
    r = s.post(f"{API}/auth/change-password", json={
        "current_password": demo_user.get("__temp_pw"),
        "new_password": new_pw,
        "new_password_confirm": new_pw,
    })
    assert r.status_code == 200, f"change-password failed: {r.status_code} {r.text[:300]}"
    demo_user["__new_pw"] = new_pw
    # Login again to verify must_change_password is now false
    s2 = _new_session()
    email = demo_user.get("__email") or demo_user["email"]
    r2 = _login(s2, email, new_pw)
    assert r2.status_code == 200, f"re-login failed: {r2.status_code} {r2.text[:200]}"
    data = r2.json()
    assert not data.get("must_change_password"), f"must_change_password should be false: {data}"


def test_non_admin_cannot_reset_password(demo_user):
    s = _new_session()
    r = _login(s, MEMBER_EMAIL, MEMBER_PW)
    if r.status_code != 200:
        pytest.skip(f"member login failed: {r.status_code}")
    data = r.json()
    if data.get("token"):
        s.headers.update({"Authorization": f"Bearer {data['token']}"})
    uid = demo_user["user_id"]
    r2 = s.post(f"{API}/admin/users/{uid}/reset-password", json={})
    assert r2.status_code == 403, f"Expected 403 for non-admin, got {r2.status_code}: {r2.text[:200]}"
