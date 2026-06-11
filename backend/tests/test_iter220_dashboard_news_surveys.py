"""
Iteration 220 - Comprehensive tests for Dashboard, News, and Surveys modules
Testing with Admin and Member roles across all endpoints
"""
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"
MEMBER_EMAIL = "member@meetflow.com"
MEMBER_PASSWORD = "11db7dbd77"


class TestAuth:
    """Authentication tests"""
    
    def test_admin_login(self):
        """Test admin login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        assert data.get("user", {}).get("role") == "admin", "User is not admin"
        print(f"✓ Admin login successful - user_id: {data.get('user', {}).get('user_id')}")
        return data["token"]
    
    def test_member_login(self):
        """Test member login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MEMBER_EMAIL,
            "password": MEMBER_PASSWORD
        })
        assert response.status_code == 200, f"Member login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        print(f"✓ Member login successful - user_id: {data.get('user', {}).get('user_id')}")
        return data["token"]


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.text}")
    return response.json()["token"]


@pytest.fixture(scope="module")
def member_token():
    """Get member auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MEMBER_EMAIL,
        "password": MEMBER_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Member login failed: {response.text}")
    return response.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def member_headers(member_token):
    return {"Authorization": f"Bearer {member_token}", "Content-Type": "application/json"}


# ============ DASHBOARD TESTS ============

class TestDashboardAdmin:
    """Dashboard tests for Admin role"""
    
    def test_dashboard_stats(self, admin_headers):
        """Test GET /api/dashboard/stats"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=admin_headers)
        assert response.status_code == 200, f"Dashboard stats failed: {response.text}"
        data = response.json()
        # Verify expected fields
        expected_fields = ["total_meetings", "active_meetings", "upcoming_meetings", "ended_meetings"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        print(f"✓ Dashboard stats: {data.get('total_meetings')} total, {data.get('active_meetings')} active, {data.get('upcoming_meetings')} upcoming")
    
    def test_dashboard_agenda(self, admin_headers):
        """Test GET /api/dashboard/agenda"""
        response = requests.get(f"{BASE_URL}/api/dashboard/agenda", headers=admin_headers)
        assert response.status_code == 200, f"Dashboard agenda failed: {response.text}"
        data = response.json()
        assert "today" in data, "Missing 'today' in agenda"
        assert "week_days" in data, "Missing 'week_days' in agenda"
        assert "recent" in data, "Missing 'recent' in agenda"
        print(f"✓ Dashboard agenda: {data.get('meetings_today', 0)} meetings today, {len(data.get('recent', []))} recent activities")


class TestDashboardMember:
    """Dashboard tests for Member role"""
    
    def test_dashboard_stats_member(self, member_headers):
        """Test GET /api/dashboard/stats for member"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=member_headers)
        assert response.status_code == 200, f"Dashboard stats failed for member: {response.text}"
        data = response.json()
        print(f"✓ Member dashboard stats: {data.get('total_meetings')} total meetings")
    
    def test_dashboard_agenda_member(self, member_headers):
        """Test GET /api/dashboard/agenda for member"""
        response = requests.get(f"{BASE_URL}/api/dashboard/agenda", headers=member_headers)
        assert response.status_code == 200, f"Dashboard agenda failed for member: {response.text}"
        data = response.json()
        print(f"✓ Member dashboard agenda: {data.get('meetings_today', 0)} meetings today")


# ============ NEWS TESTS ============

class TestNewsAdmin:
    """News tests for Admin role"""
    
    def test_news_feed(self, admin_headers):
        """Test GET /api/news/feed"""
        response = requests.get(f"{BASE_URL}/api/news/feed", headers=admin_headers)
        assert response.status_code == 200, f"News feed failed: {response.text}"
        data = response.json()
        assert "posts" in data, "Missing 'posts' in response"
        print(f"✓ News feed: {len(data.get('posts', []))} posts, {data.get('pages', 1)} pages")
    
    def test_news_categories(self, admin_headers):
        """Test GET /api/news/categories"""
        response = requests.get(f"{BASE_URL}/api/news/categories", headers=admin_headers)
        assert response.status_code == 200, f"News categories failed: {response.text}"
        data = response.json()
        print(f"✓ News categories: {len(data)} categories")
    
    def test_news_unread_count(self, admin_headers):
        """Test GET /api/news/unread-count"""
        response = requests.get(f"{BASE_URL}/api/news/unread-count", headers=admin_headers)
        assert response.status_code == 200, f"News unread count failed: {response.text}"
        data = response.json()
        assert "unread" in data, "Missing 'unread' in response"
        assert "total" in data, "Missing 'total' in response"
        print(f"✓ News unread count: {data.get('unread')} unread of {data.get('total')} total, {data.get('mandatory_unread', 0)} mandatory")
    
    def test_news_stats(self, admin_headers):
        """Test GET /api/news/stats (admin only)"""
        response = requests.get(f"{BASE_URL}/api/news/stats", headers=admin_headers)
        assert response.status_code == 200, f"News stats failed: {response.text}"
        data = response.json()
        print(f"✓ News stats: {data.get('published')} published, {data.get('drafts')} drafts")
    
    def test_editorial_calendar(self, admin_headers):
        """Test GET /api/news/editorial-calendar"""
        response = requests.get(f"{BASE_URL}/api/news/editorial-calendar", headers=admin_headers)
        assert response.status_code == 200, f"Editorial calendar failed: {response.text}"
        data = response.json()
        assert "items" in data, "Missing 'items' in response"
        print(f"✓ Editorial calendar: {data.get('total', 0)} items")
    
    def test_create_news_post(self, admin_headers):
        """Test POST /api/news/posts - create a news post"""
        post_data = {
            "title": f"TEST_Admin News Post {datetime.now().isoformat()}",
            "content": "This is a test news post created by admin for testing purposes.",
            "priority": "normal",
            "status": "draft",
            "target_all": True,
            "channels": ["intranet"]
        }
        response = requests.post(f"{BASE_URL}/api/news/posts", headers=admin_headers, json=post_data)
        assert response.status_code == 200, f"Create news post failed: {response.text}"
        data = response.json()
        assert "post_id" in data, "Missing 'post_id' in response"
        print(f"✓ Created news post: {data.get('post_id')}")
        return data["post_id"]


class TestNewsMember:
    """News tests for Member role"""
    
    def test_news_feed_member(self, member_headers):
        """Test GET /api/news/feed for member"""
        response = requests.get(f"{BASE_URL}/api/news/feed", headers=member_headers)
        assert response.status_code == 200, f"News feed failed for member: {response.text}"
        data = response.json()
        print(f"✓ Member news feed: {len(data.get('posts', []))} posts visible")
    
    def test_news_categories_member(self, member_headers):
        """Test GET /api/news/categories for member"""
        response = requests.get(f"{BASE_URL}/api/news/categories", headers=member_headers)
        assert response.status_code == 200, f"News categories failed for member: {response.text}"
    
    def test_news_unread_count_member(self, member_headers):
        """Test GET /api/news/unread-count for member"""
        response = requests.get(f"{BASE_URL}/api/news/unread-count", headers=member_headers)
        assert response.status_code == 200, f"News unread count failed for member: {response.text}"
        data = response.json()
        print(f"✓ Member unread count: {data.get('unread')} unread, {data.get('mandatory_unread', 0)} mandatory")
    
    def test_news_stats_forbidden_for_member(self, member_headers):
        """Test GET /api/news/stats - should be forbidden for member"""
        response = requests.get(f"{BASE_URL}/api/news/stats", headers=member_headers)
        assert response.status_code == 403, f"News stats should be forbidden for member, got {response.status_code}"
        print("✓ News stats correctly forbidden for member")
    
    def test_editorial_calendar_forbidden_for_member(self, member_headers):
        """Test GET /api/news/editorial-calendar - should be forbidden for member"""
        response = requests.get(f"{BASE_URL}/api/news/editorial-calendar", headers=member_headers)
        assert response.status_code == 403, f"Editorial calendar should be forbidden for member, got {response.status_code}"
        print("✓ Editorial calendar correctly forbidden for member")


class TestNewsInteractions:
    """News interaction tests (reactions, comments, Q&A)"""
    
    def test_news_post_detail_and_interactions(self, admin_headers, member_headers):
        """Test news post detail view and interactions"""
        # First get a published post from feed
        response = requests.get(f"{BASE_URL}/api/news/feed?limit=5", headers=admin_headers)
        if response.status_code != 200:
            pytest.skip("Could not fetch news feed")
        
        posts = response.json().get("posts", [])
        if not posts:
            pytest.skip("No posts available for testing")
        
        post_id = posts[0]["post_id"]
        
        # Test get post detail
        response = requests.get(f"{BASE_URL}/api/news/posts/{post_id}", headers=admin_headers)
        assert response.status_code == 200, f"Get post detail failed: {response.text}"
        post = response.json()
        print(f"✓ Post detail: {post.get('title')}")
        
        # Test mark as read
        response = requests.post(f"{BASE_URL}/api/news/posts/{post_id}/read", headers=member_headers)
        assert response.status_code == 200, f"Mark as read failed: {response.text}"
        print("✓ Mark as read successful")
        
        # Test add reaction
        response = requests.post(f"{BASE_URL}/api/news/posts/{post_id}/reactions", 
                                headers=member_headers, json={"reaction_type": "like"})
        assert response.status_code == 200, f"Add reaction failed: {response.text}"
        print("✓ Add reaction successful")
        
        # Test get comments
        response = requests.get(f"{BASE_URL}/api/news/posts/{post_id}/comments", headers=member_headers)
        assert response.status_code == 200, f"Get comments failed: {response.text}"
        print(f"✓ Get comments: {len(response.json())} comments")
        
        # Test add comment
        response = requests.post(f"{BASE_URL}/api/news/posts/{post_id}/comments",
                                headers=member_headers, json={"content": "TEST_Comment from member"})
        assert response.status_code == 200, f"Add comment failed: {response.text}"
        comment_id = response.json().get("comment_id")
        print(f"✓ Add comment successful: {comment_id}")
        
        # Test get questions
        response = requests.get(f"{BASE_URL}/api/news/posts/{post_id}/questions", headers=member_headers)
        assert response.status_code == 200, f"Get questions failed: {response.text}"
        print(f"✓ Get questions: {len(response.json())} questions")
        
        # Test add question
        response = requests.post(f"{BASE_URL}/api/news/posts/{post_id}/questions",
                                headers=member_headers, json={"text": "TEST_Question from member?"})
        assert response.status_code == 200, f"Add question failed: {response.text}"
        question_id = response.json().get("question_id")
        print(f"✓ Add question successful: {question_id}")


# ============ SURVEYS TESTS ============

class TestSurveysAdmin:
    """Surveys tests for Admin role"""
    
    def test_list_surveys(self, admin_headers):
        """Test GET /api/surveys"""
        response = requests.get(f"{BASE_URL}/api/surveys?status=published", headers=admin_headers)
        assert response.status_code == 200, f"List surveys failed: {response.text}"
        data = response.json()
        print(f"✓ List surveys: {len(data)} published surveys")
    
    def test_surveys_pending_count(self, admin_headers):
        """Test GET /api/surveys/pending-count"""
        response = requests.get(f"{BASE_URL}/api/surveys/pending-count", headers=admin_headers)
        assert response.status_code == 200, f"Surveys pending count failed: {response.text}"
        data = response.json()
        print(f"✓ Surveys pending count: {data.get('count')} pending of {data.get('total')} total")
    
    def test_pulse_checks(self, admin_headers):
        """Test GET /api/pulse-checks"""
        response = requests.get(f"{BASE_URL}/api/pulse-checks", headers=admin_headers)
        assert response.status_code == 200, f"Pulse checks failed: {response.text}"
        data = response.json()
        print(f"✓ Pulse checks: {len(data)} pulse checks")
    
    def test_feedback_entries(self, admin_headers):
        """Test GET /api/feedback/entries (admin only)"""
        response = requests.get(f"{BASE_URL}/api/feedback/entries", headers=admin_headers)
        assert response.status_code == 200, f"Feedback entries failed: {response.text}"
        data = response.json()
        print(f"✓ Feedback entries: {len(data)} entries")
    
    def test_interaction_stats(self, admin_headers):
        """Test GET /api/interaction-stats (admin only)"""
        response = requests.get(f"{BASE_URL}/api/interaction-stats", headers=admin_headers)
        assert response.status_code == 200, f"Interaction stats failed: {response.text}"
        data = response.json()
        assert "news" in data, "Missing 'news' in stats"
        assert "surveys" in data, "Missing 'surveys' in stats"
        assert "feedback" in data, "Missing 'feedback' in stats"
        print(f"✓ Interaction stats: {data.get('news', {}).get('comments')} comments, {data.get('surveys', {}).get('responses')} survey responses")
    
    def test_create_survey(self, admin_headers):
        """Test POST /api/surveys - create a survey"""
        survey_data = {
            "title": f"TEST_Admin Survey {datetime.now().isoformat()}",
            "description": "Test survey created by admin",
            "survey_type": "survey",
            "questions": [
                {
                    "question_id": "q1",
                    "text": "How satisfied are you?",
                    "type": "single_choice",
                    "options": ["Very satisfied", "Satisfied", "Neutral", "Dissatisfied"],
                    "required": True
                },
                {
                    "question_id": "q2",
                    "text": "Any additional comments?",
                    "type": "free_text",
                    "required": False
                }
            ],
            "anonymous": False,
            "status": "published",
            "target_all": True
        }
        response = requests.post(f"{BASE_URL}/api/surveys", headers=admin_headers, json=survey_data)
        assert response.status_code == 200, f"Create survey failed: {response.text}"
        data = response.json()
        assert "survey_id" in data, "Missing 'survey_id' in response"
        print(f"✓ Created survey: {data.get('survey_id')}")
        return data["survey_id"]


class TestSurveysMember:
    """Surveys tests for Member role"""
    
    def test_list_surveys_member(self, member_headers):
        """Test GET /api/surveys for member"""
        response = requests.get(f"{BASE_URL}/api/surveys?status=published", headers=member_headers)
        assert response.status_code == 200, f"List surveys failed for member: {response.text}"
        data = response.json()
        print(f"✓ Member list surveys: {len(data)} surveys visible")
    
    def test_surveys_pending_count_member(self, member_headers):
        """Test GET /api/surveys/pending-count for member"""
        response = requests.get(f"{BASE_URL}/api/surveys/pending-count", headers=member_headers)
        assert response.status_code == 200, f"Surveys pending count failed for member: {response.text}"
        data = response.json()
        print(f"✓ Member pending surveys: {data.get('count')} pending")
    
    def test_feedback_entries_forbidden_for_member(self, member_headers):
        """Test GET /api/feedback/entries - should be forbidden for member"""
        response = requests.get(f"{BASE_URL}/api/feedback/entries", headers=member_headers)
        assert response.status_code == 403, f"Feedback entries should be forbidden for member, got {response.status_code}"
        print("✓ Feedback entries correctly forbidden for member")
    
    def test_interaction_stats_forbidden_for_member(self, member_headers):
        """Test GET /api/interaction-stats - should be forbidden for member"""
        response = requests.get(f"{BASE_URL}/api/interaction-stats", headers=member_headers)
        assert response.status_code == 403, f"Interaction stats should be forbidden for member, got {response.status_code}"
        print("✓ Interaction stats correctly forbidden for member")
    
    def test_submit_feedback(self, member_headers):
        """Test POST /api/feedback/submit"""
        feedback_data = {
            "category": "ideas",
            "subject": "TEST_Feedback from member",
            "content": "This is a test feedback submission",
            "anonymous": True
        }
        response = requests.post(f"{BASE_URL}/api/feedback/submit", headers=member_headers, json=feedback_data)
        assert response.status_code == 200, f"Submit feedback failed: {response.text}"
        data = response.json()
        assert "feedback_id" in data, "Missing 'feedback_id' in response"
        print(f"✓ Submitted feedback: {data.get('feedback_id')}, tracking_code: {data.get('tracking_code')}")
        return data.get("tracking_code")


class TestSurveyResponseFlow:
    """Test survey response flow"""
    
    def test_survey_response_flow(self, admin_headers, member_headers):
        """Test complete survey response flow: Admin creates -> Member responds -> Admin sees results"""
        # 1. Admin creates a survey
        survey_data = {
            "title": f"TEST_Flow Survey {datetime.now().isoformat()}",
            "description": "Survey for testing response flow",
            "survey_type": "survey",
            "questions": [
                {
                    "question_id": "q1",
                    "text": "Rate this test",
                    "type": "scale",
                    "scale_min": 1,
                    "scale_max": 5,
                    "required": True
                }
            ],
            "anonymous": False,
            "status": "published",
            "target_all": True
        }
        response = requests.post(f"{BASE_URL}/api/surveys", headers=admin_headers, json=survey_data)
        assert response.status_code == 200, f"Create survey failed: {response.text}"
        survey_id = response.json()["survey_id"]
        print(f"✓ Admin created survey: {survey_id}")
        
        # 2. Member gets the survey
        response = requests.get(f"{BASE_URL}/api/surveys/{survey_id}", headers=member_headers)
        assert response.status_code == 200, f"Get survey failed: {response.text}"
        survey = response.json()
        assert survey.get("participated") == False, "Member should not have participated yet"
        print(f"✓ Member can see survey: {survey.get('title')}")
        
        # 3. Member responds to the survey
        response_data = {
            "answers": {"q1": 4}
        }
        response = requests.post(f"{BASE_URL}/api/surveys/{survey_id}/respond", 
                                headers=member_headers, json=response_data)
        assert response.status_code == 200, f"Submit response failed: {response.text}"
        print("✓ Member submitted response")
        
        # 4. Verify member can't respond again
        response = requests.post(f"{BASE_URL}/api/surveys/{survey_id}/respond", 
                                headers=member_headers, json=response_data)
        assert response.status_code == 400, "Should not allow duplicate response"
        print("✓ Duplicate response correctly rejected")
        
        # 5. Admin gets results
        response = requests.get(f"{BASE_URL}/api/surveys/{survey_id}/results", headers=admin_headers)
        assert response.status_code == 200, f"Get results failed: {response.text}"
        results = response.json()
        assert results.get("total_responses") >= 1, "Should have at least 1 response"
        print(f"✓ Admin sees results: {results.get('total_responses')} responses")
        
        # Cleanup - delete the test survey
        response = requests.delete(f"{BASE_URL}/api/surveys/{survey_id}", headers=admin_headers)
        assert response.status_code == 200, f"Delete survey failed: {response.text}"
        print("✓ Test survey cleaned up")


class TestAnonymousSurvey:
    """Test anonymous survey functionality"""
    
    def test_anonymous_survey_flow(self, admin_headers, member_headers):
        """Test anonymous survey - responses should not show user info"""
        # Create anonymous survey
        survey_data = {
            "title": f"TEST_Anonymous Survey {datetime.now().isoformat()}",
            "description": "Anonymous survey test",
            "survey_type": "survey",
            "questions": [
                {
                    "question_id": "q1",
                    "text": "Anonymous feedback",
                    "type": "free_text",
                    "required": True
                }
            ],
            "anonymous": True,
            "status": "published",
            "target_all": True
        }
        response = requests.post(f"{BASE_URL}/api/surveys", headers=admin_headers, json=survey_data)
        assert response.status_code == 200, f"Create anonymous survey failed: {response.text}"
        survey_id = response.json()["survey_id"]
        print(f"✓ Created anonymous survey: {survey_id}")
        
        # Member responds
        response_data = {
            "answers": {"q1": "This is anonymous feedback"}
        }
        response = requests.post(f"{BASE_URL}/api/surveys/{survey_id}/respond", 
                                headers=member_headers, json=response_data)
        assert response.status_code == 200, f"Submit anonymous response failed: {response.text}"
        resp_data = response.json()
        # Anonymous response should have user_id = "anonymous"
        assert resp_data.get("user_id") == "anonymous" or resp_data.get("user_name") == "Anonym", \
            "Anonymous response should not reveal user identity"
        print("✓ Anonymous response submitted correctly")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/surveys/{survey_id}", headers=admin_headers)


class TestFeedbackTracking:
    """Test feedback tracking functionality"""
    
    def test_feedback_tracking_flow(self, member_headers, admin_headers):
        """Test anonymous feedback with tracking code"""
        # Submit anonymous feedback
        feedback_data = {
            "category": "improvements",
            "subject": "TEST_Trackable Feedback",
            "content": "This feedback should be trackable",
            "anonymous": True
        }
        response = requests.post(f"{BASE_URL}/api/feedback/submit", headers=member_headers, json=feedback_data)
        assert response.status_code == 200, f"Submit feedback failed: {response.text}"
        data = response.json()
        tracking_code = data.get("tracking_code")
        assert tracking_code, "Anonymous feedback should have tracking code"
        print(f"✓ Submitted feedback with tracking code: {tracking_code}")
        
        # Track the feedback
        response = requests.post(f"{BASE_URL}/api/feedback/track", 
                                headers=member_headers, json={"tracking_code": tracking_code})
        assert response.status_code == 200, f"Track feedback failed: {response.text}"
        tracked = response.json()
        assert tracked.get("status") == "new", "New feedback should have 'new' status"
        print(f"✓ Tracked feedback status: {tracked.get('status')}")


# ============ TASKS TESTS (Dashboard related) ============

class TestTasksForDashboard:
    """Test tasks endpoints used by dashboard"""
    
    def test_list_tasks(self, admin_headers):
        """Test GET /api/tasks"""
        response = requests.get(f"{BASE_URL}/api/tasks", headers=admin_headers)
        assert response.status_code == 200, f"List tasks failed: {response.text}"
        data = response.json()
        assert "tasks" in data, "Missing 'tasks' in response"
        print(f"✓ List tasks: {len(data.get('tasks', []))} tasks")
    
    def test_create_task(self, admin_headers):
        """Test POST /api/tasks"""
        task_data = {
            "title": f"TEST_Dashboard Task {datetime.now().isoformat()}",
            "description": "Task created for dashboard testing",
            "priority": "normal",
            "status": "open"
        }
        response = requests.post(f"{BASE_URL}/api/tasks", headers=admin_headers, json=task_data)
        assert response.status_code in [200, 201], f"Create task failed: {response.text}"
        data = response.json()
        assert "task_id" in data, "Missing 'task_id' in response"
        print(f"✓ Created task: {data.get('task_id')}")
        return data["task_id"]


# ============ FOCUS TIME TESTS (Dashboard related) ============

class TestFocusTime:
    """Test focus time endpoints used by dashboard"""
    
    def test_list_focus_times(self, admin_headers):
        """Test GET /api/focus-times"""
        response = requests.get(f"{BASE_URL}/api/focus-times", headers=admin_headers)
        assert response.status_code == 200, f"List focus times failed: {response.text}"
        print(f"✓ List focus times: {len(response.json())} focus times")
    
    def test_active_focus_time(self, admin_headers):
        """Test GET /api/focus-times/active"""
        response = requests.get(f"{BASE_URL}/api/focus-times/active", headers=admin_headers)
        assert response.status_code == 200, f"Active focus time failed: {response.text}"
        data = response.json()
        print(f"✓ Active focus time: {'Yes' if data.get('active') else 'No'}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
