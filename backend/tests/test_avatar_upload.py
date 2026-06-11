"""
Test suite for Avatar Upload feature:
- POST /api/users/avatar - Upload avatar image
- GET /api/users/avatar/{user_id} - Retrieve avatar image
- Validation: File size limit (5MB), image format validation
"""

import pytest
import requests
import os
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8001').rstrip('/')


class TestAvatarUpload:
    """Tests for avatar upload and retrieval"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login as admin and get session"""
        self.session = requests.Session()
        
        # Login as admin (with JSON content type)
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", 
            json={"email": "admin@meetflow.com", "password": "admin123"},
            headers={"Content-Type": "application/json"})
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.user = login_resp.json()
        self.user_id = self.user.get("user_id")
        # Don't set default Content-Type header - let requests handle it for multipart
        yield
    
    def test_avatar_upload_valid_png(self):
        """POST /api/users/avatar accepts valid PNG image"""
        # Create a minimal valid PNG (1x1 red pixel)
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1 dimensions
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,  # 8-bit RGB
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT chunk
            0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,  # compressed data
            0x00, 0x00, 0x03, 0x00, 0x01, 0x00, 0x18, 0xDD,
            0x8D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45,  # IEND chunk
            0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82
        ])
        
        files = {'file': ('test_avatar.png', io.BytesIO(png_data), 'image/png')}
        
        resp = self.session.post(f"{BASE_URL}/api/users/avatar", files=files)
        assert resp.status_code == 200, f"Avatar upload failed: {resp.text}"
        
        data = resp.json()
        assert "avatar" in data, "Response should contain 'avatar' key"
        assert data["avatar"].startswith("/api/users/avatar/"), f"Avatar URL should start with /api/users/avatar/, got: {data['avatar']}"
        print(f"✓ Avatar upload successful: {data['avatar']}")
    
    def test_avatar_upload_valid_jpeg(self):
        """POST /api/users/avatar accepts valid JPEG image"""
        # Minimal JPEG (1x1 pixel)
        jpeg_data = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46,
            0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01,
            0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
            0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08,
            0x07, 0x07, 0x07, 0x09, 0x09, 0x08, 0x0A, 0x0C,
            0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
            0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D,
            0x1A, 0x1C, 0x1C, 0x20, 0x24, 0x2E, 0x27, 0x20,
            0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
            0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27,
            0x39, 0x3D, 0x38, 0x32, 0x3C, 0x2E, 0x33, 0x34,
            0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
            0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4,
            0x00, 0x1F, 0x00, 0x00, 0x01, 0x05, 0x01, 0x01,
            0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04,
            0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0xFF,
            0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
            0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04,
            0x00, 0x00, 0x01, 0x7D, 0x01, 0x02, 0x03, 0x00,
            0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
            0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32,
            0x81, 0x91, 0xA1, 0x08, 0x23, 0x42, 0xB1, 0xC1,
            0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
            0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A,
            0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x34, 0x35,
            0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
            0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55,
            0x56, 0x57, 0x58, 0x59, 0x5A, 0x63, 0x64, 0x65,
            0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
            0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85,
            0x86, 0x87, 0x88, 0x89, 0x8A, 0x92, 0x93, 0x94,
            0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
            0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2,
            0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA,
            0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
            0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8,
            0xD9, 0xDA, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6,
            0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
            0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA,
            0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00,
            0xFB, 0xD5, 0xDB, 0x20, 0xA8, 0xF1, 0x7F, 0xFF,
            0xD9
        ])
        
        files = {'file': ('test_avatar.jpg', io.BytesIO(jpeg_data), 'image/jpeg')}
        
        resp = self.session.post(f"{BASE_URL}/api/users/avatar", files=files)
        assert resp.status_code == 200, f"JPEG avatar upload failed: {resp.text}"
        print("✓ JPEG avatar upload successful")
    
    def test_avatar_get_returns_image(self):
        """GET /api/users/avatar/{user_id} returns the uploaded image"""
        # First upload an avatar
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
            0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
            0x00, 0x00, 0x03, 0x00, 0x01, 0x00, 0x18, 0xDD,
            0x8D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45,
            0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82
        ])
        
        files = {'file': ('test_avatar.png', io.BytesIO(png_data), 'image/png')}
        
        upload_resp = self.session.post(f"{BASE_URL}/api/users/avatar", files=files)
        assert upload_resp.status_code == 200
        
        # Now retrieve the avatar
        get_resp = self.session.get(f"{BASE_URL}/api/users/avatar/{self.user_id}")
        assert get_resp.status_code == 200, f"Avatar retrieval failed: {get_resp.status_code}"
        
        # Check content type is an image
        content_type = get_resp.headers.get('content-type', '')
        assert content_type.startswith('image/'), f"Expected image content-type, got: {content_type}"
        
        # Check we got actual data
        assert len(get_resp.content) > 0, "Avatar response should have content"
        print(f"✓ Avatar retrieval successful: {len(get_resp.content)} bytes, content-type: {content_type}")
    
    def test_avatar_upload_rejects_large_file(self):
        """POST /api/users/avatar rejects files > 5MB"""
        # Create a file larger than 5MB (5.1MB)
        large_data = b'x' * (5 * 1024 * 1024 + 100000)  # 5.1MB
        
        files = {'file': ('large_avatar.png', io.BytesIO(large_data), 'image/png')}
        
        resp = self.session.post(f"{BASE_URL}/api/users/avatar", files=files)
        assert resp.status_code == 400, f"Expected 400 for large file, got: {resp.status_code}"
        
        data = resp.json()
        assert "too large" in data.get("detail", "").lower() or "5mb" in data.get("detail", "").lower(), \
            f"Error message should mention file size: {data}"
        print("✓ Large file correctly rejected")
    
    def test_avatar_upload_rejects_non_image(self):
        """POST /api/users/avatar rejects non-image files"""
        # Create a text file
        text_data = b'This is not an image file'
        
        files = {'file': ('document.txt', io.BytesIO(text_data), 'text/plain')}
        
        resp = self.session.post(f"{BASE_URL}/api/users/avatar", files=files)
        assert resp.status_code == 400, f"Expected 400 for non-image, got: {resp.status_code}"
        
        data = resp.json()
        assert "invalid" in data.get("detail", "").lower() or "format" in data.get("detail", "").lower(), \
            f"Error message should mention invalid format: {data}"
        print("✓ Non-image file correctly rejected")
    
    def test_avatar_upload_rejects_pdf(self):
        """POST /api/users/avatar rejects PDF files"""
        # Minimal PDF header
        pdf_data = b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'
        
        files = {'file': ('document.pdf', io.BytesIO(pdf_data), 'application/pdf')}
        
        resp = self.session.post(f"{BASE_URL}/api/users/avatar", files=files)
        assert resp.status_code == 400, f"Expected 400 for PDF, got: {resp.status_code}"
        print("✓ PDF file correctly rejected")
    
    def test_avatar_get_nonexistent_user_returns_404(self):
        """GET /api/users/avatar/{user_id} returns 404 for non-existent user"""
        resp = self.session.get(f"{BASE_URL}/api/users/avatar/nonexistent_user_12345")
        assert resp.status_code == 404, f"Expected 404 for non-existent user, got: {resp.status_code}"
        print("✓ Non-existent user avatar returns 404")
    
    def test_avatar_upload_requires_auth(self):
        """POST /api/users/avatar requires authentication"""
        unauth_session = requests.Session()
        
        png_data = bytes([0x89, 0x50, 0x4E, 0x47])  # PNG header
        files = {'file': ('test.png', io.BytesIO(png_data), 'image/png')}
        
        resp = unauth_session.post(f"{BASE_URL}/api/users/avatar", files=files)
        assert resp.status_code == 401, f"Expected 401 for unauthenticated request, got: {resp.status_code}"
        print("✓ Avatar upload requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
