"""
Phase 4 Features Test Suite
Tests for: Export Functions (CSV), Q&A Function, Multilingual News, Sentiment Analysis
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPhase4Features:
    """Phase 4: Export, Q&A, Multilingual, Sentiment"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with admin login"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Use existing news post
        self.post_id = "news_c8cb197d4429"
        yield
    
    # ============ Q&A FUNCTION TESTS ============
    
    def test_create_question(self):
        """POST /api/news/posts/{id}/questions creates a question"""
        resp = self.session.post(f"{BASE_URL}/api/news/posts/{self.post_id}/questions", json={
            "text": "TEST_Question: What is the deadline for this?"
        })
        assert resp.status_code == 200, f"Create question failed: {resp.text}"
        data = resp.json()
        assert "question_id" in data
        assert data["text"] == "TEST_Question: What is the deadline for this?"
        assert data["post_id"] == self.post_id
        assert data["upvote_count"] == 0
        assert data["answer"] is None
        self.test_question_id = data["question_id"]
        return data["question_id"]
    
    def test_get_questions_sorted_by_upvotes(self):
        """GET /api/news/posts/{id}/questions returns questions sorted by upvotes"""
        resp = self.session.get(f"{BASE_URL}/api/news/posts/{self.post_id}/questions")
        assert resp.status_code == 200, f"Get questions failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list)
        # Verify sorted by upvote_count descending
        if len(data) > 1:
            for i in range(len(data) - 1):
                assert data[i].get("upvote_count", 0) >= data[i+1].get("upvote_count", 0), "Questions not sorted by upvotes"
    
    def test_upvote_question_toggle(self):
        """POST /api/news/questions/{qid}/upvote toggles upvote"""
        # First create a question
        q_id = self.test_create_question()
        
        # Upvote
        resp = self.session.post(f"{BASE_URL}/api/news/questions/{q_id}/upvote")
        assert resp.status_code == 200, f"Upvote failed: {resp.text}"
        data = resp.json()
        assert data["upvote_count"] == 1
        assert data["user_upvoted"] == True
        
        # Toggle off (remove upvote)
        resp2 = self.session.post(f"{BASE_URL}/api/news/questions/{q_id}/upvote")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["upvote_count"] == 0
        assert data2["user_upvoted"] == False
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/news/questions/{q_id}")
    
    def test_answer_question(self):
        """POST /api/news/questions/{qid}/answer adds editor answer"""
        # Create question
        q_id = self.test_create_question()
        
        # Answer it
        resp = self.session.post(f"{BASE_URL}/api/news/questions/{q_id}/answer", json={
            "answer": "The deadline is next Friday."
        })
        assert resp.status_code == 200, f"Answer question failed: {resp.text}"
        data = resp.json()
        assert data["message"] == "Beantwortet"
        
        # Verify answer is stored
        questions = self.session.get(f"{BASE_URL}/api/news/posts/{self.post_id}/questions").json()
        answered_q = next((q for q in questions if q["question_id"] == q_id), None)
        assert answered_q is not None
        assert answered_q["answer"] == "The deadline is next Friday."
        assert answered_q["answered_by"] is not None
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/news/questions/{q_id}")
    
    def test_delete_question(self):
        """DELETE /api/news/questions/{qid} deletes a question"""
        # Create question
        q_id = self.test_create_question()
        
        # Delete it
        resp = self.session.delete(f"{BASE_URL}/api/news/questions/{q_id}")
        assert resp.status_code == 200, f"Delete question failed: {resp.text}"
        data = resp.json()
        assert data["message"] == "Geloescht"
        
        # Verify deleted
        questions = self.session.get(f"{BASE_URL}/api/news/posts/{self.post_id}/questions").json()
        assert not any(q["question_id"] == q_id for q in questions)
    
    def test_question_validation(self):
        """POST /api/news/posts/{id}/questions validates empty text"""
        resp = self.session.post(f"{BASE_URL}/api/news/posts/{self.post_id}/questions", json={
            "text": ""
        })
        assert resp.status_code == 400, "Should reject empty question"
    
    # ============ MULTILINGUAL NEWS TESTS ============
    
    def test_set_translations(self):
        """PUT /api/news/posts/{id}/translations stores translations for multiple languages"""
        resp = self.session.put(f"{BASE_URL}/api/news/posts/{self.post_id}/translations", json={
            "en": {
                "title": "English Title",
                "content": "English content here",
                "excerpt": "English excerpt"
            },
            "de": {
                "title": "Deutscher Titel",
                "content": "Deutscher Inhalt hier",
                "excerpt": "Deutsche Kurzfassung"
            }
        })
        assert resp.status_code == 200, f"Set translations failed: {resp.text}"
        data = resp.json()
        assert "en" in data.get("languages", [])
        assert "de" in data.get("languages", [])
    
    def test_get_localized_post_english(self):
        """GET /api/news/posts/{id}/localized?lang=en returns post with English content"""
        # First set translations
        self.test_set_translations()
        
        resp = self.session.get(f"{BASE_URL}/api/news/posts/{self.post_id}/localized?lang=en")
        assert resp.status_code == 200, f"Get localized EN failed: {resp.text}"
        data = resp.json()
        assert data["title"] == "English Title"
        assert data["content"] == "English content here"
        assert data["excerpt"] == "English excerpt"
    
    def test_get_localized_post_german(self):
        """GET /api/news/posts/{id}/localized?lang=de returns original German content"""
        # First set translations
        self.test_set_translations()
        
        resp = self.session.get(f"{BASE_URL}/api/news/posts/{self.post_id}/localized?lang=de")
        assert resp.status_code == 200, f"Get localized DE failed: {resp.text}"
        data = resp.json()
        assert data["title"] == "Deutscher Titel"
        assert data["content"] == "Deutscher Inhalt hier"
    
    def test_get_localized_post_unsupported_lang(self):
        """GET /api/news/posts/{id}/localized?lang=xx returns original content"""
        resp = self.session.get(f"{BASE_URL}/api/news/posts/{self.post_id}/localized?lang=xx")
        assert resp.status_code == 200, f"Get localized XX failed: {resp.text}"
        # Should return original post without translation
        data = resp.json()
        assert "post_id" in data
    
    # ============ SENTIMENT ANALYSIS TESTS ============
    
    def test_analyze_sentiment(self):
        """POST /api/news/analyze-sentiment analyzes texts and returns sentiment scores"""
        resp = self.session.post(f"{BASE_URL}/api/news/analyze-sentiment", json={
            "texts": [
                "This is great news! I love it!",
                "This is terrible, very disappointing.",
                "The meeting is scheduled for tomorrow."
            ]
        })
        assert resp.status_code == 200, f"Analyze sentiment failed: {resp.text}"
        data = resp.json()
        assert "results" in data
        results = data["results"]
        assert len(results) == 3
        # Each result should have sentiment and score
        for r in results:
            assert "sentiment" in r
            assert r["sentiment"] in ["positive", "neutral", "negative"]
            assert "score" in r
    
    def test_analyze_sentiment_empty_texts(self):
        """POST /api/news/analyze-sentiment validates empty texts"""
        resp = self.session.post(f"{BASE_URL}/api/news/analyze-sentiment", json={
            "texts": []
        })
        assert resp.status_code == 400, "Should reject empty texts"
    
    def test_get_post_sentiment(self):
        """GET /api/news/posts/{id}/sentiment analyzes comments of a post"""
        resp = self.session.get(f"{BASE_URL}/api/news/posts/{self.post_id}/sentiment")
        assert resp.status_code == 200, f"Get post sentiment failed: {resp.text}"
        data = resp.json()
        assert "post_id" in data
        assert "comments" in data
        assert "sentiment_summary" in data
        summary = data["sentiment_summary"]
        assert "positive" in summary
        assert "neutral" in summary
        assert "negative" in summary
    
    # ============ EXPORT FUNCTIONS TESTS ============
    
    def test_export_read_receipts_csv(self):
        """GET /api/news/posts/{id}/reads/export returns CSV with read receipts"""
        resp = self.session.get(f"{BASE_URL}/api/news/posts/{self.post_id}/reads/export")
        assert resp.status_code == 200, f"Export read receipts failed: {resp.text}"
        assert "text/csv" in resp.headers.get("Content-Type", "")
        assert "attachment" in resp.headers.get("Content-Disposition", "")
        # Verify CSV content
        content = resp.text
        assert "Benutzer" in content or "Gelesen am" in content  # CSV headers
    
    def test_export_survey_results_csv(self):
        """GET /api/surveys/{id}/export returns CSV with survey responses"""
        # First create a test survey
        survey_resp = self.session.post(f"{BASE_URL}/api/surveys", json={
            "title": "TEST_Export Survey",
            "description": "Test survey for export",
            "survey_type": "survey",
            "questions": [
                {"question_id": "q1", "text": "How satisfied are you?", "type": "scale", "scale_min": 1, "scale_max": 5}
            ],
            "status": "published",
            "target_all": True
        })
        assert survey_resp.status_code == 200, f"Create survey failed: {survey_resp.text}"
        survey_id = survey_resp.json()["survey_id"]
        
        # Export CSV
        resp = self.session.get(f"{BASE_URL}/api/surveys/{survey_id}/export")
        assert resp.status_code == 200, f"Export survey failed: {resp.text}"
        assert "text/csv" in resp.headers.get("Content-Type", "")
        assert "attachment" in resp.headers.get("Content-Disposition", "")
        # Verify CSV content
        content = resp.text
        assert "Teilnehmer" in content or "Zeitpunkt" in content  # CSV headers
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/surveys/{survey_id}")
    
    def test_export_feedback_csv(self):
        """GET /api/feedback/export returns CSV with all feedback entries"""
        resp = self.session.get(f"{BASE_URL}/api/feedback/export")
        assert resp.status_code == 200, f"Export feedback failed: {resp.text}"
        assert "text/csv" in resp.headers.get("Content-Type", "")
        assert "attachment" in resp.headers.get("Content-Disposition", "")
        # Verify CSV content
        content = resp.text
        assert "ID" in content or "Kategorie" in content  # CSV headers
    
    # ============ PERMISSION TESTS ============
    
    def test_non_editor_cannot_answer_question(self):
        """Non-editor cannot answer questions"""
        # Create a regular user session
        user_session = requests.Session()
        user_session.headers.update({"Content-Type": "application/json"})
        
        # Register a test user
        reg_resp = user_session.post(f"{BASE_URL}/api/auth/register", json={
            "email": "test_qa_user@test.com",
            "password": "testpass123",
            "name": "Test QA User"
        })
        if reg_resp.status_code == 200:
            token = reg_resp.json().get("token")
            user_session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            # User might already exist, try login
            login_resp = user_session.post(f"{BASE_URL}/api/auth/login", json={
                "email": "test_qa_user@test.com",
                "password": "testpass123"
            })
            if login_resp.status_code == 200:
                token = login_resp.json().get("token")
                user_session.headers.update({"Authorization": f"Bearer {token}"})
            else:
                pytest.skip("Could not create/login test user")
        
        # Create a question as admin
        q_id = self.test_create_question()
        
        # Try to answer as regular user
        resp = user_session.post(f"{BASE_URL}/api/news/questions/{q_id}/answer", json={
            "answer": "Unauthorized answer"
        })
        assert resp.status_code == 403, "Non-editor should not be able to answer"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/news/questions/{q_id}")
    
    def test_non_editor_cannot_set_translations(self):
        """Non-editor cannot set translations"""
        user_session = requests.Session()
        user_session.headers.update({"Content-Type": "application/json"})
        
        login_resp = user_session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test_qa_user@test.com",
            "password": "testpass123"
        })
        if login_resp.status_code != 200:
            pytest.skip("Test user not available")
        
        token = login_resp.json().get("token")
        user_session.headers.update({"Authorization": f"Bearer {token}"})
        
        resp = user_session.put(f"{BASE_URL}/api/news/posts/{self.post_id}/translations", json={
            "en": {"title": "Unauthorized", "content": "Test", "excerpt": "Test"}
        })
        assert resp.status_code == 403, "Non-editor should not be able to set translations"
    
    def test_non_editor_cannot_analyze_sentiment(self):
        """Non-editor cannot analyze sentiment"""
        user_session = requests.Session()
        user_session.headers.update({"Content-Type": "application/json"})
        
        login_resp = user_session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test_qa_user@test.com",
            "password": "testpass123"
        })
        if login_resp.status_code != 200:
            pytest.skip("Test user not available")
        
        token = login_resp.json().get("token")
        user_session.headers.update({"Authorization": f"Bearer {token}"})
        
        resp = user_session.post(f"{BASE_URL}/api/news/analyze-sentiment", json={
            "texts": ["Test text"]
        })
        assert resp.status_code == 403, "Non-editor should not be able to analyze sentiment"
    
    def test_non_editor_cannot_export_read_receipts(self):
        """Non-editor cannot export read receipts"""
        user_session = requests.Session()
        user_session.headers.update({"Content-Type": "application/json"})
        
        login_resp = user_session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test_qa_user@test.com",
            "password": "testpass123"
        })
        if login_resp.status_code != 200:
            pytest.skip("Test user not available")
        
        token = login_resp.json().get("token")
        user_session.headers.update({"Authorization": f"Bearer {token}"})
        
        resp = user_session.get(f"{BASE_URL}/api/news/posts/{self.post_id}/reads/export")
        assert resp.status_code == 403, "Non-editor should not be able to export read receipts"
    
    # ============ CLEANUP ============
    
    def test_cleanup_test_questions(self):
        """Cleanup any remaining test questions"""
        questions = self.session.get(f"{BASE_URL}/api/news/posts/{self.post_id}/questions").json()
        for q in questions:
            if q.get("text", "").startswith("TEST_"):
                self.session.delete(f"{BASE_URL}/api/news/questions/{q['question_id']}")
        print("Cleanup completed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
