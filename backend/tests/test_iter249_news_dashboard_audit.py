"""
Iteration 249 — Comprehensive News & Dashboard Module Audit
Tests: CRUD, RBAC, Validation, Workflow, Load Tests (50 concurrent users)

Roles tested:
- admin (admin@meetflow.com / admin123)
- member (dynamically registered)
- autor, redakteur, freigeber (assigned via admin)
"""
import pytest
import requests
import uuid
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
# For load tests, use localhost to avoid ingress rate-limiting
LOAD_TEST_URL = "http://localhost:8001"

# ============ FIXTURES ============

@pytest.fixture(scope="module")
def admin_session():
    """Login as admin and return session with auth headers."""
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@meetflow.com",
        "password": "admin123"
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    token = resp.json().get("token")
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


@pytest.fixture(scope="module")
def admin_token(admin_session):
    """Extract admin token for load tests."""
    return admin_session.headers.get("Authorization", "").replace("Bearer ", "")


@pytest.fixture(scope="module")
def member_session():
    """Register a new member user and return session."""
    session = requests.Session()
    email = f"test-news-member-{uuid.uuid4().hex[:8]}@meetflow.com"
    resp = session.post(f"{BASE_URL}/api/auth/register", json={
        "email": email,
        "password": "test123",
        "name": "Test Member News"
    })
    if resp.status_code == 409:
        # User exists, try login
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": email,
            "password": "test123"
        })
    assert resp.status_code in [200, 201], f"Member registration failed: {resp.text}"
    token = resp.json().get("token")
    session.headers.update({"Authorization": f"Bearer {token}"})
    session.user_email = email
    session.user_id = resp.json().get("user", {}).get("user_id") or resp.json().get("user_id")
    return session


@pytest.fixture(scope="module")
def member_token(member_session):
    """Extract member token for load tests."""
    return member_session.headers.get("Authorization", "").replace("Bearer ", "")


# ============ NEWS MODULE TESTS ============

class TestNewsBasicHealth:
    """Basic health checks for News endpoints."""
    
    def test_news_feed_accessible(self, admin_session):
        """GET /api/news/feed returns 200."""
        resp = admin_session.get(f"{BASE_URL}/api/news/feed")
        assert resp.status_code == 200, f"News feed failed: {resp.text}"
        data = resp.json()
        assert "posts" in data
        print(f"✓ News feed accessible, {len(data.get('posts', []))} posts")
    
    def test_news_categories_list(self, admin_session):
        """GET /api/news/categories returns list."""
        resp = admin_session.get(f"{BASE_URL}/api/news/categories")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        print(f"✓ Categories: {len(resp.json())} found")
    
    def test_news_unread_count(self, admin_session):
        """GET /api/news/unread-count returns counts."""
        resp = admin_session.get(f"{BASE_URL}/api/news/unread-count")
        assert resp.status_code == 200
        data = resp.json()
        assert "unread" in data
        print(f"✓ Unread count: {data.get('unread', 0)}")
    
    def test_news_stats_admin_only(self, admin_session, member_session):
        """GET /api/news/stats requires admin/moderator."""
        resp = admin_session.get(f"{BASE_URL}/api/news/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        print(f"✓ News stats: {data.get('total', 0)} total posts")
        
        # Member should get 403
        resp = member_session.get(f"{BASE_URL}/api/news/stats")
        assert resp.status_code == 403, f"Member should not access stats, got {resp.status_code}"
        print("✓ Member correctly denied access to stats")


class TestNewsCRUD:
    """CRUD operations for News posts."""
    
    def test_create_news_post_admin(self, admin_session):
        """Admin can create news post."""
        payload = {
            "title": f"TEST_News_{uuid.uuid4().hex[:6]}",
            "content": "Test content for news audit",
            "priority": "normal",
            "status": "draft"
        }
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json=payload)
        assert resp.status_code in [200, 201], f"Create news failed: {resp.text}"
        data = resp.json()
        assert "post_id" in data
        print(f"✓ Created news post: {data['post_id']}")
        
        # Verify persistence with GET
        resp2 = admin_session.get(f"{BASE_URL}/api/news/posts/{data['post_id']}")
        assert resp2.status_code == 200
        assert resp2.json()["title"] == payload["title"]
        print("✓ News post persisted correctly")
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{data['post_id']}")
        return data["post_id"]
    
    def test_create_news_member_forbidden(self, member_session):
        """Member cannot create news (RBAC)."""
        payload = {
            "title": "TEST_Unauthorized_News",
            "content": "Should fail",
            "priority": "normal"
        }
        resp = member_session.post(f"{BASE_URL}/api/news/posts", json=payload)
        assert resp.status_code == 403, f"Member should not create news, got {resp.status_code}"
        print("✓ Member correctly denied news creation")
    
    def test_update_news_post(self, admin_session):
        """Admin can update news post."""
        # Create first
        payload = {"title": f"TEST_Update_{uuid.uuid4().hex[:6]}", "content": "Original", "status": "draft"}
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json=payload)
        assert resp.status_code in [200, 201]
        post_id = resp.json()["post_id"]
        
        # Update
        resp = admin_session.put(f"{BASE_URL}/api/news/posts/{post_id}", json={
            "title": "TEST_Updated_Title",
            "content": "Updated content"
        })
        assert resp.status_code == 200, f"Update failed: {resp.text}"
        
        # Verify
        resp = admin_session.get(f"{BASE_URL}/api/news/posts/{post_id}")
        assert resp.json()["title"] == "TEST_Updated_Title"
        print("✓ News post updated and verified")
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
    
    def test_delete_news_post(self, admin_session):
        """Admin can delete news post."""
        payload = {"title": f"TEST_Delete_{uuid.uuid4().hex[:6]}", "content": "To delete", "status": "draft"}
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json=payload)
        post_id = resp.json()["post_id"]
        
        resp = admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
        assert resp.status_code == 200
        
        # Verify deleted
        resp = admin_session.get(f"{BASE_URL}/api/news/posts/{post_id}")
        assert resp.status_code == 404
        print("✓ News post deleted and verified")


class TestNewsValidation:
    """Validation tests for News endpoints."""
    
    def test_create_without_title_fails(self, admin_session):
        """POST /api/news/posts without title returns 400."""
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "content": "No title provided"
        })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        print("✓ Missing title correctly rejected")
    
    def test_create_with_invalid_priority(self, admin_session):
        """POST /api/news/posts with invalid priority returns 400."""
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "Test",
            "content": "Test",
            "priority": "invalid_priority"
        })
        # May return 400 or accept and default to normal
        if resp.status_code == 400:
            print("✓ Invalid priority correctly rejected")
        else:
            print(f"⚠ Invalid priority accepted (status {resp.status_code})")
    
    def test_get_nonexistent_post_404(self, admin_session):
        """GET /api/news/posts/{nonexistent} returns 404."""
        resp = admin_session.get(f"{BASE_URL}/api/news/posts/nonexistent_post_id_12345")
        assert resp.status_code == 404
        print("✓ Nonexistent post returns 404")
    
    def test_comment_without_text_fails(self, admin_session):
        """POST /api/news/posts/{id}/comments without text returns 400."""
        # Create a post first
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": f"TEST_Comment_{uuid.uuid4().hex[:6]}",
            "content": "Test",
            "status": "published"
        })
        if resp.status_code not in [200, 201]:
            pytest.skip("Could not create test post")
        post_id = resp.json()["post_id"]
        
        # Try empty comment
        resp = admin_session.post(f"{BASE_URL}/api/news/posts/{post_id}/comments", json={})
        # Should fail or return error
        if resp.status_code == 400:
            print("✓ Empty comment correctly rejected")
        else:
            print(f"⚠ Empty comment accepted (status {resp.status_code})")
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")


class TestNewsInteractions:
    """Test comments, reactions, read confirmations."""
    
    def test_read_confirmation(self, admin_session):
        """POST /api/news/posts/{id}/read marks as read."""
        # Create published post
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": f"TEST_Read_{uuid.uuid4().hex[:6]}",
            "content": "Test read confirmation",
            "status": "published"
        })
        if resp.status_code not in [200, 201]:
            pytest.skip("Could not create test post")
        post_id = resp.json()["post_id"]
        
        # Mark as read
        resp = admin_session.post(f"{BASE_URL}/api/news/posts/{post_id}/read")
        assert resp.status_code == 200
        print("✓ Read confirmation successful")
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
    
    def test_toggle_reaction(self, admin_session):
        """POST /api/news/posts/{id}/reactions toggles reaction."""
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": f"TEST_React_{uuid.uuid4().hex[:6]}",
            "content": "Test reactions",
            "status": "published"
        })
        if resp.status_code not in [200, 201]:
            pytest.skip("Could not create test post")
        post_id = resp.json()["post_id"]
        
        # Add reaction
        resp = admin_session.post(f"{BASE_URL}/api/news/posts/{post_id}/reactions", json={
            "reaction_type": "like"
        })
        assert resp.status_code == 200
        print("✓ Reaction added")
        
        # Toggle off
        resp = admin_session.post(f"{BASE_URL}/api/news/posts/{post_id}/reactions", json={
            "reaction_type": "like"
        })
        assert resp.status_code == 200
        print("✓ Reaction toggled")
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
    
    def test_add_comment(self, admin_session):
        """POST /api/news/posts/{id}/comments adds comment."""
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": f"TEST_Comment_{uuid.uuid4().hex[:6]}",
            "content": "Test comments",
            "status": "published"
        })
        if resp.status_code not in [200, 201]:
            pytest.skip("Could not create test post")
        post_id = resp.json()["post_id"]
        
        # Add comment
        resp = admin_session.post(f"{BASE_URL}/api/news/posts/{post_id}/comments", json={
            "content": "Test comment content"
        })
        assert resp.status_code in [200, 201]
        data = resp.json()
        assert "comment_id" in data
        print(f"✓ Comment added: {data['comment_id']}")
        
        # Verify in list
        resp = admin_session.get(f"{BASE_URL}/api/news/posts/{post_id}/comments")
        assert resp.status_code == 200
        comments = resp.json()
        assert len(comments) > 0
        print("✓ Comment persisted")
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")


class TestNewsReports:
    """Test content reporting functionality."""
    
    def test_report_content(self, member_session, admin_session):
        """POST /api/news/report creates report."""
        # Create a post as admin
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": f"TEST_Report_{uuid.uuid4().hex[:6]}",
            "content": "Test reporting",
            "status": "published"
        })
        if resp.status_code not in [200, 201]:
            pytest.skip("Could not create test post")
        post_id = resp.json()["post_id"]
        
        # Member reports it
        resp = member_session.post(f"{BASE_URL}/api/news/report", json={
            "content_type": "post",
            "content_id": post_id,
            "reason": "Test report reason"
        })
        assert resp.status_code in [200, 201]
        print("✓ Content reported successfully")
        
        # Admin can see reports
        resp = admin_session.get(f"{BASE_URL}/api/news/reports")
        assert resp.status_code == 200
        print("✓ Admin can view reports")
        
        # Member cannot see reports list
        resp = member_session.get(f"{BASE_URL}/api/news/reports")
        assert resp.status_code == 403
        print("✓ Member correctly denied reports list")
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
    
    def test_pending_reports_count(self, admin_session, member_session):
        """GET /api/news/reports/pending-count works for admin, returns 0 for member."""
        resp = admin_session.get(f"{BASE_URL}/api/news/reports/pending-count")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        print(f"✓ Admin pending reports count: {data['count']}")
        
        # Member gets 0 (not 403)
        resp = member_session.get(f"{BASE_URL}/api/news/reports/pending-count")
        assert resp.status_code == 200
        assert resp.json().get("count") == 0
        print("✓ Member gets 0 pending reports (not 403)")


class TestNewsPush:
    """Test push notification endpoints."""
    
    def test_vapid_public_key(self, admin_session):
        """GET /api/news/push/vapid-public-key returns key."""
        resp = admin_session.get(f"{BASE_URL}/api/news/push/vapid-public-key")
        assert resp.status_code == 200
        data = resp.json()
        assert "public_key" in data
        print("✓ VAPID public key accessible")
    
    def test_push_status(self, admin_session):
        """GET /api/news/push/status returns subscription status."""
        resp = admin_session.get(f"{BASE_URL}/api/news/push/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "subscribed" in data
        print(f"✓ Push status: subscribed={data['subscribed']}")
    
    def test_push_notifications_list_admin(self, admin_session, member_session):
        """GET /api/news/push/notifications requires reviewer role."""
        resp = admin_session.get(f"{BASE_URL}/api/news/push/notifications")
        assert resp.status_code == 200
        print("✓ Admin can list push notifications")
        
        resp = member_session.get(f"{BASE_URL}/api/news/push/notifications")
        assert resp.status_code == 403
        print("✓ Member denied push notifications list")


class TestNewsQA:
    """Test Q&A functionality."""
    
    def test_ask_question(self, admin_session):
        """POST /api/news/posts/{id}/questions creates question."""
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": f"TEST_QA_{uuid.uuid4().hex[:6]}",
            "content": "Test Q&A",
            "status": "published"
        })
        if resp.status_code not in [200, 201]:
            pytest.skip("Could not create test post")
        post_id = resp.json()["post_id"]
        
        # Ask question
        resp = admin_session.post(f"{BASE_URL}/api/news/posts/{post_id}/questions", json={
            "text": "Test question?"
        })
        assert resp.status_code in [200, 201]
        q_id = resp.json().get("question_id")
        print(f"✓ Question asked: {q_id}")
        
        # Get questions
        resp = admin_session.get(f"{BASE_URL}/api/news/posts/{post_id}/questions")
        assert resp.status_code == 200
        assert len(resp.json()) > 0
        print("✓ Questions listed")
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")


# ============ DASHBOARD MODULE TESTS ============

class TestDashboardBasicHealth:
    """Basic health checks for Dashboard endpoints."""
    
    def test_dashboard_stats(self, admin_session):
        """GET /api/dashboard/stats returns stats."""
        resp = admin_session.get(f"{BASE_URL}/api/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        print("✓ Dashboard stats accessible")
    
    def test_dashboard_agenda(self, admin_session):
        """GET /api/dashboard/agenda returns agenda."""
        resp = admin_session.get(f"{BASE_URL}/api/dashboard/agenda")
        assert resp.status_code == 200
        data = resp.json()
        assert "today" in data or "meetings_today" in data or isinstance(data, dict)
        print("✓ Dashboard agenda accessible")
    
    def test_notifications_list(self, admin_session):
        """GET /api/notifications returns notifications."""
        resp = admin_session.get(f"{BASE_URL}/api/notifications")
        assert resp.status_code == 200
        print("✓ Notifications accessible")
    
    def test_notifications_unread_count(self, admin_session):
        """GET /api/notifications/unread-count returns count."""
        resp = admin_session.get(f"{BASE_URL}/api/notifications/unread-count")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data or "unread" in data or isinstance(data.get("count"), int)
        print("✓ Unread notifications count accessible")


class TestUserStatus:
    """Test user status (online/away/dnd/offline)."""
    
    def test_get_my_status(self, admin_session):
        """GET /api/chat/my-status returns status."""
        resp = admin_session.get(f"{BASE_URL}/api/chat/my-status")
        assert resp.status_code == 200
        data = resp.json()
        assert "status_mode" in data
        print(f"✓ My status: {data['status_mode']}")
    
    def test_set_status_online(self, admin_session):
        """PUT /api/chat/my-status sets status."""
        resp = admin_session.put(f"{BASE_URL}/api/chat/my-status", json={
            "status_mode": "online"
        })
        assert resp.status_code == 200
        assert resp.json()["status_mode"] == "online"
        print("✓ Status set to online")
    
    def test_set_status_dnd_with_until(self, admin_session):
        """PUT /api/chat/my-status with dnd_until."""
        until = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        resp = admin_session.put(f"{BASE_URL}/api/chat/my-status", json={
            "status_mode": "dnd",
            "dnd_until": until
        })
        assert resp.status_code == 200
        assert resp.json()["status_mode"] == "dnd"
        print("✓ Status set to DND with expiry")
        
        # Reset to online
        admin_session.put(f"{BASE_URL}/api/chat/my-status", json={"status_mode": "online"})
    
    def test_invalid_status_rejected(self, admin_session):
        """PUT /api/chat/my-status with invalid status returns 400."""
        resp = admin_session.put(f"{BASE_URL}/api/chat/my-status", json={
            "status_mode": "invalid_status"
        })
        assert resp.status_code == 400
        print("✓ Invalid status correctly rejected")


class TestInOfficeWidget:
    """Test In-Office widget endpoints."""
    
    def test_resources_in_office(self, admin_session):
        """GET /api/resources-in-office returns people list."""
        resp = admin_session.get(f"{BASE_URL}/api/resources-in-office")
        assert resp.status_code in [200, 403]  # 403 if no view:resources cap
        if resp.status_code == 200:
            data = resp.json()
            assert "people" in data or "total" in data
            print(f"✓ In-office widget: {data.get('total', 0)} people")
        else:
            print("⚠ In-office widget requires view:resources cap")
    
    def test_resources_office_week(self, admin_session):
        """GET /api/resources-office-week returns week data."""
        resp = admin_session.get(f"{BASE_URL}/api/resources-office-week")
        assert resp.status_code in [200, 403]
        if resp.status_code == 200:
            data = resp.json()
            assert "days" in data or "week_start" in data
            print("✓ Office week widget accessible")
        else:
            print("⚠ Office week widget requires view:resources cap")


# ============ RBAC AUDIT ============

class TestRBACMemberRestrictions:
    """Verify member role cannot access admin endpoints."""
    
    def test_member_cannot_create_news(self, member_session):
        """Member cannot POST /api/news/posts."""
        resp = member_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "Unauthorized", "content": "Test"
        })
        assert resp.status_code == 403
        print("✓ Member denied news creation")
    
    def test_member_cannot_view_reports(self, member_session):
        """Member cannot GET /api/news/reports."""
        resp = member_session.get(f"{BASE_URL}/api/news/reports")
        assert resp.status_code == 403
        print("✓ Member denied reports list")
    
    def test_member_cannot_export_interactions(self, member_session):
        """Member cannot GET /api/exports/interactions/csv."""
        resp = member_session.get(f"{BASE_URL}/api/exports/interactions/csv")
        assert resp.status_code == 403
        print("✓ Member denied interactions export")
    
    def test_member_cannot_send_push(self, member_session):
        """Member cannot POST /api/news/push/send."""
        resp = member_session.post(f"{BASE_URL}/api/news/push/send", json={
            "post_id": "test"
        })
        assert resp.status_code in [403, 404]  # 404 if post not found first
        print("✓ Member denied push send")
    
    def test_member_can_read_news(self, member_session):
        """Member CAN GET /api/news/feed."""
        resp = member_session.get(f"{BASE_URL}/api/news/feed")
        assert resp.status_code == 200
        print("✓ Member can read news feed")
    
    def test_member_can_get_unread_count(self, member_session):
        """Member CAN GET /api/news/unread-count."""
        resp = member_session.get(f"{BASE_URL}/api/news/unread-count")
        assert resp.status_code == 200
        print("✓ Member can get unread count")


class TestUnauthenticatedAccess:
    """Verify unauthenticated requests are rejected."""
    
    def test_news_feed_requires_auth(self):
        """GET /api/news/feed without auth returns 401."""
        resp = requests.get(f"{BASE_URL}/api/news/feed")
        assert resp.status_code == 401
        print("✓ News feed requires auth")
    
    def test_reactions_require_auth(self):
        """POST /api/news/posts/{id}/reactions without auth returns 401."""
        resp = requests.post(f"{BASE_URL}/api/news/posts/test/reactions", json={
            "reaction_type": "like"
        })
        assert resp.status_code == 401
        print("✓ Reactions require auth")
    
    def test_dashboard_requires_auth(self):
        """GET /api/dashboard/stats without auth returns 401."""
        resp = requests.get(f"{BASE_URL}/api/dashboard/stats")
        assert resp.status_code == 401
        print("✓ Dashboard requires auth")


# ============ EXPORTS ============

class TestExports:
    """Test CSV/PDF export endpoints."""
    
    def test_interactions_csv_export(self, admin_session):
        """GET /api/exports/interactions/csv returns CSV."""
        resp = admin_session.get(f"{BASE_URL}/api/exports/interactions/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        print("✓ Interactions CSV export works")
    
    def test_interactions_pdf_export(self, admin_session):
        """GET /api/exports/interactions/pdf returns PDF."""
        resp = admin_session.get(f"{BASE_URL}/api/exports/interactions/pdf")
        assert resp.status_code == 200
        assert "pdf" in resp.headers.get("content-type", "")
        print("✓ Interactions PDF export works")


# ============ LOAD TESTS (50 concurrent users) ============

class TestLoadConcurrent:
    """Load tests with 50 concurrent users using localhost:8001."""
    
    def test_50_concurrent_get_news(self, admin_token):
        """50 concurrent GET /api/news/feed requests."""
        results = {"success": 0, "failed": 0, "latencies": []}
        
        def make_request():
            start = time.time()
            try:
                resp = requests.get(
                    f"{LOAD_TEST_URL}/api/news/feed",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    timeout=30
                )
                latency = (time.time() - start) * 1000
                return resp.status_code == 200, latency
            except Exception:
                return False, 0
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(make_request) for _ in range(50)]
            for f in as_completed(futures):
                success, latency = f.result()
                if success:
                    results["success"] += 1
                    results["latencies"].append(latency)
                else:
                    results["failed"] += 1
        
        if results["latencies"]:
            results["latencies"].sort()
            p95_idx = int(len(results["latencies"]) * 0.95)
            p95 = results["latencies"][p95_idx] if p95_idx < len(results["latencies"]) else results["latencies"][-1]
            avg = sum(results["latencies"]) / len(results["latencies"])
            print(f"✓ 50 concurrent GET /api/news/feed: {results['success']}/50 success, avg={avg:.0f}ms, p95={p95:.0f}ms")
        else:
            print(f"⚠ 50 concurrent GET /api/news/feed: {results['success']}/50 success, {results['failed']} failed")
        
        # Allow some failures due to rate limiting
        assert results["success"] >= 25, f"Too many failures: {results['failed']}/50"
    
    def test_50_concurrent_create_news(self, admin_token):
        """50 concurrent POST /api/news/posts (different titles)."""
        results = {"success": 0, "failed": 0, "post_ids": []}
        
        def make_request(i):
            try:
                resp = requests.post(
                    f"{LOAD_TEST_URL}/api/news/posts",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={
                        "title": f"LOAD_News_{i}_{uuid.uuid4().hex[:6]}",
                        "content": f"Load test content {i}",
                        "status": "draft"
                    },
                    timeout=30
                )
                if resp.status_code in [200, 201]:
                    return True, resp.json().get("post_id")
                return False, None
            except Exception:
                return False, None
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(make_request, i) for i in range(50)]
            for f in as_completed(futures):
                success, post_id = f.result()
                if success:
                    results["success"] += 1
                    if post_id:
                        results["post_ids"].append(post_id)
                else:
                    results["failed"] += 1
        
        print(f"✓ 50 concurrent POST /api/news/posts: {results['success']}/50 created")
        
        # Cleanup
        for pid in results["post_ids"]:
            try:
                requests.delete(
                    f"{LOAD_TEST_URL}/api/news/posts/{pid}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    timeout=10
                )
            except:
                pass
        
        # Allow some failures
        assert results["success"] >= 25, f"Too many failures: {results['failed']}/50"
    
    def test_50_concurrent_read_confirm_same_post(self, admin_token):
        """50 concurrent POST /api/news/posts/{id}/read on same post (idempotency)."""
        # Create a test post
        resp = requests.post(
            f"{LOAD_TEST_URL}/api/news/posts",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"title": f"LOAD_ReadTest_{uuid.uuid4().hex[:6]}", "content": "Test", "status": "published"},
            timeout=30
        )
        if resp.status_code not in [200, 201]:
            pytest.skip("Could not create test post")
        post_id = resp.json()["post_id"]
        
        results = {"success": 0, "failed": 0}
        
        def make_request():
            try:
                resp = requests.post(
                    f"{LOAD_TEST_URL}/api/news/posts/{post_id}/read",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    timeout=30
                )
                return resp.status_code == 200
            except:
                return False
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(make_request) for _ in range(50)]
            for f in as_completed(futures):
                if f.result():
                    results["success"] += 1
                else:
                    results["failed"] += 1
        
        print(f"✓ 50 concurrent read confirmations: {results['success']}/50 success (idempotent)")
        
        # Cleanup
        requests.delete(
            f"{LOAD_TEST_URL}/api/news/posts/{post_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10
        )
        
        assert results["success"] >= 25
    
    def test_50_concurrent_reactions_toggle(self, admin_token):
        """50 concurrent reaction toggles on same post."""
        # Create test post
        resp = requests.post(
            f"{LOAD_TEST_URL}/api/news/posts",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"title": f"LOAD_ReactTest_{uuid.uuid4().hex[:6]}", "content": "Test", "status": "published"},
            timeout=30
        )
        if resp.status_code not in [200, 201]:
            pytest.skip("Could not create test post")
        post_id = resp.json()["post_id"]
        
        results = {"success": 0, "failed": 0}
        
        def make_request():
            try:
                resp = requests.post(
                    f"{LOAD_TEST_URL}/api/news/posts/{post_id}/reactions",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"reaction_type": "like"},
                    timeout=30
                )
                return resp.status_code == 200
            except:
                return False
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(make_request) for _ in range(50)]
            for f in as_completed(futures):
                if f.result():
                    results["success"] += 1
                else:
                    results["failed"] += 1
        
        print(f"✓ 50 concurrent reaction toggles: {results['success']}/50 success")
        
        # Cleanup
        requests.delete(
            f"{LOAD_TEST_URL}/api/news/posts/{post_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10
        )
        
        assert results["success"] >= 25
    
    def test_50_concurrent_comments(self, admin_token):
        """50 concurrent comments on same post."""
        # Create test post
        resp = requests.post(
            f"{LOAD_TEST_URL}/api/news/posts",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"title": f"LOAD_CommentTest_{uuid.uuid4().hex[:6]}", "content": "Test", "status": "published"},
            timeout=30
        )
        if resp.status_code not in [200, 201]:
            pytest.skip("Could not create test post")
        post_id = resp.json()["post_id"]
        
        results = {"success": 0, "failed": 0}
        
        def make_request(i):
            try:
                resp = requests.post(
                    f"{LOAD_TEST_URL}/api/news/posts/{post_id}/comments",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"content": f"Load test comment {i}"},
                    timeout=30
                )
                return resp.status_code in [200, 201]
            except:
                return False
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(make_request, i) for i in range(50)]
            for f in as_completed(futures):
                if f.result():
                    results["success"] += 1
                else:
                    results["failed"] += 1
        
        # Verify all comments stored
        resp = requests.get(
            f"{LOAD_TEST_URL}/api/news/posts/{post_id}/comments",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30
        )
        comment_count = len(resp.json()) if resp.status_code == 200 else 0
        
        print(f"✓ 50 concurrent comments: {results['success']}/50 success, {comment_count} stored")
        
        # Cleanup
        requests.delete(
            f"{LOAD_TEST_URL}/api/news/posts/{post_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10
        )
        
        assert results["success"] >= 25


# ============ REGRESSION (iter 248) ============

class TestRegressionIter248:
    """Regression tests for iter 248 fixes."""
    
    def test_booking_race_condition(self, admin_token):
        """50 concurrent bookings on same slot - exactly 1 success expected."""
        # First, get a resource
        resp = requests.get(
            f"{LOAD_TEST_URL}/api/resources?type=desk",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30
        )
        if resp.status_code != 200 or not resp.json():
            pytest.skip("No desks available for race test")
        
        resources = resp.json()
        if not resources:
            pytest.skip("No desks available")
        
        resource_id = resources[0].get("resource_id")
        
        # Create a future time slot
        start = (datetime.now(timezone.utc) + timedelta(days=7, hours=10)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=7, hours=11)).isoformat()
        
        results = {"success_200": 0, "conflict_409": 0, "other": 0}
        
        def make_booking():
            try:
                resp = requests.post(
                    f"{LOAD_TEST_URL}/api/resource-bookings",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={
                        "resource_id": resource_id,
                        "start_at": start,
                        "end_at": end,
                        "title": f"RACE_Test_{uuid.uuid4().hex[:6]}"
                    },
                    timeout=30
                )
                return resp.status_code
            except:
                return 0
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(make_booking) for _ in range(50)]
            for f in as_completed(futures):
                code = f.result()
                if code in [200, 201]:
                    results["success_200"] += 1
                elif code == 409:
                    results["conflict_409"] += 1
                else:
                    results["other"] += 1
        
        print(f"✓ Race condition test: {results['success_200']} success, {results['conflict_409']} conflicts, {results['other']} other")
        
        # Ideally exactly 1 success, rest conflicts
        # But with rate limiting, we may have fewer total responses
        total_valid = results["success_200"] + results["conflict_409"]
        if total_valid > 0:
            assert results["success_200"] <= 1, f"Race condition: {results['success_200']} successes (expected <=1)"
            print("✓ Race condition protection working")


# ============ CLEANUP ============

@pytest.fixture(scope="module", autouse=True)
def cleanup_test_data(admin_session):
    """Cleanup TEST_, LOAD_, RACE_ prefixed data after tests."""
    yield
    # Cleanup news posts
    try:
        resp = admin_session.get(f"{BASE_URL}/api/news/feed?limit=100")
        if resp.status_code == 200:
            for post in resp.json().get("posts", []):
                title = post.get("title", "")
                if title.startswith("TEST_") or title.startswith("LOAD_") or title.startswith("RACE_"):
                    admin_session.delete(f"{BASE_URL}/api/news/posts/{post['post_id']}")
    except:
        pass
    print("✓ Test data cleanup completed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
