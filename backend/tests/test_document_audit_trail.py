"""
Document Audit Trail Feature Tests
Tests the audit logging functionality for document actions:
- Upload creates 'uploaded' audit entry
- View/download creates 'viewed' audit entry
- Toggle presentation creates 'presented' or 'presentation_stopped' entry
- Live signing creates 'signed' entry
- Async public signing creates 'signed_async' entry
- Request signatures creates 'signature_requested' entry
- Send for signing creates 'sent_for_signing' entry
- GET /audit-log returns entries sorted by timestamp DESC
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDocumentAuditTrail:
    """Document Audit Trail endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and create test meeting with document"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.user = login_resp.json()
        
        # Create a test meeting
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Audit_Trail_Meeting",
            "description": "Meeting for audit trail testing",
            "scheduled_time": "2026-12-01T10:00:00Z",
            "duration_minutes": 60
        })
        assert meeting_resp.status_code in [200, 201], f"Meeting creation failed: {meeting_resp.text}"
        self.meeting = meeting_resp.json()
        self.meeting_id = self.meeting["meeting_id"]
        
        yield
        
        # Cleanup: Delete test meeting
        try:
            self.session.delete(f"{BASE_URL}/api/meetings/{self.meeting_id}")
        except:
            pass
    
    def _upload_test_document(self, filename="TEST_audit_doc.pdf"):
        """Helper to upload a test document"""
        files = {
            'file': (filename, b'%PDF-1.4 test content', 'application/pdf')
        }
        
        # Use a fresh session for file upload to avoid Content-Type issues
        upload_session = requests.Session()
        upload_session.cookies.update(self.session.cookies)
        
        resp = upload_session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents",
            files=files
        )
        return resp
    
    # ============ AUDIT LOG ENDPOINT TESTS ============
    
    def test_get_audit_log_returns_entries_sorted_desc(self):
        """GET /audit-log returns audit entries sorted by timestamp DESC"""
        # Upload a document (creates 'uploaded' entry)
        upload_resp = self._upload_test_document()
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        doc = upload_resp.json()
        doc_id = doc["doc_id"]
        
        # View the document (creates 'viewed' entry)
        view_resp = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc_id}/view")
        assert view_resp.status_code == 200
        
        # Get audit log
        audit_resp = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc_id}/audit-log")
        assert audit_resp.status_code == 200
        
        logs = audit_resp.json()
        assert isinstance(logs, list)
        assert len(logs) >= 2, f"Expected at least 2 audit entries, got {len(logs)}"
        
        # Verify sorted by timestamp DESC (newest first)
        if len(logs) >= 2:
            for i in range(len(logs) - 1):
                assert logs[i]["timestamp"] >= logs[i+1]["timestamp"], \
                    f"Audit logs not sorted DESC: {logs[i]['timestamp']} < {logs[i+1]['timestamp']}"
        
        print(f"✓ Audit log returns {len(logs)} entries sorted by timestamp DESC")
    
    def test_audit_log_entry_structure(self):
        """Audit entries have correct structure: log_id, doc_id, meeting_id, action, user_id, user_name, user_email, ip, details, timestamp"""
        upload_resp = self._upload_test_document()
        assert upload_resp.status_code == 200
        doc = upload_resp.json()
        
        audit_resp = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc['doc_id']}/audit-log")
        assert audit_resp.status_code == 200
        
        logs = audit_resp.json()
        assert len(logs) >= 1
        
        entry = logs[0]
        required_fields = ["log_id", "doc_id", "meeting_id", "action", "user_id", "user_name", "user_email", "ip", "details", "timestamp"]
        for field in required_fields:
            assert field in entry, f"Missing field '{field}' in audit entry"
        
        print(f"✓ Audit entry has all required fields: {required_fields}")
    
    def test_audit_log_requires_authentication(self):
        """GET /audit-log requires authentication"""
        # Create document first
        upload_resp = self._upload_test_document()
        assert upload_resp.status_code == 200
        doc = upload_resp.json()
        
        # Try to access audit log without auth
        unauthenticated_session = requests.Session()
        audit_resp = unauthenticated_session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc['doc_id']}/audit-log"
        )
        assert audit_resp.status_code == 401, f"Expected 401, got {audit_resp.status_code}"
        
        print("✓ Audit log endpoint requires authentication")
    
    # ============ UPLOAD AUDIT TESTS ============
    
    def test_upload_creates_uploaded_audit_entry(self):
        """Upload document creates 'uploaded' audit entry with filename and file size"""
        filename = "TEST_upload_audit.pdf"
        upload_resp = self._upload_test_document(filename)
        assert upload_resp.status_code == 200
        doc = upload_resp.json()
        
        audit_resp = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc['doc_id']}/audit-log")
        assert audit_resp.status_code == 200
        
        logs = audit_resp.json()
        uploaded_entries = [l for l in logs if l["action"] == "uploaded"]
        assert len(uploaded_entries) >= 1, "No 'uploaded' audit entry found"
        
        entry = uploaded_entries[0]
        assert entry["user_id"] == self.user["user_id"]
        assert entry["user_name"] == self.user["name"]
        assert entry["user_email"] == self.user["email"]
        assert filename in entry["details"], f"Filename not in details: {entry['details']}"
        assert "Bytes" in entry["details"], f"File size not in details: {entry['details']}"
        
        print(f"✓ Upload creates 'uploaded' audit entry with filename and size: {entry['details']}")
    
    # ============ VIEW AUDIT TESTS ============
    
    def test_view_creates_viewed_audit_entry(self):
        """View/download document creates 'viewed' audit entry"""
        upload_resp = self._upload_test_document()
        assert upload_resp.status_code == 200
        doc = upload_resp.json()
        
        # View the document
        view_resp = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc['doc_id']}/view")
        assert view_resp.status_code == 200
        
        audit_resp = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc['doc_id']}/audit-log")
        logs = audit_resp.json()
        
        viewed_entries = [l for l in logs if l["action"] == "viewed"]
        assert len(viewed_entries) >= 1, "No 'viewed' audit entry found"
        
        entry = viewed_entries[0]
        assert entry["ip"], "IP address should be logged"
        
        print(f"✓ View creates 'viewed' audit entry with IP: {entry['ip']}")
    
    # ============ PRESENTATION AUDIT TESTS ============
    
    def test_present_creates_presented_audit_entry(self):
        """Toggle presentation ON creates 'presented' audit entry"""
        upload_resp = self._upload_test_document()
        assert upload_resp.status_code == 200
        doc = upload_resp.json()
        
        # Start presentation
        present_resp = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc['doc_id']}/present",
            json={"presenting": True, "page": 1}
        )
        assert present_resp.status_code == 200
        
        audit_resp = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc['doc_id']}/audit-log")
        logs = audit_resp.json()
        
        presented_entries = [l for l in logs if l["action"] == "presented"]
        assert len(presented_entries) >= 1, "No 'presented' audit entry found"
        
        entry = presented_entries[0]
        assert entry["user_id"] == self.user["user_id"]
        assert "Seite" in entry["details"], f"Page info not in details: {entry['details']}"
        
        print(f"✓ Present creates 'presented' audit entry: {entry['details']}")
    
    def test_stop_presentation_creates_stopped_audit_entry(self):
        """Toggle presentation OFF creates 'presentation_stopped' audit entry"""
        upload_resp = self._upload_test_document()
        assert upload_resp.status_code == 200
        doc = upload_resp.json()
        
        # Start then stop presentation
        self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc['doc_id']}/present",
            json={"presenting": True, "page": 1}
        )
        
        stop_resp = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc['doc_id']}/present",
            json={"presenting": False, "page": 1}
        )
        assert stop_resp.status_code == 200
        
        audit_resp = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc['doc_id']}/audit-log")
        logs = audit_resp.json()
        
        stopped_entries = [l for l in logs if l["action"] == "presentation_stopped"]
        assert len(stopped_entries) >= 1, "No 'presentation_stopped' audit entry found"
        
        print("✓ Stop presentation creates 'presentation_stopped' audit entry")
    
    # ============ SIGNATURE AUDIT TESTS ============
    
    def test_live_sign_creates_signed_audit_entry(self):
        """Live signing creates 'signed' audit entry with signer info"""
        upload_resp = self._upload_test_document()
        assert upload_resp.status_code == 200
        doc = upload_resp.json()
        
        # Sign the document
        sign_resp = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc['doc_id']}/sign",
            json={"type": "typed", "signature_data": "Test Signature"}
        )
        assert sign_resp.status_code == 200
        
        audit_resp = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc['doc_id']}/audit-log")
        logs = audit_resp.json()
        
        signed_entries = [l for l in logs if l["action"] == "signed"]
        assert len(signed_entries) >= 1, "No 'signed' audit entry found"
        
        entry = signed_entries[0]
        assert entry["user_id"] == self.user["user_id"]
        assert entry["user_name"] == self.user["name"]
        assert "Typ:" in entry["details"], f"Signature type not in details: {entry['details']}"
        
        print(f"✓ Live sign creates 'signed' audit entry: {entry['details']}")
    
    def test_async_sign_creates_signed_async_audit_entry(self):
        """Async public signing creates 'signed_async' audit entry"""
        upload_resp = self._upload_test_document()
        assert upload_resp.status_code == 200
        doc = upload_resp.json()
        sign_token = doc["sign_token"]
        
        # Sign via public endpoint (no auth needed)
        public_session = requests.Session()
        sign_resp = public_session.post(
            f"{BASE_URL}/api/sign/{sign_token}",
            json={
                "signer_name": "TEST_External Signer",
                "signer_email": "test_external@example.com",
                "type": "typed",
                "signature_data": "External Signature"
            }
        )
        assert sign_resp.status_code == 200, f"Async sign failed: {sign_resp.text}"
        
        # Check audit log (need auth)
        audit_resp = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc['doc_id']}/audit-log")
        logs = audit_resp.json()
        
        async_entries = [l for l in logs if l["action"] == "signed_async"]
        assert len(async_entries) >= 1, "No 'signed_async' audit entry found"
        
        entry = async_entries[0]
        assert entry["user_name"] == "TEST_External Signer"
        assert entry["user_email"] == "test_external@example.com"
        
        print(f"✓ Async sign creates 'signed_async' audit entry: {entry['user_name']}")
    
    def test_request_signatures_creates_audit_entry(self):
        """Request signatures creates 'signature_requested' audit entry"""
        upload_resp = self._upload_test_document()
        assert upload_resp.status_code == 200
        doc = upload_resp.json()
        
        # Request signatures (host only)
        req_resp = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc['doc_id']}/request-signatures"
        )
        assert req_resp.status_code == 200
        
        audit_resp = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc['doc_id']}/audit-log")
        logs = audit_resp.json()
        
        req_entries = [l for l in logs if l["action"] == "signature_requested"]
        assert len(req_entries) >= 1, "No 'signature_requested' audit entry found"
        
        entry = req_entries[0]
        assert entry["user_id"] == self.user["user_id"]
        
        print("✓ Request signatures creates 'signature_requested' audit entry")
    
    def test_send_for_signing_creates_audit_entry(self):
        """Send for signing creates 'sent_for_signing' audit entry with recipients"""
        upload_resp = self._upload_test_document()
        assert upload_resp.status_code == 200
        doc = upload_resp.json()
        
        # Send for signing
        send_resp = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc['doc_id']}/send-for-signing",
            json={"emails": ["test1@example.com", "test2@example.com"]}
        )
        assert send_resp.status_code == 200
        
        audit_resp = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc['doc_id']}/audit-log")
        logs = audit_resp.json()
        
        send_entries = [l for l in logs if l["action"] == "sent_for_signing"]
        assert len(send_entries) >= 1, "No 'sent_for_signing' audit entry found"
        
        entry = send_entries[0]
        assert "Empfänger:" in entry["details"], f"Recipients not in details: {entry['details']}"
        assert "test1@example.com" in entry["details"]
        assert "test2@example.com" in entry["details"]
        
        print(f"✓ Send for signing creates 'sent_for_signing' audit entry: {entry['details']}")
    
    # ============ EXISTING TEST DATA VERIFICATION ============
    
    def test_existing_audit_data_from_main_agent(self):
        """Verify existing audit data from main agent's test (meet_9ed4c75edc, doc_937022119e)"""
        # Use the test data provided by main agent
        test_meeting_id = "meet_9ed4c75edc"
        test_doc_id = "doc_937022119e"
        
        audit_resp = self.session.get(f"{BASE_URL}/api/meetings/{test_meeting_id}/documents/{test_doc_id}/audit-log")
        assert audit_resp.status_code == 200
        
        logs = audit_resp.json()
        assert len(logs) >= 5, f"Expected at least 5 audit entries, got {len(logs)}"
        
        # Verify all expected actions are present
        actions = [l["action"] for l in logs]
        expected_actions = ["uploaded", "viewed", "presented", "signed", "signed_async"]
        for action in expected_actions:
            assert action in actions, f"Missing expected action '{action}' in audit log"
        
        print(f"✓ Existing test data verified: {len(logs)} entries with actions {set(actions)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
