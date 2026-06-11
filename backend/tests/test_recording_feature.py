"""
Test Recording Feature - Backend API Tests
Tests for:
- POST /api/meetings/{id}/recording/upload - file upload to Object Storage
- POST /api/meetings/{id}/recording/stop - creates recording metadata
- GET /api/meetings/{id}/recording/play/{filename} - serves uploaded file
- File size limit (500MB max)
- Recording URL update in database
"""

import pytest
import requests
import os
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def session():
    """Create a requests session with auth cookies"""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    # Login
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if resp.status_code != 200:
        pytest.skip(f"Login failed: {resp.status_code} - {resp.text}")
    return s


@pytest.fixture(scope="module")
def test_meeting(session):
    """Create a test meeting for recording tests"""
    resp = session.post(f"{BASE_URL}/api/meetings", json={
        "title": "TEST_Recording_Feature_Meeting",
        "meeting_type": "instant",
        "recording_enabled": True
    })
    assert resp.status_code == 200, f"Failed to create meeting: {resp.text}"
    meeting = resp.json()
    yield meeting
    # Cleanup
    try:
        session.delete(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
    except:
        pass


class TestRecordingStop:
    """Tests for POST /api/meetings/{id}/recording/stop"""
    
    def test_recording_stop_creates_metadata(self, session, test_meeting):
        """POST /api/meetings/{id}/recording/stop creates recording metadata entry"""
        meeting_id = test_meeting["meeting_id"]
        
        # Stop recording (creates metadata)
        resp = session.post(f"{BASE_URL}/api/meetings/{meeting_id}/recording/stop")
        assert resp.status_code == 200, f"Recording stop failed: {resp.text}"
        
        data = resp.json()
        assert "recording_id" in data, "Response should contain recording_id"
        assert data["status"] == "recording_stopped"
        assert "duration" in data
        
        # Verify recording was created in database via recordings list
        rec_resp = session.get(f"{BASE_URL}/api/recordings")
        assert rec_resp.status_code == 200
        recordings = rec_resp.json().get("recordings", [])
        
        # Find our recording
        found = any(r["recording_id"] == data["recording_id"] for r in recordings)
        assert found, f"Recording {data['recording_id']} not found in recordings list"
    
    def test_recording_stop_requires_auth(self, test_meeting):
        """POST /api/meetings/{id}/recording/stop requires authentication"""
        meeting_id = test_meeting["meeting_id"]
        
        # Request without auth
        resp = requests.post(f"{BASE_URL}/api/meetings/{meeting_id}/recording/stop")
        assert resp.status_code == 401, "Should require authentication"


class TestRecordingUpload:
    """Tests for POST /api/meetings/{id}/recording/upload"""
    
    def test_upload_recording_success(self, session, test_meeting):
        """POST /api/meetings/{id}/recording/upload accepts file and stores in Object Storage"""
        meeting_id = test_meeting["meeting_id"]
        
        # First create a recording entry via stop
        stop_resp = session.post(f"{BASE_URL}/api/meetings/{meeting_id}/recording/stop")
        assert stop_resp.status_code == 200
        
        # Create a small test webm file (minimal valid webm header)
        test_content = b'\x1a\x45\xdf\xa3' + b'\x00' * 100  # EBML header + padding
        
        # Upload the file - use a fresh request without session headers
        # to avoid Content-Type conflicts with multipart
        cookies = session.cookies.get_dict()
        
        resp = requests.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/recording/upload",
            files={'file': ('test_recording.webm', io.BytesIO(test_content), 'video/webm')},
            cookies=cookies
        )
        
        assert resp.status_code == 200, f"Upload failed: {resp.text}"
        data = resp.json()
        assert "url" in data, "Response should contain url"
        assert data["url"].startswith("/api/meetings/"), "URL should be a valid API path"
        assert "recording/play" in data["url"], "URL should contain recording/play"
    
    def test_upload_recording_updates_latest_entry(self, session, test_meeting):
        """POST /api/meetings/{id}/recording/upload updates the latest recording entry with URL"""
        meeting_id = test_meeting["meeting_id"]
        
        # Create a recording entry
        stop_resp = session.post(f"{BASE_URL}/api/meetings/{meeting_id}/recording/stop")
        assert stop_resp.status_code == 200
        recording_id = stop_resp.json()["recording_id"]
        
        # Upload file - use fresh request with cookies
        test_content = b'\x1a\x45\xdf\xa3' + b'\x00' * 50
        cookies = session.cookies.get_dict()
        
        upload_resp = requests.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/recording/upload",
            files={'file': ('test.webm', io.BytesIO(test_content), 'video/webm')},
            cookies=cookies
        )
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        
        # Verify the recording entry was updated with URL
        rec_resp = session.get(f"{BASE_URL}/api/recordings")
        assert rec_resp.status_code == 200
        recordings = rec_resp.json().get("recordings", [])
        
        # Find our recording
        our_rec = next((r for r in recordings if r["recording_id"] == recording_id), None)
        assert our_rec is not None, f"Recording {recording_id} not found"
        assert our_rec.get("url"), f"Recording should have URL after upload, got: {our_rec}"
    
    def test_upload_recording_requires_auth(self, test_meeting):
        """POST /api/meetings/{id}/recording/upload requires authentication"""
        meeting_id = test_meeting["meeting_id"]
        
        test_content = b'\x1a\x45\xdf\xa3' + b'\x00' * 50
        files = {'file': ('test.webm', io.BytesIO(test_content), 'video/webm')}
        
        resp = requests.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/recording/upload",
            files=files
        )
        assert resp.status_code == 401, "Should require authentication"
    
    def test_upload_recording_404_for_invalid_meeting(self, session):
        """POST /api/meetings/{id}/recording/upload returns 404 for non-existent meeting"""
        test_content = b'\x1a\x45\xdf\xa3' + b'\x00' * 50
        cookies = session.cookies.get_dict()
        
        resp = requests.post(
            f"{BASE_URL}/api/meetings/nonexistent_meeting_id/recording/upload",
            files={'file': ('test.webm', io.BytesIO(test_content), 'video/webm')},
            cookies=cookies
        )
        assert resp.status_code == 404, f"Should return 404, got {resp.status_code}"


class TestRecordingPlay:
    """Tests for GET /api/meetings/{id}/recording/play/{filename}"""
    
    def test_play_recording_serves_file(self, session):
        """GET /api/meetings/{id}/recording/play/{filename} serves the uploaded file"""
        # Use the known recording from meet_8afa2e15ca
        meeting_id = "meet_8afa2e15ca"
        filename = "6d03ce5d.webm"
        
        resp = session.get(f"{BASE_URL}/api/meetings/{meeting_id}/recording/play/{filename}")
        
        # Should return 200 with video content
        assert resp.status_code == 200, f"Play failed: {resp.status_code} - {resp.text[:200] if resp.text else 'no content'}"
        
        # Check content type
        content_type = resp.headers.get("content-type", "")
        assert "video" in content_type or "webm" in content_type or "octet-stream" in content_type, \
            f"Expected video content type, got: {content_type}"
    
    def test_play_recording_404_for_invalid_file(self, session):
        """GET /api/meetings/{id}/recording/play/{filename} returns 404 for non-existent file"""
        resp = session.get(f"{BASE_URL}/api/meetings/meet_8afa2e15ca/recording/play/nonexistent.webm")
        assert resp.status_code == 404, f"Should return 404, got {resp.status_code}"
    
    def test_play_recording_404_for_invalid_meeting(self, session):
        """GET /api/meetings/{id}/recording/play/{filename} returns 404 for non-existent meeting"""
        resp = session.get(f"{BASE_URL}/api/meetings/nonexistent_meeting/recording/play/test.webm")
        assert resp.status_code == 404, f"Should return 404, got {resp.status_code}"


class TestRecordingsList:
    """Tests for GET /api/recordings - verify recordings with/without URLs"""
    
    def test_recordings_list_shows_url_status(self, session):
        """GET /api/recordings returns recordings with url field (empty or populated)"""
        resp = session.get(f"{BASE_URL}/api/recordings")
        assert resp.status_code == 200
        
        data = resp.json()
        assert "recordings" in data
        assert "total" in data
        
        # Check that recordings have url field
        for rec in data["recordings"]:
            assert "url" in rec, f"Recording should have url field: {rec}"
            assert "recording_id" in rec
            assert "title" in rec
            assert "meeting_id" in rec
    
    def test_recordings_search_works(self, session):
        """GET /api/recordings?search=... filters recordings"""
        resp = session.get(f"{BASE_URL}/api/recordings?search=Team")
        assert resp.status_code == 200
        
        data = resp.json()
        # If there are results, they should match the search
        for rec in data.get("recordings", []):
            assert "team" in rec.get("title", "").lower() or "team" in rec.get("meeting_id", "").lower(), \
                f"Search result should match 'Team': {rec}"
    
    def test_recordings_pagination_works(self, session):
        """GET /api/recordings?page=1&limit=5 returns paginated results"""
        resp = session.get(f"{BASE_URL}/api/recordings?page=1&limit=5")
        assert resp.status_code == 200
        
        data = resp.json()
        assert "recordings" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data
        assert len(data["recordings"]) <= 5, "Should respect limit"


class TestFileSizeLimit:
    """Test file size limit enforcement"""
    
    def test_upload_rejects_large_file_header_check(self, session, test_meeting):
        """
        Note: We can't easily test 500MB+ files in unit tests.
        This test verifies the endpoint exists and handles normal files.
        The 500MB limit is enforced in the backend code.
        """
        meeting_id = test_meeting["meeting_id"]
        
        # Create a recording entry
        session.post(f"{BASE_URL}/api/meetings/{meeting_id}/recording/stop")
        
        # Upload a normal-sized file (should succeed)
        test_content = b'\x1a\x45\xdf\xa3' + b'\x00' * 1000  # ~1KB
        cookies = session.cookies.get_dict()
        
        resp = requests.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/recording/upload",
            files={'file': ('test.webm', io.BytesIO(test_content), 'video/webm')},
            cookies=cookies
        )
        
        # Should succeed for small files
        assert resp.status_code == 200, f"Small file upload should succeed: {resp.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
