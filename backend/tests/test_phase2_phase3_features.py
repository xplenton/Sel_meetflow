"""
Test Phase 2 (Approval Workflow) and Phase 3 (Surveys, Pulse Checks, Feedback, Interaction Dashboard)

Phase 2 - Approval Workflow:
- POST /api/news/posts/{id}/submit-review - changes status to 'review'
- POST /api/news/posts/{id}/approve-review - Redakteur forwards to approval, Admin/Freigeber publishes directly
- POST /api/news/posts/{id}/reject - returns to draft with reason
- GET /api/news/approval-queue - returns posts in review/approval status
- GET /api/news/audit/{post_id} - returns audit trail entries

Phase 3 - Surveys:
- POST /api/surveys - creates a survey with questions (single_choice, multiple_choice, free_text, scale)
- GET /api/surveys - returns published surveys with participation status
- GET /api/surveys/{id} - returns survey with my_response
- POST /api/surveys/{id}/respond - submits answers (prevents double submission)
- GET /api/surveys/{id}/results - returns aggregated results per question
- DELETE /api/surveys/{id} - deletes survey and responses

Phase 3 - Pulse Checks:
- GET /api/pulse-checks - returns pulse_check type surveys

Phase 3 - Feedback:
- POST /api/feedback/submit - creates anonymous feedback entry
- GET /api/feedback/entries - returns all feedback (admin only)
- PUT /api/feedback/entries/{id} - updates status

Phase 3 - Dashboard:
- GET /api/interaction-stats - returns news/survey/feedback stats
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuthSetup:
    """Authentication setup for tests"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin and return session with auth cookie"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return session
    
    def test_admin_login(self, admin_session):
        """Verify admin login works"""
        response = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "admin@meetflow.com"
        assert data["role"] == "admin"
        print(f"✓ Admin login successful: {data['email']} (role: {data['role']})")


class TestApprovalWorkflow:
    """Phase 2: Approval Workflow Tests"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin and return session with auth cookie"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert response.status_code == 200
        return session
    
    @pytest.fixture(scope="class")
    def test_draft_post(self, admin_session):
        """Create a draft post for approval workflow testing"""
        unique_id = uuid.uuid4().hex[:8]
        response = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": f"TEST_Approval_Draft_{unique_id}",
            "content": "This is a test draft for approval workflow",
            "status": "draft",
            "priority": "normal"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "draft"
        print(f"✓ Created draft post: {data['post_id']}")
        return data
    
    def test_submit_for_review(self, admin_session, test_draft_post):
        """POST /api/news/posts/{id}/submit-review - changes status to 'review'"""
        post_id = test_draft_post["post_id"]
        response = admin_session.post(f"{BASE_URL}/api/news/posts/{post_id}/submit-review")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "review"
        print(f"✓ Submitted for review: {data}")
        
        # Verify post status changed
        get_response = admin_session.get(f"{BASE_URL}/api/news/posts/{post_id}")
        assert get_response.status_code == 200
        post_data = get_response.json()
        assert post_data["status"] == "review"
        assert post_data["approval_status"] == "pending_review"
        print(f"✓ Post status verified: status={post_data['status']}, approval_status={post_data['approval_status']}")
    
    def test_approval_queue_shows_review_posts(self, admin_session, test_draft_post):
        """GET /api/news/approval-queue - returns posts in review/approval status"""
        response = admin_session.get(f"{BASE_URL}/api/news/approval-queue")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Find our test post in the queue
        post_ids = [p["post_id"] for p in data]
        assert test_draft_post["post_id"] in post_ids, "Test post not found in approval queue"
        print(f"✓ Approval queue contains {len(data)} posts, including test post")
    
    def test_approve_review_admin_publishes_directly(self, admin_session):
        """POST /api/news/posts/{id}/approve-review - Admin publishes directly"""
        # Create a new draft and submit for review
        unique_id = uuid.uuid4().hex[:8]
        create_response = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": f"TEST_Admin_Approve_{unique_id}",
            "content": "Test post for admin direct approval",
            "status": "draft"
        })
        assert create_response.status_code == 200
        post_id = create_response.json()["post_id"]
        
        # Submit for review
        submit_response = admin_session.post(f"{BASE_URL}/api/news/posts/{post_id}/submit-review")
        assert submit_response.status_code == 200
        
        # Admin approves - should publish directly
        approve_response = admin_session.post(f"{BASE_URL}/api/news/posts/{post_id}/approve-review", json={
            "comment": "Approved by admin"
        })
        assert approve_response.status_code == 200
        data = approve_response.json()
        assert data["status"] == "published"
        print(f"✓ Admin approved and published directly: {data}")
        
        # Verify post is published
        get_response = admin_session.get(f"{BASE_URL}/api/news/posts/{post_id}")
        assert get_response.status_code == 200
        post_data = get_response.json()
        assert post_data["status"] == "published"
        assert post_data["approval_status"] == "approved"
        print("✓ Post verified as published with approval_status=approved")
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
    
    def test_reject_post(self, admin_session):
        """POST /api/news/posts/{id}/reject - returns to draft with reason"""
        # Create a new draft and submit for review
        unique_id = uuid.uuid4().hex[:8]
        create_response = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": f"TEST_Reject_{unique_id}",
            "content": "Test post for rejection",
            "status": "draft"
        })
        assert create_response.status_code == 200
        post_id = create_response.json()["post_id"]
        
        # Submit for review
        submit_response = admin_session.post(f"{BASE_URL}/api/news/posts/{post_id}/submit-review")
        assert submit_response.status_code == 200
        
        # Reject with reason
        reject_response = admin_session.post(f"{BASE_URL}/api/news/posts/{post_id}/reject", json={
            "reason": "Content needs revision"
        })
        assert reject_response.status_code == 200
        data = reject_response.json()
        assert data["status"] == "draft"
        print(f"✓ Post rejected: {data}")
        
        # Verify post is back to draft with rejection reason
        get_response = admin_session.get(f"{BASE_URL}/api/news/posts/{post_id}")
        assert get_response.status_code == 200
        post_data = get_response.json()
        assert post_data["status"] == "draft"
        assert post_data["approval_status"] == "rejected"
        assert post_data["rejection_reason"] == "Content needs revision"
        print(f"✓ Post verified as draft with rejection_reason: {post_data['rejection_reason']}")
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
    
    def test_audit_trail(self, admin_session, test_draft_post):
        """GET /api/news/audit/{post_id} - returns audit trail entries"""
        post_id = test_draft_post["post_id"]
        response = admin_session.get(f"{BASE_URL}/api/news/audit/{post_id}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0, "Audit trail should have entries"
        
        # Verify audit entries have required fields
        for entry in data:
            assert "action" in entry
            assert "post_id" in entry
            assert "user_id" in entry
            assert "timestamp" in entry
        
        # Check for expected actions
        actions = [e["action"] for e in data]
        assert "created" in actions or "submitted_for_review" in actions
        print(f"✓ Audit trail has {len(data)} entries with actions: {actions}")


class TestSurveys:
    """Phase 3: Surveys Tests"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin and return session with auth cookie"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert response.status_code == 200
        return session
    
    @pytest.fixture(scope="class")
    def test_survey(self, admin_session):
        """Create a test survey with all question types"""
        unique_id = uuid.uuid4().hex[:8]
        response = admin_session.post(f"{BASE_URL}/api/surveys", json={
            "title": f"TEST_Survey_{unique_id}",
            "description": "Test survey with all question types",
            "survey_type": "survey",
            "anonymous": False,
            "status": "published",
            "target_all": True,
            "questions": [
                {
                    "question_id": "q1",
                    "text": "Single choice question?",
                    "type": "single_choice",
                    "options": ["Option A", "Option B", "Option C"],
                    "required": True
                },
                {
                    "question_id": "q2",
                    "text": "Multiple choice question?",
                    "type": "multiple_choice",
                    "options": ["Choice 1", "Choice 2", "Choice 3"],
                    "required": False
                },
                {
                    "question_id": "q3",
                    "text": "Free text question?",
                    "type": "free_text",
                    "required": False
                },
                {
                    "question_id": "q4",
                    "text": "Scale question (1-10)?",
                    "type": "scale",
                    "scale_min": 1,
                    "scale_max": 10,
                    "required": True
                }
            ]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["title"].startswith("TEST_Survey_")
        assert len(data["questions"]) == 4
        print(f"✓ Created test survey: {data['survey_id']} with {len(data['questions'])} questions")
        return data
    
    def test_create_survey_with_all_question_types(self, test_survey):
        """POST /api/surveys - creates a survey with questions (single_choice, multiple_choice, free_text, scale)"""
        # Verify all question types
        question_types = [q["type"] for q in test_survey["questions"]]
        assert "single_choice" in question_types
        assert "multiple_choice" in question_types
        assert "free_text" in question_types
        assert "scale" in question_types
        print(f"✓ Survey has all question types: {question_types}")
    
    def test_list_surveys(self, admin_session, test_survey):
        """GET /api/surveys - returns published surveys with participation status"""
        response = admin_session.get(f"{BASE_URL}/api/surveys?status=published")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Find our test survey
        survey_ids = [s["survey_id"] for s in data]
        assert test_survey["survey_id"] in survey_ids
        
        # Verify participation status field exists
        for survey in data:
            assert "participated" in survey
            assert "response_count" in survey
        print(f"✓ Listed {len(data)} surveys, test survey found with participation status")
    
    def test_get_survey_detail(self, admin_session, test_survey):
        """GET /api/surveys/{id} - returns survey with my_response"""
        survey_id = test_survey["survey_id"]
        response = admin_session.get(f"{BASE_URL}/api/surveys/{survey_id}")
        assert response.status_code == 200
        data = response.json()
        
        assert data["survey_id"] == survey_id
        assert "participated" in data
        assert "my_response" in data
        assert "response_count" in data
        assert len(data["questions"]) == 4
        print(f"✓ Got survey detail with my_response field: participated={data['participated']}")
    
    def test_submit_survey_response(self, admin_session, test_survey):
        """POST /api/surveys/{id}/respond - submits answers"""
        survey_id = test_survey["survey_id"]
        response = admin_session.post(f"{BASE_URL}/api/surveys/{survey_id}/respond", json={
            "answers": {
                "q1": "Option A",
                "q2": ["Choice 1", "Choice 2"],
                "q3": "This is my free text answer",
                "q4": 8
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert "response_id" in data
        assert data["survey_id"] == survey_id
        assert data["answers"]["q1"] == "Option A"
        assert data["answers"]["q4"] == 8
        print(f"✓ Submitted survey response: {data['response_id']}")
    
    def test_prevent_double_submission(self, admin_session, test_survey):
        """POST /api/surveys/{id}/respond - prevents double submission"""
        survey_id = test_survey["survey_id"]
        response = admin_session.post(f"{BASE_URL}/api/surveys/{survey_id}/respond", json={
            "answers": {"q1": "Option B"}
        })
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        print(f"✓ Double submission prevented: {data['detail']}")
    
    def test_get_survey_results(self, admin_session, test_survey):
        """GET /api/surveys/{id}/results - returns aggregated results per question"""
        survey_id = test_survey["survey_id"]
        response = admin_session.get(f"{BASE_URL}/api/surveys/{survey_id}/results")
        assert response.status_code == 200
        data = response.json()
        
        assert "survey" in data
        assert "total_responses" in data
        assert "results" in data
        assert data["total_responses"] >= 1
        
        # Verify results structure for each question type
        results = data["results"]
        assert "q1" in results  # single_choice
        assert "q2" in results  # multiple_choice
        assert "q3" in results  # free_text
        assert "q4" in results  # scale
        
        # Check single_choice results
        assert results["q1"]["type"] == "single_choice"
        assert "answers" in results["q1"]
        
        # Check scale results
        assert results["q4"]["type"] == "scale"
        assert "average" in results["q4"]
        assert "values" in results["q4"]
        
        print(f"✓ Got survey results: {data['total_responses']} responses, scale average: {results['q4']['average']}")
    
    def test_delete_survey(self, admin_session):
        """DELETE /api/surveys/{id} - deletes survey and responses"""
        # Create a survey to delete
        unique_id = uuid.uuid4().hex[:8]
        create_response = admin_session.post(f"{BASE_URL}/api/surveys", json={
            "title": f"TEST_Delete_Survey_{unique_id}",
            "survey_type": "survey",
            "status": "draft",
            "questions": [{"question_id": "q1", "text": "Test?", "type": "free_text"}]
        })
        assert create_response.status_code == 200
        survey_id = create_response.json()["survey_id"]
        
        # Delete the survey
        delete_response = admin_session.delete(f"{BASE_URL}/api/surveys/{survey_id}")
        assert delete_response.status_code == 200
        data = delete_response.json()
        assert "message" in data
        print(f"✓ Deleted survey: {data['message']}")
        
        # Verify survey is deleted
        get_response = admin_session.get(f"{BASE_URL}/api/surveys/{survey_id}")
        assert get_response.status_code == 404


class TestPulseChecks:
    """Phase 3: Pulse Checks Tests"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin and return session with auth cookie"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert response.status_code == 200
        return session
    
    @pytest.fixture(scope="class")
    def test_pulse_check(self, admin_session):
        """Create a test pulse check"""
        unique_id = uuid.uuid4().hex[:8]
        response = admin_session.post(f"{BASE_URL}/api/surveys", json={
            "title": f"TEST_Pulse_Check_{unique_id}",
            "description": "How are you feeling today?",
            "survey_type": "pulse_check",
            "anonymous": True,
            "status": "published",
            "target_all": True,
            "questions": [
                {
                    "question_id": "mood",
                    "text": "How is your mood today?",
                    "type": "scale",
                    "scale_min": 1,
                    "scale_max": 5,
                    "required": True
                }
            ]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["survey_type"] == "pulse_check"
        print(f"✓ Created pulse check: {data['survey_id']}")
        return data
    
    def test_list_pulse_checks(self, admin_session, test_pulse_check):
        """GET /api/pulse-checks - returns pulse_check type surveys"""
        response = admin_session.get(f"{BASE_URL}/api/pulse-checks")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # All returned items should be pulse_check type
        for item in data:
            assert item["survey_type"] == "pulse_check"
            assert "participated" in item
            assert "response_count" in item
        
        # Find our test pulse check
        pulse_ids = [p["survey_id"] for p in data]
        assert test_pulse_check["survey_id"] in pulse_ids
        print(f"✓ Listed {len(data)} pulse checks, test pulse check found")


class TestFeedback:
    """Phase 3: Anonymous Feedback Tests"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin and return session with auth cookie"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert response.status_code == 200
        return session
    
    @pytest.fixture(scope="class")
    def test_feedback(self, admin_session):
        """Create a test feedback entry"""
        unique_id = uuid.uuid4().hex[:8]
        response = admin_session.post(f"{BASE_URL}/api/feedback/submit", json={
            "category": "ideas",
            "subject": f"TEST_Feedback_{unique_id}",
            "content": "This is a test feedback submission"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "ideas"
        assert data["anonymous"] == True
        assert data["status"] == "new"
        print(f"✓ Created feedback: {data['feedback_id']}")
        return data
    
    def test_submit_anonymous_feedback(self, test_feedback):
        """POST /api/feedback/submit - creates anonymous feedback entry"""
        assert "feedback_id" in test_feedback
        assert test_feedback["anonymous"] == True
        assert test_feedback["status"] == "new"
        print("✓ Feedback is anonymous with status 'new'")
    
    def test_submit_feedback_different_categories(self, admin_session):
        """Test feedback submission with different categories"""
        categories = ["ideas", "complaints", "improvements", "questions"]
        
        for category in categories:
            response = admin_session.post(f"{BASE_URL}/api/feedback/submit", json={
                "category": category,
                "subject": f"Test {category}",
                "content": f"Feedback for {category} category"
            })
            assert response.status_code == 200
            data = response.json()
            assert data["category"] == category
            print(f"✓ Created feedback with category: {category}")
    
    def test_list_feedback_entries(self, admin_session, test_feedback):
        """GET /api/feedback/entries - returns all feedback (admin only)"""
        response = admin_session.get(f"{BASE_URL}/api/feedback/entries")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Find our test feedback
        feedback_ids = [f["feedback_id"] for f in data]
        assert test_feedback["feedback_id"] in feedback_ids
        
        # Verify feedback entries have required fields
        for entry in data:
            assert "feedback_id" in entry
            assert "category" in entry
            assert "status" in entry
            assert "created_at" in entry
        print(f"✓ Listed {len(data)} feedback entries")
    
    def test_filter_feedback_by_category(self, admin_session):
        """GET /api/feedback/entries?category=ideas - filters by category"""
        response = admin_session.get(f"{BASE_URL}/api/feedback/entries?category=ideas")
        assert response.status_code == 200
        data = response.json()
        
        for entry in data:
            assert entry["category"] == "ideas"
        print(f"✓ Filtered feedback by category 'ideas': {len(data)} entries")
    
    def test_filter_feedback_by_status(self, admin_session):
        """GET /api/feedback/entries?status=new - filters by status"""
        response = admin_session.get(f"{BASE_URL}/api/feedback/entries?status=new")
        assert response.status_code == 200
        data = response.json()
        
        for entry in data:
            assert entry["status"] == "new"
        print(f"✓ Filtered feedback by status 'new': {len(data)} entries")
    
    def test_update_feedback_status(self, admin_session, test_feedback):
        """PUT /api/feedback/entries/{id} - updates status"""
        feedback_id = test_feedback["feedback_id"]
        
        # Update to in_progress
        response = admin_session.put(f"{BASE_URL}/api/feedback/entries/{feedback_id}", json={
            "status": "in_progress"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"
        print("✓ Updated feedback status to 'in_progress'")
        
        # Update to resolved with admin response
        response = admin_session.put(f"{BASE_URL}/api/feedback/entries/{feedback_id}", json={
            "status": "resolved",
            "response": "Thank you for your feedback!"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "resolved"
        assert data["admin_response"] == "Thank you for your feedback!"
        assert "responded_by" in data
        assert "responded_at" in data
        print("✓ Updated feedback status to 'resolved' with admin response")


class TestInteractionDashboard:
    """Phase 3: Interaction Dashboard Tests"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin and return session with auth cookie"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert response.status_code == 200
        return session
    
    def test_get_interaction_stats(self, admin_session):
        """GET /api/interaction-stats - returns news/survey/feedback stats"""
        response = admin_session.get(f"{BASE_URL}/api/interaction-stats")
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "news" in data
        assert "surveys" in data
        assert "feedback" in data
        assert "approval_queue" in data
        
        # Verify news stats
        assert "posts" in data["news"]
        assert "comments" in data["news"]
        assert "reactions" in data["news"]
        assert "reads" in data["news"]
        
        # Verify survey stats
        assert "total" in data["surveys"]
        assert "responses" in data["surveys"]
        
        # Verify feedback stats
        assert "total" in data["feedback"]
        assert "new" in data["feedback"]
        
        print(f"✓ Interaction stats: news={data['news']['posts']} posts, surveys={data['surveys']['total']}, feedback={data['feedback']['total']}, approval_queue={data['approval_queue']}")


class TestPermissions:
    """Test role-based permissions"""
    
    def test_unauthenticated_cannot_access_surveys(self):
        """Unauthenticated users cannot access surveys"""
        session = requests.Session()
        response = session.get(f"{BASE_URL}/api/surveys")
        assert response.status_code == 401
        print("✓ Unauthenticated access to surveys blocked")
    
    def test_unauthenticated_cannot_access_feedback_entries(self):
        """Unauthenticated users cannot access feedback entries"""
        session = requests.Session()
        response = session.get(f"{BASE_URL}/api/feedback/entries")
        assert response.status_code == 401
        print("✓ Unauthenticated access to feedback entries blocked")
    
    def test_unauthenticated_cannot_access_interaction_stats(self):
        """Unauthenticated users cannot access interaction stats"""
        session = requests.Session()
        response = session.get(f"{BASE_URL}/api/interaction-stats")
        assert response.status_code == 401
        print("✓ Unauthenticated access to interaction stats blocked")
    
    def test_unauthenticated_cannot_access_approval_queue(self):
        """Unauthenticated users cannot access approval queue"""
        session = requests.Session()
        response = session.get(f"{BASE_URL}/api/news/approval-queue")
        assert response.status_code == 401
        print("✓ Unauthenticated access to approval queue blocked")


class TestCleanup:
    """Cleanup test data"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin and return session with auth cookie"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert response.status_code == 200
        return session
    
    def test_cleanup_test_surveys(self, admin_session):
        """Clean up TEST_ prefixed surveys"""
        response = admin_session.get(f"{BASE_URL}/api/surveys?status=published")
        if response.status_code == 200:
            surveys = response.json()
            for survey in surveys:
                if survey["title"].startswith("TEST_"):
                    admin_session.delete(f"{BASE_URL}/api/surveys/{survey['survey_id']}")
                    print(f"✓ Deleted test survey: {survey['survey_id']}")
        
        # Also check draft surveys
        response = admin_session.get(f"{BASE_URL}/api/surveys?status=draft")
        if response.status_code == 200:
            surveys = response.json()
            for survey in surveys:
                if survey["title"].startswith("TEST_"):
                    admin_session.delete(f"{BASE_URL}/api/surveys/{survey['survey_id']}")
                    print(f"✓ Deleted test survey: {survey['survey_id']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
