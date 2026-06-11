"""
Test suite for Meeting Summary Email feature (Iteration 12)
Tests:
- GET /api/meetings/{id}/summary - returns meeting info, summary content, participants, email_sent status
- POST /api/meetings/{id}/ai/summarize - generates AI summary via GPT-5.2 and stores it
- POST /api/meetings/{id}/send-summary-email - generates summary (if not exists), sends to all participants
- send-summary-email requires host or admin role (403 for others)
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSummaryEmailFeature:
    """Tests for the meeting summary email feature"""
    
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
        self.admin_user = login_resp.json()
        
        # Create a test user session for permission tests
        self.test_session = requests.Session()
        self.test_session.headers.update({"Content-Type": "application/json"})
        
        # Register or login test user
        test_email = f"test_summary_{uuid.uuid4().hex[:6]}@test.com"
        reg_resp = self.test_session.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "test123",
            "name": "Test Summary User"
        })
        if reg_resp.status_code != 200:
            # User might exist, try login
            login_resp = self.test_session.post(f"{BASE_URL}/api/auth/login", json={
                "email": test_email,
                "password": "test123"
            })
        
        yield
        
        # Cleanup - no specific cleanup needed as we use unique test data
    
    # ============ GET /api/meetings/{id}/summary Tests ============
    
    def test_get_summary_returns_meeting_info(self):
        """GET /api/meetings/{id}/summary returns meeting info with all required fields"""
        # Use the known ended meeting with summary
        meeting_id = "meet_8afa2e15ca"
        
        response = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}/summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify meeting info is present
        assert "meeting" in data, "Response should contain 'meeting' field"
        meeting = data["meeting"]
        assert "meeting_id" in meeting
        assert "title" in meeting
        assert meeting["meeting_id"] == meeting_id
        
        # Verify summary content
        assert "summary" in data, "Response should contain 'summary' field"
        
        # Verify participants
        assert "participants" in data, "Response should contain 'participants' field"
        assert isinstance(data["participants"], list)
        
        # Verify email_sent status
        assert "email_sent" in data, "Response should contain 'email_sent' field"
        assert isinstance(data["email_sent"], bool)
        
        print(f"✓ GET /api/meetings/{meeting_id}/summary returns all required fields")
    
    def test_get_summary_includes_summary_id(self):
        """GET /api/meetings/{id}/summary includes summary_id when summary exists"""
        meeting_id = "meet_8afa2e15ca"
        
        response = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}/summary")
        assert response.status_code == 200
        
        data = response.json()
        
        # If summary exists, summary_id should be present
        if data.get("summary"):
            assert "summary_id" in data, "summary_id should be present when summary exists"
            assert data["summary_id"] is not None
            print(f"✓ Summary ID present: {data['summary_id']}")
        else:
            print("✓ No summary exists yet (summary_id is None)")
    
    def test_get_summary_404_for_nonexistent_meeting(self):
        """GET /api/meetings/{id}/summary returns 404 for non-existent meeting"""
        response = self.session.get(f"{BASE_URL}/api/meetings/nonexistent_meeting_id/summary")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ GET /api/meetings/nonexistent/summary returns 404")
    
    def test_get_summary_requires_auth(self):
        """GET /api/meetings/{id}/summary requires authentication"""
        unauthenticated_session = requests.Session()
        response = unauthenticated_session.get(f"{BASE_URL}/api/meetings/meet_8afa2e15ca/summary")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ GET /api/meetings/{id}/summary requires authentication")
    
    # ============ POST /api/meetings/{id}/ai/summarize Tests ============
    
    def test_ai_summarize_generates_summary(self):
        """POST /api/meetings/{id}/ai/summarize generates AI summary and stores it"""
        # Use an ended meeting without summary
        meeting_id = "meet_9e67b028a5"
        
        response = self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/ai/summarize")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert "summary" in data, "Response should contain 'summary' field"
        assert "summary_id" in data, "Response should contain 'summary_id' field"
        assert data["summary"] is not None and len(data["summary"]) > 0, "Summary should not be empty"
        assert data["summary_id"].startswith("sum_"), "Summary ID should start with 'sum_'"
        
        print(f"✓ AI summary generated successfully, ID: {data['summary_id']}")
        print(f"  Summary preview: {data['summary'][:100]}...")
    
    def test_ai_summarize_404_for_nonexistent_meeting(self):
        """POST /api/meetings/{id}/ai/summarize returns 404 for non-existent meeting"""
        response = self.session.post(f"{BASE_URL}/api/meetings/nonexistent_meeting/ai/summarize")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ POST /api/meetings/nonexistent/ai/summarize returns 404")
    
    def test_ai_summarize_requires_auth(self):
        """POST /api/meetings/{id}/ai/summarize requires authentication"""
        unauthenticated_session = requests.Session()
        response = unauthenticated_session.post(f"{BASE_URL}/api/meetings/meet_8afa2e15ca/ai/summarize")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ POST /api/meetings/{id}/ai/summarize requires authentication")
    
    # ============ POST /api/meetings/{id}/send-summary-email Tests ============
    
    def test_send_summary_email_as_host(self):
        """POST /api/meetings/{id}/send-summary-email works for host"""
        meeting_id = "meet_8afa2e15ca"
        
        response = self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/send-summary-email")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert "message" in data, "Response should contain 'message' field"
        assert "sent_to" in data, "Response should contain 'sent_to' field"
        assert isinstance(data["sent_to"], int), "sent_to should be an integer"
        assert "summary" in data, "Response should contain 'summary' field"
        
        print(f"✓ Summary email sent to {data['sent_to']} participants")
    
    def test_send_summary_email_generates_if_not_exists(self):
        """POST /api/meetings/{id}/send-summary-email generates summary if not exists"""
        # Create a new meeting to test this
        create_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Summary_Email_Test",
            "meeting_type": "instant"
        })
        assert create_resp.status_code == 200
        meeting_id = create_resp.json()["meeting_id"]
        
        # End the meeting
        self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/leave")
        
        # Send summary email (should generate summary first)
        response = self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/send-summary-email")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "summary" in data, "Response should contain generated summary"
        assert data["summary"] is not None, "Summary should be generated"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
        
        print("✓ send-summary-email generates summary if not exists")
    
    def test_send_summary_email_403_for_non_host(self):
        """POST /api/meetings/{id}/send-summary-email returns 403 for non-host/non-admin"""
        meeting_id = "meet_8afa2e15ca"
        
        response = self.test_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/send-summary-email")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data
        assert "host" in data["detail"].lower() or "admin" in data["detail"].lower()
        
        print("✓ send-summary-email returns 403 for non-host/non-admin users")
    
    def test_send_summary_email_404_for_nonexistent_meeting(self):
        """POST /api/meetings/{id}/send-summary-email returns 404 for non-existent meeting"""
        response = self.session.post(f"{BASE_URL}/api/meetings/nonexistent_meeting/send-summary-email")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ POST /api/meetings/nonexistent/send-summary-email returns 404")
    
    def test_send_summary_email_requires_auth(self):
        """POST /api/meetings/{id}/send-summary-email requires authentication"""
        unauthenticated_session = requests.Session()
        response = unauthenticated_session.post(f"{BASE_URL}/api/meetings/meet_8afa2e15ca/send-summary-email")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ POST /api/meetings/{id}/send-summary-email requires authentication")
    
    # ============ Email Sent Status Tests ============
    
    def test_email_sent_status_updated_after_send(self):
        """Verify email_sent status is updated after sending summary email"""
        meeting_id = "meet_8afa2e15ca"
        
        # Send summary email
        send_resp = self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/send-summary-email")
        assert send_resp.status_code == 200
        
        # Get summary and verify email_sent is true
        summary_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}/summary")
        assert summary_resp.status_code == 200
        
        data = summary_resp.json()
        assert data["email_sent"] == True, "email_sent should be True after sending"
        
        print("✓ email_sent status is True after sending summary email")
    
    # ============ Participant Data Tests ============
    
    def test_summary_includes_participant_details(self):
        """GET /api/meetings/{id}/summary includes participant details"""
        meeting_id = "meet_8afa2e15ca"
        
        response = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}/summary")
        assert response.status_code == 200
        
        data = response.json()
        participants = data.get("participants", [])
        
        assert len(participants) > 0, "Should have at least one participant"
        
        # Verify participant structure
        participant = participants[0]
        assert "user_id" in participant
        assert "name" in participant
        assert "email" in participant
        assert "role" in participant
        
        print(f"✓ Summary includes {len(participants)} participant(s) with full details")


class TestSummaryMarkdownContent:
    """Tests for AI summary content structure"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        yield
    
    def test_summary_contains_markdown_formatting(self):
        """AI summary should contain markdown formatting (headings, bold, lists)"""
        meeting_id = "meet_8afa2e15ca"
        
        response = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}/summary")
        assert response.status_code == 200
        
        data = response.json()
        summary = data.get("summary", "")
        
        if summary:
            # Check for common markdown elements
            has_headings = "##" in summary or "#" in summary
            has_bold = "**" in summary
            has_lists = "- " in summary or "* " in summary
            
            print("✓ Summary markdown check:")
            print(f"  - Has headings: {has_headings}")
            print(f"  - Has bold text: {has_bold}")
            print(f"  - Has lists: {has_lists}")
            
            # At least one markdown element should be present
            assert has_headings or has_bold or has_lists, "Summary should contain some markdown formatting"
        else:
            print("⚠ No summary content to check")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
