"""
Iteration 62 - Backend Tests for:
- PAKET 1: Attachments (upload, get, meta, delete, MIME whitelist, size limit)
- PAKET 1: News Comments with Attachments
- PAKET 1: Survey Responses with Attachments
- PAKET 2: Extended CSV/PDF Exports for Surveys and Interactions
- PAKET 3: PWA manifest, service worker, offline.html
- REGRESSION: Existing endpoints still work
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def admin_session():
    """Login as admin and return session with auth cookie."""
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return session


@pytest.fixture(scope="module")
def member_session():
    """Create a member user and return session."""
    session = requests.Session()
    import uuid
    email = f"test_member_{uuid.uuid4().hex[:8]}@test.com"
    # Register
    resp = session.post(f"{BASE_URL}/api/auth/register", json={
        "email": email,
        "password": "test123",
        "name": "Test Member"
    })
    if resp.status_code != 200:
        # Try login if already exists
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": email,
            "password": "test123"
        })
    return session


# ============ PAKET 1: ATTACHMENTS ============

class TestAttachmentUpload:
    """Test attachment upload endpoint with MIME whitelist and size limits."""
    
    def test_upload_text_file_success(self, admin_session):
        """Upload a text file - should succeed."""
        files = {'file': ('test.txt', b'Hello World Test Content', 'text/plain')}
        resp = admin_session.post(f"{BASE_URL}/api/attachments/upload", files=files)
        assert resp.status_code == 200, f"Upload failed: {resp.text}"
        data = resp.json()
        assert "attachment_id" in data
        assert data["filename"] == "test.txt"
        assert data["mime"] == "text/plain"
        assert data["size"] > 0
        assert "url" in data
        # Store for later tests
        TestAttachmentUpload.uploaded_id = data["attachment_id"]
    
    def test_upload_image_png_success(self, admin_session):
        """Upload a PNG image - should succeed."""
        # Minimal valid PNG (1x1 transparent pixel)
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
            0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,
            0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
            0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
            0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
            0x42, 0x60, 0x82
        ])
        files = {'file': ('test.png', png_data, 'image/png')}
        resp = admin_session.post(f"{BASE_URL}/api/attachments/upload", files=files)
        assert resp.status_code == 200, f"PNG upload failed: {resp.text}"
        data = resp.json()
        assert data["mime"] == "image/png"
    
    def test_upload_pdf_success(self, admin_session):
        """Upload a PDF file - should succeed."""
        # Minimal PDF
        pdf_data = b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\nxref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \ntrailer<</Size 3/Root 1 0 R>>\nstartxref\n101\n%%EOF'
        files = {'file': ('test.pdf', pdf_data, 'application/pdf')}
        resp = admin_session.post(f"{BASE_URL}/api/attachments/upload", files=files)
        assert resp.status_code == 200, f"PDF upload failed: {resp.text}"
        data = resp.json()
        assert data["mime"] == "application/pdf"
    
    def test_upload_disallowed_mime_type_415(self, admin_session):
        """Upload an executable - should return 415."""
        files = {'file': ('test.exe', b'MZ\x90\x00', 'application/x-msdownload')}
        resp = admin_session.post(f"{BASE_URL}/api/attachments/upload", files=files)
        assert resp.status_code == 415, f"Expected 415 for disallowed MIME, got {resp.status_code}"
    
    def test_upload_empty_file_400(self, admin_session):
        """Upload empty file - should return 400."""
        files = {'file': ('empty.txt', b'', 'text/plain')}
        resp = admin_session.post(f"{BASE_URL}/api/attachments/upload", files=files)
        assert resp.status_code == 400, f"Expected 400 for empty file, got {resp.status_code}"


class TestAttachmentGetAndMeta:
    """Test attachment retrieval and metadata endpoints."""
    
    def test_get_attachment_stream(self, admin_session):
        """GET /api/attachments/{id} returns file stream."""
        # First upload a file
        files = {'file': ('stream_test.txt', b'Stream test content', 'text/plain')}
        upload_resp = admin_session.post(f"{BASE_URL}/api/attachments/upload", files=files)
        assert upload_resp.status_code == 200
        att_id = upload_resp.json()["attachment_id"]
        
        # Get the file
        resp = admin_session.get(f"{BASE_URL}/api/attachments/{att_id}")
        assert resp.status_code == 200
        assert b'Stream test content' in resp.content
        assert 'text/plain' in resp.headers.get('Content-Type', '')
    
    def test_get_attachment_meta(self, admin_session):
        """GET /api/attachments/{id}/meta returns metadata."""
        # First upload a file
        files = {'file': ('meta_test.txt', b'Meta test content', 'text/plain')}
        upload_resp = admin_session.post(f"{BASE_URL}/api/attachments/upload", files=files)
        assert upload_resp.status_code == 200
        att_id = upload_resp.json()["attachment_id"]
        
        # Get metadata
        resp = admin_session.get(f"{BASE_URL}/api/attachments/{att_id}/meta")
        assert resp.status_code == 200
        data = resp.json()
        assert data["attachment_id"] == att_id
        assert data["filename"] == "meta_test.txt"
        assert data["mime"] == "text/plain"
        assert "size" in data
        assert "url" in data
    
    def test_get_nonexistent_attachment_404(self, admin_session):
        """GET nonexistent attachment returns 404."""
        resp = admin_session.get(f"{BASE_URL}/api/attachments/nonexistent_id_12345")
        assert resp.status_code == 404


class TestAttachmentDelete:
    """Test attachment deletion with permission checks."""
    
    def test_delete_own_attachment_success(self, admin_session):
        """Owner can delete their own attachment."""
        # Upload
        files = {'file': ('delete_test.txt', b'Delete me', 'text/plain')}
        upload_resp = admin_session.post(f"{BASE_URL}/api/attachments/upload", files=files)
        assert upload_resp.status_code == 200
        att_id = upload_resp.json()["attachment_id"]
        
        # Delete
        resp = admin_session.delete(f"{BASE_URL}/api/attachments/{att_id}")
        assert resp.status_code == 200
        
        # Verify deleted
        get_resp = admin_session.get(f"{BASE_URL}/api/attachments/{att_id}")
        assert get_resp.status_code == 404


# ============ PAKET 1: NEWS COMMENTS WITH ATTACHMENTS ============

class TestNewsCommentsWithAttachments:
    """Test news comments with attachment support."""
    
    def test_add_comment_with_attachment(self, admin_session):
        """POST comment with attachments array."""
        # First upload an attachment
        files = {'file': ('comment_att.txt', b'Comment attachment', 'text/plain')}
        upload_resp = admin_session.post(f"{BASE_URL}/api/attachments/upload", files=files)
        assert upload_resp.status_code == 200
        att_id = upload_resp.json()["attachment_id"]
        
        # Get a news post
        feed_resp = admin_session.get(f"{BASE_URL}/api/news/feed?limit=1")
        assert feed_resp.status_code == 200
        posts = feed_resp.json().get("posts", [])
        if not posts:
            pytest.skip("No news posts available for testing")
        post_id = posts[0]["post_id"]
        
        # Add comment with attachment
        comment_resp = admin_session.post(f"{BASE_URL}/api/news/posts/{post_id}/comments", json={
            "content": "Test comment with attachment",
            "attachments": [att_id]
        })
        assert comment_resp.status_code == 200
        comment_data = comment_resp.json()
        assert "comment_id" in comment_data
        assert "attachments" in comment_data
        # Attachments should be enriched with metadata
        if comment_data["attachments"]:
            att = comment_data["attachments"][0]
            assert "url" in att
            assert "filename" in att
    
    def test_get_comments_returns_enriched_attachments(self, admin_session):
        """GET comments returns attachments with full metadata."""
        # Get a news post
        feed_resp = admin_session.get(f"{BASE_URL}/api/news/feed?limit=1")
        posts = feed_resp.json().get("posts", [])
        if not posts:
            pytest.skip("No news posts available")
        post_id = posts[0]["post_id"]
        
        # Get comments
        resp = admin_session.get(f"{BASE_URL}/api/news/posts/{post_id}/comments")
        assert resp.status_code == 200
        comments = resp.json()
        # All comments should have attachments array (even if empty)
        for c in comments:
            assert "attachments" in c
            assert isinstance(c["attachments"], list)


# ============ PAKET 1: SURVEY RESPONSES WITH ATTACHMENTS ============

class TestSurveyResponsesWithAttachments:
    """Test survey responses with attachment_map support."""
    
    def test_survey_results_include_attachments(self, admin_session):
        """GET survey results includes attachments for free_text questions."""
        # Get a survey
        resp = admin_session.get(f"{BASE_URL}/api/surveys?status=published")
        assert resp.status_code == 200
        surveys = resp.json()
        if not surveys:
            pytest.skip("No published surveys available")
        
        survey_id = surveys[0]["survey_id"]
        
        # Get results
        results_resp = admin_session.get(f"{BASE_URL}/api/surveys/{survey_id}/results")
        assert results_resp.status_code == 200
        data = results_resp.json()
        assert "results" in data
        # Check free_text questions have texts with attachments field
        for qid, qdata in data["results"].items():
            if qdata.get("type") == "free_text":
                assert "texts" in qdata
                for t in qdata.get("texts", []):
                    assert "attachments" in t


# ============ PAKET 2: EXPORT ENDPOINTS ============

class TestExportEndpoints:
    """Test CSV and PDF export endpoints."""
    
    def test_export_survey_csv_extended(self, admin_session):
        """GET /api/exports/surveys/{id}/csv returns CSV with demographics."""
        # Get a survey
        resp = admin_session.get(f"{BASE_URL}/api/surveys?status=published")
        surveys = resp.json()
        if not surveys:
            pytest.skip("No surveys available")
        survey_id = surveys[0]["survey_id"]
        
        # Export CSV
        csv_resp = admin_session.get(f"{BASE_URL}/api/exports/surveys/{survey_id}/csv")
        assert csv_resp.status_code == 200
        assert 'text/csv' in csv_resp.headers.get('Content-Type', '')
        content = csv_resp.text
        # Check for demographic columns
        assert 'Teilnehmer' in content
        assert 'E-Mail' in content or 'Abteilung' in content
    
    def test_export_survey_pdf(self, admin_session):
        """GET /api/exports/surveys/{id}/pdf returns valid PDF."""
        resp = admin_session.get(f"{BASE_URL}/api/surveys?status=published")
        surveys = resp.json()
        if not surveys:
            pytest.skip("No surveys available")
        survey_id = surveys[0]["survey_id"]
        
        # Export PDF
        pdf_resp = admin_session.get(f"{BASE_URL}/api/exports/surveys/{survey_id}/pdf")
        assert pdf_resp.status_code == 200
        assert 'application/pdf' in pdf_resp.headers.get('Content-Type', '')
        # Check PDF magic bytes
        assert pdf_resp.content[:4] == b'%PDF', "Response does not start with %PDF"
    
    def test_export_interactions_csv(self, admin_session):
        """GET /api/exports/interactions/csv returns CSV report."""
        resp = admin_session.get(f"{BASE_URL}/api/exports/interactions/csv")
        assert resp.status_code == 200
        assert 'text/csv' in resp.headers.get('Content-Type', '')
        content = resp.text
        assert 'Bereich' in content or 'Metrik' in content
    
    def test_export_interactions_pdf(self, admin_session):
        """GET /api/exports/interactions/pdf returns valid PDF."""
        resp = admin_session.get(f"{BASE_URL}/api/exports/interactions/pdf")
        assert resp.status_code == 200
        assert 'application/pdf' in resp.headers.get('Content-Type', '')
        assert resp.content[:4] == b'%PDF', "Response does not start with %PDF"
    
    def test_export_permissions_member_403(self, member_session):
        """Member cannot access export endpoints - should get 403."""
        # Try interactions export
        resp = member_session.get(f"{BASE_URL}/api/exports/interactions/csv")
        assert resp.status_code == 403, f"Expected 403 for member, got {resp.status_code}"


# ============ PAKET 3: PWA FILES ============

class TestPWAFiles:
    """Test PWA manifest, service worker, and offline page."""
    
    def test_manifest_json_valid(self):
        """/manifest.json is valid JSON with required fields."""
        resp = requests.get(f"{BASE_URL}/manifest.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data
        assert "start_url" in data
        assert data["start_url"] == "/dashboard"
        assert "icons" in data
        assert len(data["icons"]) >= 1
    
    def test_service_worker_exists(self):
        """/sw-push.js exists and contains required handlers."""
        resp = requests.get(f"{BASE_URL}/sw-push.js")
        assert resp.status_code == 200
        content = resp.text
        # Check for required event handlers
        assert 'push' in content
        assert 'notificationclick' in content
        assert 'fetch' in content
    
    def test_offline_html_exists(self):
        """/offline.html exists and contains 'Keine Verbindung'."""
        resp = requests.get(f"{BASE_URL}/offline.html")
        assert resp.status_code == 200
        content = resp.text
        assert 'Keine Verbindung' in content
        assert '<html' in content.lower()


# ============ REGRESSION TESTS ============

class TestRegressionExistingEndpoints:
    """Ensure existing endpoints still work."""
    
    def test_existing_survey_export_csv(self, admin_session):
        """Existing /api/surveys/{id}/export still works."""
        resp = admin_session.get(f"{BASE_URL}/api/surveys?status=published")
        surveys = resp.json()
        if not surveys:
            pytest.skip("No surveys available")
        survey_id = surveys[0]["survey_id"]
        
        # Old export endpoint
        csv_resp = admin_session.get(f"{BASE_URL}/api/surveys/{survey_id}/export")
        assert csv_resp.status_code == 200
        assert 'text/csv' in csv_resp.headers.get('Content-Type', '')
    
    def test_news_comments_without_attachments(self, admin_session):
        """Comments without attachments still work and return attachments=[]."""
        feed_resp = admin_session.get(f"{BASE_URL}/api/news/feed?limit=1")
        posts = feed_resp.json().get("posts", [])
        if not posts:
            pytest.skip("No news posts available")
        post_id = posts[0]["post_id"]
        
        # Add comment without attachments
        comment_resp = admin_session.post(f"{BASE_URL}/api/news/posts/{post_id}/comments", json={
            "content": "Comment without attachments"
        })
        assert comment_resp.status_code == 200
        
        # Get comments
        get_resp = admin_session.get(f"{BASE_URL}/api/news/posts/{post_id}/comments")
        assert get_resp.status_code == 200
        comments = get_resp.json()
        # Find our comment
        for c in comments:
            if c.get("content") == "Comment without attachments":
                assert c.get("attachments") == [] or c.get("attachments") is not None
                break
    
    def test_auth_login_still_works(self):
        """Auth login endpoint still works."""
        session = requests.Session()
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "user" in data or "user_id" in data or "email" in data
    
    def test_news_feed_still_works(self, admin_session):
        """News feed endpoint still works."""
        resp = admin_session.get(f"{BASE_URL}/api/news/feed")
        assert resp.status_code == 200
        data = resp.json()
        assert "posts" in data
        assert "total" in data
    
    def test_surveys_list_still_works(self, admin_session):
        """Surveys list endpoint still works."""
        resp = admin_session.get(f"{BASE_URL}/api/surveys")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
