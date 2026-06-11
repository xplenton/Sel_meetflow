"""
Test suite for News Module - Phase 1 News & zentrale Kommunikation
Tests: Categories CRUD, Posts CRUD, Feed filtering/sorting, Reactions, Comments, Read receipts, File upload
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestNewsModule:
    """News Module API Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login as admin and get session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        
        # Store cookies for authenticated requests
        self.cookies = login_resp.cookies
        self.session.cookies.update(self.cookies)
        
        # Get user info
        me_resp = self.session.get(f"{BASE_URL}/api/auth/me")
        assert me_resp.status_code == 200
        self.user = me_resp.json()
        
        yield
        
        # Cleanup: Delete test data created during tests
        self._cleanup_test_data()
    
    def _cleanup_test_data(self):
        """Clean up test-created data"""
        # Delete test posts
        try:
            feed_resp = self.session.get(f"{BASE_URL}/api/news/feed?limit=100")
            if feed_resp.status_code == 200:
                posts = feed_resp.json().get("posts", [])
                for post in posts:
                    if post.get("title", "").startswith("TEST_"):
                        self.session.delete(f"{BASE_URL}/api/news/posts/{post['post_id']}")
        except:
            pass
        
        # Delete test categories
        try:
            cats_resp = self.session.get(f"{BASE_URL}/api/news/categories")
            if cats_resp.status_code == 200:
                for cat in cats_resp.json():
                    if cat.get("name", "").startswith("TEST_"):
                        self.session.delete(f"{BASE_URL}/api/news/categories/{cat['category_id']}")
        except:
            pass

    # ============ CATEGORIES TESTS ============
    
    def test_01_list_categories(self):
        """GET /api/news/categories returns all categories"""
        resp = self.session.get(f"{BASE_URL}/api/news/categories")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Should return list of categories"
        print(f"✓ GET /api/news/categories - Found {len(data)} categories")
    
    def test_02_create_category(self):
        """POST /api/news/categories creates a category with name and color"""
        cat_name = f"TEST_Category_{uuid.uuid4().hex[:6]}"
        resp = self.session.post(f"{BASE_URL}/api/news/categories", json={
            "name": cat_name,
            "color": "#FF5733"
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("name") == cat_name, "Category name should match"
        assert data.get("color") == "#FF5733", "Category color should match"
        assert "category_id" in data, "Should have category_id"
        self.test_category_id = data["category_id"]
        print(f"✓ POST /api/news/categories - Created category: {cat_name}")
        return data
    
    def test_03_delete_category(self):
        """DELETE /api/news/categories/{cat_id} deletes a category"""
        # First create a category to delete
        cat = self.test_02_create_category()
        cat_id = cat["category_id"]
        
        resp = self.session.delete(f"{BASE_URL}/api/news/categories/{cat_id}")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        print(f"✓ DELETE /api/news/categories/{cat_id} - Category deleted")

    # ============ NEWS POSTS TESTS ============
    
    def test_04_create_news_post_draft(self):
        """POST /api/news/posts creates a news post as draft"""
        title = f"TEST_News_{uuid.uuid4().hex[:6]}"
        resp = self.session.post(f"{BASE_URL}/api/news/posts", json={
            "title": title,
            "content": "This is test content for the news post.",
            "priority": "normal",
            "status": "draft",
            "target_all": True
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("title") == title, "Title should match"
        assert data.get("status") == "draft", "Status should be draft"
        assert data.get("priority") == "normal", "Priority should be normal"
        assert "post_id" in data, "Should have post_id"
        print(f"✓ POST /api/news/posts - Created draft: {title}")
        return data
    
    def test_05_create_news_post_published(self):
        """POST /api/news/posts creates a published news post"""
        title = f"TEST_Published_{uuid.uuid4().hex[:6]}"
        resp = self.session.post(f"{BASE_URL}/api/news/posts", json={
            "title": title,
            "content": "Published news content.",
            "priority": "important",
            "status": "published",
            "pinned": True,
            "is_mandatory": True,
            "target_all": True,
            "tags": ["test", "important"]
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("title") == title
        assert data.get("status") == "published"
        assert data.get("priority") == "important"
        assert data.get("pinned") == True
        assert data.get("is_mandatory") == True
        assert "published_at" in data and data["published_at"], "Should have published_at"
        print(f"✓ POST /api/news/posts - Created published post: {title}")
        return data
    
    def test_06_get_news_feed(self):
        """GET /api/news/feed returns published posts"""
        # First create a published post
        post = self.test_05_create_news_post_published()
        
        resp = self.session.get(f"{BASE_URL}/api/news/feed")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "posts" in data, "Should have posts array"
        assert "total" in data, "Should have total count"
        assert "page" in data, "Should have page number"
        assert "pages" in data, "Should have pages count"
        
        # Verify our post is in the feed
        post_ids = [p["post_id"] for p in data["posts"]]
        assert post["post_id"] in post_ids, "Created post should be in feed"
        print(f"✓ GET /api/news/feed - Found {len(data['posts'])} posts, total: {data['total']}")
    
    def test_07_get_news_feed_search(self):
        """GET /api/news/feed?search=xxx filters posts by search term"""
        # Create a post with unique content
        unique_term = f"UNIQUESEARCH{uuid.uuid4().hex[:6]}"
        post = self.session.post(f"{BASE_URL}/api/news/posts", json={
            "title": f"TEST_{unique_term}",
            "content": f"Content with {unique_term} term",
            "status": "published",
            "target_all": True
        }).json()
        
        resp = self.session.get(f"{BASE_URL}/api/news/feed?search={unique_term}")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert len(data["posts"]) >= 1, "Should find at least 1 post"
        found = any(unique_term in p.get("title", "") or unique_term in p.get("content", "") for p in data["posts"])
        assert found, "Search should find the post with unique term"
        print(f"✓ GET /api/news/feed?search={unique_term} - Found {len(data['posts'])} matching posts")
    
    def test_08_get_news_feed_priority_filter(self):
        """GET /api/news/feed?priority=critical filters by priority"""
        # Create a critical post
        post = self.session.post(f"{BASE_URL}/api/news/posts", json={
            "title": f"TEST_Critical_{uuid.uuid4().hex[:6]}",
            "content": "Critical news content",
            "priority": "critical",
            "status": "published",
            "target_all": True
        }).json()
        
        resp = self.session.get(f"{BASE_URL}/api/news/feed?priority=critical")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        # All returned posts should be critical
        for p in data["posts"]:
            assert p.get("priority") == "critical", f"Post {p['post_id']} should be critical"
        print(f"✓ GET /api/news/feed?priority=critical - Found {len(data['posts'])} critical posts")
    
    def test_09_get_news_feed_sort_relevance(self):
        """GET /api/news/feed?sort=relevance sorts by mandatory+priority+date"""
        resp = self.session.get(f"{BASE_URL}/api/news/feed?sort=relevance")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "posts" in data
        print(f"✓ GET /api/news/feed?sort=relevance - Returned {len(data['posts'])} posts sorted by relevance")
    
    def test_10_get_single_post(self):
        """GET /api/news/posts/{post_id} returns single post with reaction counts and read status"""
        # Create a post first
        post = self.test_05_create_news_post_published()
        post_id = post["post_id"]
        
        resp = self.session.get(f"{BASE_URL}/api/news/posts/{post_id}")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("post_id") == post_id
        assert "reaction_counts" in data, "Should have reaction_counts"
        assert "is_read" in data, "Should have is_read status"
        assert "comment_count" in data, "Should have comment_count"
        print(f"✓ GET /api/news/posts/{post_id} - Got post with reaction_counts and read status")
    
    def test_11_update_news_post(self):
        """PUT /api/news/posts/{post_id} updates a post"""
        # Create a post first
        post = self.test_04_create_news_post_draft()
        post_id = post["post_id"]
        
        new_title = f"TEST_Updated_{uuid.uuid4().hex[:6]}"
        resp = self.session.put(f"{BASE_URL}/api/news/posts/{post_id}", json={
            "title": new_title,
            "priority": "important",
            "pinned": True
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("title") == new_title, "Title should be updated"
        assert data.get("priority") == "important", "Priority should be updated"
        assert data.get("pinned") == True, "Pinned should be updated"
        print(f"✓ PUT /api/news/posts/{post_id} - Post updated successfully")
    
    def test_12_publish_news_post(self):
        """POST /api/news/posts/{post_id}/publish changes status to published"""
        # Create a draft post
        post = self.test_04_create_news_post_draft()
        post_id = post["post_id"]
        assert post.get("status") == "draft"
        
        resp = self.session.post(f"{BASE_URL}/api/news/posts/{post_id}/publish")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "published_at" in data, "Should have published_at"
        
        # Verify status changed
        get_resp = self.session.get(f"{BASE_URL}/api/news/posts/{post_id}")
        assert get_resp.json().get("status") == "published"
        print(f"✓ POST /api/news/posts/{post_id}/publish - Post published")
    
    def test_13_archive_news_post(self):
        """POST /api/news/posts/{post_id}/archive changes status to archived"""
        # Create and publish a post
        post = self.test_05_create_news_post_published()
        post_id = post["post_id"]
        
        resp = self.session.post(f"{BASE_URL}/api/news/posts/{post_id}/archive")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        
        # Verify status changed
        get_resp = self.session.get(f"{BASE_URL}/api/news/posts/{post_id}")
        assert get_resp.json().get("status") == "archived"
        print(f"✓ POST /api/news/posts/{post_id}/archive - Post archived")

    # ============ READ RECEIPTS TESTS ============
    
    def test_14_mark_post_as_read(self):
        """POST /api/news/posts/{post_id}/read marks post as read"""
        post = self.test_05_create_news_post_published()
        post_id = post["post_id"]
        
        resp = self.session.post(f"{BASE_URL}/api/news/posts/{post_id}/read")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        
        # Verify read status
        get_resp = self.session.get(f"{BASE_URL}/api/news/posts/{post_id}")
        assert get_resp.json().get("is_read") == True, "Post should be marked as read"
        print(f"✓ POST /api/news/posts/{post_id}/read - Post marked as read")
    
    def test_15_get_read_receipts(self):
        """GET /api/news/posts/{post_id}/reads returns read receipts with count"""
        post = self.test_05_create_news_post_published()
        post_id = post["post_id"]
        
        # Mark as read first
        self.session.post(f"{BASE_URL}/api/news/posts/{post_id}/read")
        
        resp = self.session.get(f"{BASE_URL}/api/news/posts/{post_id}/reads")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "reads" in data, "Should have reads array"
        assert "read_count" in data, "Should have read_count"
        assert "total_target" in data, "Should have total_target"
        assert data["read_count"] >= 1, "Should have at least 1 read"
        print(f"✓ GET /api/news/posts/{post_id}/reads - {data['read_count']} reads out of {data['total_target']} target")

    # ============ REACTIONS TESTS ============
    
    def test_16_toggle_reaction_add(self):
        """POST /api/news/posts/{post_id}/reactions adds a reaction"""
        post = self.test_05_create_news_post_published()
        post_id = post["post_id"]
        
        resp = self.session.post(f"{BASE_URL}/api/news/posts/{post_id}/reactions", json={
            "reaction_type": "like"
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("action") == "added", "Should add reaction"
        assert data.get("reaction_type") == "like"
        
        # Verify reaction in post
        get_resp = self.session.get(f"{BASE_URL}/api/news/posts/{post_id}")
        post_data = get_resp.json()
        assert post_data.get("user_reaction") == "like", "User reaction should be like"
        assert post_data.get("reaction_counts", {}).get("like", 0) >= 1
        print(f"✓ POST /api/news/posts/{post_id}/reactions - Added 'like' reaction")
    
    def test_17_toggle_reaction_change(self):
        """POST /api/news/posts/{post_id}/reactions changes reaction type"""
        post = self.test_05_create_news_post_published()
        post_id = post["post_id"]
        
        # Add like first
        self.session.post(f"{BASE_URL}/api/news/posts/{post_id}/reactions", json={"reaction_type": "like"})
        
        # Change to agree
        resp = self.session.post(f"{BASE_URL}/api/news/posts/{post_id}/reactions", json={
            "reaction_type": "agree"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("action") == "changed", "Should change reaction"
        assert data.get("reaction_type") == "agree"
        print(f"✓ POST /api/news/posts/{post_id}/reactions - Changed reaction to 'agree'")
    
    def test_18_toggle_reaction_remove(self):
        """POST /api/news/posts/{post_id}/reactions removes reaction when same type"""
        post = self.test_05_create_news_post_published()
        post_id = post["post_id"]
        
        # Add like
        self.session.post(f"{BASE_URL}/api/news/posts/{post_id}/reactions", json={"reaction_type": "like"})
        
        # Toggle same reaction to remove
        resp = self.session.post(f"{BASE_URL}/api/news/posts/{post_id}/reactions", json={
            "reaction_type": "like"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("action") == "removed", "Should remove reaction"
        print(f"✓ POST /api/news/posts/{post_id}/reactions - Removed 'like' reaction")

    # ============ COMMENTS TESTS ============
    
    def test_19_add_comment(self):
        """POST /api/news/posts/{post_id}/comments adds a comment"""
        post = self.test_05_create_news_post_published()
        post_id = post["post_id"]
        
        comment_text = f"TEST_Comment_{uuid.uuid4().hex[:6]}"
        resp = self.session.post(f"{BASE_URL}/api/news/posts/{post_id}/comments", json={
            "content": comment_text
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("content") == comment_text
        assert "comment_id" in data
        assert data.get("user_id") == self.user["user_id"]
        print(f"✓ POST /api/news/posts/{post_id}/comments - Added comment")
        return data
    
    def test_20_get_comments(self):
        """GET /api/news/posts/{post_id}/comments returns comments"""
        post = self.test_05_create_news_post_published()
        post_id = post["post_id"]
        
        # Add a comment first
        comment_text = f"TEST_Comment_{uuid.uuid4().hex[:6]}"
        self.session.post(f"{BASE_URL}/api/news/posts/{post_id}/comments", json={"content": comment_text})
        
        resp = self.session.get(f"{BASE_URL}/api/news/posts/{post_id}/comments")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Should return list of comments"
        assert len(data) >= 1, "Should have at least 1 comment"
        print(f"✓ GET /api/news/posts/{post_id}/comments - Found {len(data)} comments")
    
    def test_21_delete_comment(self):
        """DELETE /api/news/comments/{comment_id} soft-deletes a comment"""
        post = self.test_05_create_news_post_published()
        post_id = post["post_id"]
        
        # Add a comment
        comment = self.session.post(f"{BASE_URL}/api/news/posts/{post_id}/comments", json={
            "content": f"TEST_ToDelete_{uuid.uuid4().hex[:6]}"
        }).json()
        comment_id = comment["comment_id"]
        
        resp = self.session.delete(f"{BASE_URL}/api/news/comments/{comment_id}")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        
        # Verify comment is soft-deleted (not in list)
        comments_resp = self.session.get(f"{BASE_URL}/api/news/posts/{post_id}/comments")
        comment_ids = [c["comment_id"] for c in comments_resp.json()]
        assert comment_id not in comment_ids, "Deleted comment should not appear in list"
        print(f"✓ DELETE /api/news/comments/{comment_id} - Comment soft-deleted")

    # ============ UNREAD COUNT TEST ============
    
    def test_22_get_unread_count(self):
        """GET /api/news/unread-count returns unread and mandatory_unread counts"""
        resp = self.session.get(f"{BASE_URL}/api/news/unread-count")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "unread" in data, "Should have unread count"
        assert "total" in data, "Should have total count"
        assert "mandatory_unread" in data, "Should have mandatory_unread count"
        print(f"✓ GET /api/news/unread-count - Unread: {data['unread']}, Mandatory unread: {data['mandatory_unread']}")

    # ============ STATS TEST ============
    
    def test_23_get_news_stats(self):
        """GET /api/news/stats returns news statistics (admin only)"""
        resp = self.session.get(f"{BASE_URL}/api/news/stats")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "total" in data
        assert "published" in data
        assert "drafts" in data
        assert "archived" in data
        assert "mandatory" in data
        print(f"✓ GET /api/news/stats - Total: {data['total']}, Published: {data['published']}, Drafts: {data['drafts']}")

    # ============ FILE UPLOAD TEST ============
    
    def test_24_upload_file(self):
        """POST /api/news/upload uploads a file and returns URL"""
        # Create a simple test file
        files = {
            'file': ('test_file.txt', b'Test file content for news upload', 'text/plain')
        }
        
        # Remove Content-Type header for multipart upload
        headers = dict(self.session.headers)
        headers.pop('Content-Type', None)
        
        resp = requests.post(
            f"{BASE_URL}/api/news/upload",
            files=files,
            cookies=self.cookies
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "url" in data, "Should have url"
        assert "filename" in data, "Should have filename"
        assert "file_id" in data, "Should have file_id"
        assert data["url"].startswith("/api/news/files/"), "URL should be correct format"
        print(f"✓ POST /api/news/upload - File uploaded: {data['url']}")
        return data

    # ============ ERROR HANDLING TESTS ============
    
    def test_25_get_nonexistent_post(self):
        """GET /api/news/posts/{invalid_id} returns 404"""
        resp = self.session.get(f"{BASE_URL}/api/news/posts/nonexistent_post_id")
        assert resp.status_code == 404, f"Should return 404, got {resp.status_code}"
        print("✓ GET /api/news/posts/nonexistent - Returns 404")
    
    def test_26_create_post_without_title(self):
        """POST /api/news/posts without title returns 400"""
        resp = self.session.post(f"{BASE_URL}/api/news/posts", json={
            "content": "Content without title"
        })
        assert resp.status_code == 400, f"Should return 400, got {resp.status_code}"
        print("✓ POST /api/news/posts without title - Returns 400")
    
    def test_27_create_category_without_name(self):
        """POST /api/news/categories without name returns 400"""
        resp = self.session.post(f"{BASE_URL}/api/news/categories", json={
            "color": "#FF0000"
        })
        assert resp.status_code == 400, f"Should return 400, got {resp.status_code}"
        print("✓ POST /api/news/categories without name - Returns 400")


class TestNewsModuleUnauthenticated:
    """Test unauthenticated access to news endpoints"""
    
    def test_unauthenticated_feed_access(self):
        """GET /api/news/feed without auth returns 401"""
        resp = requests.get(f"{BASE_URL}/api/news/feed")
        assert resp.status_code == 401, f"Should return 401, got {resp.status_code}"
        print("✓ GET /api/news/feed unauthenticated - Returns 401")
    
    def test_unauthenticated_categories_access(self):
        """GET /api/news/categories without auth returns 401"""
        resp = requests.get(f"{BASE_URL}/api/news/categories")
        assert resp.status_code == 401, f"Should return 401, got {resp.status_code}"
        print("✓ GET /api/news/categories unauthenticated - Returns 401")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
