"""
Test Attendance Report Feature
- GET /api/meetings/{meeting_id}/attendance-report - JSON report
- GET /api/meetings/{meeting_id}/attendance-report/pdf - PDF export
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAttendanceReport:
    """Attendance Report API tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.user = login_resp.json()
        print(f"Logged in as: {self.user.get('email')}")
    
    def test_attendance_report_requires_auth(self):
        """Test that attendance report requires authentication"""
        # Use fresh session without cookies
        resp = requests.get(f"{BASE_URL}/api/meetings/meet_044aab394f/attendance-report")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: Attendance report requires authentication (401)")
    
    def test_attendance_report_pdf_requires_auth(self):
        """Test that PDF export requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/meetings/meet_044aab394f/attendance-report/pdf")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: PDF export requires authentication (401)")
    
    def test_attendance_report_not_found(self):
        """Test 404 for non-existent meeting"""
        resp = self.session.get(f"{BASE_URL}/api/meetings/nonexistent_meeting_id/attendance-report")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("PASS: Non-existent meeting returns 404")
    
    def test_attendance_report_pdf_not_found(self):
        """Test 404 for PDF of non-existent meeting"""
        resp = self.session.get(f"{BASE_URL}/api/meetings/nonexistent_meeting_id/attendance-report/pdf")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("PASS: PDF for non-existent meeting returns 404")
    
    def test_attendance_report_json_structure(self):
        """Test attendance report JSON structure and data"""
        # First get list of meetings to find a valid one
        meetings_resp = self.session.get(f"{BASE_URL}/api/meetings?limit=5")
        assert meetings_resp.status_code == 200
        meetings = meetings_resp.json().get('meetings', [])
        
        if not meetings:
            pytest.skip("No meetings available for testing")
        
        meeting_id = meetings[0]['meeting_id']
        print(f"Testing with meeting: {meeting_id}")
        
        resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}/attendance-report")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        
        # Verify top-level structure
        assert 'meeting_id' in data, "Missing meeting_id"
        assert 'title' in data, "Missing title"
        assert 'total_participants' in data, "Missing total_participants"
        assert 'active_participants' in data, "Missing active_participants"
        assert 'total_chat_messages' in data, "Missing total_chat_messages"
        assert 'total_documents' in data, "Missing total_documents"
        assert 'participants' in data, "Missing participants array"
        
        print(f"Report structure valid - {data['total_participants']} participants, {data['total_chat_messages']} chat messages")
        
        # Verify participant structure if any exist
        if data['participants']:
            p = data['participants'][0]
            assert 'name' in p, "Participant missing name"
            assert 'email' in p, "Participant missing email"
            assert 'role' in p, "Participant missing role"
            assert 'joined_at' in p, "Participant missing joined_at"
            assert 'left_at' in p, "Participant missing left_at"
            assert 'duration_minutes' in p, "Participant missing duration_minutes"
            assert 'chat_messages' in p, "Participant missing chat_messages"
            assert 'signatures' in p, "Participant missing signatures"
            assert 'status' in p, "Participant missing status"
            
            # Verify status is one of expected values
            assert p['status'] in ['aktiv', 'verlassen', 'abwesend'], f"Invalid status: {p['status']}"
            
            print(f"Participant structure valid - {p['name']} ({p['status']})")
        
        print("PASS: Attendance report JSON structure is correct")
    
    def test_attendance_report_pdf_download(self):
        """Test PDF export returns valid PDF"""
        # Get a valid meeting
        meetings_resp = self.session.get(f"{BASE_URL}/api/meetings?limit=5")
        assert meetings_resp.status_code == 200
        meetings = meetings_resp.json().get('meetings', [])
        
        if not meetings:
            pytest.skip("No meetings available for testing")
        
        meeting_id = meetings[0]['meeting_id']
        
        resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}/attendance-report/pdf")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        # Verify content type
        content_type = resp.headers.get('content-type', '')
        assert 'application/pdf' in content_type, f"Expected PDF content type, got: {content_type}"
        
        # Verify content disposition header
        content_disp = resp.headers.get('content-disposition', '')
        assert 'attachment' in content_disp, f"Expected attachment disposition, got: {content_disp}"
        assert 'anwesenheit' in content_disp.lower(), f"Expected 'anwesenheit' in filename, got: {content_disp}"
        
        # Verify PDF magic bytes
        content = resp.content
        assert content[:4] == b'%PDF', "Content doesn't start with PDF magic bytes"
        assert len(content) > 1000, f"PDF seems too small: {len(content)} bytes"
        
        print(f"PASS: PDF export works - {len(content)} bytes, filename in header")
    
    def test_attendance_report_with_test_meeting(self):
        """Test with the known test meeting meet_044aab394f"""
        test_meeting_id = "meet_044aab394f"
        
        resp = self.session.get(f"{BASE_URL}/api/meetings/{test_meeting_id}/attendance-report")
        
        if resp.status_code == 404:
            print(f"Test meeting {test_meeting_id} not found - skipping specific test")
            pytest.skip("Test meeting not found")
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        
        print(f"Test meeting report: {data['total_participants']} participants, {data['total_chat_messages']} chat, {data['total_documents']} docs")
        
        # Verify expected data from test meeting (1 participant, 3 chat messages, 1 document, 3 signatures)
        assert data['total_participants'] >= 1, "Expected at least 1 participant"
        
        print("PASS: Test meeting attendance report retrieved successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
