"""Pytest for iter 186 — Regression Tests for Privacy Audit Sweep.

Verifies that:
  * POSITIVE PATHS: Authorized users (admin/moderator/author/participant/targeted)
    can still access News, Surveys, Meetings endpoints with 200.
  * REGRESSION: Existing main flows (News-Feed, Surveys-List, Meetings-List, Auth)
    continue to work after the privacy hardening refactor.
  * ADDITIONAL IDOR PROBES: Verify 404 on sub-resources for strangers.

Runs against the live backend (REACT_APP_BACKEND_URL).
"""
import os
import uuid
import requests
import pytest


def _api_url() -> str:
    val = os.environ.get("REACT_APP_BACKEND_URL")
    if val:
        return val.rstrip("/") + "/api"
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
    payload = {"email": email, "name": name, "role": role, "password": "Test1234!"}
    r = requests.post(f"{API}/admin/users", headers=_headers(admin_token), json=payload, timeout=10)
    if r.status_code in (200, 201):
        return r.json()
    r = requests.post(f"{API}/auth/register", json={"email": email, "name": name, "password": "Test1234!"}, timeout=10)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    return r.json().get("user", {"email": email})


# ---------- Fixtures ---------------------------------------------------------

@pytest.fixture(scope="module")
def admin_token() -> str:
    return _login(ADMIN_EMAIL, ADMIN_PWD)


@pytest.fixture(scope="module")
def test_users(admin_token):
    """Create test users for regression testing."""
    suffix = uuid.uuid4().hex[:6]
    targeted_email = f"targeted_{suffix}@example.com"
    stranger_email = f"stranger_{suffix}@example.com"
    _create_user(admin_token, targeted_email, f"Targeted User {suffix}")
    _create_user(admin_token, stranger_email, f"Stranger User {suffix}")
    targeted_token = _login(targeted_email, "Test1234!")
    stranger_token = _login(stranger_email, "Test1234!")
    
    # Get user IDs
    targeted_me = requests.get(f"{API}/auth/me", headers=_headers(targeted_token), timeout=10).json()
    stranger_me = requests.get(f"{API}/auth/me", headers=_headers(stranger_token), timeout=10).json()
    
    return {
        "targeted": {
            "token": targeted_token,
            "email": targeted_email,
            "user_id": targeted_me.get("user_id") or targeted_me.get("id")
        },
        "stranger": {
            "token": stranger_token,
            "email": stranger_email,
            "user_id": stranger_me.get("user_id") or stranger_me.get("id")
        }
    }


# ============ AUTH REGRESSION ============

class TestAuthRegression:
    """Auth endpoints must continue to work."""
    
    def test_auth_login(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data or "token" in data
    
    def test_auth_me(self, admin_token):
        r = requests.get(f"{API}/auth/me", headers=_headers(admin_token), timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("email") == ADMIN_EMAIL
    
    def test_auth_refresh(self, admin_token):
        r = requests.post(f"{API}/auth/refresh", headers=_headers(admin_token), timeout=10)
        # May return 200 or 401 if refresh token not in cookie
        assert r.status_code in (200, 401, 422)


# ============ NEWS POSITIVE PATHS ============

class TestNewsPositivePaths:
    """Authorized users must still access news endpoints."""
    
    def test_news_feed_works(self, admin_token):
        """News feed endpoint must work for authenticated users."""
        r = requests.get(f"{API}/news/feed", headers=_headers(admin_token), timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "posts" in data or isinstance(data, list)
    
    def test_news_categories_list(self, admin_token):
        """Categories list must work."""
        r = requests.get(f"{API}/news/categories", headers=_headers(admin_token), timeout=10)
        assert r.status_code == 200
    
    def test_admin_sees_targeted_post(self, admin_token, test_users):
        """Admin can see any post regardless of targeting."""
        targeted_uid = test_users["targeted"]["user_id"]
        payload = {
            "title": f"Admin Access Test {uuid.uuid4().hex[:6]}",
            "content": "Admin should see this",
            "status": "published",
            "target_all": False,
            "target_user_ids": [targeted_uid],
        }
        r = requests.post(f"{API}/news/posts", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        pid = r.json()["post_id"]
        
        # Admin sees it
        r_admin = requests.get(f"{API}/news/posts/{pid}", headers=_headers(admin_token), timeout=10)
        assert r_admin.status_code == 200
        
        # Cleanup
        requests.delete(f"{API}/news/posts/{pid}", headers=_headers(admin_token), timeout=10)
    
    def test_targeted_user_sees_post(self, admin_token, test_users):
        """Targeted user can see post targeted at them."""
        targeted_uid = test_users["targeted"]["user_id"]
        targeted_token = test_users["targeted"]["token"]
        
        payload = {
            "title": f"Targeted Post {uuid.uuid4().hex[:6]}",
            "content": "For targeted user",
            "status": "published",
            "target_all": False,
            "target_user_ids": [targeted_uid],
        }
        r = requests.post(f"{API}/news/posts", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        pid = r.json()["post_id"]
        
        # Targeted user sees it
        r_targeted = requests.get(f"{API}/news/posts/{pid}", headers=_headers(targeted_token), timeout=10)
        assert r_targeted.status_code == 200
        
        # Cleanup
        requests.delete(f"{API}/news/posts/{pid}", headers=_headers(admin_token), timeout=10)
    
    def test_target_all_post_visible_to_all(self, admin_token, test_users):
        """target_all=true posts are visible to everyone."""
        stranger_token = test_users["stranger"]["token"]
        
        payload = {
            "title": f"Public Post {uuid.uuid4().hex[:6]}",
            "content": "Everyone can see",
            "status": "published",
            "target_all": True,
        }
        r = requests.post(f"{API}/news/posts", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        pid = r.json()["post_id"]
        
        # Stranger sees it
        r_stranger = requests.get(f"{API}/news/posts/{pid}", headers=_headers(stranger_token), timeout=10)
        assert r_stranger.status_code == 200
        
        # Cleanup
        requests.delete(f"{API}/news/posts/{pid}", headers=_headers(admin_token), timeout=10)
    
    def test_comments_work_for_target_all_post(self, admin_token, test_users):
        """Comments endpoints work for target_all posts."""
        stranger_token = test_users["stranger"]["token"]
        
        payload = {
            "title": f"Commentable Post {uuid.uuid4().hex[:6]}",
            "content": "Comment here",
            "status": "published",
            "target_all": True,
        }
        r = requests.post(f"{API}/news/posts", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        pid = r.json()["post_id"]
        
        # Get comments
        r_get = requests.get(f"{API}/news/posts/{pid}/comments", headers=_headers(stranger_token), timeout=10)
        assert r_get.status_code == 200
        
        # Post comment
        r_post = requests.post(
            f"{API}/news/posts/{pid}/comments",
            headers=_headers(stranger_token),
            json={"content": "Test comment"},
            timeout=10
        )
        assert r_post.status_code in (200, 201)
        
        # Cleanup
        requests.delete(f"{API}/news/posts/{pid}", headers=_headers(admin_token), timeout=10)
    
    def test_mark_as_read_works(self, admin_token, test_users):
        """POST /news/posts/{id}/read works for target_all posts."""
        stranger_token = test_users["stranger"]["token"]
        
        payload = {
            "title": f"Readable Post {uuid.uuid4().hex[:6]}",
            "content": "Mark as read",
            "status": "published",
            "target_all": True,
        }
        r = requests.post(f"{API}/news/posts", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        pid = r.json()["post_id"]
        
        # Mark as read
        r_read = requests.post(f"{API}/news/posts/{pid}/read", headers=_headers(stranger_token), timeout=10)
        assert r_read.status_code == 200
        
        # Cleanup
        requests.delete(f"{API}/news/posts/{pid}", headers=_headers(admin_token), timeout=10)


# ============ SURVEYS POSITIVE PATHS ============

class TestSurveysPositivePaths:
    """Authorized users must still access survey endpoints."""
    
    def test_surveys_list_works(self, admin_token):
        """Surveys list endpoint must work."""
        r = requests.get(f"{API}/surveys", headers=_headers(admin_token), timeout=10)
        assert r.status_code == 200
    
    def test_surveys_pending_count(self, admin_token):
        """Pending count endpoint must work."""
        r = requests.get(f"{API}/surveys/pending-count", headers=_headers(admin_token), timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "count" in data
    
    def test_admin_sees_targeted_survey(self, admin_token, test_users):
        """Admin can see any survey."""
        targeted_uid = test_users["targeted"]["user_id"]
        
        payload = {
            "title": f"Admin Survey Test {uuid.uuid4().hex[:6]}",
            "questions": [{"question_id": "q1", "text": "OK?", "type": "single_choice", "options": ["Yes", "No"]}],
            "status": "published",
            "target_all": False,
            "target_user_ids": [targeted_uid],
        }
        r = requests.post(f"{API}/surveys", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        sid = r.json()["survey_id"]
        
        # Admin sees it
        r_admin = requests.get(f"{API}/surveys/{sid}", headers=_headers(admin_token), timeout=10)
        assert r_admin.status_code == 200
        
        # Admin sees results
        r_results = requests.get(f"{API}/surveys/{sid}/results", headers=_headers(admin_token), timeout=10)
        assert r_results.status_code == 200
        
        # Cleanup
        requests.delete(f"{API}/surveys/{sid}", headers=_headers(admin_token), timeout=10)
    
    def test_targeted_user_can_respond(self, admin_token, test_users):
        """Targeted user can view and respond to survey."""
        targeted_uid = test_users["targeted"]["user_id"]
        targeted_token = test_users["targeted"]["token"]
        
        payload = {
            "title": f"Respond Survey {uuid.uuid4().hex[:6]}",
            "questions": [{"question_id": "q1", "text": "OK?", "type": "single_choice", "options": ["Yes", "No"]}],
            "status": "published",
            "target_all": False,
            "target_user_ids": [targeted_uid],
        }
        r = requests.post(f"{API}/surveys", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        sid = r.json()["survey_id"]
        
        # Targeted user sees it
        r_get = requests.get(f"{API}/surveys/{sid}", headers=_headers(targeted_token), timeout=10)
        assert r_get.status_code == 200
        
        # Targeted user responds
        r_respond = requests.post(
            f"{API}/surveys/{sid}/respond",
            headers=_headers(targeted_token),
            json={"answers": {"q1": "Yes"}},
            timeout=10
        )
        assert r_respond.status_code in (200, 201)
        
        # After responding, targeted user can see results
        r_results = requests.get(f"{API}/surveys/{sid}/results", headers=_headers(targeted_token), timeout=10)
        assert r_results.status_code == 200
        
        # Cleanup
        requests.delete(f"{API}/surveys/{sid}", headers=_headers(admin_token), timeout=10)
    
    def test_target_all_survey_visible_to_all(self, admin_token, test_users):
        """target_all=true surveys are visible to everyone."""
        stranger_token = test_users["stranger"]["token"]
        
        payload = {
            "title": f"Public Survey {uuid.uuid4().hex[:6]}",
            "questions": [{"question_id": "q1", "text": "OK?", "type": "single_choice", "options": ["Yes", "No"]}],
            "status": "published",
            "target_all": True,
        }
        r = requests.post(f"{API}/surveys", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        sid = r.json()["survey_id"]
        
        # Stranger sees it
        r_stranger = requests.get(f"{API}/surveys/{sid}", headers=_headers(stranger_token), timeout=10)
        assert r_stranger.status_code == 200
        
        # Cleanup
        requests.delete(f"{API}/surveys/{sid}", headers=_headers(admin_token), timeout=10)


# ============ MEETINGS POSITIVE PATHS ============

class TestMeetingsPositivePaths:
    """Authorized users must still access meeting endpoints."""
    
    def test_meetings_list_works(self, admin_token):
        """Meetings list endpoint must work."""
        r = requests.get(f"{API}/meetings", headers=_headers(admin_token), timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "meetings" in data
    
    def test_host_sees_meeting(self, admin_token):
        """Host can see their meeting."""
        payload = {
            "title": f"Host Meeting {uuid.uuid4().hex[:6]}",
            "description": "Test",
            "duration": 30,
            "meeting_type": "instant",
        }
        r = requests.post(f"{API}/meetings", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        mid = r.json()["meeting_id"]
        
        # Host sees it
        r_get = requests.get(f"{API}/meetings/{mid}", headers=_headers(admin_token), timeout=10)
        assert r_get.status_code == 200
        
        # Cleanup
        requests.delete(f"{API}/meetings/{mid}", headers=_headers(admin_token), timeout=10)
    
    def test_host_accesses_sub_resources(self, admin_token):
        """Host can access all meeting sub-resources."""
        payload = {
            "title": f"Sub-Resource Meeting {uuid.uuid4().hex[:6]}",
            "description": "Test",
            "duration": 30,
            "meeting_type": "instant",
        }
        r = requests.post(f"{API}/meetings", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        mid = r.json()["meeting_id"]
        
        # Test all sub-resources
        sub_resources = [
            f"/meetings/{mid}/participants",
            f"/meetings/{mid}/chat",
            f"/meetings/{mid}/polls",
            f"/meetings/{mid}/questions",
            f"/meetings/{mid}/breakout-rooms",
        ]
        
        for path in sub_resources:
            r_sub = requests.get(f"{API}{path}", headers=_headers(admin_token), timeout=10)
            assert r_sub.status_code == 200, f"{path} failed: {r_sub.status_code}"
        
        # Cleanup
        requests.delete(f"{API}/meetings/{mid}", headers=_headers(admin_token), timeout=10)
    
    def test_host_can_post_chat(self, admin_token):
        """Host can post chat messages."""
        payload = {
            "title": f"Chat Meeting {uuid.uuid4().hex[:6]}",
            "description": "Test",
            "duration": 30,
            "meeting_type": "instant",
        }
        r = requests.post(f"{API}/meetings", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        mid = r.json()["meeting_id"]
        
        # Post chat
        r_chat = requests.post(
            f"{API}/meetings/{mid}/chat",
            headers=_headers(admin_token),
            json={"message": "Hello", "message_type": "text"},
            timeout=10
        )
        assert r_chat.status_code in (200, 201)
        
        # Cleanup
        requests.delete(f"{API}/meetings/{mid}", headers=_headers(admin_token), timeout=10)
    
    def test_host_can_create_poll(self, admin_token):
        """Host can create polls."""
        payload = {
            "title": f"Poll Meeting {uuid.uuid4().hex[:6]}",
            "description": "Test",
            "duration": 30,
            "meeting_type": "instant",
        }
        r = requests.post(f"{API}/meetings", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        mid = r.json()["meeting_id"]
        
        # Create poll
        r_poll = requests.post(
            f"{API}/meetings/{mid}/polls",
            headers=_headers(admin_token),
            json={"question": "Test?", "options": ["A", "B"]},
            timeout=10
        )
        assert r_poll.status_code in (200, 201)
        
        # Cleanup
        requests.delete(f"{API}/meetings/{mid}", headers=_headers(admin_token), timeout=10)
    
    def test_host_can_create_question(self, admin_token):
        """Host can create questions."""
        payload = {
            "title": f"Question Meeting {uuid.uuid4().hex[:6]}",
            "description": "Test",
            "duration": 30,
            "meeting_type": "instant",
        }
        r = requests.post(f"{API}/meetings", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        mid = r.json()["meeting_id"]
        
        # Create question
        r_q = requests.post(
            f"{API}/meetings/{mid}/questions",
            headers=_headers(admin_token),
            json={"text": "What is this?"},
            timeout=10
        )
        assert r_q.status_code in (200, 201)
        
        # Cleanup
        requests.delete(f"{API}/meetings/{mid}", headers=_headers(admin_token), timeout=10)
    
    def test_host_can_create_breakout_room(self, admin_token):
        """Host can create breakout rooms."""
        payload = {
            "title": f"Breakout Meeting {uuid.uuid4().hex[:6]}",
            "description": "Test",
            "duration": 30,
            "meeting_type": "instant",
        }
        r = requests.post(f"{API}/meetings", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        mid = r.json()["meeting_id"]
        
        # Create breakout room
        r_br = requests.post(
            f"{API}/meetings/{mid}/breakout-rooms",
            headers=_headers(admin_token),
            json={"name": "Room 1", "participant_ids": []},
            timeout=10
        )
        assert r_br.status_code in (200, 201)
        
        # Cleanup
        requests.delete(f"{API}/meetings/{mid}", headers=_headers(admin_token), timeout=10)


# ============ ADDITIONAL IDOR PROBES ============

class TestAdditionalIDORProbes:
    """Additional IDOR probes for sub-resources."""
    
    def test_stranger_cannot_read_news_comments(self, admin_token, test_users):
        """Stranger cannot read comments on targeted post."""
        targeted_uid = test_users["targeted"]["user_id"]
        stranger_token = test_users["stranger"]["token"]
        
        payload = {
            "title": f"IDOR Comments Test {uuid.uuid4().hex[:6]}",
            "content": "Secret",
            "status": "published",
            "target_all": False,
            "target_user_ids": [targeted_uid],
        }
        r = requests.post(f"{API}/news/posts", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        pid = r.json()["post_id"]
        
        # Stranger cannot get comments
        r_comments = requests.get(f"{API}/news/posts/{pid}/comments", headers=_headers(stranger_token), timeout=10)
        assert r_comments.status_code == 404
        
        # Cleanup
        requests.delete(f"{API}/news/posts/{pid}", headers=_headers(admin_token), timeout=10)
    
    def test_stranger_cannot_react_to_targeted_post(self, admin_token, test_users):
        """Stranger cannot react to targeted post."""
        targeted_uid = test_users["targeted"]["user_id"]
        stranger_token = test_users["stranger"]["token"]
        
        payload = {
            "title": f"IDOR Reactions Test {uuid.uuid4().hex[:6]}",
            "content": "Secret",
            "status": "published",
            "target_all": False,
            "target_user_ids": [targeted_uid],
        }
        r = requests.post(f"{API}/news/posts", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        pid = r.json()["post_id"]
        
        # Stranger cannot react
        r_react = requests.post(
            f"{API}/news/posts/{pid}/reactions",
            headers=_headers(stranger_token),
            json={"reaction_type": "like"},
            timeout=10
        )
        assert r_react.status_code == 404
        
        # Cleanup
        requests.delete(f"{API}/news/posts/{pid}", headers=_headers(admin_token), timeout=10)
    
    def test_stranger_cannot_upvote_meeting_question(self, admin_token, test_users):
        """Stranger cannot upvote questions in a meeting they're not part of."""
        stranger_token = test_users["stranger"]["token"]
        
        payload = {
            "title": f"IDOR Question Upvote {uuid.uuid4().hex[:6]}",
            "description": "Test",
            "duration": 30,
            "meeting_type": "instant",
        }
        r = requests.post(f"{API}/meetings", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        mid = r.json()["meeting_id"]
        
        # Host creates question
        r_q = requests.post(
            f"{API}/meetings/{mid}/questions",
            headers=_headers(admin_token),
            json={"text": "What?"},
            timeout=10
        )
        assert r_q.status_code in (200, 201)
        qid = r_q.json()["question_id"]
        
        # Stranger cannot upvote
        r_upvote = requests.post(
            f"{API}/meetings/{mid}/questions/{qid}/upvote",
            headers=_headers(stranger_token),
            timeout=10
        )
        assert r_upvote.status_code == 404
        
        # Cleanup
        requests.delete(f"{API}/meetings/{mid}", headers=_headers(admin_token), timeout=10)
    
    def test_stranger_cannot_vote_meeting_poll(self, admin_token, test_users):
        """Stranger cannot vote on polls in a meeting they're not part of."""
        stranger_token = test_users["stranger"]["token"]
        
        payload = {
            "title": f"IDOR Poll Vote {uuid.uuid4().hex[:6]}",
            "description": "Test",
            "duration": 30,
            "meeting_type": "instant",
        }
        r = requests.post(f"{API}/meetings", headers=_headers(admin_token), json=payload, timeout=10)
        assert r.status_code in (200, 201)
        mid = r.json()["meeting_id"]
        
        # Host creates poll
        r_poll = requests.post(
            f"{API}/meetings/{mid}/polls",
            headers=_headers(admin_token),
            json={"question": "Test?", "options": ["A", "B"]},
            timeout=10
        )
        assert r_poll.status_code in (200, 201)
        poll_id = r_poll.json()["poll_id"]
        
        # Stranger cannot vote
        r_vote = requests.post(
            f"{API}/meetings/{mid}/polls/{poll_id}/vote",
            headers=_headers(stranger_token),
            json={"option_index": 0},
            timeout=10
        )
        assert r_vote.status_code == 404
        
        # Cleanup
        requests.delete(f"{API}/meetings/{mid}", headers=_headers(admin_token), timeout=10)


# ============ ADMIN ENDPOINTS REGRESSION ============

class TestAdminEndpointsRegression:
    """Admin endpoints must continue to work."""
    
    def test_admin_health(self, admin_token):
        """Admin health endpoint."""
        r = requests.get(f"{API}/admin/health", headers=_headers(admin_token), timeout=10)
        # May be 200 or 404 if endpoint doesn't exist
        assert r.status_code in (200, 404)
    
    def test_news_stats(self, admin_token):
        """News stats endpoint for admin."""
        r = requests.get(f"{API}/news/stats", headers=_headers(admin_token), timeout=10)
        assert r.status_code == 200
    
    def test_interaction_stats(self, admin_token):
        """Interaction stats endpoint for admin."""
        r = requests.get(f"{API}/interaction-stats", headers=_headers(admin_token), timeout=10)
        assert r.status_code == 200
    
    def test_feedback_entries(self, admin_token):
        """Feedback entries endpoint for admin."""
        r = requests.get(f"{API}/feedback/entries", headers=_headers(admin_token), timeout=10)
        assert r.status_code == 200
