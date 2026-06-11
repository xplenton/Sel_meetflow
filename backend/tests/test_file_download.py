"""
Test file download and serve functionality for chat files.
Tests:
- File serve endpoint returns correct MIME type
- File download endpoint returns Content-Disposition attachment header
- File upload creates message with file metadata
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestFileServeAndDownload:
    """Tests for GET /api/chat/files/{file_id} endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_serve_jpeg_file_returns_correct_mime_type(self):
        """Test that serving a JPEG file returns image/jpeg content type"""
        response = self.session.get(f"{BASE_URL}/api/chat/files/chatfile_4be1eb1c.jpeg")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.headers.get('content-type') == 'image/jpeg', f"Expected image/jpeg, got {response.headers.get('content-type')}"
        # Should NOT have Content-Disposition attachment header when not downloading
        content_disp = response.headers.get('content-disposition', '')
        assert 'attachment' not in content_disp, f"Should not have attachment header when serving, got: {content_disp}"
        print("✓ JPEG file serve returns correct MIME type (image/jpeg)")
    
    def test_download_jpeg_file_returns_attachment_header(self):
        """Test that downloading a JPEG file returns Content-Disposition attachment header"""
        response = self.session.get(f"{BASE_URL}/api/chat/files/chatfile_4be1eb1c.jpeg?download=1")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.headers.get('content-type') == 'image/jpeg', f"Expected image/jpeg, got {response.headers.get('content-type')}"
        # Should have Content-Disposition attachment header
        content_disp = response.headers.get('content-disposition', '')
        assert 'attachment' in content_disp, f"Expected attachment header, got: {content_disp}"
        assert 'filename=' in content_disp, f"Expected filename in header, got: {content_disp}"
        print("✓ JPEG file download returns Content-Disposition attachment header")
    
    def test_serve_txt_file_returns_correct_mime_type(self):
        """Test that serving a TXT file returns text/plain content type"""
        response = self.session.get(f"{BASE_URL}/api/chat/files/chatfile_1a8897fc.txt")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        content_type = response.headers.get('content-type', '')
        assert 'text/plain' in content_type, f"Expected text/plain, got {content_type}"
        print("✓ TXT file serve returns correct MIME type (text/plain)")
    
    def test_download_txt_file_returns_attachment_header(self):
        """Test that downloading a TXT file returns Content-Disposition attachment header"""
        response = self.session.get(f"{BASE_URL}/api/chat/files/chatfile_1a8897fc.txt?download=1")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        content_disp = response.headers.get('content-disposition', '')
        assert 'attachment' in content_disp, f"Expected attachment header, got: {content_disp}"
        print("✓ TXT file download returns Content-Disposition attachment header")
    
    def test_serve_png_file_returns_correct_mime_type(self):
        """Test that serving a PNG file returns image/png content type"""
        response = self.session.get(f"{BASE_URL}/api/chat/files/chatfile_2cc4cba9.png")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.headers.get('content-type') == 'image/png', f"Expected image/png, got {response.headers.get('content-type')}"
        print("✓ PNG file serve returns correct MIME type (image/png)")
    
    def test_serve_webm_audio_returns_correct_mime_type(self):
        """Test that serving a WebM audio file returns audio/webm content type"""
        response = self.session.get(f"{BASE_URL}/api/chat/files/voice_79404088.webm")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        content_type = response.headers.get('content-type', '')
        # WebM can be audio/webm or video/webm depending on mimetypes module
        assert 'webm' in content_type, f"Expected webm content type, got {content_type}"
        print(f"✓ WebM file serve returns correct MIME type ({content_type})")
    
    def test_nonexistent_file_returns_404(self):
        """Test that requesting a non-existent file returns 404"""
        response = self.session.get(f"{BASE_URL}/api/chat/files/nonexistent_file.txt")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent file returns 404")


class TestFileUpload:
    """Tests for POST /api/chat/conversations/{conv_id}/upload endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication using cookies"""
        self.session = requests.Session()
        # Login to get auth cookie
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        if login_response.status_code != 200:
            pytest.skip("Authentication failed - skipping authenticated tests")
        self.user = login_response.json().get("user", {})
        # Session cookies are automatically stored
    
    def test_file_upload_creates_message_with_file_metadata(self):
        """Test that file upload creates a message with correct file metadata"""
        # First get or create a conversation
        convs_response = self.session.get(f"{BASE_URL}/api/chat/conversations")
        assert convs_response.status_code == 200, f"Failed to get conversations: {convs_response.status_code}"
        
        convs = convs_response.json()
        if not convs:
            pytest.skip("No conversations available for testing")
        
        conv_id = convs[0]['conversation_id']
        
        # Create a test file
        test_content = b"Test file content for upload testing"
        files = {'file': ('test_upload.txt', test_content, 'text/plain')}
        
        # Use session which has cookies from login
        response = self.session.post(
            f"{BASE_URL}/api/chat/conversations/{conv_id}/upload",
            files=files
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get('type') == 'file', f"Expected type='file', got {data.get('type')}"
        assert data.get('file_name') == 'test_upload.txt', f"Expected file_name='test_upload.txt', got {data.get('file_name')}"
        assert data.get('file_type') == 'text/plain', f"Expected file_type='text/plain', got {data.get('file_type')}"
        assert data.get('file_url'), "Expected file_url to be set"
        assert data.get('file_size') == len(test_content), f"Expected file_size={len(test_content)}, got {data.get('file_size')}"
        
        print("✓ File upload creates message with correct file metadata")
        
        # Verify the uploaded file can be served
        file_url = data.get('file_url')
        serve_response = self.session.get(f"{BASE_URL}{file_url}")
        assert serve_response.status_code == 200, f"Failed to serve uploaded file: {serve_response.status_code}"
        assert serve_response.content == test_content, "Served file content doesn't match uploaded content"
        
        print("✓ Uploaded file can be served correctly")
        
        # Verify download with ?download=1
        download_response = self.session.get(f"{BASE_URL}{file_url}?download=1")
        assert download_response.status_code == 200, f"Failed to download file: {download_response.status_code}"
        content_disp = download_response.headers.get('content-disposition', '')
        assert 'attachment' in content_disp, f"Expected attachment header, got: {content_disp}"
        
        print("✓ Uploaded file can be downloaded with attachment header")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
