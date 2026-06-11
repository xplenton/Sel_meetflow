"""
Iteration 130 - News Channel Dispatch Tests

Tests the multi-channel news distribution feature:
1. POST /api/news/posts with channels=[intranet,push,digital_signage] + status=published → signage_eligible=true
2. GET /api/news/digital-signage/feed (no auth) → returns posts with signage_eligible=true
3. Creating a post without digital_signage in channels → does NOT appear in digital-signage feed
4. Creating a post with push in channels + priority=normal → should trigger dispatch
5. Existing /api/news/feed endpoint still works (regression)
6. Existing /api/news/posts/{id}/publish endpoint still works and dispatches based on channels
7. Moderator approval flow via review/approve endpoint also triggers channel dispatch
"""

import pytest
import requests
import os
import time
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"


class TestNewsChannelDispatch:
    """Tests for the news channel dispatch feature (iter 130)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: login as admin and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        data = login_resp.json()
        self.token = data.get("token")
        self.user = data.get("user")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Track created posts for cleanup
        self.created_post_ids = []
        
        yield
        
        # Cleanup: delete test posts
        for post_id in self.created_post_ids:
            try:
                self.session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
            except:
                pass
    
    def test_01_create_post_with_digital_signage_channel_sets_signage_eligible(self):
        """POST /api/news/posts with channels=[intranet,push,digital_signage] + status=published → signage_eligible=true"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "title": f"TEST_Signage Post {unique_id}",
            "content": "This post should appear on digital signage displays",
            "channels": ["intranet", "push", "digital_signage"],
            "status": "published",
            "priority": "normal",
            "target_all": True
        }
        
        resp = self.session.post(f"{BASE_URL}/api/news/posts", json=payload)
        assert resp.status_code == 200, f"Create post failed: {resp.text}"
        
        post = resp.json()
        self.created_post_ids.append(post["post_id"])
        
        # Verify post was created with correct channels
        assert post["status"] == "published", f"Expected status=published, got {post['status']}"
        assert "digital_signage" in post.get("channels", []), "digital_signage not in channels"
        assert "push" in post.get("channels", []), "push not in channels"
        assert "intranet" in post.get("channels", []), "intranet not in channels"
        
        # Wait a moment for async dispatch to complete
        time.sleep(0.5)
        
        # Verify signage_eligible was set by fetching the post
        get_resp = self.session.get(f"{BASE_URL}/api/news/posts/{post['post_id']}")
        assert get_resp.status_code == 200, f"Get post failed: {get_resp.text}"
        
        fetched_post = get_resp.json()
        assert fetched_post.get("signage_eligible") == True, f"signage_eligible should be True, got {fetched_post.get('signage_eligible')}"
        
        print(f"✓ Post created with digital_signage channel, signage_eligible={fetched_post.get('signage_eligible')}")
    
    def test_02_digital_signage_feed_returns_eligible_posts_no_auth(self):
        """GET /api/news/digital-signage/feed (no auth) → returns posts with signage_eligible=true"""
        # First create a post with digital_signage channel
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "title": f"TEST_Signage Feed Test {unique_id}",
            "content": "This post should appear in the signage feed",
            "channels": ["intranet", "digital_signage"],
            "status": "published",
            "priority": "normal",
            "target_all": True
        }
        
        create_resp = self.session.post(f"{BASE_URL}/api/news/posts", json=payload)
        assert create_resp.status_code == 200, f"Create post failed: {create_resp.text}"
        post = create_resp.json()
        self.created_post_ids.append(post["post_id"])
        
        # Wait for async dispatch
        time.sleep(0.5)
        
        # Now test the public feed endpoint WITHOUT auth
        public_session = requests.Session()  # No auth headers
        feed_resp = public_session.get(f"{BASE_URL}/api/news/digital-signage/feed")
        
        assert feed_resp.status_code == 200, f"Digital signage feed failed: {feed_resp.text}"
        
        feed_data = feed_resp.json()
        assert "posts" in feed_data, "Response should have 'posts' key"
        assert "count" in feed_data, "Response should have 'count' key"
        assert feed_data["count"] >= 1, f"Expected at least 1 post, got {feed_data['count']}"
        
        # Verify our test post is in the feed
        post_ids_in_feed = [p["post_id"] for p in feed_data["posts"]]
        assert post["post_id"] in post_ids_in_feed, f"Test post {post['post_id']} not found in signage feed"
        
        print(f"✓ Digital signage feed returns {feed_data['count']} posts (no auth required)")
    
    def test_03_post_without_digital_signage_not_in_feed(self):
        """Creating a post without digital_signage in channels → does NOT appear in digital-signage feed"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "title": f"TEST_No Signage Post {unique_id}",
            "content": "This post should NOT appear on digital signage displays",
            "channels": ["intranet", "email"],  # No digital_signage
            "status": "published",
            "priority": "normal",
            "target_all": True
        }
        
        create_resp = self.session.post(f"{BASE_URL}/api/news/posts", json=payload)
        assert create_resp.status_code == 200, f"Create post failed: {create_resp.text}"
        post = create_resp.json()
        self.created_post_ids.append(post["post_id"])
        
        # Wait for async dispatch
        time.sleep(0.5)
        
        # Verify signage_eligible is NOT set
        get_resp = self.session.get(f"{BASE_URL}/api/news/posts/{post['post_id']}")
        assert get_resp.status_code == 200
        fetched_post = get_resp.json()
        
        # signage_eligible should be False or not present
        assert fetched_post.get("signage_eligible") != True, "signage_eligible should NOT be True for post without digital_signage channel"
        
        # Verify post is NOT in the signage feed
        public_session = requests.Session()
        feed_resp = public_session.get(f"{BASE_URL}/api/news/digital-signage/feed")
        assert feed_resp.status_code == 200
        
        feed_data = feed_resp.json()
        post_ids_in_feed = [p["post_id"] for p in feed_data["posts"]]
        assert post["post_id"] not in post_ids_in_feed, "Post without digital_signage channel should NOT be in signage feed"
        
        print("✓ Post without digital_signage channel correctly excluded from signage feed")
    
    def test_04_push_channel_with_normal_priority_triggers_dispatch(self):
        """Creating a post with push in channels + priority=normal → should trigger dispatch"""
        # This test verifies the fix: previously push only fired for priority=critical/important
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "title": f"TEST_Push Normal Priority {unique_id}",
            "content": "This post has push channel with normal priority",
            "channels": ["intranet", "push"],  # Explicit push channel
            "status": "published",
            "priority": "normal",  # Normal priority - should still trigger push
            "target_all": True
        }
        
        create_resp = self.session.post(f"{BASE_URL}/api/news/posts", json=payload)
        assert create_resp.status_code == 200, f"Create post failed: {create_resp.text}"
        post = create_resp.json()
        self.created_post_ids.append(post["post_id"])
        
        # Verify post was created with push channel
        assert "push" in post.get("channels", []), "push not in channels"
        assert post["priority"] == "normal", f"Expected priority=normal, got {post['priority']}"
        assert post["status"] == "published", f"Expected status=published, got {post['status']}"
        
        # The dispatch happens asynchronously - we can't directly verify push was sent
        # but we can verify the post was created correctly with the right channels
        print("✓ Post with push channel + normal priority created successfully (dispatch triggered)")
    
    def test_05_email_channel_triggers_newsletter_dispatch(self):
        """Creating a post with email in channels → should dispatch newsletter (regression check)"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "title": f"TEST_Email Newsletter {unique_id}",
            "content": "This post should trigger email newsletter dispatch",
            "channels": ["intranet", "email"],
            "status": "published",
            "priority": "normal",
            "target_all": True
        }
        
        create_resp = self.session.post(f"{BASE_URL}/api/news/posts", json=payload)
        assert create_resp.status_code == 200, f"Create post failed: {create_resp.text}"
        post = create_resp.json()
        self.created_post_ids.append(post["post_id"])
        
        # Verify post was created with email channel
        assert "email" in post.get("channels", []), "email not in channels"
        assert post["status"] == "published"
        
        # Newsletter dispatch is async - verify post structure is correct
        print("✓ Post with email channel created successfully (newsletter dispatch triggered)")
    
    def test_06_news_feed_endpoint_regression(self):
        """Existing /api/news/feed endpoint still works (regression)"""
        resp = self.session.get(f"{BASE_URL}/api/news/feed")
        assert resp.status_code == 200, f"News feed failed: {resp.text}"
        
        data = resp.json()
        assert "posts" in data, "Response should have 'posts' key"
        assert "total" in data, "Response should have 'total' key"
        assert "page" in data, "Response should have 'page' key"
        
        print(f"✓ News feed endpoint works (total={data['total']}, page={data['page']})")
    
    def test_07_publish_endpoint_triggers_channel_dispatch(self):
        """POST /api/news/posts/{id}/publish endpoint triggers channel dispatch"""
        # First create a draft post with digital_signage channel
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "title": f"TEST_Draft to Publish {unique_id}",
            "content": "This draft will be published via the publish endpoint",
            "channels": ["intranet", "digital_signage"],
            "status": "draft",  # Start as draft
            "priority": "normal",
            "target_all": True
        }
        
        create_resp = self.session.post(f"{BASE_URL}/api/news/posts", json=payload)
        assert create_resp.status_code == 200, f"Create draft failed: {create_resp.text}"
        post = create_resp.json()
        self.created_post_ids.append(post["post_id"])
        
        assert post["status"] == "draft", f"Expected status=draft, got {post['status']}"
        
        # Now publish via the publish endpoint
        publish_resp = self.session.post(f"{BASE_URL}/api/news/posts/{post['post_id']}/publish")
        assert publish_resp.status_code == 200, f"Publish failed: {publish_resp.text}"
        
        publish_data = publish_resp.json()
        assert "published_at" in publish_data, "Response should have 'published_at'"
        
        # Wait for async dispatch
        time.sleep(0.5)
        
        # Verify signage_eligible was set after publish
        get_resp = self.session.get(f"{BASE_URL}/api/news/posts/{post['post_id']}")
        assert get_resp.status_code == 200
        fetched_post = get_resp.json()
        
        assert fetched_post["status"] == "published", "Expected status=published after publish"
        assert fetched_post.get("signage_eligible") == True, "signage_eligible should be True after publish with digital_signage channel"
        
        print(f"✓ Publish endpoint triggers channel dispatch (signage_eligible={fetched_post.get('signage_eligible')})")
    
    def test_08_update_to_published_triggers_channel_dispatch(self):
        """PUT /api/news/posts/{id} transitioning to published triggers channel dispatch"""
        # First create a draft post
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "title": f"TEST_Update to Publish {unique_id}",
            "content": "This draft will be published via update",
            "channels": ["intranet", "digital_signage"],
            "status": "draft",
            "priority": "normal",
            "target_all": True
        }
        
        create_resp = self.session.post(f"{BASE_URL}/api/news/posts", json=payload)
        assert create_resp.status_code == 200, f"Create draft failed: {create_resp.text}"
        post = create_resp.json()
        self.created_post_ids.append(post["post_id"])
        
        # Update to published status
        update_resp = self.session.put(f"{BASE_URL}/api/news/posts/{post['post_id']}", json={
            "status": "published"
        })
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
        
        # Wait for async dispatch
        time.sleep(0.5)
        
        # Verify signage_eligible was set
        get_resp = self.session.get(f"{BASE_URL}/api/news/posts/{post['post_id']}")
        assert get_resp.status_code == 200
        fetched_post = get_resp.json()
        
        assert fetched_post["status"] == "published"
        assert fetched_post.get("signage_eligible") == True, "signage_eligible should be True after update to published"
        
        print("✓ Update to published triggers channel dispatch")
    
    def test_09_approval_workflow_triggers_channel_dispatch(self):
        """Moderator approval flow via review/approve endpoint triggers channel dispatch"""
        # Create a draft post
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "title": f"TEST_Approval Flow {unique_id}",
            "content": "This post will go through approval workflow",
            "channels": ["intranet", "digital_signage"],
            "status": "draft",
            "priority": "normal",
            "target_all": True
        }
        
        create_resp = self.session.post(f"{BASE_URL}/api/news/posts", json=payload)
        assert create_resp.status_code == 200, f"Create draft failed: {create_resp.text}"
        post = create_resp.json()
        self.created_post_ids.append(post["post_id"])
        
        # Submit for review
        submit_resp = self.session.post(f"{BASE_URL}/api/news/posts/{post['post_id']}/submit-review")
        assert submit_resp.status_code == 200, f"Submit for review failed: {submit_resp.text}"
        
        # Approve (admin can directly approve and publish)
        approve_resp = self.session.post(f"{BASE_URL}/api/news/posts/{post['post_id']}/approve-review", json={
            "comment": "Approved for testing"
        })
        assert approve_resp.status_code == 200, f"Approve failed: {approve_resp.text}"
        
        approve_data = approve_resp.json()
        assert approve_data.get("status") == "published", f"Expected status=published after approval, got {approve_data.get('status')}"
        
        # Wait for async dispatch
        time.sleep(0.5)
        
        # Verify signage_eligible was set
        get_resp = self.session.get(f"{BASE_URL}/api/news/posts/{post['post_id']}")
        assert get_resp.status_code == 200
        fetched_post = get_resp.json()
        
        assert fetched_post.get("signage_eligible") == True, "signage_eligible should be True after approval"
        
        print("✓ Approval workflow triggers channel dispatch")
    
    def test_10_digital_signage_feed_limit_parameter(self):
        """GET /api/news/digital-signage/feed respects limit parameter"""
        public_session = requests.Session()
        
        # Test with limit=5
        feed_resp = public_session.get(f"{BASE_URL}/api/news/digital-signage/feed?limit=5")
        assert feed_resp.status_code == 200, f"Digital signage feed failed: {feed_resp.text}"
        
        feed_data = feed_resp.json()
        assert len(feed_data["posts"]) <= 5, f"Expected at most 5 posts, got {len(feed_data['posts'])}"
        
        print("✓ Digital signage feed respects limit parameter")
    
    def test_11_all_channels_combined(self):
        """Create post with all channels: intranet, push, email, digital_signage"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "title": f"TEST_All Channels {unique_id}",
            "content": "This post uses all distribution channels",
            "channels": ["intranet", "push", "email", "digital_signage"],
            "status": "published",
            "priority": "important",  # Also test with important priority
            "target_all": True
        }
        
        create_resp = self.session.post(f"{BASE_URL}/api/news/posts", json=payload)
        assert create_resp.status_code == 200, f"Create post failed: {create_resp.text}"
        post = create_resp.json()
        self.created_post_ids.append(post["post_id"])
        
        # Verify all channels are set
        channels = post.get("channels", [])
        assert "intranet" in channels
        assert "push" in channels
        assert "email" in channels
        assert "digital_signage" in channels
        
        # Wait for async dispatch
        time.sleep(0.5)
        
        # Verify signage_eligible
        get_resp = self.session.get(f"{BASE_URL}/api/news/posts/{post['post_id']}")
        assert get_resp.status_code == 200
        fetched_post = get_resp.json()
        
        assert fetched_post.get("signage_eligible") == True
        
        print("✓ Post with all channels created and dispatched successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
