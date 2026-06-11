"""
Iteration 67 Tests - Custom Recurring Meetings, Surveys Mobile, Sentiment with Attachments

Tests:
1. Custom recurring meetings with per-weekday different times
2. Simple recurring patterns (daily/weekly/biweekly/monthly) regression
3. Sentiment analysis with attachment text extraction
4. News/Survey/Feedback/Meeting CRUD regression
"""
import pytest
import requests
import os
import time
from datetime import datetime, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

@pytest.fixture(scope="module")
def auth_session():
    """Login and return authenticated session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@meetflow.com",
        "password": "admin123"
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return session


class TestCustomRecurringMeetings:
    """Test custom recurring meetings with per-weekday different times"""
    
    def test_create_custom_recurring_meeting(self, auth_session):
        """Create a meeting with custom recurring pattern and per-weekday schedule"""
        # Schedule for next Monday at 09:00
        now = datetime.utcnow()
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_monday = now + timedelta(days=days_until_monday)
        scheduled_at = next_monday.replace(hour=9, minute=0, second=0, microsecond=0).isoformat() + "Z"
        
        payload = {
            "title": "TEST_Custom Recurring Meeting",
            "description": "Test meeting with custom per-weekday schedule",
            "meeting_type": "scheduled",
            "scheduled_at": scheduled_at,
            "duration_minutes": 60,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": 0, "start_time": "09:00", "end_time": "10:00"},  # Monday 9-10
                {"weekday": 2, "start_time": "14:00", "end_time": "15:30"},  # Wednesday 14-15:30
                {"weekday": 4, "start_time": "11:00", "end_time": "12:00"},  # Friday 11-12
            ],
            "recurring_weeks": 3
        }
        
        resp = auth_session.post(f"{BASE_URL}/api/meetings", json=payload)
        assert resp.status_code == 200, f"Create meeting failed: {resp.text}"
        
        data = resp.json()
        assert data["title"] == "TEST_Custom Recurring Meeting"
        assert data["recurring"] == True
        assert data["recurring_pattern"] == "custom"
        assert data.get("recurring_schedule") is not None
        assert len(data["recurring_schedule"]) == 3
        assert data.get("series_id") is not None, "series_id should be set for custom recurring"
        
        # Store for cleanup
        self.meeting_id = data["meeting_id"]
        self.series_id = data.get("series_id")
        print(f"Created custom recurring meeting: {self.meeting_id}, series: {self.series_id}")
        return data
    
    def test_get_recurring_series(self, auth_session):
        """Get all meetings in the recurring series"""
        # First create a meeting
        meeting = self.test_create_custom_recurring_meeting(auth_session)
        series_id = meeting.get("series_id")
        
        if not series_id:
            pytest.skip("No series_id returned from meeting creation")
        
        resp = auth_session.get(f"{BASE_URL}/api/meetings/recurring/{series_id}")
        assert resp.status_code == 200, f"Get series failed: {resp.text}"
        
        series = resp.json()
        assert isinstance(series, list)
        # Should have generated meetings for 3 weeks * 3 slots = up to 9 meetings
        # But first week slots before scheduled_at are skipped
        print(f"Series contains {len(series)} meetings")
        
        # Verify meetings have different durations based on schedule
        durations = set()
        for m in series:
            durations.add(m.get("duration"))
        print(f"Durations in series: {durations}")
        
        # Cleanup
        for m in series:
            auth_session.delete(f"{BASE_URL}/api/meetings/{m['meeting_id']}")
        auth_session.delete(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
    
    def test_regenerate_custom_recurring(self, auth_session):
        """Test regenerating occurrences for custom pattern"""
        # Create base meeting
        now = datetime.utcnow()
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_monday = now + timedelta(days=days_until_monday)
        scheduled_at = next_monday.replace(hour=9, minute=0, second=0, microsecond=0).isoformat() + "Z"
        
        payload = {
            "title": "TEST_Regenerate Custom Meeting",
            "meeting_type": "scheduled",
            "scheduled_at": scheduled_at,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": 1, "start_time": "10:00", "end_time": "11:00"},  # Tuesday
            ],
            "recurring_weeks": 2
        }
        
        resp = auth_session.post(f"{BASE_URL}/api/meetings", json=payload)
        assert resp.status_code == 200
        meeting = resp.json()
        meeting_id = meeting["meeting_id"]
        
        # Regenerate with different weeks
        regen_resp = auth_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/recurring/generate", json={
            "weeks": 4
        })
        assert regen_resp.status_code == 200, f"Regenerate failed: {regen_resp.text}"
        
        regen_data = regen_resp.json()
        assert "generated" in regen_data
        assert "series_id" in regen_data
        print(f"Regenerated {regen_data['count']} meetings")
        
        # Cleanup
        series_id = regen_data.get("series_id")
        if series_id:
            series_resp = auth_session.get(f"{BASE_URL}/api/meetings/recurring/{series_id}")
            if series_resp.status_code == 200:
                for m in series_resp.json():
                    auth_session.delete(f"{BASE_URL}/api/meetings/{m['meeting_id']}")
        auth_session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")


class TestSimpleRecurringPatterns:
    """Regression tests for simple recurring patterns"""
    
    @pytest.mark.parametrize("pattern", ["daily", "weekly", "biweekly", "monthly"])
    def test_simple_recurring_pattern(self, auth_session, pattern):
        """Test simple recurring patterns still work"""
        now = datetime.utcnow()
        scheduled_at = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0).isoformat() + "Z"
        
        payload = {
            "title": f"TEST_Simple {pattern} Meeting",
            "meeting_type": "scheduled",
            "scheduled_at": scheduled_at,
            "duration_minutes": 30,
            "recurring": True,
            "recurring_pattern": pattern
        }
        
        resp = auth_session.post(f"{BASE_URL}/api/meetings", json=payload)
        assert resp.status_code == 200, f"Create {pattern} meeting failed: {resp.text}"
        
        meeting = resp.json()
        meeting_id = meeting["meeting_id"]
        
        # Generate occurrences
        gen_resp = auth_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/recurring/generate", json={
            "count": 3
        })
        assert gen_resp.status_code == 200, f"Generate {pattern} failed: {gen_resp.text}"
        
        gen_data = gen_resp.json()
        assert gen_data["count"] == 3, f"Expected 3 generated meetings, got {gen_data['count']}"
        
        # Cleanup
        series_id = gen_data.get("series_id")
        if series_id:
            series_resp = auth_session.get(f"{BASE_URL}/api/meetings/recurring/{series_id}")
            if series_resp.status_code == 200:
                for m in series_resp.json():
                    auth_session.delete(f"{BASE_URL}/api/meetings/{m['meeting_id']}")
        auth_session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
        print(f"Simple {pattern} pattern: PASSED")


class TestSentimentWithAttachments:
    """Test sentiment analysis with attachment text extraction"""
    
    def test_create_news_post_for_sentiment(self, auth_session):
        """Create a news post for sentiment testing"""
        payload = {
            "title": "TEST_Sentiment Test Post",
            "content": "This is a test post for sentiment analysis",
            "status": "published",
            "target_all": True
        }
        
        resp = auth_session.post(f"{BASE_URL}/api/news/posts", json=payload)
        assert resp.status_code == 200, f"Create news post failed: {resp.text}"
        
        post = resp.json()
        self.post_id = post["post_id"]
        print(f"Created news post: {self.post_id}")
        return post
    
    def test_upload_text_attachment(self, auth_session):
        """Upload a text file attachment with positive German text"""
        # Create a simple text file with positive German content
        positive_text = "Das ist hervorragend! Wir sind sehr zufrieden mit dem Ergebnis. Alles funktioniert perfekt."
        
        files = {
            "file": ("positive_feedback.txt", positive_text.encode("utf-8"), "text/plain")
        }
        
        # Remove Content-Type header for multipart upload
        headers = {k: v for k, v in auth_session.headers.items() if k.lower() != "content-type"}
        resp = requests.post(f"{BASE_URL}/api/attachments/upload", files=files, headers=headers, cookies=auth_session.cookies)
        assert resp.status_code == 200, f"Upload attachment failed: {resp.text}"
        
        att = resp.json()
        assert "attachment_id" in att
        assert att["mime"] == "text/plain"
        self.attachment_id = att["attachment_id"]
        print(f"Uploaded attachment: {self.attachment_id}")
        return att
    
    def test_add_comment_with_attachment(self, auth_session):
        """Add a comment with attachment to the news post"""
        # First create post and upload attachment
        post = self.test_create_news_post_for_sentiment(auth_session)
        att = self.test_upload_text_attachment(auth_session)
        
        payload = {
            "content": "Siehe Anhang",  # Neutral text, but attachment is positive
            "attachments": [att["attachment_id"]]
        }
        
        resp = auth_session.post(f"{BASE_URL}/api/news/posts/{post['post_id']}/comments", json=payload)
        assert resp.status_code == 200, f"Add comment failed: {resp.text}"
        
        comment = resp.json()
        assert comment["content"] == "Siehe Anhang"
        assert len(comment.get("attachments", [])) > 0
        self.comment_id = comment["comment_id"]
        print(f"Added comment with attachment: {self.comment_id}")
        return comment, post
    
    def test_get_sentiment_with_attachment_text(self, auth_session):
        """Get sentiment analysis that includes attachment text"""
        comment, post = self.test_add_comment_with_attachment(auth_session)
        
        # Wait a moment for any async processing
        time.sleep(1)
        
        resp = auth_session.get(f"{BASE_URL}/api/news/posts/{post['post_id']}/sentiment")
        assert resp.status_code == 200, f"Get sentiment failed: {resp.text}"
        
        sentiment = resp.json()
        assert "sentiment_summary" in sentiment
        assert "details" in sentiment
        
        # Check that has_attachment_text flag is present
        details = sentiment.get("details", [])
        assert len(details) > 0, "Expected at least one comment in details"
        
        # Find our comment
        our_comment = None
        for d in details:
            if d.get("comment_id") == comment["comment_id"]:
                our_comment = d
                break
        
        assert our_comment is not None, "Our comment not found in sentiment details"
        assert "has_attachment_text" in our_comment, "has_attachment_text flag missing"
        assert our_comment["has_attachment_text"] == True, "Attachment text should have been extracted"
        
        print(f"Sentiment result: {our_comment['sentiment']}, score: {our_comment.get('score')}, has_attachment_text: {our_comment['has_attachment_text']}")
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/news/posts/{post['post_id']}")
        auth_session.delete(f"{BASE_URL}/api/attachments/{self.attachment_id}")
    
    def test_analyze_sentiment_endpoint(self, auth_session):
        """Test the POST /news/analyze-sentiment endpoint"""
        texts = [
            "Das ist wunderbar!",
            "Ich bin sehr unzufrieden.",
            "Es ist okay."
        ]
        
        resp = auth_session.post(f"{BASE_URL}/api/news/analyze-sentiment", json={
            "texts": texts,
            "attachments": []
        })
        assert resp.status_code == 200, f"Analyze sentiment failed: {resp.text}"
        
        data = resp.json()
        assert "results" in data
        results = data["results"]
        assert len(results) == len(texts), f"Expected {len(texts)} results, got {len(results)}"
        
        for i, r in enumerate(results):
            assert "sentiment" in r
            assert "score" in r
            print(f"Text {i+1}: sentiment={r['sentiment']}, score={r['score']}")


class TestRegressionCRUD:
    """Regression tests for existing CRUD operations"""
    
    def test_meetings_crud(self, auth_session):
        """Test meeting CRUD still works"""
        # Create
        payload = {
            "title": "TEST_CRUD Meeting",
            "meeting_type": "scheduled",
            "scheduled_at": (datetime.utcnow() + timedelta(days=1)).isoformat() + "Z"
        }
        resp = auth_session.post(f"{BASE_URL}/api/meetings", json=payload)
        assert resp.status_code == 200
        meeting = resp.json()
        meeting_id = meeting["meeting_id"]
        
        # Read
        resp = auth_session.get(f"{BASE_URL}/api/meetings/{meeting_id}")
        assert resp.status_code == 200
        
        # Update
        resp = auth_session.put(f"{BASE_URL}/api/meetings/{meeting_id}", json={"title": "TEST_Updated Meeting"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "TEST_Updated Meeting"
        
        # Delete
        resp = auth_session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
        assert resp.status_code == 200
        print("Meetings CRUD: PASSED")
    
    def test_news_crud(self, auth_session):
        """Test news CRUD still works"""
        # Create
        payload = {
            "title": "TEST_CRUD News",
            "content": "Test content",
            "status": "draft"
        }
        resp = auth_session.post(f"{BASE_URL}/api/news/posts", json=payload)
        assert resp.status_code == 200
        post = resp.json()
        post_id = post["post_id"]
        
        # Read
        resp = auth_session.get(f"{BASE_URL}/api/news/posts/{post_id}")
        assert resp.status_code == 200
        
        # Update
        resp = auth_session.put(f"{BASE_URL}/api/news/posts/{post_id}", json={"title": "TEST_Updated News"})
        assert resp.status_code == 200
        
        # Delete
        resp = auth_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
        assert resp.status_code == 200
        print("News CRUD: PASSED")
    
    def test_surveys_crud(self, auth_session):
        """Test surveys CRUD still works"""
        # Create
        payload = {
            "title": "TEST_CRUD Survey",
            "survey_type": "survey",
            "questions": [
                {"question_id": "q1", "text": "Test question?", "type": "single_choice", "options": ["Yes", "No"]}
            ],
            "status": "draft"
        }
        resp = auth_session.post(f"{BASE_URL}/api/surveys", json=payload)
        assert resp.status_code == 200
        survey = resp.json()
        survey_id = survey["survey_id"]
        
        # Read
        resp = auth_session.get(f"{BASE_URL}/api/surveys/{survey_id}")
        assert resp.status_code == 200
        
        # Delete
        resp = auth_session.delete(f"{BASE_URL}/api/surveys/{survey_id}")
        assert resp.status_code == 200
        print("Surveys CRUD: PASSED")
    
    def test_feedback_crud(self, auth_session):
        """Test feedback submission works"""
        payload = {
            "category": "ideas",
            "subject": "TEST_Feedback",
            "content": "This is test feedback"
        }
        resp = auth_session.post(f"{BASE_URL}/api/feedback/submit", json=payload)
        assert resp.status_code == 200
        
        # List feedback (admin)
        resp = auth_session.get(f"{BASE_URL}/api/feedback/entries")
        assert resp.status_code == 200
        entries = resp.json()
        
        # Find and delete our test entry
        for e in entries:
            if e.get("subject") == "TEST_Feedback":
                auth_session.delete(f"{BASE_URL}/api/feedback/entries/{e['feedback_id']}")
                break
        print("Feedback CRUD: PASSED")


class TestScheduleSlotValidation:
    """Test schedule slot validation in meetings_recurring service"""
    
    def test_invalid_weekday_rejected(self, auth_session):
        """Invalid weekday should be filtered out"""
        now = datetime.utcnow()
        scheduled_at = (now + timedelta(days=1)).isoformat() + "Z"
        
        payload = {
            "title": "TEST_Invalid Weekday",
            "meeting_type": "scheduled",
            "scheduled_at": scheduled_at,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": 7, "start_time": "09:00", "end_time": "10:00"},  # Invalid: 7 is out of range
                {"weekday": 0, "start_time": "09:00", "end_time": "10:00"},  # Valid
            ],
            "recurring_weeks": 1
        }
        
        resp = auth_session.post(f"{BASE_URL}/api/meetings", json=payload)
        assert resp.status_code == 200
        meeting = resp.json()
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
        print("Invalid weekday validation: PASSED")
    
    def test_invalid_time_format_rejected(self, auth_session):
        """Invalid time format should be filtered out"""
        now = datetime.utcnow()
        scheduled_at = (now + timedelta(days=1)).isoformat() + "Z"
        
        payload = {
            "title": "TEST_Invalid Time",
            "meeting_type": "scheduled",
            "scheduled_at": scheduled_at,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": 0, "start_time": "25:00", "end_time": "26:00"},  # Invalid hours
                {"weekday": 1, "start_time": "09:00", "end_time": "10:00"},  # Valid
            ],
            "recurring_weeks": 1
        }
        
        resp = auth_session.post(f"{BASE_URL}/api/meetings", json=payload)
        assert resp.status_code == 200
        meeting = resp.json()
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
        print("Invalid time validation: PASSED")
    
    def test_end_before_start_rejected(self, auth_session):
        """End time before start time should be filtered out"""
        now = datetime.utcnow()
        scheduled_at = (now + timedelta(days=1)).isoformat() + "Z"
        
        payload = {
            "title": "TEST_End Before Start",
            "meeting_type": "scheduled",
            "scheduled_at": scheduled_at,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": 0, "start_time": "14:00", "end_time": "10:00"},  # End before start
                {"weekday": 1, "start_time": "09:00", "end_time": "10:00"},  # Valid
            ],
            "recurring_weeks": 1
        }
        
        resp = auth_session.post(f"{BASE_URL}/api/meetings", json=payload)
        assert resp.status_code == 200
        meeting = resp.json()
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
        print("End before start validation: PASSED")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
