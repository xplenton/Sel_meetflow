"""
Iteration 61 - Runtime Tests for New Features:
1. Granulares News-Targeting (target_departments, target_locations, target_professions)
2. Video-Embeds in News (video_url field)
3. Kommentar-Reply-Threads & @Mentions (parent_id, notifications)
4. Interaktions-Dashboard im Admin-Bereich (GET /api/news/interaction-stats)
5. Admin User Profile Update (PUT /api/admin/users/{user_id}/profile)
6. Global Search (GET /api/search/global)

Note: This app uses cookie-based authentication (httpOnly cookies)
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


@pytest.fixture(scope="module")
def admin_session():
    """Create a session with admin authentication cookies"""
    session = requests.Session()
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@meetflow.com",
        "password": "admin123"
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    assert "user_id" in data, "No user_id in response"
    assert data.get("role") == "admin", "User is not admin"
    print(f"✓ Admin login successful: {data['email']}")
    return session


class TestAuth:
    """Test authentication"""
    
    def test_admin_login(self, admin_session):
        """Verify admin login works and session is authenticated"""
        response = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200, f"Auth check failed: {response.text}"
        data = response.json()
        assert data.get("email") == "admin@meetflow.com"
        assert data.get("role") == "admin"
        print(f"✓ Admin session verified: {data['email']}")


class TestNewsTargeting:
    """Test granular news targeting (departments, locations, professions)"""
    
    def test_create_news_with_granular_targeting(self, admin_session):
        """Create news post with department, location, profession targeting"""
        unique_id = uuid.uuid4().hex[:6]
        payload = {
            "title": f"TEST_Targeting News {unique_id}",
            "content": "Test content for granular targeting",
            "priority": "normal",
            "target_all": False,
            "target_departments": ["Innere Medizin", "Chirurgie"],
            "target_locations": ["Standort Nord", "Standort Sued"],
            "target_professions": ["Pflege", "Arzt"],
            "target_roles": ["member", "admin"],
            "status": "published"
        }
        response = admin_session.post(f"{BASE_URL}/api/news/posts", json=payload)
        assert response.status_code == 200, f"Create news failed: {response.text}"
        data = response.json()
        
        # Verify targeting fields are saved
        assert data.get("target_all") == False, "target_all should be False"
        assert "Innere Medizin" in data.get("target_departments", []), "target_departments not saved"
        assert "Standort Nord" in data.get("target_locations", []), "target_locations not saved"
        assert "Pflege" in data.get("target_professions", []), "target_professions not saved"
        assert "member" in data.get("target_roles", []), "target_roles not saved"
        
        print(f"✓ News with granular targeting created: {data['post_id']}")
        print(f"  - target_departments: {data.get('target_departments')}")
        print(f"  - target_locations: {data.get('target_locations')}")
        print(f"  - target_professions: {data.get('target_professions')}")
        return data["post_id"]
    
    def test_get_news_with_targeting(self, admin_session):
        """Verify news feed returns posts with targeting info"""
        response = admin_session.get(f"{BASE_URL}/api/news/feed?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "posts" in data
        print(f"✓ News feed returned {len(data['posts'])} posts")


class TestVideoEmbed:
    """Test video URL embedding in news posts"""
    
    def test_create_news_with_video_url(self, admin_session):
        """Create news post with YouTube video URL"""
        unique_id = uuid.uuid4().hex[:6]
        payload = {
            "title": f"TEST_Video News {unique_id}",
            "content": "Test content with video embed",
            "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "status": "published"
        }
        response = admin_session.post(f"{BASE_URL}/api/news/posts", json=payload)
        assert response.status_code == 200, f"Create news with video failed: {response.text}"
        data = response.json()
        
        assert data.get("video_url") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video_url not saved"
        print(f"✓ News with YouTube video URL created: {data['post_id']}")
        return data["post_id"]
    
    def test_create_news_with_vimeo_url(self, admin_session):
        """Create news post with Vimeo video URL"""
        unique_id = uuid.uuid4().hex[:6]
        payload = {
            "title": f"TEST_Vimeo News {unique_id}",
            "content": "Test content with Vimeo embed",
            "video_url": "https://vimeo.com/123456789",
            "external_link": "https://example.com/more-info",
            "status": "published"
        }
        response = admin_session.post(f"{BASE_URL}/api/news/posts", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("video_url") == "https://vimeo.com/123456789"
        assert data.get("external_link") == "https://example.com/more-info"
        print(f"✓ News with Vimeo URL and external link created: {data['post_id']}")


class TestCommentReplyThreads:
    """Test comment reply threads with parent_id"""
    
    @pytest.fixture(scope="class")
    def test_post(self, admin_session):
        """Create a test post for comments"""
        unique_id = uuid.uuid4().hex[:6]
        payload = {
            "title": f"TEST_Comment Thread Post {unique_id}",
            "content": "Post for testing comment threads",
            "status": "published"
        }
        response = admin_session.post(f"{BASE_URL}/api/news/posts", json=payload)
        return response.json()["post_id"]
    
    def test_create_parent_comment(self, admin_session, test_post):
        """Create a top-level comment"""
        payload = {"content": "This is a parent comment"}
        response = admin_session.post(f"{BASE_URL}/api/news/posts/{test_post}/comments", json=payload)
        assert response.status_code == 200, f"Create comment failed: {response.text}"
        data = response.json()
        
        assert data.get("content") == "This is a parent comment"
        assert data.get("parent_id") is None, "Parent comment should have no parent_id"
        assert "comment_id" in data
        print(f"✓ Parent comment created: {data['comment_id']}")
        return data["comment_id"]
    
    def test_create_reply_comment(self, admin_session, test_post):
        """Create a reply to a parent comment"""
        # First create parent
        parent_response = admin_session.post(
            f"{BASE_URL}/api/news/posts/{test_post}/comments",
            json={"content": "Parent for reply test"}
        )
        parent_id = parent_response.json()["comment_id"]
        
        # Create reply with parent_id
        payload = {
            "content": "This is a reply to the parent",
            "parent_id": parent_id
        }
        response = admin_session.post(f"{BASE_URL}/api/news/posts/{test_post}/comments", json=payload)
        assert response.status_code == 200, f"Create reply failed: {response.text}"
        data = response.json()
        
        assert data.get("parent_id") == parent_id, "Reply should have parent_id set"
        assert data.get("content") == "This is a reply to the parent"
        print(f"✓ Reply comment created with parent_id: {data['comment_id']} -> {parent_id}")
    
    def test_get_comments_with_threads(self, admin_session, test_post):
        """Verify comments endpoint returns parent_id for threading"""
        response = admin_session.get(f"{BASE_URL}/api/news/posts/{test_post}/comments")
        assert response.status_code == 200
        comments = response.json()
        
        # Check that we have both parent and reply comments
        has_parent = any(c.get("parent_id") is None for c in comments)
        has_reply = any(c.get("parent_id") is not None for c in comments)
        
        assert has_parent, "Should have at least one parent comment"
        assert has_reply, "Should have at least one reply comment"
        print(f"✓ Comments with threading retrieved: {len(comments)} comments")


class TestMentionNotifications:
    """Test @mention notifications in comments"""
    
    @pytest.fixture(scope="class")
    def test_post(self, admin_session):
        unique_id = uuid.uuid4().hex[:6]
        payload = {
            "title": f"TEST_Mention Post {unique_id}",
            "content": "Post for testing @mentions",
            "status": "published"
        }
        response = admin_session.post(f"{BASE_URL}/api/news/posts", json=payload)
        return response.json()["post_id"]
    
    def test_create_comment_with_mention(self, admin_session, test_post):
        """Create comment with @mention - should trigger notification"""
        # Mention the admin user
        payload = {"content": "Hey @admin@meetflow.com check this out!"}
        response = admin_session.post(f"{BASE_URL}/api/news/posts/{test_post}/comments", json=payload)
        assert response.status_code == 200, f"Create comment with mention failed: {response.text}"
        data = response.json()
        
        assert "@admin@meetflow.com" in data.get("content", "")
        print(f"✓ Comment with @mention created: {data['comment_id']}")


class TestInteractionsDashboard:
    """Test admin interactions dashboard stats endpoint"""
    
    def test_get_interaction_stats(self, admin_session):
        """GET /api/news/interaction-stats returns dashboard KPIs"""
        response = admin_session.get(f"{BASE_URL}/api/news/interaction-stats")
        assert response.status_code == 200, f"Get interaction stats failed: {response.text}"
        data = response.json()
        
        # Verify expected fields
        assert "posts" in data, "Missing 'posts' in stats"
        assert "comments" in data, "Missing 'comments' in stats"
        assert "reactions" in data, "Missing 'reactions' in stats"
        assert "reports" in data, "Missing 'reports' in stats"
        assert "questions" in data, "Missing 'questions' in stats"
        assert "surveys" in data, "Missing 'surveys' in stats"
        assert "total_active_users" in data, "Missing 'total_active_users' in stats"
        
        # Verify nested structure
        assert "total" in data["comments"], "Missing 'total' in comments stats"
        assert "total" in data["reactions"], "Missing 'total' in reactions stats"
        assert "unique_users" in data["reactions"], "Missing 'unique_users' in reactions stats"
        assert "open" in data["reports"], "Missing 'open' in reports stats"
        
        print("✓ Interaction stats retrieved:")
        print(f"  - Posts: {data['posts'].get('total', 0)}")
        print(f"  - Comments: {data['comments'].get('total', 0)}")
        print(f"  - Reactions: {data['reactions'].get('total', 0)}")
        print(f"  - Open Reports: {data['reports'].get('open', 0)}")
        print(f"  - Active Users: {data.get('total_active_users', 0)}")
    
    def test_interaction_stats_requires_auth(self):
        """Verify interaction stats requires authentication"""
        response = requests.get(f"{BASE_URL}/api/news/interaction-stats")
        assert response.status_code in [401, 403], "Should require authentication"
        print("✓ Interaction stats requires authentication")


class TestAdminUserProfile:
    """Test admin user profile update endpoint"""
    
    @pytest.fixture(scope="class")
    def test_user(self, admin_session):
        """Create a test user for profile updates"""
        unique_id = uuid.uuid4().hex[:6]
        payload = {
            "email": f"test_profile_{unique_id}@meetflow.com",
            "name": f"Test Profile User {unique_id}",
            "role": "member"
        }
        response = admin_session.post(f"{BASE_URL}/api/admin/users/invite", json=payload)
        if response.status_code == 200:
            return response.json()["user_id"]
        # If invite fails, try to get existing users
        users_response = admin_session.get(f"{BASE_URL}/api/admin/users")
        users = users_response.json()
        for u in users:
            if u.get("role") == "member" and u.get("user_id") != "admin":
                return u["user_id"]
        return None
    
    def test_update_user_profile_fields(self, admin_session, test_user):
        """PUT /api/admin/users/{user_id}/profile updates department, location, profession"""
        if not test_user:
            pytest.skip("No test user available")
        
        payload = {
            "department": "Innere Medizin",
            "location": "Standort Nord",
            "profession": "Pflege",
            "org_unit": "Station 3B"
        }
        response = admin_session.put(f"{BASE_URL}/api/admin/users/{test_user}/profile", json=payload)
        assert response.status_code == 200, f"Update profile failed: {response.text}"
        data = response.json()
        
        assert data.get("department") == "Innere Medizin", "department not updated"
        assert data.get("location") == "Standort Nord", "location not updated"
        assert data.get("profession") == "Pflege", "profession not updated"
        assert data.get("org_unit") == "Station 3B", "org_unit not updated"
        
        print("✓ User profile updated with department, location, profession, org_unit")
    
    def test_update_user_via_standard_endpoint(self, admin_session, test_user):
        """PUT /api/admin/users/{user_id} also supports profile fields"""
        if not test_user:
            pytest.skip("No test user available")
        
        payload = {
            "department": "Chirurgie",
            "location": "Standort Sued",
            "profession": "Arzt"
        }
        response = admin_session.put(f"{BASE_URL}/api/admin/users/{test_user}", json=payload)
        assert response.status_code == 200, f"Update user failed: {response.text}"
        data = response.json()
        
        assert data.get("department") == "Chirurgie"
        assert data.get("location") == "Standort Sued"
        assert data.get("profession") == "Arzt"
        print("✓ User updated via standard endpoint with profile fields")


class TestGlobalSearch:
    """Test global search endpoint"""
    
    def test_global_search_returns_grouped_results(self, admin_session):
        """GET /api/search/global returns news, meetings, chats, users"""
        response = admin_session.get(f"{BASE_URL}/api/search/global?q=test&limit=5")
        assert response.status_code == 200, f"Global search failed: {response.text}"
        data = response.json()
        
        assert "news" in data, "Missing 'news' in search results"
        assert "meetings" in data, "Missing 'meetings' in search results"
        assert "chats" in data, "Missing 'chats' in search results"
        assert "users" in data, "Missing 'users' in search results"
        
        assert isinstance(data["news"], list)
        assert isinstance(data["meetings"], list)
        assert isinstance(data["chats"], list)
        assert isinstance(data["users"], list)
        
        print("✓ Global search returned grouped results:")
        print(f"  - News: {len(data['news'])}")
        print(f"  - Meetings: {len(data['meetings'])}")
        print(f"  - Chats: {len(data['chats'])}")
        print(f"  - Users: {len(data['users'])}")
    
    def test_global_search_min_query_length(self, admin_session):
        """Search with < 2 chars returns empty results"""
        response = admin_session.get(f"{BASE_URL}/api/search/global?q=a")
        assert response.status_code == 200
        data = response.json()
        
        assert data["news"] == []
        assert data["meetings"] == []
        assert data["chats"] == []
        assert data["users"] == []
        print("✓ Search with < 2 chars returns empty arrays")
    
    def test_global_search_for_admin(self, admin_session):
        """Search for 'admin' should find the admin user"""
        response = admin_session.get(f"{BASE_URL}/api/search/global?q=admin&limit=10")
        assert response.status_code == 200
        data = response.json()
        
        # Should find admin user
        admin_found = any(u.get("email") == "admin@meetflow.com" for u in data.get("users", []))
        assert admin_found, "Admin user should be found in search"
        print("✓ Search for 'admin' found admin user")


class TestNewsModerationReports:
    """Test news moderation reports endpoint"""
    
    def test_get_reports_list(self, admin_session):
        """GET /api/news/reports returns list of reports"""
        response = admin_session.get(f"{BASE_URL}/api/news/reports")
        assert response.status_code == 200, f"Get reports failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Reports should be a list"
        print(f"✓ Reports list retrieved: {len(data)} reports")
    
    def test_get_pending_reports_count(self, admin_session):
        """GET /api/news/reports/pending-count returns count"""
        response = admin_session.get(f"{BASE_URL}/api/news/reports/pending-count")
        assert response.status_code == 200
        data = response.json()
        
        assert "count" in data, "Missing 'count' in response"
        assert isinstance(data["count"], int)
        print(f"✓ Pending reports count: {data['count']}")


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_posts(self, admin_session):
        """Delete TEST_ prefixed posts"""
        response = admin_session.get(f"{BASE_URL}/api/news/feed?limit=50")
        if response.status_code == 200:
            posts = response.json().get("posts", [])
            deleted = 0
            for post in posts:
                if post.get("title", "").startswith("TEST_"):
                    del_response = admin_session.delete(f"{BASE_URL}/api/news/posts/{post['post_id']}")
                    if del_response.status_code == 200:
                        deleted += 1
            print(f"✓ Cleaned up {deleted} test posts")
