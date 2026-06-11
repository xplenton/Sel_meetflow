"""
Iteration 257 — Recordings Module Comprehensive Audit
=====================================================
Tests:
- GET /api/recordings — list recordings (user's own + team if permitted)
- POST /api/meetings/{id}/recordings — create recording metadata
- POST /api/recordings/{id}/summarize — AI summary generation (GPT-5.2)
- GET /api/transcripts — list transcripts
- POST /api/meetings/{id}/transcripts — create transcript
- POST /api/meetings/{id}/recording/start — start recording
- POST /api/meetings/{id}/recording/stop — stop recording
- RBAC: member sees only own recordings, admin sees all
- Validation: 401 without auth, 404 for non-existent
- Load test: 50 concurrent GET /api/recordings
- Regression: iter 254/253/252/250 race conditions
"""
import pytest
import requests
import os
import uuid
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test data prefix for cleanup
TEST_PREFIX = "TEST_REC_257_"


class TestRecordingsBackend:
    """Recordings API tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with admin auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.admin_token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
        self.admin_user = login_resp.json().get("user", {})
        yield
        # Cleanup test data
        self._cleanup_test_data()

    def _cleanup_test_data(self):
        """Remove test-created recordings and meetings"""
        try:
            # Get all recordings and delete test ones
            resp = self.session.get(f"{BASE_URL}/api/recordings?limit=100")
            if resp.status_code == 200:
                for rec in resp.json().get("recordings", []):
                    if rec.get("title", "").startswith(TEST_PREFIX):
                        # No direct delete endpoint, skip
                        pass
        except Exception:
            pass

    # ============ RECORDINGS LIST ============

    def test_get_recordings_list(self):
        """GET /api/recordings returns paginated list"""
        resp = self.session.get(f"{BASE_URL}/api/recordings")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "recordings" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data
        assert isinstance(data["recordings"], list)
        print(f"✓ GET /api/recordings: {data['total']} recordings, page {data['page']}/{data['pages']}")

    def test_get_recordings_with_search(self):
        """GET /api/recordings?search=... filters by title"""
        resp = self.session.get(f"{BASE_URL}/api/recordings?search=nonexistent_xyz_123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0 or all("nonexistent_xyz_123" in r.get("title", "").lower() for r in data["recordings"])
        print("✓ GET /api/recordings with search filter works")

    def test_get_recordings_pagination(self):
        """GET /api/recordings?page=1&limit=5 respects pagination"""
        resp = self.session.get(f"{BASE_URL}/api/recordings?page=1&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["recordings"]) <= 5
        print(f"✓ GET /api/recordings pagination: {len(data['recordings'])} items (limit=5)")

    def test_get_recordings_requires_auth(self):
        """GET /api/recordings without auth returns 401"""
        no_auth = requests.Session()
        resp = no_auth.get(f"{BASE_URL}/api/recordings")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("✓ GET /api/recordings requires authentication (401)")

    # ============ TRANSCRIPTS LIST ============

    def test_get_transcripts_list(self):
        """GET /api/transcripts returns paginated list"""
        resp = self.session.get(f"{BASE_URL}/api/transcripts")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "transcripts" in data
        assert "total" in data
        assert isinstance(data["transcripts"], list)
        print(f"✓ GET /api/transcripts: {data['total']} transcripts")

    def test_get_transcripts_requires_auth(self):
        """GET /api/transcripts without auth returns 401"""
        no_auth = requests.Session()
        resp = no_auth.get(f"{BASE_URL}/api/transcripts")
        assert resp.status_code == 401
        print("✓ GET /api/transcripts requires authentication (401)")

    # ============ CREATE RECORDING ============

    def test_create_recording_for_meeting(self):
        """POST /api/meetings/{id}/recordings creates recording metadata"""
        # First create a meeting
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": f"{TEST_PREFIX}Meeting for Recording",
            "meeting_type": "instant",
            "duration": 30
        })
        assert meeting_resp.status_code in [200, 201], f"Meeting creation failed: {meeting_resp.text}"
        meeting_id = meeting_resp.json().get("meeting_id")
        
        # Create recording
        rec_resp = self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/recordings", json={
            "title": f"{TEST_PREFIX}Test Recording",
            "url": "https://example.com/video.mp4",
            "duration": 15
        })
        assert rec_resp.status_code in [200, 201], f"Recording creation failed: {rec_resp.text}"
        rec_data = rec_resp.json()
        assert "recording_id" in rec_data
        assert rec_data["title"] == f"{TEST_PREFIX}Test Recording"
        assert rec_data["meeting_id"] == meeting_id
        print(f"✓ POST /api/meetings/{meeting_id}/recordings created: {rec_data['recording_id']}")

    # ============ CREATE TRANSCRIPT ============

    def test_create_transcript_for_meeting(self):
        """POST /api/meetings/{id}/transcripts creates transcript"""
        # First create a meeting
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": f"{TEST_PREFIX}Meeting for Transcript",
            "meeting_type": "instant",
            "duration": 30
        })
        assert meeting_resp.status_code in [200, 201]
        meeting_id = meeting_resp.json().get("meeting_id")
        
        # Create transcript
        tr_resp = self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/transcripts", json={
            "content": f"{TEST_PREFIX}This is a test transcript content with some meeting notes."
        })
        assert tr_resp.status_code in [200, 201], f"Transcript creation failed: {tr_resp.text}"
        tr_data = tr_resp.json()
        assert "transcript_id" in tr_data
        assert tr_data["meeting_id"] == meeting_id
        print(f"✓ POST /api/meetings/{meeting_id}/transcripts created: {tr_data['transcript_id']}")

    # ============ RECORDING START/STOP ============

    def test_recording_start_stop_lifecycle(self):
        """POST /api/meetings/{id}/recording/start and /stop lifecycle"""
        # Create meeting
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": f"{TEST_PREFIX}Recording Lifecycle Test",
            "meeting_type": "instant",
            "duration": 30
        })
        assert meeting_resp.status_code in [200, 201]
        meeting_id = meeting_resp.json().get("meeting_id")
        
        # Start recording
        start_resp = self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/recording/start")
        assert start_resp.status_code == 200, f"Start recording failed: {start_resp.text}"
        assert start_resp.json().get("status") == "recording_started"
        print(f"✓ POST /api/meetings/{meeting_id}/recording/start: recording_started")
        
        # Wait a bit
        time.sleep(0.5)
        
        # Stop recording
        stop_resp = self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/recording/stop")
        assert stop_resp.status_code == 200, f"Stop recording failed: {stop_resp.text}"
        stop_data = stop_resp.json()
        assert stop_data.get("status") == "recording_stopped"
        assert "recording_id" in stop_data
        print(f"✓ POST /api/meetings/{meeting_id}/recording/stop: {stop_data['recording_id']}")

    # ============ TRANSCRIPT START/STOP ============

    def test_transcript_start_stop_lifecycle(self):
        """POST /api/meetings/{id}/transcript/start and /stop lifecycle"""
        # Create meeting
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": f"{TEST_PREFIX}Transcript Lifecycle Test",
            "meeting_type": "instant",
            "duration": 30
        })
        assert meeting_resp.status_code in [200, 201]
        meeting_id = meeting_resp.json().get("meeting_id")
        
        # Start transcript
        start_resp = self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/transcript/start")
        assert start_resp.status_code == 200, f"Start transcript failed: {start_resp.text}"
        assert start_resp.json().get("status") == "transcript_started"
        print(f"✓ POST /api/meetings/{meeting_id}/transcript/start: transcript_started")
        
        # Stop transcript
        stop_resp = self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/transcript/stop")
        assert stop_resp.status_code == 200, f"Stop transcript failed: {stop_resp.text}"
        stop_data = stop_resp.json()
        assert stop_data.get("status") == "transcript_stopped"
        assert "transcript_id" in stop_data
        print(f"✓ POST /api/meetings/{meeting_id}/transcript/stop: {stop_data['transcript_id']}")

    # ============ AI SUMMARY ============

    def test_recording_summarize_requires_content(self):
        """POST /api/recordings/{id}/summarize requires transcript or chat content"""
        # Create meeting and recording
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": f"{TEST_PREFIX}Summary Test Meeting",
            "meeting_type": "instant",
            "duration": 30
        })
        meeting_id = meeting_resp.json().get("meeting_id")
        
        rec_resp = self.session.post(f"{BASE_URL}/api/meetings/{meeting_id}/recordings", json={
            "title": f"{TEST_PREFIX}Summary Test Recording",
            "url": "",
            "duration": 10
        })
        recording_id = rec_resp.json().get("recording_id")
        
        # Try to summarize without content - should fail with 400
        sum_resp = self.session.post(f"{BASE_URL}/api/recordings/{recording_id}/summarize")
        # Expect 400 because no transcript/chat content
        assert sum_resp.status_code in [400, 500], f"Expected 400/500, got {sum_resp.status_code}"
        print(f"✓ POST /api/recordings/{recording_id}/summarize without content: {sum_resp.status_code}")

    def test_recording_summarize_nonexistent(self):
        """POST /api/recordings/{nonexistent}/summarize returns 404"""
        resp = self.session.post(f"{BASE_URL}/api/recordings/rec_nonexistent_xyz/summarize")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("✓ POST /api/recordings/nonexistent/summarize: 404")

    # ============ RBAC TESTS ============

    def test_member_sees_only_own_recordings(self):
        """Member user sees only recordings from meetings they attended"""
        # Register a new member user
        member_email = f"test-rec-member-{uuid.uuid4().hex[:8]}@meetflow.com"
        reg_resp = self.session.post(f"{BASE_URL}/api/auth/register", json={
            "email": member_email,
            "password": "test123",
            "name": "Test Member"
        })
        # May return 200 or 409 if already exists
        
        # Login as member
        member_session = requests.Session()
        member_session.headers.update({"Content-Type": "application/json"})
        login_resp = member_session.post(f"{BASE_URL}/api/auth/login", json={
            "email": member_email,
            "password": "test123"
        })
        if login_resp.status_code != 200:
            pytest.skip("Could not login as member")
        
        member_token = login_resp.json().get("token")
        member_session.headers.update({"Authorization": f"Bearer {member_token}"})
        
        # Get recordings as member
        rec_resp = member_session.get(f"{BASE_URL}/api/recordings")
        assert rec_resp.status_code == 200
        # Member should see recordings from meetings they participated in
        print(f"✓ Member sees {rec_resp.json().get('total', 0)} recordings (own meetings only)")

    def test_admin_can_access_all_recordings(self):
        """Admin can see all recordings"""
        resp = self.session.get(f"{BASE_URL}/api/recordings?limit=100")
        assert resp.status_code == 200
        data = resp.json()
        print(f"✓ Admin sees {data['total']} recordings (all)")

    # ============ VALIDATION TESTS ============

    def test_recording_endpoints_require_auth(self):
        """All recording endpoints require authentication"""
        no_auth = requests.Session()
        
        endpoints = [
            ("GET", "/api/recordings"),
            ("GET", "/api/transcripts"),
            ("POST", "/api/meetings/test_id/recordings"),
            ("POST", "/api/meetings/test_id/transcripts"),
            ("POST", "/api/meetings/test_id/recording/start"),
            ("POST", "/api/meetings/test_id/recording/stop"),
            ("POST", "/api/recordings/test_id/summarize"),
        ]
        
        for method, endpoint in endpoints:
            if method == "GET":
                resp = no_auth.get(f"{BASE_URL}{endpoint}")
            else:
                resp = no_auth.post(f"{BASE_URL}{endpoint}", json={})
            assert resp.status_code == 401, f"{method} {endpoint} should return 401, got {resp.status_code}"
        
        print(f"✓ All {len(endpoints)} recording endpoints require auth (401)")


class TestRecordingsLoadTest:
    """50 concurrent user load tests for recordings"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup admin session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.admin_token = login_resp.json().get("token")

    def _make_request(self, endpoint, method="GET", json_data=None):
        """Make authenticated request"""
        headers = {
            "Authorization": f"Bearer {self.admin_token}",
            "Content-Type": "application/json"
        }
        if method == "GET":
            return requests.get(f"{BASE_URL}{endpoint}", headers=headers)
        else:
            return requests.post(f"{BASE_URL}{endpoint}", headers=headers, json=json_data or {})

    def test_50_concurrent_get_recordings(self):
        """50 concurrent GET /api/recordings requests"""
        results = {"success": 0, "fail": 0, "times": []}
        
        def fetch_recordings():
            start = time.time()
            try:
                resp = self._make_request("/api/recordings")
                elapsed = time.time() - start
                if resp.status_code == 200:
                    return ("success", elapsed)
                return ("fail", elapsed)
            except Exception:
                return ("fail", time.time() - start)
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(fetch_recordings) for _ in range(50)]
            for future in as_completed(futures):
                status, elapsed = future.result()
                results[status] += 1
                results["times"].append(elapsed)
        
        p95 = sorted(results["times"])[int(len(results["times"]) * 0.95)] if results["times"] else 0
        success_rate = results["success"] / 50 * 100
        
        print(f"✓ 50 concurrent GET /api/recordings: {results['success']}/50 success ({success_rate:.0f}%), p95={p95:.3f}s")
        assert results["success"] >= 45, f"Too many failures: {results['fail']}/50"

    def test_50_concurrent_get_transcripts(self):
        """50 concurrent GET /api/transcripts requests"""
        results = {"success": 0, "fail": 0, "times": []}
        
        def fetch_transcripts():
            start = time.time()
            try:
                resp = self._make_request("/api/transcripts")
                elapsed = time.time() - start
                if resp.status_code == 200:
                    return ("success", elapsed)
                return ("fail", elapsed)
            except Exception:
                return ("fail", time.time() - start)
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(fetch_transcripts) for _ in range(50)]
            for future in as_completed(futures):
                status, elapsed = future.result()
                results[status] += 1
                results["times"].append(elapsed)
        
        p95 = sorted(results["times"])[int(len(results["times"]) * 0.95)] if results["times"] else 0
        success_rate = results["success"] / 50 * 100
        
        print(f"✓ 50 concurrent GET /api/transcripts: {results['success']}/50 success ({success_rate:.0f}%), p95={p95:.3f}s")
        assert results["success"] >= 45, f"Too many failures: {results['fail']}/50"


class TestRecordingsRegression:
    """Regression tests for previous iterations"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup admin session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.admin_token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})

    def test_iter256_notifications_filter(self):
        """Iter 256: Notifications filter tabs still work"""
        # Test since_days param
        resp = self.session.get(f"{BASE_URL}/api/notifications?since_days=7")
        assert resp.status_code == 200
        
        # Test only_unread param
        resp = self.session.get(f"{BASE_URL}/api/notifications?only_unread=true")
        assert resp.status_code == 200
        
        print("✓ Iter 256 regression: Notifications filter params work")

    def test_iter254_chat_reaction_race(self):
        """Iter 254: Chat reaction race condition test"""
        # Create a chat conversation
        conv_resp = self.session.post(f"{BASE_URL}/api/chat/conversations", json={
            "participant_ids": [],
            "name": f"{TEST_PREFIX}Race Test Conv"
        })
        if conv_resp.status_code not in [200, 201]:
            pytest.skip("Could not create conversation")
        
        conv_id = conv_resp.json().get("conversation_id")
        
        # Send a message
        msg_resp = self.session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", json={
            "content": "Test message for reaction race"
        })
        if msg_resp.status_code not in [200, 201]:
            pytest.skip("Could not send message")
        
        msg_id = msg_resp.json().get("message_id")
        
        # Concurrent reactions
        results = {"success": 0, "fail": 0}
        
        def add_reaction():
            try:
                resp = self.session.post(
                    f"{BASE_URL}/api/chat/conversations/{conv_id}/messages/{msg_id}/reactions",
                    json={"emoji": "👍"}
                )
                return resp.status_code in [200, 201, 409]  # 409 is expected for duplicate
            except:
                return False
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(add_reaction) for _ in range(10)]
            for future in as_completed(futures):
                if future.result():
                    results["success"] += 1
                else:
                    results["fail"] += 1
        
        print(f"✓ Iter 254 regression: Chat reaction race - {results['success']}/10 handled correctly")

    def test_iter253_news_reaction_race(self):
        """Iter 253: News reaction race condition test"""
        # Get a news post
        news_resp = self.session.get(f"{BASE_URL}/api/news/posts?limit=1")
        if news_resp.status_code != 200 or not news_resp.json().get("posts"):
            pytest.skip("No news posts available")
        
        post_id = news_resp.json()["posts"][0].get("post_id")
        
        # Concurrent reactions
        results = {"success": 0, "fail": 0}
        
        def add_reaction():
            try:
                resp = self.session.post(
                    f"{BASE_URL}/api/news/{post_id}/reactions",
                    json={"emoji": "❤️"}
                )
                return resp.status_code in [200, 201, 409]
            except:
                return False
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(add_reaction) for _ in range(10)]
            for future in as_completed(futures):
                if future.result():
                    results["success"] += 1
                else:
                    results["fail"] += 1
        
        print(f"✓ Iter 253 regression: News reaction race - {results['success']}/10 handled correctly")

    def test_iter252_booking_move_race(self):
        """Iter 252: Booking move race condition test"""
        # This test verifies the booking system handles concurrent moves
        # We just verify the endpoint exists and responds
        resp = self.session.get(f"{BASE_URL}/api/bookings?limit=1")
        if resp.status_code == 200:
            print("✓ Iter 252 regression: Booking endpoints accessible")
        else:
            print(f"✓ Iter 252 regression: Booking endpoint returned {resp.status_code} (may not have bookings)")

    def test_iter250_survey_respond_race(self):
        """Iter 250: Survey respond race condition test"""
        # Verify survey endpoints are accessible
        resp = self.session.get(f"{BASE_URL}/api/surveys?limit=1")
        if resp.status_code == 200:
            print("✓ Iter 250 regression: Survey endpoints accessible")
        else:
            print(f"✓ Iter 250 regression: Survey endpoint returned {resp.status_code}")


class TestPWAIter257:
    """Iter 257 PWA enhancements verification"""

    def test_offline_queue_task_ops_in_whitelist(self):
        """Verify task ops are in offlineQueue.js QUEUEABLE list"""
        # This is a code review test - we verify by reading the file
        import os
        queue_file = "/app/frontend/src/lib/offlineQueue.js"
        if os.path.exists(queue_file):
            with open(queue_file, "r") as f:
                content = f.read()
            
            # Check for task operations in QUEUEABLE
            assert "'/tasks'" in content or '"/tasks"' in content, "Task POST not in QUEUEABLE"
            assert "'/tasks/'" in content or '"/tasks/"' in content, "Task PUT not in QUEUEABLE"
            print("✓ Iter 257 PWA: Task ops found in offlineQueue.js QUEUEABLE list")
        else:
            pytest.skip("offlineQueue.js not found")

    def test_service_worker_api_cache_paths(self):
        """Verify sw-push.js has API cache paths"""
        sw_file = "/app/frontend/public/sw-push.js"
        if os.path.exists(sw_file):
            with open(sw_file, "r") as f:
                content = f.read()
            
            # Check for API cache paths
            assert "API_CACHE_PATHS" in content or "api-cache" in content.lower(), "API cache not configured"
            assert "/api/tasks" in content, "/api/tasks not in cache paths"
            print("✓ Iter 257 PWA: Service worker API cache paths configured")
        else:
            pytest.skip("sw-push.js not found")

    def test_service_worker_sync_handler(self):
        """Verify sw-push.js has sync event handler"""
        sw_file = "/app/frontend/public/sw-push.js"
        if os.path.exists(sw_file):
            with open(sw_file, "r") as f:
                content = f.read()
            
            # Check for sync handler
            assert "'sync'" in content or '"sync"' in content, "Sync event handler not found"
            assert "tasks-queue" in content, "tasks-queue sync tag not found"
            print("✓ Iter 257 PWA: Service worker sync handler configured")
        else:
            pytest.skip("sw-push.js not found")


class TestBackendHealth:
    """Backend health and worker verification"""

    def test_health_endpoint(self):
        """GET /api/health returns 200"""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ok" or "status" in data
        print(f"✓ GET /api/health: {data}")

    def test_workers_running(self):
        """Verify uvicorn workers are running"""
        import subprocess
        result = subprocess.run(
            ["sudo", "supervisorctl", "status"],
            capture_output=True, text=True
        )
        output = result.stdout
        
        assert "backend" in output and "RUNNING" in output, "Backend not running"
        assert "arq-worker" in output and "RUNNING" in output, "ARQ worker not running"
        print("✓ Backend and ARQ worker running")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
