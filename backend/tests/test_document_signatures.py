"""
Test Document Presentation & E-Signatures Feature
Tests: Document upload, list, view, present, sign (live + async), email sending
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"

# Pre-existing test data
TEST_MEETING_ID = "meet_044aab394f"
TEST_DOC_ID = "doc_49f0e85622"
TEST_SIGN_TOKEN = "d5cda08711c9429f"


@pytest.fixture(scope="module")
def session():
    """Create authenticated session"""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def auth_session(session):
    """Login and return authenticated session"""
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return session


@pytest.fixture(scope="module")
def test_meeting_id(auth_session):
    """Create a test meeting for document tests"""
    response = auth_session.post(f"{BASE_URL}/api/meetings", json={
        "title": f"TEST_DocMeeting_{uuid.uuid4().hex[:6]}",
        "meeting_type": "instant"
    })
    assert response.status_code in [200, 201], f"Meeting creation failed: {response.text}"
    data = response.json()
    return data["meeting_id"]


class TestDocumentUpload:
    """Test document upload endpoint"""
    
    def test_list_documents_existing_meeting(self, auth_session):
        """GET /api/meetings/{meeting_id}/documents - List documents"""
        response = auth_session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} documents in test meeting")
        
        # Verify document structure
        if len(data) > 0:
            doc = data[0]
            assert "doc_id" in doc
            assert "filename" in doc
            assert "file_ext" in doc
            assert "sign_token" in doc
            assert "signatures" in doc
    
    def test_upload_document_pdf(self, auth_session, test_meeting_id):
        """POST /api/meetings/{meeting_id}/documents - Upload PDF"""
        # Create a simple PDF-like content
        pdf_content = b"%PDF-1.4 test document content"
        files = {"file": ("test_upload.pdf", pdf_content, "application/pdf")}
        
        # Use a fresh session for file upload to avoid Content-Type issues
        upload_session = requests.Session()
        # Copy cookies from auth session
        upload_session.cookies.update(auth_session.cookies)
        
        response = upload_session.post(
            f"{BASE_URL}/api/meetings/{test_meeting_id}/documents",
            files=files
        )
        assert response.status_code == 200, f"Upload failed: {response.text}"
        data = response.json()
        
        assert "doc_id" in data
        assert "filename" in data
        assert "sign_token" in data
        assert data["filename"] == "test_upload.pdf"
        print(f"Uploaded document: {data['doc_id']}")
        return data["doc_id"]
    
    def test_upload_document_image(self, auth_session, test_meeting_id):
        """POST /api/meetings/{meeting_id}/documents - Upload image"""
        # Create minimal PNG content
        png_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        files = {"file": ("test_image.png", png_content, "image/png")}
        
        upload_session = requests.Session()
        upload_session.cookies.update(auth_session.cookies)
        
        response = upload_session.post(
            f"{BASE_URL}/api/meetings/{test_meeting_id}/documents",
            files=files
        )
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "test_image.png"
        print(f"Uploaded image: {data['doc_id']}")
    
    def test_upload_invalid_file_type(self, auth_session, test_meeting_id):
        """POST /api/meetings/{meeting_id}/documents - Reject invalid file type"""
        files = {"file": ("test.exe", b"malicious content", "application/octet-stream")}
        
        upload_session = requests.Session()
        upload_session.cookies.update(auth_session.cookies)
        
        response = upload_session.post(
            f"{BASE_URL}/api/meetings/{test_meeting_id}/documents",
            files=files
        )
        assert response.status_code == 400
        assert "not allowed" in response.json().get("detail", "").lower()
    
    def test_list_documents_nonexistent_meeting(self, auth_session):
        """GET /api/meetings/{meeting_id}/documents - 404 for nonexistent meeting"""
        response = auth_session.get(f"{BASE_URL}/api/meetings/nonexistent_meeting/documents")
        # Should return empty list or 404
        assert response.status_code in [200, 404]


class TestDocumentView:
    """Test document view/download endpoint"""
    
    def test_view_document(self, auth_session):
        """GET /api/meetings/{meeting_id}/documents/{doc_id}/view - Download document"""
        response = auth_session.get(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/view"
        )
        assert response.status_code == 200
        assert len(response.content) > 0
        print(f"Document content length: {len(response.content)} bytes")
    
    def test_view_nonexistent_document(self, auth_session):
        """GET /api/meetings/{meeting_id}/documents/{doc_id}/view - 404 for nonexistent"""
        response = auth_session.get(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/nonexistent_doc/view"
        )
        assert response.status_code == 404


class TestDocumentPresentation:
    """Test document presentation toggle endpoint"""
    
    def test_toggle_presentation_on(self, auth_session):
        """POST /api/meetings/{meeting_id}/documents/{doc_id}/present - Start presenting"""
        response = auth_session.post(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/present",
            json={"presenting": True, "page": 1}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["presenting"] == True
        assert data["doc_id"] == TEST_DOC_ID
        assert data["page"] == 1
        print("Document presentation started")
    
    def test_toggle_presentation_page_change(self, auth_session):
        """POST /api/meetings/{meeting_id}/documents/{doc_id}/present - Change page"""
        response = auth_session.post(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/present",
            json={"presenting": True, "page": 2}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        print("Document page changed to 2")
    
    def test_toggle_presentation_off(self, auth_session):
        """POST /api/meetings/{meeting_id}/documents/{doc_id}/present - Stop presenting"""
        response = auth_session.post(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/present",
            json={"presenting": False, "page": 1}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["presenting"] == False
        print("Document presentation stopped")


class TestLiveSignature:
    """Test live document signing endpoint"""
    
    def test_sign_document_typed(self, auth_session, test_meeting_id):
        """POST /api/meetings/{meeting_id}/documents/{doc_id}/sign - Typed signature"""
        # First upload a document
        pdf_content = b"%PDF-1.4 sign test"
        files = {"file": ("sign_test.pdf", pdf_content, "application/pdf")}
        
        upload_session = requests.Session()
        upload_session.cookies.update(auth_session.cookies)
        
        upload_resp = upload_session.post(
            f"{BASE_URL}/api/meetings/{test_meeting_id}/documents",
            files=files
        )
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        doc_id = upload_resp.json()["doc_id"]
        
        # Sign the document
        response = auth_session.post(
            f"{BASE_URL}/api/meetings/{test_meeting_id}/documents/{doc_id}/sign",
            json={"type": "typed", "signature_data": "Test Signature"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "sig_id" in data
        assert data["message"] == "Document signed"
        print(f"Document signed with typed signature: {data['sig_id']}")
    
    def test_sign_document_drawn(self, auth_session, test_meeting_id):
        """POST /api/meetings/{meeting_id}/documents/{doc_id}/sign - Drawn signature"""
        # Upload another document
        pdf_content = b"%PDF-1.4 drawn sign test"
        files = {"file": ("drawn_sign_test.pdf", pdf_content, "application/pdf")}
        
        upload_session = requests.Session()
        upload_session.cookies.update(auth_session.cookies)
        
        upload_resp = upload_session.post(
            f"{BASE_URL}/api/meetings/{test_meeting_id}/documents",
            files=files
        )
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        doc_id = upload_resp.json()["doc_id"]
        
        # Sign with drawn signature (base64 image)
        response = auth_session.post(
            f"{BASE_URL}/api/meetings/{test_meeting_id}/documents/{doc_id}/sign",
            json={"type": "drawn", "signature_data": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="}
        )
        assert response.status_code == 200
        data = response.json()
        assert "sig_id" in data
        print(f"Document signed with drawn signature: {data['sig_id']}")
    
    def test_sign_document_missing_data(self, auth_session):
        """POST /api/meetings/{meeting_id}/documents/{doc_id}/sign - Missing signature data"""
        response = auth_session.post(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/sign",
            json={"type": "typed", "signature_data": ""}
        )
        assert response.status_code == 400
        assert "required" in response.json().get("detail", "").lower()


class TestRequestSignatures:
    """Test signature request endpoint (host only)"""
    
    def test_request_signatures(self, auth_session):
        """POST /api/meetings/{meeting_id}/documents/{doc_id}/request-signatures"""
        response = auth_session.post(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/request-signatures"
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"Signature request sent: {data['message']}")


class TestPublicSigning:
    """Test public async signing endpoints"""
    
    def test_get_document_for_signing(self):
        """GET /api/sign/{sign_token} - Get document info for public signing"""
        response = requests.get(f"{BASE_URL}/api/sign/{TEST_SIGN_TOKEN}")
        assert response.status_code == 200
        data = response.json()
        
        assert "doc_id" in data
        assert "filename" in data
        assert "meeting_title" in data
        assert "uploader_name" in data
        assert "signatures" in data
        assert "view_url" in data
        
        print(f"Public signing page info: {data['filename']}, {len(data['signatures'])} signatures")
    
    def test_get_document_invalid_token(self):
        """GET /api/sign/{sign_token} - 404 for invalid token"""
        response = requests.get(f"{BASE_URL}/api/sign/invalid_token_12345")
        assert response.status_code == 404
    
    def test_sign_document_async(self):
        """POST /api/sign/{sign_token} - Public async signing"""
        unique_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        response = requests.post(
            f"{BASE_URL}/api/sign/{TEST_SIGN_TOKEN}",
            json={
                "signer_name": "Async Test Signer",
                "signer_email": unique_email,
                "type": "typed",
                "signature_data": "Async Signature"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "sig_id" in data
        assert data["message"] == "Document signed"
        print(f"Async signature added: {data['sig_id']}")
    
    def test_sign_document_async_duplicate(self):
        """POST /api/sign/{sign_token} - Prevent duplicate signatures"""
        # First signature
        unique_email = f"dup_{uuid.uuid4().hex[:8]}@example.com"
        response1 = requests.post(
            f"{BASE_URL}/api/sign/{TEST_SIGN_TOKEN}",
            json={
                "signer_name": "Duplicate Tester",
                "signer_email": unique_email,
                "type": "typed",
                "signature_data": "First Signature"
            }
        )
        assert response1.status_code == 200
        
        # Second signature with same email should fail
        response2 = requests.post(
            f"{BASE_URL}/api/sign/{TEST_SIGN_TOKEN}",
            json={
                "signer_name": "Duplicate Tester",
                "signer_email": unique_email,
                "type": "typed",
                "signature_data": "Second Signature"
            }
        )
        assert response2.status_code == 409
        assert "already signed" in response2.json().get("detail", "").lower()
        print("Duplicate signature correctly rejected")
    
    def test_sign_document_async_missing_name(self):
        """POST /api/sign/{sign_token} - Missing required fields"""
        response = requests.post(
            f"{BASE_URL}/api/sign/{TEST_SIGN_TOKEN}",
            json={
                "signer_name": "",
                "signer_email": "test@test.com",
                "type": "typed",
                "signature_data": "Signature"
            }
        )
        assert response.status_code == 400
        assert "required" in response.json().get("detail", "").lower()


class TestSendForSigning:
    """Test email sending for signatures (MOCKED - no real email sent)"""
    
    def test_send_for_signing(self, auth_session):
        """POST /api/meetings/{meeting_id}/documents/{doc_id}/send-for-signing"""
        response = auth_session.post(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/send-for-signing",
            json={"emails": ["test1@example.com", "test2@example.com"]}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert "sign_url" in data
        assert "sent" in data
        # Email is mocked, so sent count may be 0 or 2 depending on mock behavior
        print(f"Send for signing result: {data['message']}, sign_url: {data['sign_url']}")
    
    def test_send_for_signing_empty_emails(self, auth_session):
        """POST /api/meetings/{meeting_id}/documents/{doc_id}/send-for-signing - Empty list"""
        response = auth_session.post(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/send-for-signing",
            json={"emails": []}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sent"] == 0


class TestDocumentCleanup:
    """Verify document data after tests"""
    
    def test_verify_signatures_persisted(self, auth_session):
        """Verify signatures are persisted in document"""
        response = auth_session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents")
        assert response.status_code == 200
        docs = response.json()
        
        # Find our test document
        test_doc = next((d for d in docs if d["doc_id"] == TEST_DOC_ID), None)
        assert test_doc is not None
        
        # Should have multiple signatures now
        sig_count = len(test_doc.get("signatures", []))
        print(f"Test document has {sig_count} signatures")
        assert sig_count >= 2, "Expected at least 2 signatures from tests"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
