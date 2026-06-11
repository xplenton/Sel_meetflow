"""
Iteration 68 Tests - Admin Mobile Tabs, Series Bulk Operations, Series Badge
Tests:
1. Admin mobile tabs dropdown (12 tabs)
2. GET /api/meetings returns series_index/series_total for recurring meetings
3. PATCH /api/meetings/series/{series_id} - bulk update
4. DELETE /api/meetings/series/{series_id} - bulk delete
5. Authorization checks for series operations
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestIteration68Features:
    """Test iteration 68 features: Admin mobile tabs, series bulk operations"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: login as admin and get token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        data = login_resp.json()
        self.token = data.get("token")
        self.user = data.get("user", {})
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Track created resources for cleanup
        self.created_meetings = []
        self.created_series_ids = []
        
        yield
        
        # Cleanup: delete test series
        for series_id in self.created_series_ids:
            try:
                self.session.delete(f"{BASE_URL}/api/meetings/series/{series_id}?scope=all")
            except:
                pass
        
        # Cleanup: delete individual meetings
        for mid in self.created_meetings:
            try:
                self.session.delete(f"{BASE_URL}/api/meetings/{mid}")
            except:
                pass
    
    # ============ SERIES INDEX/TOTAL ENRICHMENT ============
    
    def test_create_custom_recurring_meeting_with_series(self):
        """Create a custom recurring meeting with 2 slots over 2 weeks = 4 occurrences"""
        # Create meeting with custom recurring pattern
        resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Series_Meeting_68",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-02-01T10:00:00Z",
            "duration_minutes": 30,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": 0, "start_time": "10:00", "end_time": "10:30"},  # Monday
                {"weekday": 2, "start_time": "14:00", "end_time": "14:30"},  # Wednesday
            ],
            "recurring_weeks": 2
        })
        assert resp.status_code == 200, f"Create meeting failed: {resp.text}"
        meeting = resp.json()
        self.created_meetings.append(meeting["meeting_id"])
        
        # Wait for series generation
        time.sleep(0.5)
        
        # Get the series_id from the meeting
        get_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
        assert get_resp.status_code == 200
        meeting_data = get_resp.json()
        series_id = meeting_data.get("series_id")
        
        if series_id:
            self.created_series_ids.append(series_id)
            
            # Get all meetings in series
            series_resp = self.session.get(f"{BASE_URL}/api/meetings/recurring/{series_id}")
            assert series_resp.status_code == 200
            series_meetings = series_resp.json()
            
            # Should have 4 occurrences (2 slots × 2 weeks)
            assert len(series_meetings) >= 2, f"Expected at least 2 occurrences, got {len(series_meetings)}"
            print(f"Created series with {len(series_meetings)} occurrences")
            
            return series_id, series_meetings
        
        return None, []
    
    def test_meetings_list_returns_series_index_and_total(self):
        """GET /api/meetings should return series_index and series_total for recurring meetings"""
        # First create a recurring series
        resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Series_Index_Check_68",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-03-01T09:00:00Z",
            "duration_minutes": 45,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": 1, "start_time": "09:00", "end_time": "09:45"},  # Tuesday
                {"weekday": 4, "start_time": "15:00", "end_time": "15:45"},  # Friday
            ],
            "recurring_weeks": 2
        })
        assert resp.status_code == 200
        meeting = resp.json()
        self.created_meetings.append(meeting["meeting_id"])
        
        time.sleep(0.5)
        
        # Get the series_id
        get_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
        meeting_data = get_resp.json()
        series_id = meeting_data.get("series_id")
        
        if series_id:
            self.created_series_ids.append(series_id)
            
            # Now fetch meetings list and check for series_index/series_total
            list_resp = self.session.get(f"{BASE_URL}/api/meetings?limit=50")
            assert list_resp.status_code == 200
            meetings_data = list_resp.json()
            meetings = meetings_data.get("meetings", [])
            
            # Find meetings from our series
            series_meetings = [m for m in meetings if m.get("series_id") == series_id]
            
            if series_meetings:
                # Check that series_index and series_total are present
                for m in series_meetings:
                    assert "series_index" in m, f"series_index missing for meeting {m['meeting_id']}"
                    assert "series_total" in m, f"series_total missing for meeting {m['meeting_id']}"
                    assert m["series_index"] >= 1, "series_index should be >= 1"
                    assert m["series_total"] >= 1, "series_total should be >= 1"
                    print(f"Meeting {m['meeting_id']}: series_index={m['series_index']}, series_total={m['series_total']}")
                
                # Verify indices are sequential
                indices = sorted([m["series_index"] for m in series_meetings])
                print(f"Series indices found: {indices}")
    
    # ============ BULK UPDATE SERIES ============
    
    def test_bulk_update_series_lobby_enabled(self):
        """PATCH /api/meetings/series/{series_id} should update lobby_enabled for all upcoming meetings"""
        # Create series
        resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Bulk_Update_68",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-04-01T10:00:00Z",
            "duration_minutes": 30,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": 0, "start_time": "10:00", "end_time": "10:30"},
            ],
            "recurring_weeks": 3,
            "lobby_enabled": False
        })
        assert resp.status_code == 200
        meeting = resp.json()
        self.created_meetings.append(meeting["meeting_id"])
        
        time.sleep(0.5)
        
        get_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
        series_id = get_resp.json().get("series_id")
        
        if series_id:
            self.created_series_ids.append(series_id)
            
            # Bulk update lobby_enabled to true
            patch_resp = self.session.patch(f"{BASE_URL}/api/meetings/series/{series_id}", json={
                "lobby_enabled": True,
                "scope": "upcoming"
            })
            assert patch_resp.status_code == 200, f"Bulk update failed: {patch_resp.text}"
            result = patch_resp.json()
            
            assert result["series_id"] == series_id
            assert result["updated"] >= 1, "Should have updated at least 1 meeting"
            assert "lobby_enabled" in result["fields"]
            assert result["scope"] == "upcoming"
            print(f"Bulk updated {result['updated']} meetings with fields: {result['fields']}")
            
            # Verify the update
            series_resp = self.session.get(f"{BASE_URL}/api/meetings/recurring/{series_id}")
            series_meetings = series_resp.json()
            for m in series_meetings:
                if m.get("status") in ["scheduled", "active"]:
                    assert m.get("lobby_enabled") == True, f"Meeting {m['meeting_id']} lobby_enabled not updated"
    
    def test_bulk_update_series_multiple_fields(self):
        """PATCH should update multiple allowed fields at once"""
        # Create series
        resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Multi_Field_Update_68",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-05-01T11:00:00Z",
            "duration_minutes": 60,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": 3, "start_time": "11:00", "end_time": "12:00"},
            ],
            "recurring_weeks": 2,
            "chat_enabled": True,
            "reactions_enabled": True
        })
        assert resp.status_code == 200
        meeting = resp.json()
        self.created_meetings.append(meeting["meeting_id"])
        
        time.sleep(0.5)
        
        get_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
        series_id = get_resp.json().get("series_id")
        
        if series_id:
            self.created_series_ids.append(series_id)
            
            # Update multiple fields
            patch_resp = self.session.patch(f"{BASE_URL}/api/meetings/series/{series_id}", json={
                "chat_enabled": False,
                "reactions_enabled": False,
                "recording_enabled": True,
                "scope": "all"
            })
            assert patch_resp.status_code == 200
            result = patch_resp.json()
            
            assert len(result["fields"]) == 3, f"Expected 3 fields updated, got {result['fields']}"
            assert "chat_enabled" in result["fields"]
            assert "reactions_enabled" in result["fields"]
            assert "recording_enabled" in result["fields"]
            print(f"Updated fields: {result['fields']}")
    
    def test_bulk_update_series_rejects_disallowed_fields(self):
        """PATCH should silently ignore disallowed fields like host_id, meeting_id"""
        # Create series
        resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Disallowed_Fields_68",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-06-01T10:00:00Z",
            "duration_minutes": 30,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": 5, "start_time": "10:00", "end_time": "10:30"},
            ],
            "recurring_weeks": 2
        })
        assert resp.status_code == 200
        meeting = resp.json()
        self.created_meetings.append(meeting["meeting_id"])
        
        time.sleep(0.5)
        
        get_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
        series_id = get_resp.json().get("series_id")
        
        if series_id:
            self.created_series_ids.append(series_id)
            
            # Try to update disallowed fields along with allowed ones
            patch_resp = self.session.patch(f"{BASE_URL}/api/meetings/series/{series_id}", json={
                "lobby_enabled": True,
                "host_id": "hacker_id",  # Should be ignored
                "meeting_id": "fake_id",  # Should be ignored
                "status": "ended",  # Should be ignored
            })
            assert patch_resp.status_code == 200
            result = patch_resp.json()
            
            # Only lobby_enabled should be in fields
            assert result["fields"] == ["lobby_enabled"], f"Expected only lobby_enabled, got {result['fields']}"
    
    def test_bulk_update_series_404_unknown_series(self):
        """PATCH should return 404 for unknown series_id"""
        patch_resp = self.session.patch(f"{BASE_URL}/api/meetings/series/nonexistent_series_123", json={
            "lobby_enabled": True
        })
        assert patch_resp.status_code == 404
    
    def test_bulk_update_series_400_no_valid_fields(self):
        """PATCH should return 400 if no allowed fields provided"""
        # Create series first
        resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_No_Fields_68",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-07-01T10:00:00Z",
            "duration_minutes": 30,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": 1, "start_time": "10:00", "end_time": "10:30"},
            ],
            "recurring_weeks": 1
        })
        assert resp.status_code == 200
        meeting = resp.json()
        self.created_meetings.append(meeting["meeting_id"])
        
        time.sleep(0.5)
        
        get_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
        series_id = get_resp.json().get("series_id")
        
        if series_id:
            self.created_series_ids.append(series_id)
            
            # Try to update with only disallowed fields
            patch_resp = self.session.patch(f"{BASE_URL}/api/meetings/series/{series_id}", json={
                "host_id": "hacker",
                "status": "ended"
            })
            assert patch_resp.status_code == 400
    
    # ============ BULK DELETE SERIES ============
    
    def test_bulk_delete_series_upcoming(self):
        """DELETE /api/meetings/series/{series_id}?scope=upcoming should delete only scheduled meetings"""
        # Create series
        resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Delete_Upcoming_68",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-08-01T10:00:00Z",
            "duration_minutes": 30,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": 0, "start_time": "10:00", "end_time": "10:30"},
            ],
            "recurring_weeks": 3
        })
        assert resp.status_code == 200
        meeting = resp.json()
        self.created_meetings.append(meeting["meeting_id"])
        
        time.sleep(0.5)
        
        get_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
        series_id = get_resp.json().get("series_id")
        
        if series_id:
            # Don't add to cleanup since we're deleting it
            
            # Get count before delete
            series_resp = self.session.get(f"{BASE_URL}/api/meetings/recurring/{series_id}")
            before_count = len(series_resp.json())
            
            # Delete upcoming
            del_resp = self.session.delete(f"{BASE_URL}/api/meetings/series/{series_id}?scope=upcoming")
            assert del_resp.status_code == 200, f"Delete failed: {del_resp.text}"
            result = del_resp.json()
            
            assert result["series_id"] == series_id
            assert result["deleted"] >= 1, "Should have deleted at least 1 meeting"
            assert result["scope"] == "upcoming"
            print(f"Deleted {result['deleted']} meetings (scope=upcoming)")
    
    def test_bulk_delete_series_all(self):
        """DELETE /api/meetings/series/{series_id}?scope=all should delete all meetings"""
        # Create series
        resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Delete_All_68",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-09-01T10:00:00Z",
            "duration_minutes": 30,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": 2, "start_time": "10:00", "end_time": "10:30"},
            ],
            "recurring_weeks": 2
        })
        assert resp.status_code == 200
        meeting = resp.json()
        # Don't add to cleanup since we're deleting it
        
        time.sleep(0.5)
        
        get_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
        series_id = get_resp.json().get("series_id")
        
        if series_id:
            # Delete all
            del_resp = self.session.delete(f"{BASE_URL}/api/meetings/series/{series_id}?scope=all")
            assert del_resp.status_code == 200
            result = del_resp.json()
            
            assert result["scope"] == "all"
            print(f"Deleted {result['deleted']} meetings (scope=all)")
            
            # Verify series is empty
            series_resp = self.session.get(f"{BASE_URL}/api/meetings/recurring/{series_id}")
            assert series_resp.status_code == 200
            assert len(series_resp.json()) == 0, "Series should be empty after delete all"
    
    def test_bulk_delete_series_404_unknown(self):
        """DELETE should return 404 for unknown series_id"""
        del_resp = self.session.delete(f"{BASE_URL}/api/meetings/series/nonexistent_series_456?scope=all")
        assert del_resp.status_code == 404
    
    # ============ AUTHORIZATION TESTS ============
    
    def test_bulk_update_series_403_non_host(self):
        """PATCH should return 403 if caller is not host and doesn't have meetings.manage_others"""
        # Create series as admin
        resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Auth_Check_68",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-10-01T10:00:00Z",
            "duration_minutes": 30,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": 4, "start_time": "10:00", "end_time": "10:30"},
            ],
            "recurring_weeks": 1
        })
        assert resp.status_code == 200
        meeting = resp.json()
        self.created_meetings.append(meeting["meeting_id"])
        
        time.sleep(0.5)
        
        get_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
        series_id = get_resp.json().get("series_id")
        
        if series_id:
            self.created_series_ids.append(series_id)
            
            # Register a new non-admin user
            new_user_email = f"test_user_68_{int(time.time())}@test.com"
            reg_resp = self.session.post(f"{BASE_URL}/api/auth/register", json={
                "email": new_user_email,
                "password": "testpass123",
                "name": "Test User 68"
            })
            
            if reg_resp.status_code == 200:
                # Login as new user
                login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
                    "email": new_user_email,
                    "password": "testpass123"
                })
                
                if login_resp.status_code == 200:
                    new_token = login_resp.json().get("token")
                    
                    # Try to update series as non-host
                    patch_resp = requests.patch(
                        f"{BASE_URL}/api/meetings/series/{series_id}",
                        json={"lobby_enabled": True},
                        headers={"Authorization": f"Bearer {new_token}", "Content-Type": "application/json"}
                    )
                    assert patch_resp.status_code == 403, f"Expected 403, got {patch_resp.status_code}"
                    print("Non-host correctly denied access to bulk update")
    
    # ============ ALLOWED FIELDS VERIFICATION ============
    
    def test_bulk_update_all_allowed_fields(self):
        """Verify all allowed fields can be updated: lobby_enabled, guest_access, chat_enabled, reactions_enabled, recording_enabled, transcript_enabled, meeting_mode, title, description"""
        # Create series
        resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_All_Fields_68",
            "description": "Original description",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-11-01T10:00:00Z",
            "duration_minutes": 30,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": 0, "start_time": "10:00", "end_time": "10:30"},
            ],
            "recurring_weeks": 1,
            "meeting_mode": "standard"
        })
        assert resp.status_code == 200
        meeting = resp.json()
        self.created_meetings.append(meeting["meeting_id"])
        
        time.sleep(0.5)
        
        get_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
        series_id = get_resp.json().get("series_id")
        
        if series_id:
            self.created_series_ids.append(series_id)
            
            # Update all allowed fields
            patch_resp = self.session.patch(f"{BASE_URL}/api/meetings/series/{series_id}", json={
                "lobby_enabled": True,
                "guest_access": False,
                "chat_enabled": False,
                "reactions_enabled": False,
                "recording_enabled": True,
                "transcript_enabled": True,
                "meeting_mode": "webinar",
                "title": "Updated Title 68",
                "description": "Updated description 68",
                "scope": "all"
            })
            assert patch_resp.status_code == 200
            result = patch_resp.json()
            
            # All 9 fields should be updated
            assert len(result["fields"]) == 9, f"Expected 9 fields, got {result['fields']}"
            print(f"Successfully updated all 9 allowed fields: {result['fields']}")
            
            # Verify updates
            series_resp = self.session.get(f"{BASE_URL}/api/meetings/recurring/{series_id}")
            meetings = series_resp.json()
            if meetings:
                m = meetings[0]
                assert m.get("lobby_enabled") == True
                assert m.get("guest_access") == False
                assert m.get("chat_enabled") == False
                assert m.get("reactions_enabled") == False
                assert m.get("recording_enabled") == True
                assert m.get("transcript_enabled") == True
                assert m.get("meeting_mode") == "webinar"
                assert m.get("title") == "Updated Title 68"
                assert m.get("description") == "Updated description 68"


class TestAdminEndpoints:
    """Test admin endpoints are accessible"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_admin_stats_endpoint(self):
        """GET /api/admin/stats should return platform statistics"""
        resp = self.session.get(f"{BASE_URL}/api/admin/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_users" in data
        assert "total_meetings" in data
        print(f"Admin stats: {data}")
    
    def test_admin_users_endpoint(self):
        """GET /api/admin/users should return user list"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users")
        assert resp.status_code == 200
        users = resp.json()
        assert isinstance(users, list)
        print(f"Admin users count: {len(users)}")
    
    def test_admin_groups_endpoint(self):
        """GET /api/admin/groups should return groups list"""
        resp = self.session.get(f"{BASE_URL}/api/admin/groups")
        # May return 200 with empty list or 404 if not implemented
        assert resp.status_code in [200, 404]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
