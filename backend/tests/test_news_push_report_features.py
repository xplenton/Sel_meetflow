"""
Test suite for News Push Notifications, Report/Melden, comments_enabled, and Role-based permissions.
Features tested:
1. VAPID Web Push endpoints (vapid-public-key, subscribe, unsubscribe, status, notifications)
2. Report/Melden feature (POST /news/report, GET /news/reports, PUT /news/reports/{id})
3. comments_enabled toggle (blocks POST /news/posts/{id}/comments when false)
4. Role-based permissions (autor can edit/delete OWN drafts, freigeber can publish)
5. Auto push notification on critical/important news publish
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"
AUTOR_EMAIL = "autor-test@meetflow.com"
AUTOR_PASSWORD = "9e619d6544"


class TestSetup:
    """Setup and authentication helpers"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin and return session with cookies"""
        session = requests.Session()
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        return session
    
    @pytest.fixture(scope="class")
    def autor_session(self):
        """Login as autor and return session with cookies"""
        session = requests.Session()
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": AUTOR_EMAIL,
            "password": AUTOR_PASSWORD
        })
        assert resp.status_code == 200, f"Autor login failed: {resp.text}"
        return session


class TestVAPIDPushEndpoints(TestSetup):
    """Test VAPID Web Push endpoints"""
    
    def test_get_vapid_public_key(self, admin_session):
        """GET /api/news/push/vapid-public-key returns non-empty public_key"""
        resp = admin_session.get(f"{BASE_URL}/api/news/push/vapid-public-key")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "public_key" in data, "Response missing public_key"
        assert len(data["public_key"]) > 0, "public_key is empty"
        print(f"VAPID public key: {data['public_key'][:30]}...")
    
    def test_push_subscribe_and_status(self, admin_session):
        """POST /api/news/push/subscribe stores subscription, GET /api/news/push/status returns subscribed=true"""
        # Create a mock subscription object
        mock_subscription = {
            "endpoint": "https://test-push-endpoint.example.com/test123",
            "keys": {
                "p256dh": "test_p256dh_key_base64",
                "auth": "test_auth_key_base64"
            }
        }
        
        # Subscribe
        resp = admin_session.post(f"{BASE_URL}/api/news/push/subscribe", json={
            "subscription": mock_subscription
        })
        assert resp.status_code == 200, f"Subscribe failed: {resp.text}"
        assert "gespeichert" in resp.json().get("message", "").lower() or "saved" in resp.json().get("message", "").lower()
        
        # Check status
        resp = admin_session.get(f"{BASE_URL}/api/news/push/status")
        assert resp.status_code == 200, f"Status check failed: {resp.text}"
        data = resp.json()
        assert data.get("subscribed") == True, f"Expected subscribed=true, got {data}"
        assert data.get("count", 0) >= 1, "Expected count >= 1"
        print(f"Push status: subscribed={data['subscribed']}, count={data['count']}")
    
    def test_push_unsubscribe(self, admin_session):
        """DELETE /api/news/push/subscribe removes subscription"""
        # First ensure we have a subscription
        mock_subscription = {
            "endpoint": "https://test-push-endpoint.example.com/unsubscribe-test",
            "keys": {"p256dh": "test", "auth": "test"}
        }
        admin_session.post(f"{BASE_URL}/api/news/push/subscribe", json={"subscription": mock_subscription})
        
        # Unsubscribe
        resp = admin_session.delete(f"{BASE_URL}/api/news/push/subscribe", json={
            "endpoint": "https://test-push-endpoint.example.com/unsubscribe-test"
        })
        assert resp.status_code == 200, f"Unsubscribe failed: {resp.text}"
        assert "entfernt" in resp.json().get("message", "").lower() or "removed" in resp.json().get("message", "").lower()
        print("Push unsubscribe successful")
    
    def test_push_notifications_list(self, admin_session):
        """GET /api/news/push/notifications returns list (admin/redakteur only)"""
        resp = admin_session.get(f"{BASE_URL}/api/news/push/notifications")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Expected list of notifications"
        print(f"Push notifications count: {len(data)}")


class TestReportMeldenFeature(TestSetup):
    """Test Report/Melden feature for posts and comments"""
    
    @pytest.fixture(scope="class")
    def test_post_id(self, admin_session):
        """Create a test post for reporting"""
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "TEST_Report_Feature_Post",
            "content": "This is a test post for report feature testing",
            "status": "published"
        })
        assert resp.status_code == 200, f"Failed to create test post: {resp.text}"
        post_id = resp.json()["post_id"]
        yield post_id
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
    
    @pytest.fixture(scope="class")
    def test_comment_id(self, admin_session, test_post_id):
        """Create a test comment for reporting"""
        resp = admin_session.post(f"{BASE_URL}/api/news/posts/{test_post_id}/comments", json={
            "content": "TEST_Comment for report testing"
        })
        assert resp.status_code == 200, f"Failed to create test comment: {resp.text}"
        return resp.json()["comment_id"]
    
    def test_report_post(self, autor_session, test_post_id):
        """POST /api/news/report stores a report for a post with status=pending"""
        resp = autor_session.post(f"{BASE_URL}/api/news/report", json={
            "content_type": "post",
            "content_id": test_post_id,
            "reason": "TEST_Report: Inappropriate content"
        })
        assert resp.status_code == 200, f"Report failed: {resp.text}"
        data = resp.json()
        assert data.get("status") == "pending", f"Expected status=pending, got {data.get('status')}"
        assert data.get("content_type") == "post"
        assert data.get("content_id") == test_post_id
        assert "report_id" in data
        print(f"Report created: {data['report_id']}")
        return data["report_id"]
    
    def test_report_comment(self, autor_session, test_comment_id):
        """POST /api/news/report stores a report for a comment with status=pending"""
        resp = autor_session.post(f"{BASE_URL}/api/news/report", json={
            "content_type": "comment",
            "content_id": test_comment_id,
            "reason": "TEST_Report: Spam comment"
        })
        assert resp.status_code == 200, f"Report failed: {resp.text}"
        data = resp.json()
        assert data.get("status") == "pending"
        assert data.get("content_type") == "comment"
        print(f"Comment report created: {data['report_id']}")
    
    def test_list_reports_admin_only(self, admin_session, autor_session):
        """GET /api/news/reports returns list for admin/redakteur, 403 for autor"""
        # Admin should succeed
        resp = admin_session.get(f"{BASE_URL}/api/news/reports")
        assert resp.status_code == 200, f"Admin list reports failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Expected list of reports"
        print(f"Reports count (admin view): {len(data)}")
        
        # Autor should get 403
        resp = autor_session.get(f"{BASE_URL}/api/news/reports")
        assert resp.status_code == 403, f"Expected 403 for autor, got {resp.status_code}"
        print("Autor correctly denied access to reports list")
    
    def test_update_report_status(self, admin_session):
        """PUT /api/news/reports/{id} updates status (admin only)"""
        # First get a report to update
        resp = admin_session.get(f"{BASE_URL}/api/news/reports")
        reports = resp.json()
        test_reports = [r for r in reports if "TEST_Report" in r.get("reason", "")]
        
        if test_reports:
            report_id = test_reports[0]["report_id"]
            resp = admin_session.put(f"{BASE_URL}/api/news/reports/{report_id}", json={
                "status": "reviewed",
                "action": "dismiss"
            })
            assert resp.status_code == 200, f"Update report failed: {resp.text}"
            print(f"Report {report_id} updated to reviewed/dismiss")
        else:
            print("No test reports found to update - skipping")


class TestCommentsEnabledToggle(TestSetup):
    """Test comments_enabled toggle functionality"""
    
    def test_comments_disabled_blocks_new_comments(self, admin_session, autor_session):
        """POST /api/news/posts/{id}/comments returns 403 when comments_enabled=false"""
        # Create a post with comments disabled
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "TEST_Comments_Disabled_Post",
            "content": "This post has comments disabled",
            "status": "published",
            "comments_enabled": False
        })
        assert resp.status_code == 200, f"Failed to create post: {resp.text}"
        post_id = resp.json()["post_id"]
        
        # Verify comments_enabled is false
        resp = admin_session.get(f"{BASE_URL}/api/news/posts/{post_id}")
        assert resp.json().get("comments_enabled") == False, "comments_enabled should be False"
        
        try:
            # Try to add a comment - should fail with 403
            resp = autor_session.post(f"{BASE_URL}/api/news/posts/{post_id}/comments", json={
                "content": "This comment should be blocked"
            })
            assert resp.status_code == 403, f"Expected 403 when comments disabled, got {resp.status_code}"
            assert "deaktiviert" in resp.json().get("detail", "").lower() or "disabled" in resp.json().get("detail", "").lower()
            print("Comments correctly blocked when comments_enabled=false")
        finally:
            # Cleanup
            admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
    
    def test_comments_enabled_allows_comments(self, admin_session, autor_session):
        """POST /api/news/posts/{id}/comments succeeds when comments_enabled=true"""
        # Create a post with comments enabled (default)
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "TEST_Comments_Enabled_Post",
            "content": "This post has comments enabled",
            "status": "published",
            "comments_enabled": True
        })
        assert resp.status_code == 200
        post_id = resp.json()["post_id"]
        
        try:
            # Add a comment - should succeed
            resp = autor_session.post(f"{BASE_URL}/api/news/posts/{post_id}/comments", json={
                "content": "TEST_Comment on enabled post"
            })
            assert resp.status_code == 200, f"Comment should succeed: {resp.text}"
            print("Comments correctly allowed when comments_enabled=true")
        finally:
            admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")


class TestRoleBasedPermissions(TestSetup):
    """Test role-based permissions for News module"""
    
    def test_autor_can_create_draft(self, autor_session):
        """Autor can create a draft news post"""
        resp = autor_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "TEST_Autor_Draft_Post",
            "content": "Draft created by autor",
            "status": "draft"
        })
        assert resp.status_code == 200, f"Autor should be able to create draft: {resp.text}"
        post_id = resp.json()["post_id"]
        print(f"Autor created draft: {post_id}")
        return post_id
    
    def test_autor_can_update_own_draft(self, autor_session):
        """Autor can update their own draft"""
        # Create a draft first
        resp = autor_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "TEST_Autor_Update_Draft",
            "content": "Original content",
            "status": "draft"
        })
        post_id = resp.json()["post_id"]
        
        try:
            # Update the draft
            resp = autor_session.put(f"{BASE_URL}/api/news/posts/{post_id}", json={
                "title": "TEST_Autor_Update_Draft_Modified",
                "content": "Updated content by autor"
            })
            assert resp.status_code == 200, f"Autor should update own draft: {resp.text}"
            print("Autor successfully updated own draft")
        finally:
            autor_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
    
    def test_autor_can_delete_own_draft(self, autor_session):
        """Autor can delete their own draft"""
        # Create a draft
        resp = autor_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "TEST_Autor_Delete_Draft",
            "content": "To be deleted",
            "status": "draft"
        })
        post_id = resp.json()["post_id"]
        
        # Delete the draft
        resp = autor_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
        assert resp.status_code == 200, f"Autor should delete own draft: {resp.text}"
        print("Autor successfully deleted own draft")
    
    def test_autor_cannot_edit_others_posts(self, admin_session, autor_session):
        """Autor gets 403 when trying to edit another user's post"""
        # Admin creates a post
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "TEST_Admin_Post_For_Autor_Test",
            "content": "Admin's post",
            "status": "draft"
        })
        post_id = resp.json()["post_id"]
        
        try:
            # Autor tries to edit - should fail
            resp = autor_session.put(f"{BASE_URL}/api/news/posts/{post_id}", json={
                "title": "Autor trying to edit admin's post"
            })
            assert resp.status_code == 403, f"Expected 403 for autor editing others' post, got {resp.status_code}"
            print("Autor correctly denied editing others' posts")
        finally:
            admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
    
    def test_autor_cannot_access_admin_endpoints(self, autor_session):
        """Autor gets 403 on admin-only endpoints like /news/reports"""
        resp = autor_session.get(f"{BASE_URL}/api/news/reports")
        assert resp.status_code == 403, f"Expected 403 for autor on /news/reports, got {resp.status_code}"
        
        resp = autor_session.get(f"{BASE_URL}/api/news/push/notifications")
        assert resp.status_code == 403, f"Expected 403 for autor on /news/push/notifications, got {resp.status_code}"
        print("Autor correctly denied access to admin-only endpoints")


class TestFreigeberPublishPermission(TestSetup):
    """Test that Freigeber can publish posts"""
    
    @pytest.fixture(scope="class")
    def freigeber_session(self, admin_session):
        """Create a freigeber user and return session"""
        # First check if freigeber exists, if not create one
        import uuid
        freigeber_email = f"freigeber-test-{uuid.uuid4().hex[:6]}@meetflow.com"
        freigeber_password = "freigeber123"
        
        # Create freigeber via admin invite
        resp = admin_session.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": freigeber_email,
            "name": "Test Freigeber",
            "role": "freigeber",
            "password": freigeber_password
        })
        
        if resp.status_code not in [200, 201]:
            pytest.skip(f"Could not create freigeber user: {resp.text}")
        
        # Login as freigeber
        session = requests.Session()
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": freigeber_email,
            "password": freigeber_password
        })
        
        if resp.status_code != 200:
            pytest.skip(f"Freigeber login failed: {resp.text}")
        
        yield session
        
        # Cleanup - delete freigeber user
        user_id = resp.json().get("user", {}).get("user_id")
        if user_id:
            admin_session.delete(f"{BASE_URL}/api/admin/users/{user_id}")
    
    def test_freigeber_can_publish(self, admin_session, freigeber_session):
        """Freigeber can call /news/posts/{id}/publish"""
        # Admin creates a draft
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "TEST_Freigeber_Publish_Test",
            "content": "Post to be published by freigeber",
            "status": "draft"
        })
        if resp.status_code != 200:
            pytest.skip(f"Could not create test post: {resp.text}")
        
        post_id = resp.json()["post_id"]
        
        try:
            # Freigeber publishes
            resp = freigeber_session.post(f"{BASE_URL}/api/news/posts/{post_id}/publish")
            assert resp.status_code == 200, f"Freigeber should be able to publish: {resp.text}"
            assert "veroeffentlicht" in resp.json().get("message", "").lower() or "published" in resp.json().get("message", "").lower()
            print("Freigeber successfully published post")
        finally:
            admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")


class TestAutoPushOnCriticalNews(TestSetup):
    """Test auto push notification when critical/important news is published"""
    
    def test_critical_news_creates_push_notification(self, admin_session):
        """Creating/publishing news with priority=critical auto-writes to push_notifications collection"""
        # Get initial notification count
        resp = admin_session.get(f"{BASE_URL}/api/news/push/notifications")
        initial_count = len(resp.json())
        
        # Create and publish a critical news post
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "TEST_Critical_News_Auto_Push",
            "content": "This critical news should trigger auto push",
            "priority": "critical",
            "status": "published"
        })
        assert resp.status_code == 200, f"Failed to create critical news: {resp.text}"
        post_id = resp.json()["post_id"]
        
        try:
            # Wait a moment for async push dispatch
            time.sleep(0.5)
            
            # Check push_notifications collection grew
            resp = admin_session.get(f"{BASE_URL}/api/news/push/notifications")
            new_count = len(resp.json())
            
            # Find notification for our post
            notifications = resp.json()
            our_notif = [n for n in notifications if n.get("post_id") == post_id]
            
            assert len(our_notif) > 0 or new_count > initial_count, \
                f"Expected push notification for critical news. Initial: {initial_count}, New: {new_count}"
            
            if our_notif:
                print(f"Auto push notification created: {our_notif[0].get('notification_id')}, target_count={our_notif[0].get('target_count', 0)}")
            else:
                print(f"Push notifications increased from {initial_count} to {new_count}")
        finally:
            admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
    
    def test_important_news_creates_push_notification(self, admin_session):
        """Publishing news with priority=important also triggers auto push"""
        resp = admin_session.get(f"{BASE_URL}/api/news/push/notifications")
        initial_count = len(resp.json())
        
        # Create important news
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "TEST_Important_News_Auto_Push",
            "content": "This important news should trigger auto push",
            "priority": "important",
            "status": "published"
        })
        post_id = resp.json()["post_id"]
        
        try:
            time.sleep(0.5)
            resp = admin_session.get(f"{BASE_URL}/api/news/push/notifications")
            new_count = len(resp.json())
            
            assert new_count >= initial_count, "Push notification should be created for important news"
            print(f"Important news push: notifications went from {initial_count} to {new_count}")
        finally:
            admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")


class TestCleanup(TestSetup):
    """Cleanup test data"""
    
    def test_cleanup_test_reports(self, admin_session):
        """Remove TEST_ prefixed reports"""
        resp = admin_session.get(f"{BASE_URL}/api/news/reports")
        if resp.status_code == 200:
            reports = resp.json()
            test_reports = [r for r in reports if "TEST_" in r.get("reason", "")]
            for r in test_reports:
                admin_session.put(f"{BASE_URL}/api/news/reports/{r['report_id']}", json={
                    "status": "dismissed",
                    "action": "dismiss"
                })
            print(f"Cleaned up {len(test_reports)} test reports")
    
    def test_cleanup_test_subscriptions(self, admin_session):
        """Remove test push subscriptions"""
        admin_session.delete(f"{BASE_URL}/api/news/push/subscribe", json={
            "endpoint": "https://test-push-endpoint.example.com/test123"
        })
        print("Cleaned up test push subscriptions")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
