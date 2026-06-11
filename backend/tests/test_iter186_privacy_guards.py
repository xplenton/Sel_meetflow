"""Pytest for iter 186 — Privacy Audit Sweep on News/Surveys/Meetings.

Verifies that:
  * Detail/list endpoints return 404 for unauthorised users (no IDOR/BOLA leak).
  * Authorised users (admin / moderator / author / participant / targeted)
    get 200 as before.

Runs against the live backend (REACT_APP_BACKEND_URL) so it covers the
real FastAPI dependency-injection chain.
"""
import os
import uuid
import requests
import pytest


def _api_url() -> str:
    # Prefer the env var the rest of the project uses.
    val = os.environ.get("REACT_APP_BACKEND_URL")
    if val:
        return val.rstrip("/") + "/api"
    # Fallback: parse it from frontend/.env to keep the test self-contained.
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/") + "/api"
    except Exception:
        pass
    return "http://localhost:8001/api"


API = _api_url()
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PWD = "admin123"


# ---------- Helpers ----------------------------------------------------------

def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=10)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    body = r.json()
    return body.get("access_token") or body.get("token")


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _create_user(admin_token: str, email: str, name: str, role: str = "member") -> dict:
    payload = {
        "email": email, "name": name, "role": role,
        "password": "Test1234!",
    }
    r = requests.post(
        f"{API}/admin/users", headers=_headers(admin_token), json=payload, timeout=10,
    )
    if r.status_code in (200, 201):
        return r.json()
    # Fallback to register endpoint
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "name": name, "password": "Test1234!"},
        timeout=10,
    )
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    return r.json().get("user", {"email": email})


# ---------- Fixtures ---------------------------------------------------------

@pytest.fixture(scope="module")
def admin_token() -> str:
    return _login(ADMIN_EMAIL, ADMIN_PWD)


@pytest.fixture(scope="module")
def two_users(admin_token):
    """Create (or reuse) two ordinary users for cross-access checks."""
    suffix = uuid.uuid4().hex[:6]
    a_email = f"privacy_a_{suffix}@example.com"
    b_email = f"privacy_b_{suffix}@example.com"
    _create_user(admin_token, a_email, f"Priv A {suffix}")
    _create_user(admin_token, b_email, f"Priv B {suffix}")
    a_token = _login(a_email, "Test1234!")
    b_token = _login(b_email, "Test1234!")
    return {"a": {"token": a_token, "email": a_email},
            "b": {"token": b_token, "email": b_email}}


# ---------- News -------------------------------------------------------------

def test_news_post_not_in_audience_returns_404(admin_token, two_users):
    """A draft / non-targeted news post must return 404 to a stranger,
    NOT leak its existence via 403."""
    user_a = two_users["a"]
    user_b = two_users["b"]
    # 1) Look up A's user_id (so we can target the post specifically at A)
    me_a = requests.get(f"{API}/auth/me", headers=_headers(user_a["token"]), timeout=10).json()
    a_uid = me_a.get("user_id") or me_a.get("id")
    assert a_uid

    # 2) Admin creates a news post targeted ONLY at user A
    payload = {
        "title": f"Privacy Test {uuid.uuid4().hex[:6]}",
        "content": "Top secret content",
        "status": "published",
        "target_all": False,
        "target_user_ids": [a_uid],
    }
    r = requests.post(f"{API}/news/posts", headers=_headers(admin_token), json=payload, timeout=10)
    assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text}"
    post = r.json()
    pid = post["post_id"]

    # 3) User A sees it
    r_a = requests.get(f"{API}/news/posts/{pid}", headers=_headers(user_a["token"]), timeout=10)
    assert r_a.status_code == 200, f"author/targeted access broken: {r_a.status_code} {r_a.text}"

    # 4) User B (NOT in audience) gets 404 — no existence leak
    r_b = requests.get(f"{API}/news/posts/{pid}", headers=_headers(user_b["token"]), timeout=10)
    assert r_b.status_code == 404, f"BOLA leak: B got {r_b.status_code}"

    # 5) Cleanup
    requests.delete(f"{API}/news/posts/{pid}", headers=_headers(admin_token), timeout=10)


def test_news_post_draft_hidden_from_non_authors(admin_token, two_users):
    user_b = two_users["b"]
    # Admin creates DRAFT
    r = requests.post(
        f"{API}/news/posts",
        headers=_headers(admin_token),
        json={"title": f"Draft {uuid.uuid4().hex[:5]}", "content": "X", "status": "draft", "target_all": True},
        timeout=10,
    )
    assert r.status_code in (200, 201)
    pid = r.json()["post_id"]
    r_b = requests.get(f"{API}/news/posts/{pid}", headers=_headers(user_b["token"]), timeout=10)
    assert r_b.status_code == 404, f"Draft leaked to non-author: {r_b.status_code}"
    requests.delete(f"{API}/news/posts/{pid}", headers=_headers(admin_token), timeout=10)


def test_news_files_require_auth():
    """File-serving endpoint must require authentication."""
    r = requests.get(f"{API}/news/files/some_random_file.bin", timeout=10)
    # Not 200 (file would be served), expected 401/403
    assert r.status_code in (401, 403, 404)


def test_news_upload_requires_create_capability(two_users):
    """Plain member without news.create cap must not upload images."""
    member_token = two_users["b"]["token"]
    files = {"file": ("test.txt", b"hello", "text/plain")}
    r = requests.post(
        f"{API}/news/upload",
        headers={"Authorization": f"Bearer {member_token}"},
        files=files,
        timeout=10,
    )
    assert r.status_code in (401, 403), f"Upload not protected: {r.status_code}"


# ---------- Surveys ----------------------------------------------------------

def test_survey_not_in_audience_returns_404(admin_token, two_users):
    user_a = two_users["a"]
    user_b = two_users["b"]
    me_a = requests.get(f"{API}/auth/me", headers=_headers(user_a["token"]), timeout=10).json()
    a_uid = me_a.get("user_id") or me_a.get("id")

    # Survey targeted at user A only
    payload = {
        "title": f"Privacy Survey {uuid.uuid4().hex[:6]}",
        "questions": [{"text": "OK?", "type": "single_choice", "options": ["Yes", "No"]}],
        "status": "published",
        "target_all": False,
        "target_user_ids": [a_uid],
    }
    r = requests.post(f"{API}/surveys", headers=_headers(admin_token), json=payload, timeout=10)
    assert r.status_code in (200, 201)
    sid = r.json()["survey_id"]

    # User A sees it
    r_a = requests.get(f"{API}/surveys/{sid}", headers=_headers(user_a["token"]), timeout=10)
    assert r_a.status_code == 200

    # User B → 404
    r_b = requests.get(f"{API}/surveys/{sid}", headers=_headers(user_b["token"]), timeout=10)
    assert r_b.status_code == 404, f"Survey leak: {r_b.status_code}"

    # User B can't submit responses either
    r_b2 = requests.post(
        f"{API}/surveys/{sid}/respond",
        headers=_headers(user_b["token"]),
        json={"answers": {"q1": "Yes"}},
        timeout=10,
    )
    assert r_b2.status_code == 404

    # User B can't see results
    r_b3 = requests.get(f"{API}/surveys/{sid}/results", headers=_headers(user_b["token"]), timeout=10)
    assert r_b3.status_code == 404

    # Cleanup
    requests.delete(f"{API}/surveys/{sid}", headers=_headers(admin_token), timeout=10)


def test_survey_results_locked_until_participation(admin_token, two_users):
    """Even targeted users must NOT see results before they have responded
    (unless they're admin/moderator/owner)."""
    user_a = two_users["a"]
    me_a = requests.get(f"{API}/auth/me", headers=_headers(user_a["token"]), timeout=10).json()
    a_uid = me_a["user_id"]

    payload = {
        "title": f"Results Lock {uuid.uuid4().hex[:6]}",
        "questions": [{"question_id": "q1", "text": "OK?", "type": "single_choice", "options": ["Yes", "No"]}],
        "status": "published",
        "target_all": False,
        "target_user_ids": [a_uid],
    }
    sid = requests.post(f"{API}/surveys", headers=_headers(admin_token), json=payload, timeout=10).json()["survey_id"]

    # A is targeted but hasn't responded yet → 403
    r = requests.get(f"{API}/surveys/{sid}/results", headers=_headers(user_a["token"]), timeout=10)
    assert r.status_code == 403, f"Results leaked before participation: {r.status_code}"

    # Admin sees them anyway
    r_admin = requests.get(f"{API}/surveys/{sid}/results", headers=_headers(admin_token), timeout=10)
    assert r_admin.status_code == 200

    requests.delete(f"{API}/surveys/{sid}", headers=_headers(admin_token), timeout=10)


# ---------- Meetings ---------------------------------------------------------

def test_meeting_not_invited_returns_404(admin_token, two_users):
    """A user who is neither host nor participant of a meeting must get 404."""
    user_a = two_users["a"]
    user_b = two_users["b"]

    # Admin creates a meeting (admin is host).
    payload = {
        "title": f"Privacy Meeting {uuid.uuid4().hex[:6]}",
        "description": "Confidential",
        "duration": 30,
        "meeting_type": "instant",
    }
    r = requests.post(f"{API}/meetings", headers=_headers(admin_token), json=payload, timeout=10)
    assert r.status_code in (200, 201), r.text
    mid = r.json()["meeting_id"]

    # Stranger A → 404
    r_a = requests.get(f"{API}/meetings/{mid}", headers=_headers(user_a["token"]), timeout=10)
    assert r_a.status_code == 404, f"Meeting leak (detail): {r_a.status_code}"

    # Sub-resource probes — all must 404 for stranger
    for path in [
        f"/meetings/{mid}/participants",
        f"/meetings/{mid}/chat",
        f"/meetings/{mid}/polls",
        f"/meetings/{mid}/questions",
        f"/meetings/{mid}/breakout-rooms",
        f"/meetings/{mid}/summary",
        f"/meetings/{mid}/attendance-report",
    ]:
        r = requests.get(f"{API}{path}", headers=_headers(user_b["token"]), timeout=10)
        assert r.status_code == 404, f"{path} leaked to non-member: {r.status_code}"

    # Admin still has access
    r_admin = requests.get(f"{API}/meetings/{mid}", headers=_headers(admin_token), timeout=10)
    assert r_admin.status_code == 200

    # Cleanup
    requests.delete(f"{API}/meetings/{mid}", headers=_headers(admin_token), timeout=10)


def test_meeting_chat_blocked_for_strangers(admin_token, two_users):
    user_a = two_users["a"]
    payload = {
        "title": f"Chat Privacy {uuid.uuid4().hex[:6]}",
        "duration": 30, "meeting_type": "instant",
    }
    mid = requests.post(f"{API}/meetings", headers=_headers(admin_token), json=payload, timeout=10).json()["meeting_id"]

    # Stranger A tries to send a chat message → 404
    r = requests.post(
        f"{API}/meetings/{mid}/chat",
        headers=_headers(user_a["token"]),
        json={"message": "hi", "message_type": "text"},
        timeout=10,
    )
    assert r.status_code == 404, f"Chat write leak: {r.status_code}"

    # Stranger A tries to create poll → 404
    r2 = requests.post(
        f"{API}/meetings/{mid}/polls",
        headers=_headers(user_a["token"]),
        json={"question": "X?", "options": ["a", "b"]},
        timeout=10,
    )
    assert r2.status_code == 404

    requests.delete(f"{API}/meetings/{mid}", headers=_headers(admin_token), timeout=10)
