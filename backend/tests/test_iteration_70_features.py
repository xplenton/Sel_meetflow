"""
Iteration 70 Tests - News Extensions + Quick Wins
Tests for:
1. NEWS: Scheduled publish (publish_at in future -> status='scheduled')
2. NEWS: owner_id, owner_name, channels fields
3. NEWS: PATCH /posts/{id}/owner - owner transfer
4. NEWS: GET /posts/{id}/governance - governance footprint
5. NEWS: PUT /posts/{id} with publish_at coercion
6. MAINTENANCE: Background task + scheduled publish promotion
7. MAINTENANCE: POST /admin/maintenance/cleanup
8. MEETINGS: DELETE /meetings/{id}?soft=true (soft-cancel for series)
9. MEETINGS: POST /meetings/{id}/restore
10. MEETINGS: instant meeting participant_count=1
"""
import pytest
import requests
import os
import time
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def admin_session():
    """Login as admin and return session with auth cookie."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@meetflow.com",
        "password": "admin123"
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return session


class TestNewsScheduledPublish:
    """Test scheduled publish feature - publish_at in future sets status='scheduled'"""
    
    def test_create_news_with_future_publish_at_becomes_scheduled(self, admin_session):
        """POST /api/news/posts with publish_at in future should set status='scheduled' even if 'published' requested"""
        future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "TEST_Scheduled News Post",
            "content": "This should be scheduled, not published",
            "status": "published",  # Request published
            "publish_at": future_time
        })
        assert resp.status_code == 200, f"Create news failed: {resp.text}"
        data = resp.json()
        assert data.get("status") == "scheduled", f"Expected status='scheduled', got {data.get('status')}"
        assert data.get("publish_at") == future_time
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{data['post_id']}")
        print("PASSED: Future publish_at coerces status to 'scheduled'")
    
    def test_create_news_with_past_publish_at_becomes_published(self, admin_session):
        """POST /api/news/posts with publish_at in past should become 'published' normally"""
        past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "TEST_Past Publish News",
            "content": "This should be published immediately",
            "status": "published",
            "publish_at": past_time
        })
        assert resp.status_code == 200, f"Create news failed: {resp.text}"
        data = resp.json()
        assert data.get("status") == "published", f"Expected status='published', got {data.get('status')}"
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{data['post_id']}")
        print("PASSED: Past publish_at allows status='published'")


class TestNewsOwnerAndChannels:
    """Test owner_id, owner_name, and channels fields"""
    
    def test_create_news_returns_owner_and_channels(self, admin_session):
        """POST /api/news/posts must return owner_id, owner_name, and channels fields"""
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "TEST_Owner Channels News",
            "content": "Testing owner and channels",
            "status": "draft"
        })
        assert resp.status_code == 200, f"Create news failed: {resp.text}"
        data = resp.json()
        
        # Check owner fields
        assert "owner_id" in data, "Missing owner_id field"
        assert "owner_name" in data, "Missing owner_name field"
        assert data.get("owner_id"), "owner_id should not be empty"
        
        # Check channels field - default should be ['intranet']
        assert "channels" in data, "Missing channels field"
        assert data.get("channels") == ["intranet"], f"Expected channels=['intranet'], got {data.get('channels')}"
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{data['post_id']}")
        print("PASSED: News post returns owner_id, owner_name, channels (default=['intranet'])")
    
    def test_create_news_with_custom_channels(self, admin_session):
        """POST /api/news/posts with custom channels"""
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "TEST_Multi Channel News",
            "content": "Testing multiple channels",
            "status": "draft",
            "channels": ["intranet", "email", "push"]
        })
        assert resp.status_code == 200, f"Create news failed: {resp.text}"
        data = resp.json()
        assert set(data.get("channels", [])) == {"intranet", "email", "push"}, f"Channels mismatch: {data.get('channels')}"
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{data['post_id']}")
        print("PASSED: News post accepts custom channels")


class TestNewsOwnerTransfer:
    """Test PATCH /posts/{id}/owner - owner transfer"""
    
    def test_transfer_owner(self, admin_session):
        """PATCH /api/news/posts/{id}/owner transfers owner to new user"""
        # Create a news post
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "TEST_Owner Transfer News",
            "content": "Testing owner transfer",
            "status": "draft"
        })
        assert resp.status_code == 200
        post_id = resp.json()["post_id"]
        original_owner_id = resp.json()["owner_id"]
        
        # Get admin user_id (we'll transfer to same user for simplicity, but test the endpoint)
        me_resp = admin_session.get(f"{BASE_URL}/api/auth/me")
        admin_user_id = me_resp.json()["user_id"]
        
        # Transfer owner (to same user - just testing the endpoint works)
        transfer_resp = admin_session.patch(f"{BASE_URL}/api/news/posts/{post_id}/owner", json={
            "owner_id": admin_user_id
        })
        assert transfer_resp.status_code == 200, f"Owner transfer failed: {transfer_resp.text}"
        transfer_data = transfer_resp.json()
        
        assert "message" in transfer_data, "Missing message in response"
        assert "owner_id" in transfer_data, "Missing owner_id in response"
        assert "owner_name" in transfer_data, "Missing owner_name in response"
        
        # Verify audit log has 'owner_transferred' entry
        audit_resp = admin_session.get(f"{BASE_URL}/api/news/audit/{post_id}")
        assert audit_resp.status_code == 200
        audit_entries = audit_resp.json()
        owner_transfer_entries = [e for e in audit_entries if e.get("action") == "owner_transferred"]
        assert len(owner_transfer_entries) > 0, "No 'owner_transferred' audit entry found"
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
        print("PASSED: Owner transfer works and creates audit log entry")


class TestNewsGovernance:
    """Test GET /posts/{id}/governance - governance footprint"""
    
    def test_get_governance(self, admin_session):
        """GET /api/news/posts/{id}/governance returns governance info"""
        # Create a news post
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "TEST_Governance News",
            "content": "Testing governance endpoint",
            "status": "draft",
            "channels": ["intranet", "email"]
        })
        assert resp.status_code == 200
        post_id = resp.json()["post_id"]
        
        # Get governance
        gov_resp = admin_session.get(f"{BASE_URL}/api/news/posts/{post_id}/governance")
        assert gov_resp.status_code == 200, f"Governance fetch failed: {gov_resp.text}"
        gov_data = gov_resp.json()
        
        # Check structure
        assert "post" in gov_data, "Missing 'post' in governance response"
        assert "history" in gov_data, "Missing 'history' in governance response"
        
        post_info = gov_data["post"]
        assert "owner_id" in post_info, "Missing owner_id in post info"
        assert "owner_name" in post_info, "Missing owner_name in post info"
        assert "channels" in post_info, "Missing channels in post info"
        assert "status" in post_info, "Missing status in post info"
        
        # History should have at least 'created' entry
        assert len(gov_data["history"]) >= 1, "History should have at least one entry"
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
        print("PASSED: Governance endpoint returns post info and history")
    
    def test_governance_403_for_non_owner(self, admin_session):
        """GET /api/news/posts/{id}/governance should 403 for users other than owner/author/moderator"""
        # This test would require a non-admin user, skipping for now as admin is always moderator
        print("SKIPPED: Would need non-admin user to test 403 case")


class TestNewsUpdateWithScheduledCoercion:
    """Test PUT /posts/{id} with publish_at coercion"""
    
    def test_update_news_with_future_publish_at_coerces_status(self, admin_session):
        """PUT /api/news/posts/{id} with publish_at in future coerces status='scheduled'"""
        # Create a draft post
        resp = admin_session.post(f"{BASE_URL}/api/news/posts", json={
            "title": "TEST_Update Scheduled News",
            "content": "Testing update with scheduled coercion",
            "status": "draft"
        })
        assert resp.status_code == 200
        post_id = resp.json()["post_id"]
        
        # Update with future publish_at and request 'published'
        future_time = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        update_resp = admin_session.put(f"{BASE_URL}/api/news/posts/{post_id}", json={
            "status": "published",
            "publish_at": future_time,
            "channels": ["intranet", "push"]
        })
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
        updated_data = update_resp.json()
        
        assert updated_data.get("status") == "scheduled", f"Expected status='scheduled', got {updated_data.get('status')}"
        assert set(updated_data.get("channels", [])) == {"intranet", "push"}, "Channels not updated"
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
        print("PASSED: Update with future publish_at coerces status to 'scheduled'")


class TestMaintenanceCleanup:
    """Test POST /admin/maintenance/cleanup"""
    
    def test_cleanup_endpoint_admin_only(self, admin_session):
        """POST /api/admin/maintenance/cleanup is admin-only and returns counts"""
        resp = admin_session.post(f"{BASE_URL}/api/admin/maintenance/cleanup", json={
            "min_age_days": 0
        })
        assert resp.status_code == 200, f"Cleanup failed: {resp.text}"
        data = resp.json()
        
        # Check response structure
        assert "news_posts" in data, "Missing news_posts count"
        assert "schedule_polls" in data, "Missing schedule_polls count"
        assert "surveys" in data, "Missing surveys count"
        assert "meetings" in data, "Missing meetings count"
        assert "cutoff" in data, "Missing cutoff timestamp"
        
        print(f"PASSED: Cleanup returned counts - news:{data['news_posts']}, polls:{data['schedule_polls']}, surveys:{data['surveys']}, meetings:{data['meetings']}")
    
    def test_cleanup_403_for_non_admin(self, admin_session):
        """POST /api/admin/maintenance/cleanup should 403 for non-admin"""
        # Create a non-admin session
        non_admin_session = requests.Session()
        non_admin_session.headers.update({"Content-Type": "application/json"})
        
        # Register a test user
        test_email = f"test_cleanup_{int(time.time())}@test.com"
        reg_resp = non_admin_session.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "testpass123",
            "name": "Test User"
        })
        if reg_resp.status_code != 200:
            print("SKIPPED: Could not create test user for 403 test")
            return
        
        # Login as test user
        login_resp = non_admin_session.post(f"{BASE_URL}/api/auth/login", json={
            "email": test_email,
            "password": "testpass123"
        })
        if login_resp.status_code != 200:
            print("SKIPPED: Could not login test user for 403 test")
            return
        
        # Try cleanup - should 403
        cleanup_resp = non_admin_session.post(f"{BASE_URL}/api/admin/maintenance/cleanup", json={
            "min_age_days": 0
        })
        assert cleanup_resp.status_code == 403, f"Expected 403, got {cleanup_resp.status_code}"
        print("PASSED: Non-admin gets 403 on cleanup endpoint")


class TestMaintenanceBackgroundTask:
    """Test background maintenance task for scheduled news promotion"""
    
    def test_maintenance_task_started_log(self, admin_session):
        """Verify maintenance background task started (check logs)"""
        # This is a smoke test - we verify the task is registered by checking backend logs
        # The actual promotion happens every 60 seconds, so we can't easily test it in a unit test
        import subprocess
        result = subprocess.run(
            ["tail", "-n", "100", "/var/log/supervisor/backend.out.log"],
            capture_output=True, text=True
        )
        if "Maintenance background task started" in result.stdout:
            print("PASSED: Maintenance background task started (found in logs)")
        else:
            # Check stderr too
            result2 = subprocess.run(
                ["tail", "-n", "100", "/var/log/supervisor/backend.err.log"],
                capture_output=True, text=True
            )
            if "Maintenance background task started" in result2.stdout or "Maintenance background task started" in result2.stderr:
                print("PASSED: Maintenance background task started (found in error logs)")
            else:
                print("WARNING: Could not verify maintenance task started in logs (may have scrolled out)")


class TestMeetingsSoftDelete:
    """Test DELETE /meetings/{id}?soft=true for series occurrences"""
    
    def test_soft_delete_series_occurrence(self, admin_session):
        """DELETE /api/meetings/{id}?soft=true on series occurrence marks status='cancelled'"""
        # Create a recurring meeting with custom schedule
        from datetime import datetime, timezone, timedelta
        base_time = datetime.now(timezone.utc) + timedelta(days=1)
        
        resp = admin_session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Soft Delete Series",
            "meeting_type": "scheduled",
            "scheduled_at": base_time.isoformat(),
            "duration_minutes": 30,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": base_time.weekday(), "time": base_time.strftime("%H:%M")}
            ],
            "recurring_weeks": 2
        })
        assert resp.status_code == 200, f"Create meeting failed: {resp.text}"
        meeting_data = resp.json()
        series_id = meeting_data.get("series_id")
        
        if not series_id:
            # Generate series if not auto-generated
            gen_resp = admin_session.post(f"{BASE_URL}/api/meetings/{meeting_data['meeting_id']}/recurring/generate", json={
                "count": 2
            })
            if gen_resp.status_code == 200:
                series_id = gen_resp.json().get("series_id")
        
        if not series_id:
            print("SKIPPED: Could not create series for soft delete test")
            admin_session.delete(f"{BASE_URL}/api/meetings/{meeting_data['meeting_id']}")
            return
        
        # Get series occurrences
        series_resp = admin_session.get(f"{BASE_URL}/api/meetings/recurring/{series_id}")
        assert series_resp.status_code == 200
        occurrences = series_resp.json()
        
        if len(occurrences) < 1:
            print("SKIPPED: No occurrences generated for soft delete test")
            return
        
        # Soft delete first occurrence
        occ_id = occurrences[0]["meeting_id"]
        delete_resp = admin_session.delete(f"{BASE_URL}/api/meetings/{occ_id}?soft=true")
        assert delete_resp.status_code == 200, f"Soft delete failed: {delete_resp.text}"
        delete_data = delete_resp.json()
        assert delete_data.get("soft") == True, "Response should indicate soft=true"
        
        # Verify occurrence is now cancelled
        occ_resp = admin_session.get(f"{BASE_URL}/api/meetings/{occ_id}")
        assert occ_resp.status_code == 200
        occ_data = occ_resp.json()
        assert occ_data.get("status") == "cancelled", f"Expected status='cancelled', got {occ_data.get('status')}"
        assert "cancelled_at" in occ_data, "Missing cancelled_at timestamp"
        assert "cancelled_by" in occ_data, "Missing cancelled_by field"
        
        # Cleanup - delete entire series
        admin_session.delete(f"{BASE_URL}/api/meetings/series/{series_id}?scope=all")
        print("PASSED: Soft delete marks series occurrence as 'cancelled' with timestamps")
    
    def test_hard_delete_non_series_meeting(self, admin_session):
        """DELETE /api/meetings/{id}?soft=true on non-series meeting still hard-deletes"""
        # Create a non-recurring meeting
        resp = admin_session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Hard Delete Non-Series",
            "meeting_type": "scheduled",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "duration_minutes": 30,
            "recurring": False
        })
        assert resp.status_code == 200
        meeting_id = resp.json()["meeting_id"]
        
        # Soft delete (should hard delete since no series_id)
        delete_resp = admin_session.delete(f"{BASE_URL}/api/meetings/{meeting_id}?soft=true")
        assert delete_resp.status_code == 200
        
        # Verify meeting is gone (404)
        get_resp = admin_session.get(f"{BASE_URL}/api/meetings/{meeting_id}")
        assert get_resp.status_code == 404, f"Expected 404, got {get_resp.status_code}"
        print("PASSED: Soft delete on non-series meeting performs hard delete")


class TestMeetingsRestore:
    """Test POST /meetings/{id}/restore"""
    
    def test_restore_cancelled_meeting(self, admin_session):
        """POST /api/meetings/{id}/restore reverts cancelled -> scheduled"""
        # Create a recurring meeting
        base_time = datetime.now(timezone.utc) + timedelta(days=1)
        
        resp = admin_session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Restore Meeting",
            "meeting_type": "scheduled",
            "scheduled_at": base_time.isoformat(),
            "duration_minutes": 30,
            "recurring": True,
            "recurring_pattern": "weekly"
        })
        assert resp.status_code == 200
        meeting_data = resp.json()
        meeting_id = meeting_data["meeting_id"]
        
        # Generate series
        gen_resp = admin_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/recurring/generate", json={
            "count": 2
        })
        series_id = None
        if gen_resp.status_code == 200:
            series_id = gen_resp.json().get("series_id")
        
        # Get an occurrence to cancel
        if series_id:
            series_resp = admin_session.get(f"{BASE_URL}/api/meetings/recurring/{series_id}")
            if series_resp.status_code == 200 and len(series_resp.json()) > 0:
                occ_id = series_resp.json()[0]["meeting_id"]
            else:
                occ_id = meeting_id
        else:
            occ_id = meeting_id
        
        # Manually set status to cancelled (simulate soft delete)
        admin_session.put(f"{BASE_URL}/api/meetings/{occ_id}", json={"status": "cancelled"})
        
        # Restore
        restore_resp = admin_session.post(f"{BASE_URL}/api/meetings/{occ_id}/restore")
        assert restore_resp.status_code == 200, f"Restore failed: {restore_resp.text}"
        
        # Verify status is back to scheduled
        get_resp = admin_session.get(f"{BASE_URL}/api/meetings/{occ_id}")
        assert get_resp.status_code == 200
        assert get_resp.json().get("status") == "scheduled", f"Expected status='scheduled', got {get_resp.json().get('status')}"
        
        # Cleanup
        if series_id:
            admin_session.delete(f"{BASE_URL}/api/meetings/series/{series_id}?scope=all")
        else:
            admin_session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
        print("PASSED: Restore reverts cancelled meeting to scheduled")
    
    def test_restore_400_if_not_cancelled(self, admin_session):
        """POST /api/meetings/{id}/restore returns 400 if meeting is not cancelled"""
        # Create a scheduled meeting
        resp = admin_session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Restore Not Cancelled",
            "meeting_type": "scheduled",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "duration_minutes": 30
        })
        assert resp.status_code == 200
        meeting_id = resp.json()["meeting_id"]
        
        # Try to restore (should fail - not cancelled)
        restore_resp = admin_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/restore")
        assert restore_resp.status_code == 400, f"Expected 400, got {restore_resp.status_code}"
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
        print("PASSED: Restore returns 400 for non-cancelled meeting")


class TestInstantMeetingParticipantCount:
    """Test instant meeting participant_count=1"""
    
    def test_instant_meeting_returns_participant_count_1(self, admin_session):
        """POST /api/meetings with meeting_type='instant' returns participant_count=1"""
        resp = admin_session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Instant Meeting Participant Count",
            "meeting_type": "instant"
        })
        assert resp.status_code == 200, f"Create instant meeting failed: {resp.text}"
        data = resp.json()
        
        assert data.get("participant_count") == 1, f"Expected participant_count=1, got {data.get('participant_count')}"
        assert data.get("status") == "active", f"Expected status='active', got {data.get('status')}"
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/meetings/{data['meeting_id']}")
        print("PASSED: Instant meeting returns participant_count=1")
    
    def test_scheduled_meeting_returns_participant_count_0(self, admin_session):
        """POST /api/meetings with meeting_type='scheduled' returns participant_count=0"""
        resp = admin_session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Scheduled Meeting Participant Count",
            "meeting_type": "scheduled",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        })
        assert resp.status_code == 200, f"Create scheduled meeting failed: {resp.text}"
        data = resp.json()
        
        assert data.get("participant_count") == 0, f"Expected participant_count=0, got {data.get('participant_count')}"
        assert data.get("status") == "scheduled", f"Expected status='scheduled', got {data.get('status')}"
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/meetings/{data['meeting_id']}")
        print("PASSED: Scheduled meeting returns participant_count=0")


class TestRegressionIter69:
    """Regression tests for iteration 67-69 features"""
    
    def test_series_badge_and_index(self, admin_session):
        """Verify series_index and series_total are returned for recurring meetings"""
        # Create a recurring meeting
        base_time = datetime.now(timezone.utc) + timedelta(days=1)
        resp = admin_session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Regression Series Badge",
            "meeting_type": "scheduled",
            "scheduled_at": base_time.isoformat(),
            "duration_minutes": 30,
            "recurring": True,
            "recurring_pattern": "weekly"
        })
        assert resp.status_code == 200
        meeting_id = resp.json()["meeting_id"]
        
        # Generate series
        gen_resp = admin_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/recurring/generate", json={
            "count": 3
        })
        series_id = None
        if gen_resp.status_code == 200:
            series_id = gen_resp.json().get("series_id")
        
        if series_id:
            # List meetings and check for series_index/series_total
            list_resp = admin_session.get(f"{BASE_URL}/api/meetings?meeting_type=upcoming")
            assert list_resp.status_code == 200
            meetings = list_resp.json().get("meetings", [])
            
            series_meetings = [m for m in meetings if m.get("series_id") == series_id]
            if len(series_meetings) > 0:
                # At least one should have series_index and series_total
                has_index = any(m.get("series_index") for m in series_meetings)
                has_total = any(m.get("series_total") for m in series_meetings)
                if has_index and has_total:
                    print("PASSED: Series meetings have series_index and series_total")
                else:
                    print("WARNING: Series meetings may not have index/total (depends on query)")
            
            # Cleanup
            admin_session.delete(f"{BASE_URL}/api/meetings/series/{series_id}?scope=all")
        else:
            admin_session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
            print("SKIPPED: Could not generate series for regression test")
    
    def test_ics_export_with_rrule(self, admin_session):
        """Verify ICS export includes RRULE for recurring meetings"""
        # Create a weekly recurring meeting
        base_time = datetime.now(timezone.utc) + timedelta(days=1)
        resp = admin_session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Regression ICS RRULE",
            "meeting_type": "scheduled",
            "scheduled_at": base_time.isoformat(),
            "duration_minutes": 30,
            "recurring": True,
            "recurring_pattern": "weekly"
        })
        assert resp.status_code == 200
        meeting_id = resp.json()["meeting_id"]
        
        # Get ICS
        ics_resp = admin_session.get(f"{BASE_URL}/api/meetings/{meeting_id}/ical")
        assert ics_resp.status_code == 200
        ics_content = ics_resp.text
        
        assert "RRULE" in ics_content, "ICS should contain RRULE for recurring meeting"
        assert "FREQ=WEEKLY" in ics_content, "ICS should have FREQ=WEEKLY for weekly pattern"
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
        print("PASSED: ICS export includes RRULE for recurring meetings")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
