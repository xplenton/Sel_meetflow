"""
Test suite for Audit Trail PDF Export feature
Tests the GET /api/meetings/{meeting_id}/documents/{doc_id}/audit-log/pdf endpoint
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuditPdfExport:
    """Tests for Audit Trail PDF Export endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.user = login_resp.json()
        # Use existing test data from iteration_20
        self.test_meeting_id = "meet_9ed4c75edc"
        self.test_doc_id = "doc_937022119e"
    
    def test_pdf_export_returns_valid_pdf(self):
        """Test that PDF export endpoint returns a valid PDF file"""
        response = self.session.get(
            f"{BASE_URL}/api/meetings/{self.test_meeting_id}/documents/{self.test_doc_id}/audit-log/pdf"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Check Content-Type is PDF
        content_type = response.headers.get('Content-Type', '')
        assert 'application/pdf' in content_type, f"Expected application/pdf, got {content_type}"
        
        # Check Content-Disposition header
        content_disp = response.headers.get('Content-Disposition', '')
        assert 'attachment' in content_disp, f"Expected attachment disposition, got {content_disp}"
        assert 'audit_trail_' in content_disp, f"Expected audit_trail_ in filename, got {content_disp}"
        
        # Check PDF magic bytes (%PDF-)
        content = response.content
        assert content[:5] == b'%PDF-', f"Expected PDF magic bytes, got {content[:20]}"
        
        # Check reasonable file size (should be at least 1KB for a valid PDF)
        assert len(content) > 1000, f"PDF too small: {len(content)} bytes"
        print(f"PDF export successful: {len(content)} bytes, Content-Type: {content_type}")
    
    def test_pdf_export_requires_authentication(self):
        """Test that PDF export endpoint requires authentication (401 for unauthenticated)"""
        # Create new session without auth
        unauth_session = requests.Session()
        response = unauth_session.get(
            f"{BASE_URL}/api/meetings/{self.test_meeting_id}/documents/{self.test_doc_id}/audit-log/pdf"
        )
        assert response.status_code == 401, f"Expected 401 for unauthenticated, got {response.status_code}"
        print("Authentication check passed: 401 returned for unauthenticated request")
    
    def test_pdf_export_returns_404_for_nonexistent_document(self):
        """Test that PDF export returns 404 for non-existent document"""
        response = self.session.get(
            f"{BASE_URL}/api/meetings/{self.test_meeting_id}/documents/nonexistent_doc_id/audit-log/pdf"
        )
        assert response.status_code == 404, f"Expected 404 for non-existent doc, got {response.status_code}"
        print("404 check passed: Non-existent document returns 404")
    
    def test_pdf_export_returns_404_for_nonexistent_meeting(self):
        """Test that PDF export returns 404 for non-existent meeting"""
        response = self.session.get(
            f"{BASE_URL}/api/meetings/nonexistent_meeting_id/documents/{self.test_doc_id}/audit-log/pdf"
        )
        # Should return 404 since document won't be found in non-existent meeting
        assert response.status_code == 404, f"Expected 404 for non-existent meeting, got {response.status_code}"
        print("404 check passed: Non-existent meeting returns 404")
    
    def test_pdf_contains_expected_content(self):
        """Test that PDF contains expected audit trail data by checking file structure"""
        response = self.session.get(
            f"{BASE_URL}/api/meetings/{self.test_meeting_id}/documents/{self.test_doc_id}/audit-log/pdf"
        )
        assert response.status_code == 200
        
        content = response.content
        # PDF should contain text streams with our expected content
        # Check for PDF structure markers
        assert b'%PDF-' in content, "Missing PDF header"
        assert b'%%EOF' in content, "Missing PDF EOF marker"
        
        # Check for ReportLab generated content markers
        assert b'/Type /Page' in content or b'/Type/Page' in content, "Missing page definition"
        
        print(f"PDF structure validated: {len(content)} bytes")
    
    def test_audit_log_endpoint_still_works(self):
        """Verify the regular audit log endpoint still works (regression test)"""
        response = self.session.get(
            f"{BASE_URL}/api/meetings/{self.test_meeting_id}/documents/{self.test_doc_id}/audit-log"
        )
        assert response.status_code == 200, f"Audit log endpoint failed: {response.status_code}"
        
        logs = response.json()
        assert isinstance(logs, list), "Expected list of audit logs"
        print(f"Regular audit log endpoint works: {len(logs)} entries")


class TestAuditPdfExportWithNewDocument:
    """Tests PDF export with a freshly created document"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session and create test data"""
        self.session = requests.Session()
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.user = login_resp.json()
        self.created_meeting_id = None
        self.created_doc_id = None
    
    def teardown_method(self, method):
        """Cleanup test data"""
        if self.created_meeting_id:
            try:
                self.session.delete(f"{BASE_URL}/api/meetings/{self.created_meeting_id}")
            except:
                pass
    
    def test_pdf_export_with_empty_audit_log(self):
        """Test PDF export works even with minimal/empty audit log"""
        # Create a test meeting
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_PDF_Export_Meeting",
            "meeting_type": "instant"
        })
        assert meeting_resp.status_code == 200, f"Meeting creation failed: {meeting_resp.text}"
        meeting = meeting_resp.json()
        self.created_meeting_id = meeting["meeting_id"]
        
        # Upload a test document
        import io
        test_content = b"Test PDF content for audit trail export testing"
        files = {'file': ('TEST_audit_export.pdf', io.BytesIO(test_content), 'application/pdf')}
        doc_resp = self.session.post(
            f"{BASE_URL}/api/meetings/{self.created_meeting_id}/documents",
            files=files
        )
        assert doc_resp.status_code == 200, f"Document upload failed: {doc_resp.text}"
        doc = doc_resp.json()
        self.created_doc_id = doc["doc_id"]
        
        # Export PDF - should work even with just the upload entry
        pdf_resp = self.session.get(
            f"{BASE_URL}/api/meetings/{self.created_meeting_id}/documents/{self.created_doc_id}/audit-log/pdf"
        )
        assert pdf_resp.status_code == 200, f"PDF export failed: {pdf_resp.status_code}"
        assert pdf_resp.content[:5] == b'%PDF-', "Invalid PDF format"
        print(f"PDF export with new document successful: {len(pdf_resp.content)} bytes")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
