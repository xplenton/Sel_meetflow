"""
Test suite for MeetFlow Signature Position and Download-Signed features
Tests:
1. POST /api/meetings/{meeting_id}/documents/{doc_id}/sign - accepts pos_x, pos_y, page fields
2. GET /api/meetings/{meeting_id}/documents/{doc_id}/download-signed - returns valid PDF with signatures
3. Download-signed endpoint requires auth (401)
4. Download-signed returns 404 for non-existent doc
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSignaturePositionAndDownload:
    """Tests for signature position fields and download-signed endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get session"""
        self.session = requests.Session()
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.user = login_resp.json()
        yield
        # Cleanup
        self.session.close()
    
    def test_sign_document_with_position_fields(self):
        """Test that sign endpoint accepts pos_x, pos_y, page fields"""
        # First, create a meeting
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_SignaturePosition_Meeting",
            "scheduled_time": "2026-02-01T10:00:00Z",
            "duration_minutes": 30
        })
        assert meeting_resp.status_code == 200, f"Meeting creation failed: {meeting_resp.text}"
        meeting = meeting_resp.json()
        meeting_id = meeting["meeting_id"]
        
        # Upload a test document
        files = {'file': ('test_doc.pdf', b'%PDF-1.4 test content', 'application/pdf')}
        upload_resp = self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/documents", files=files)
        assert upload_resp.status_code == 200, f"Document upload failed: {upload_resp.text}"
        doc = upload_resp.json()
        doc_id = doc["doc_id"]
        
        # Sign document with position fields
        sign_data = {
            "type": "typed",
            "signature_data": "Test Signature",
            "pos_x": 100,
            "pos_y": 200,
            "page": 2
        }
        sign_resp = self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/documents/{doc_id}/sign", json=sign_data)
        assert sign_resp.status_code == 200, f"Sign failed: {sign_resp.text}"
        result = sign_resp.json()
        assert "sig_id" in result, "Response should contain sig_id"
        assert result["message"] == "Document signed"
        print("✓ Sign endpoint accepts position fields (pos_x=100, pos_y=200, page=2)")
        
        # Verify signature was stored with position
        docs_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}/documents")
        assert docs_resp.status_code == 200
        docs = docs_resp.json()
        signed_doc = next((d for d in docs if d["doc_id"] == doc_id), None)
        assert signed_doc is not None
        assert len(signed_doc.get("signatures", [])) > 0
        sig = signed_doc["signatures"][0]
        assert sig.get("pos_x") == 100, f"pos_x should be 100, got {sig.get('pos_x')}"
        assert sig.get("pos_y") == 200, f"pos_y should be 200, got {sig.get('pos_y')}"
        assert sig.get("page") == 2, f"page should be 2, got {sig.get('page')}"
        print(f"✓ Signature stored with correct position: pos_x={sig['pos_x']}, pos_y={sig['pos_y']}, page={sig['page']}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
    
    def test_download_signed_returns_pdf(self):
        """Test that download-signed endpoint returns valid PDF"""
        # Create meeting and document
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_DownloadSigned_Meeting",
            "scheduled_time": "2026-02-01T11:00:00Z",
            "duration_minutes": 30
        })
        assert meeting_resp.status_code == 200
        meeting_id = meeting_resp.json()["meeting_id"]
        
        # Upload document
        files = {'file': ('test_signed.pdf', b'%PDF-1.4 test content', 'application/pdf')}
        upload_resp = self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/documents", files=files)
        assert upload_resp.status_code == 200
        doc_id = upload_resp.json()["doc_id"]
        
        # Sign the document
        sign_resp = self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/documents/{doc_id}/sign", json={
            "type": "typed",
            "signature_data": "Admin Signature",
            "pos_x": 50,
            "pos_y": 100,
            "page": 1
        })
        assert sign_resp.status_code == 200
        
        # Download signed document
        download_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}/documents/{doc_id}/download-signed")
        assert download_resp.status_code == 200, f"Download failed: {download_resp.text}"
        
        # Verify it's a PDF
        content_type = download_resp.headers.get('Content-Type', '')
        assert 'application/pdf' in content_type, f"Expected PDF, got {content_type}"
        
        # Verify PDF content starts with %PDF
        content = download_resp.content
        assert content[:4] == b'%PDF', "Response should be a valid PDF"
        print(f"✓ Download-signed returns valid PDF ({len(content)} bytes)")
        
        # Verify Content-Disposition header
        content_disp = download_resp.headers.get('Content-Disposition', '')
        assert 'attachment' in content_disp, "Should have attachment disposition"
        assert 'signed_' in content_disp, "Filename should start with 'signed_'"
        print(f"✓ Content-Disposition: {content_disp}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
    
    def test_download_signed_requires_auth(self):
        """Test that download-signed endpoint requires authentication"""
        # Use unauthenticated session
        unauth_session = requests.Session()
        
        # Try to download without auth
        resp = unauth_session.get(f"{BASE_URL}/api/meetings/meet_test123/documents/doc_test123/download-signed")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("✓ Download-signed requires auth (returns 401 without auth)")
        
        unauth_session.close()
    
    def test_download_signed_returns_404_for_nonexistent_doc(self):
        """Test that download-signed returns 404 for non-existent document"""
        # Create a meeting first
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_404_Meeting",
            "scheduled_time": "2026-02-01T12:00:00Z",
            "duration_minutes": 30
        })
        assert meeting_resp.status_code == 200
        meeting_id = meeting_resp.json()["meeting_id"]
        
        # Try to download non-existent document
        resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}/documents/doc_nonexistent/download-signed")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("✓ Download-signed returns 404 for non-existent document")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
    
    def test_sign_with_default_position(self):
        """Test that sign endpoint uses default position values when not provided"""
        # Create meeting and document
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_DefaultPosition_Meeting",
            "scheduled_time": "2026-02-01T13:00:00Z",
            "duration_minutes": 30
        })
        assert meeting_resp.status_code == 200
        meeting_id = meeting_resp.json()["meeting_id"]
        
        files = {'file': ('test_default.pdf', b'%PDF-1.4 test', 'application/pdf')}
        upload_resp = self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/documents", files=files)
        assert upload_resp.status_code == 200
        doc_id = upload_resp.json()["doc_id"]
        
        # Sign without position fields
        sign_resp = self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/documents/{doc_id}/sign", json={
            "type": "typed",
            "signature_data": "No Position Signature"
        })
        assert sign_resp.status_code == 200
        
        # Verify default values
        docs_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}/documents")
        docs = docs_resp.json()
        signed_doc = next((d for d in docs if d["doc_id"] == doc_id), None)
        sig = signed_doc["signatures"][0]
        assert sig.get("pos_x") == 0, f"Default pos_x should be 0, got {sig.get('pos_x')}"
        assert sig.get("pos_y") == 0, f"Default pos_y should be 0, got {sig.get('pos_y')}"
        assert sig.get("page") == 1, f"Default page should be 1, got {sig.get('page')}"
        print("✓ Default position values: pos_x=0, pos_y=0, page=1")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
