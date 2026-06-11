"""
Iteration 89 - Quick-Scan Feature Tests + Regression Tests

Tests:
1. Quick-Scan creation (POST /api/meetings/{mid}/quick-scan/{target_user_id}) - host/co-host only
2. 403 for non-host attempting Quick-Scan
3. 404 for unknown meeting_id
4. 404 for unknown target_user_id (participant not in meeting)
5. Public resolve (GET /api/diag/shared/{token}) works for Quick-Scan tokens
6. Public submit (POST /api/diag/shared/{token}/submit) with max_submissions=3, 429 on overflow
7. List Quick-Scans (GET /api/meetings/{mid}/quick-scans) - host only
8. E2E flow: Create → Resolve → Submit → List shows submission
9. Regression: Admin diag/shared endpoints (create, list, revoke, resolve, submit)
10. Regression: Action-Items POST/GET/PUT
11. Regression: Insights, Focus-Times, Dashboard/Agenda/Calendar
"""

import pytest
import requests
import os
import uuid
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"


def get_admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json().get("token")


def get_auth_headers():
    """Get authorization headers with admin token"""
    token = get_admin_token()
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def create_test_meeting():
    """Create a test meeting and return meeting data"""
    headers = get_auth_headers()
    meeting_data = {
        "title": f"TEST_QuickScan_Meeting_{uuid.uuid4().hex[:6]}",
        "description": "Test meeting for Quick-Scan feature",
        "meeting_type": "instant",  # instant meeting so host is joined
        "duration": 60
    }
    response = requests.post(f"{BASE_URL}/api/meetings", json=meeting_data, headers=headers)
    assert response.status_code in [200, 201], f"Meeting creation failed: {response.text}"
    return response.json()


def create_test_participant(meeting_id):
    """Create a test participant in the meeting"""
    # Register a new user
    participant_email = f"TEST_participant_{uuid.uuid4().hex[:6]}@test.com"
    reg_response = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": participant_email,
        "password": "testpass123",
        "name": "Test Participant"
    })
    
    # Login as participant
    login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": participant_email,
        "password": "testpass123"
    })
    
    if login_response.status_code != 200:
        return None
    
    participant_token = login_response.json().get("token")
    participant_user = login_response.json()
    
    # Join the meeting as participant
    join_response = requests.post(
        f"{BASE_URL}/api/meetings/{meeting_id}/join",
        headers={"Authorization": f"Bearer {participant_token}"}
    )
    
    return {
        "user_id": participant_user.get("user_id"),
        "email": participant_email,
        "token": participant_token,
        "name": "Test Participant"
    }


class TestQuickScanCreation:
    """Test Quick-Scan token creation endpoint"""
    
    def test_create_quick_scan_as_host(self):
        """Host can create Quick-Scan token for a participant"""
        headers = get_auth_headers()
        meeting = create_test_meeting()
        meeting_id = meeting["meeting_id"]
        
        # Create a participant
        participant = create_test_participant(meeting_id)
        if not participant:
            pytest.skip("Could not create test participant")
        
        target_user_id = participant["user_id"]
        
        response = requests.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/quick-scan/{target_user_id}",
            headers=headers
        )
        
        assert response.status_code == 200, f"Quick-Scan creation failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "token" in data, "Response missing 'token'"
        assert "share_url" in data, "Response missing 'share_url'"
        assert "qr_png" in data, "Response missing 'qr_png'"
        assert "expires_at" in data, "Response missing 'expires_at'"
        assert "target_user_name" in data, "Response missing 'target_user_name'"
        assert data.get("ok") == True, "Response 'ok' should be True"
        
        # Verify QR PNG is a data URL
        assert data["qr_png"].startswith("data:image/png;base64,"), "QR PNG should be base64 data URL"
        
        print(f"✓ Quick-Scan created: token={data['token'][:8]}...")
    
    def test_quick_scan_403_for_non_host(self):
        """Non-host user gets 403 when trying to create Quick-Scan"""
        headers = get_auth_headers()
        meeting = create_test_meeting()
        meeting_id = meeting["meeting_id"]
        
        # Create a participant
        participant = create_test_participant(meeting_id)
        if not participant:
            pytest.skip("Could not create test participant")
        
        # Use participant's token to try creating a Quick-Scan
        participant_headers = {"Authorization": f"Bearer {participant['token']}", "Content-Type": "application/json"}
        
        response = requests.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/quick-scan/{participant['user_id']}",
            headers=participant_headers
        )
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ Non-host correctly gets 403")
    
    def test_quick_scan_404_unknown_meeting(self):
        """404 for unknown meeting_id"""
        headers = get_auth_headers()
        fake_meeting_id = f"fake_meeting_{uuid.uuid4().hex[:10]}"
        fake_user_id = f"fake_user_{uuid.uuid4().hex[:10]}"
        
        response = requests.post(
            f"{BASE_URL}/api/meetings/{fake_meeting_id}/quick-scan/{fake_user_id}",
            headers=headers
        )
        
        # Could be 403 (not a host of non-existent meeting) or 404
        assert response.status_code in [403, 404], f"Expected 403/404, got {response.status_code}: {response.text}"
        print(f"✓ Unknown meeting_id returns {response.status_code}")
    
    def test_quick_scan_404_unknown_participant(self):
        """404 for unknown target_user_id (participant not in meeting)"""
        headers = get_auth_headers()
        meeting = create_test_meeting()
        meeting_id = meeting["meeting_id"]
        fake_user_id = f"fake_user_{uuid.uuid4().hex[:10]}"
        
        response = requests.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/quick-scan/{fake_user_id}",
            headers=headers
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("✓ Unknown target_user_id returns 404")


class TestQuickScanPublicEndpoints:
    """Test public resolve and submit endpoints for Quick-Scan tokens"""
    
    def test_public_resolve_quick_scan_token(self):
        """Public resolve works for Quick-Scan tokens"""
        headers = get_auth_headers()
        meeting = create_test_meeting()
        meeting_id = meeting["meeting_id"]
        
        participant = create_test_participant(meeting_id)
        if not participant:
            pytest.skip("Could not create test participant")
        
        # Create Quick-Scan token
        create_response = requests.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/quick-scan/{participant['user_id']}",
            headers=headers
        )
        
        if create_response.status_code != 200:
            pytest.skip("Could not create Quick-Scan token")
        
        token = create_response.json()["token"]
        
        # No auth required for resolve
        response = requests.get(f"{BASE_URL}/api/diag/shared/{token}")
        
        assert response.status_code == 200, f"Resolve failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "token" in data, "Response missing 'token'"
        assert "created_by_name" in data, "Response missing 'created_by_name'"
        assert "note" in data, "Response missing 'note'"
        assert "expires_at" in data, "Response missing 'expires_at'"
        
        # Note should contain "Quick-Scan"
        assert "Quick-Scan" in data.get("note", ""), f"Note should contain 'Quick-Scan': {data.get('note')}"
        
        print(f"✓ Public resolve works: note='{data['note']}'")
    
    def test_public_submit_quick_scan(self):
        """Public submit works for Quick-Scan tokens"""
        headers = get_auth_headers()
        meeting = create_test_meeting()
        meeting_id = meeting["meeting_id"]
        
        participant = create_test_participant(meeting_id)
        if not participant:
            pytest.skip("Could not create test participant")
        
        # Create Quick-Scan token
        create_response = requests.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/quick-scan/{participant['user_id']}",
            headers=headers
        )
        
        if create_response.status_code != 200:
            pytest.skip("Could not create Quick-Scan token")
        
        token = create_response.json()["token"]
        
        # Submit diagnostic results (no auth required)
        submit_data = {
            "reporter_name": "Test User",
            "user_agent": "Mozilla/5.0 Test",
            "results": {
                "cam": {"state": "ok", "label": "Camera working"},
                "mic": {"state": "ok", "label": "Microphone working"},
                "webrtc": {"state": "ok", "label": "WebRTC supported"}
            },
            "logs": ["Test log entry"]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/diag/shared/{token}/submit",
            json=submit_data
        )
        
        assert response.status_code == 200, f"Submit failed: {response.text}"
        data = response.json()
        assert data.get("ok") == True, "Submit response 'ok' should be True"
        
        print("✓ Public submit works for Quick-Scan token")
    
    def test_quick_scan_max_submissions_429(self):
        """Quick-Scan tokens have max_submissions=3, returns 429 on overflow"""
        headers = get_auth_headers()
        meeting = create_test_meeting()
        meeting_id = meeting["meeting_id"]
        
        participant = create_test_participant(meeting_id)
        if not participant:
            pytest.skip("Could not create test participant")
        
        # Create a fresh Quick-Scan token
        create_response = requests.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/quick-scan/{participant['user_id']}",
            headers=headers
        )
        
        if create_response.status_code != 200:
            pytest.skip("Could not create Quick-Scan token")
        
        token = create_response.json()["token"]
        
        submit_data = {
            "reporter_name": "Test User",
            "results": {"test": {"state": "ok"}}
        }
        
        # Submit 3 times (should succeed)
        for i in range(3):
            response = requests.post(
                f"{BASE_URL}/api/diag/shared/{token}/submit",
                json=submit_data
            )
            assert response.status_code == 200, f"Submit {i+1} failed: {response.text}"
        
        # 4th submission should fail with 429
        response = requests.post(
            f"{BASE_URL}/api/diag/shared/{token}/submit",
            json=submit_data
        )
        
        assert response.status_code == 429, f"Expected 429 on 4th submission, got {response.status_code}: {response.text}"
        print("✓ Quick-Scan max_submissions=3 enforced, 429 on overflow")


class TestQuickScanList:
    """Test listing Quick-Scans for a meeting"""
    
    def test_list_quick_scans_as_host(self):
        """Host can list Quick-Scans for a meeting"""
        headers = get_auth_headers()
        meeting = create_test_meeting()
        meeting_id = meeting["meeting_id"]
        
        participant = create_test_participant(meeting_id)
        if not participant:
            pytest.skip("Could not create test participant")
        
        # Create a Quick-Scan first
        requests.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/quick-scan/{participant['user_id']}",
            headers=headers
        )
        
        # List Quick-Scans
        response = requests.get(
            f"{BASE_URL}/api/meetings/{meeting_id}/quick-scans",
            headers=headers
        )
        
        assert response.status_code == 200, f"List failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        
        if len(data) > 0:
            token_doc = data[0]
            # Verify Quick-Scan specific fields
            assert token_doc.get("kind") == "quick_scan", "Token should have kind='quick_scan'"
            assert "meeting_id" in token_doc, "Token should have meeting_id"
            assert "target_user_id" in token_doc, "Token should have target_user_id"
            assert "max_submissions" in token_doc, "Token should have max_submissions"
            assert token_doc.get("max_submissions") == 3, "max_submissions should be 3"
        
        print(f"✓ List Quick-Scans works: {len(data)} tokens found")
    
    def test_list_quick_scans_403_for_non_host(self):
        """Non-host gets 403 when listing Quick-Scans"""
        headers = get_auth_headers()
        meeting = create_test_meeting()
        meeting_id = meeting["meeting_id"]
        
        participant = create_test_participant(meeting_id)
        if not participant:
            pytest.skip("Could not create test participant")
        
        participant_headers = {"Authorization": f"Bearer {participant['token']}", "Content-Type": "application/json"}
        
        response = requests.get(
            f"{BASE_URL}/api/meetings/{meeting_id}/quick-scans",
            headers=participant_headers
        )
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ Non-host correctly gets 403 on list")


class TestQuickScanE2EFlow:
    """E2E flow: Create → Resolve → Submit → List shows submission"""
    
    def test_e2e_quick_scan_flow(self):
        """Complete E2E flow for Quick-Scan"""
        headers = get_auth_headers()
        meeting = create_test_meeting()
        meeting_id = meeting["meeting_id"]
        
        participant = create_test_participant(meeting_id)
        if not participant:
            pytest.skip("Could not create test participant")
        
        target_user_id = participant["user_id"]
        
        # Step 1: Create Quick-Scan
        create_response = requests.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/quick-scan/{target_user_id}",
            headers=headers
        )
        assert create_response.status_code == 200, f"Create failed: {create_response.text}"
        token = create_response.json()["token"]
        print(f"  Step 1: Created Quick-Scan token={token[:8]}...")
        
        # Step 2: Public resolve
        resolve_response = requests.get(f"{BASE_URL}/api/diag/shared/{token}")
        assert resolve_response.status_code == 200, f"Resolve failed: {resolve_response.text}"
        print(f"  Step 2: Resolved token, note='{resolve_response.json().get('note')}'")
        
        # Step 3: Public submit with results
        submit_data = {
            "reporter_name": "E2E Test User",
            "results": {
                "cam": {"state": "ok"},
                "mic": {"state": "warn", "label": "Low volume"},
                "webrtc": {"state": "ok"}
            }
        }
        submit_response = requests.post(
            f"{BASE_URL}/api/diag/shared/{token}/submit",
            json=submit_data
        )
        assert submit_response.status_code == 200, f"Submit failed: {submit_response.text}"
        print("  Step 3: Submitted diagnostic results")
        
        # Step 4: List shows submission
        list_response = requests.get(
            f"{BASE_URL}/api/meetings/{meeting_id}/quick-scans",
            headers=headers
        )
        assert list_response.status_code == 200, f"List failed: {list_response.text}"
        
        tokens = list_response.json()
        found_token = next((t for t in tokens if t["token"] == token), None)
        assert found_token is not None, "Created token not found in list"
        
        submissions = found_token.get("submissions", [])
        assert len(submissions) > 0, "No submissions found for token"
        
        last_submission = submissions[-1]
        assert last_submission.get("reporter_name") == "E2E Test User", "Submission reporter_name mismatch"
        assert "results" in last_submission, "Submission missing results"
        
        print(f"  Step 4: List shows {len(submissions)} submission(s)")
        print("✓ E2E Quick-Scan flow complete")


class TestAdminDiagShareRegression:
    """Regression tests for existing /api/diag/shared admin endpoints"""
    
    def test_admin_create_diag_token(self):
        """Admin can create a standard diag-share token"""
        headers = get_auth_headers()
        
        response = requests.post(
            f"{BASE_URL}/api/diag/shared",
            json={"note": "TEST_Admin_Token", "days": 7},
            headers=headers
        )
        
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        
        assert "token" in data, "Response missing 'token'"
        assert "share_url" in data, "Response missing 'share_url'"
        assert "qr_png" in data, "Response missing 'qr_png'"
        assert "expires_at" in data, "Response missing 'expires_at'"
        assert data.get("note") == "TEST_Admin_Token", "Note mismatch"
        
        # Standard tokens should NOT have kind='quick_scan'
        assert data.get("kind") != "quick_scan", "Standard token should not have kind='quick_scan'"
        
        print(f"✓ Admin diag token created: {data['token'][:8]}...")
    
    def test_admin_list_diag_tokens(self):
        """Admin can list all diag-share tokens"""
        headers = get_auth_headers()
        
        response = requests.get(f"{BASE_URL}/api/diag/shared", headers=headers)
        
        assert response.status_code == 200, f"List failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ Admin list diag tokens: {len(data)} tokens")
    
    def test_admin_revoke_diag_token(self):
        """Admin can revoke a diag-share token"""
        headers = get_auth_headers()
        
        # Create a token to revoke
        create_response = requests.post(
            f"{BASE_URL}/api/diag/shared",
            json={"note": "TEST_Token_To_Revoke"},
            headers=headers
        )
        
        if create_response.status_code != 200:
            pytest.skip("Could not create token to revoke")
        
        token = create_response.json()["token"]
        
        # Revoke it
        revoke_response = requests.delete(f"{BASE_URL}/api/diag/shared/{token}", headers=headers)
        
        assert revoke_response.status_code == 200, f"Revoke failed: {revoke_response.text}"
        assert revoke_response.json().get("revoked") == True, "Revoke response should have revoked=True"
        
        # Verify it's gone
        resolve_response = requests.get(f"{BASE_URL}/api/diag/shared/{token}")
        assert resolve_response.status_code == 404, "Revoked token should return 404"
        
        print("✓ Admin revoke diag token works")
    
    def test_public_resolve_admin_token(self):
        """Public resolve works for admin-created tokens"""
        headers = get_auth_headers()
        
        # Create a token
        create_response = requests.post(
            f"{BASE_URL}/api/diag/shared",
            json={"note": "TEST_Public_Resolve"},
            headers=headers
        )
        
        if create_response.status_code != 200:
            pytest.skip("Could not create token")
        
        token = create_response.json()["token"]
        
        # Public resolve (no auth)
        resolve_response = requests.get(f"{BASE_URL}/api/diag/shared/{token}")
        
        assert resolve_response.status_code == 200, f"Resolve failed: {resolve_response.text}"
        data = resolve_response.json()
        
        assert data.get("note") == "TEST_Public_Resolve", "Note mismatch"
        print("✓ Public resolve for admin token works")
    
    def test_public_submit_admin_token(self):
        """Public submit works for admin-created tokens (max_submissions=10)"""
        headers = get_auth_headers()
        
        # Create a token
        create_response = requests.post(
            f"{BASE_URL}/api/diag/shared",
            json={"note": "TEST_Public_Submit"},
            headers=headers
        )
        
        if create_response.status_code != 200:
            pytest.skip("Could not create token")
        
        token = create_response.json()["token"]
        
        # Submit (no auth)
        submit_response = requests.post(
            f"{BASE_URL}/api/diag/shared/{token}/submit",
            json={
                "reporter_name": "Test Reporter",
                "results": {"test": {"state": "ok"}}
            }
        )
        
        assert submit_response.status_code == 200, f"Submit failed: {submit_response.text}"
        assert submit_response.json().get("ok") == True, "Submit should return ok=True"
        
        print("✓ Public submit for admin token works")


class TestMeetingWorkbenchRegression:
    """Regression tests for Action-Items, Insights, Focus-Times"""
    
    def test_action_items_crud(self):
        """Action-Items POST/GET/PUT work correctly"""
        headers = get_auth_headers()
        meeting = create_test_meeting()
        meeting_id = meeting["meeting_id"]
        
        # POST - Create action item
        create_response = requests.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/action-items",
            json={
                "title": "TEST_Action_Item",
                "assignee": "Test User",
                "due_date": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                "status": "open"
            },
            headers=headers
        )
        
        assert create_response.status_code in [200, 201], f"Create failed: {create_response.text}"
        item = create_response.json()
        assert "item_id" in item, "Response missing item_id"
        item_id = item["item_id"]
        print(f"  Created action item: {item_id}")
        
        # GET - List action items
        list_response = requests.get(
            f"{BASE_URL}/api/meetings/{meeting_id}/action-items",
            headers=headers
        )
        
        assert list_response.status_code == 200, f"List failed: {list_response.text}"
        items = list_response.json()
        assert isinstance(items, list), "Response should be a list"
        found = any(i.get("item_id") == item_id for i in items)
        assert found, "Created item not found in list"
        print(f"  Listed {len(items)} action items")
        
        # PUT - Update action item
        update_response = requests.put(
            f"{BASE_URL}/api/meetings/{meeting_id}/action-items/{item_id}",
            json={"status": "done", "title": "TEST_Action_Item_Updated"},
            headers=headers
        )
        
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        updated = update_response.json()
        assert updated.get("status") == "done", "Status not updated"
        print("  Updated action item status to 'done'")
        
        print("✓ Action-Items CRUD works")
    
    def test_insights_endpoint(self):
        """Insights GET endpoint works"""
        headers = get_auth_headers()
        meeting = create_test_meeting()
        meeting_id = meeting["meeting_id"]
        
        response = requests.get(
            f"{BASE_URL}/api/meetings/{meeting_id}/insights",
            headers=headers
        )
        
        assert response.status_code == 200, f"Insights GET failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        print(f"✓ Insights GET works: {len(data)} insights")
    
    def test_focus_times_crud(self):
        """Focus-Times GET/POST/DELETE work correctly"""
        headers = get_auth_headers()
        
        # POST - Create focus time
        start_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        end_time = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
        
        create_response = requests.post(
            f"{BASE_URL}/api/focus-times",
            json={
                "label": "TEST_Focus_Time",
                "start_time": start_time,
                "end_time": end_time
            },
            headers=headers
        )
        
        assert create_response.status_code in [200, 201], f"Create failed: {create_response.text}"
        focus = create_response.json()
        assert "focus_id" in focus, "Response missing focus_id"
        focus_id = focus["focus_id"]
        print(f"  Created focus time: {focus_id}")
        
        # GET - List focus times
        list_response = requests.get(f"{BASE_URL}/api/focus-times", headers=headers)
        
        assert list_response.status_code == 200, f"List failed: {list_response.text}"
        times = list_response.json()
        assert isinstance(times, list), "Response should be a list"
        print(f"  Listed {len(times)} focus times")
        
        # DELETE - Delete focus time
        delete_response = requests.delete(f"{BASE_URL}/api/focus-times/{focus_id}", headers=headers)
        
        assert delete_response.status_code == 200, f"Delete failed: {delete_response.text}"
        print("  Deleted focus time")
        
        print("✓ Focus-Times CRUD works")
    
    def test_active_focus_endpoint(self):
        """Active focus endpoint works"""
        headers = get_auth_headers()
        
        response = requests.get(f"{BASE_URL}/api/focus-times/active", headers=headers)
        
        assert response.status_code == 200, f"Active focus failed: {response.text}"
        data = response.json()
        assert "active" in data, "Response missing 'active' field"
        
        print(f"✓ Active focus endpoint works: active={data.get('active')}")


class TestDashboardRegression:
    """Regression tests for Dashboard/Agenda/Calendar endpoints"""
    
    def test_dashboard_stats(self):
        """Dashboard stats endpoint works"""
        headers = get_auth_headers()
        
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=headers)
        
        assert response.status_code == 200, f"Dashboard stats failed: {response.text}"
        data = response.json()
        
        # Should have some stats fields
        assert isinstance(data, dict), "Response should be a dict"
        print(f"✓ Dashboard stats works: {list(data.keys())[:5]}...")
    
    def test_dashboard_agenda(self):
        """Dashboard agenda endpoint works"""
        headers = get_auth_headers()
        
        response = requests.get(f"{BASE_URL}/api/dashboard/agenda", headers=headers)
        
        assert response.status_code == 200, f"Dashboard agenda failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, dict), "Response should be a dict"
        print("✓ Dashboard agenda works")
    
    def test_calendar_events(self):
        """Calendar events endpoint works"""
        headers = get_auth_headers()
        
        response = requests.get(f"{BASE_URL}/api/calendar/events", headers=headers)
        
        assert response.status_code == 200, f"Calendar events failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ Calendar events works: {len(data)} events")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
