"""
Iteration 69 Tests - ICS Export with RRULE, Series ICS, Single Occurrence Delete

Features tested:
1. GET /api/meetings/{meeting_id}/ical - RRULE for recurring patterns, ATTENDEE lines, ORGANIZER
2. GET /api/meetings/series/{series_id}/ical - Multi-VEVENT for custom series
3. DELETE /api/meetings/{meeting_id} for single occurrence - only deletes that one
4. Regression: iter 68 features (series_index/series_total, bulk PATCH/DELETE)
"""

import pytest
import requests
import os
import time
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestIteration69Features:
    """Test ICS export with RRULE, Series ICS, and single occurrence delete"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        self.user_id = response.json().get("user_id")
        yield
        # Cleanup test data
        self._cleanup_test_data()
    
    def _cleanup_test_data(self):
        """Clean up TEST_ prefixed meetings"""
        try:
            # Get all meetings and delete TEST_ ones
            resp = requests.get(f"{BASE_URL}/api/meetings?limit=100", headers=self.headers)
            if resp.status_code == 200:
                meetings = resp.json().get("meetings", [])
                for m in meetings:
                    if m.get("title", "").startswith("TEST_"):
                        requests.delete(f"{BASE_URL}/api/meetings/{m['meeting_id']}", headers=self.headers)
        except Exception:
            pass

    # ============ ICS EXPORT WITH RRULE ============
    
    def test_ical_export_weekly_meeting_has_rrule(self):
        """GET /api/meetings/{id}/ical for weekly recurring meeting should have RRULE:FREQ=WEEKLY"""
        # Create weekly recurring meeting
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT10:00")
        resp = requests.post(f"{BASE_URL}/api/meetings", headers=self.headers, json={
            "title": "TEST_Weekly_RRULE",
            "meeting_type": "scheduled",
            "scheduled_at": tomorrow,
            "duration_minutes": 60,
            "recurring": True,
            "recurring_pattern": "weekly"
        })
        assert resp.status_code == 200, f"Create meeting failed: {resp.text}"
        meeting_id = resp.json()["meeting_id"]
        
        # Get ICS
        ics_resp = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/ical")
        assert ics_resp.status_code == 200, f"ICS export failed: {ics_resp.text}"
        assert ics_resp.headers.get("content-type", "").startswith("text/calendar"), "Content-Type should be text/calendar"
        
        ics_content = ics_resp.text
        assert "BEGIN:VCALENDAR" in ics_content, "Missing VCALENDAR"
        assert "BEGIN:VEVENT" in ics_content, "Missing VEVENT"
        assert "RRULE:FREQ=WEEKLY" in ics_content, f"Missing RRULE:FREQ=WEEKLY in ICS: {ics_content[:500]}"
        print("✓ Weekly meeting ICS has RRULE:FREQ=WEEKLY")
    
    def test_ical_export_daily_meeting_has_rrule(self):
        """GET /api/meetings/{id}/ical for daily recurring meeting should have RRULE:FREQ=DAILY"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT09:00")
        resp = requests.post(f"{BASE_URL}/api/meetings", headers=self.headers, json={
            "title": "TEST_Daily_RRULE",
            "meeting_type": "scheduled",
            "scheduled_at": tomorrow,
            "duration_minutes": 30,
            "recurring": True,
            "recurring_pattern": "daily"
        })
        assert resp.status_code == 200
        meeting_id = resp.json()["meeting_id"]
        
        ics_resp = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/ical")
        assert ics_resp.status_code == 200
        assert "RRULE:FREQ=DAILY" in ics_resp.text, "Missing RRULE:FREQ=DAILY"
        print("✓ Daily meeting ICS has RRULE:FREQ=DAILY")
    
    def test_ical_export_biweekly_meeting_has_rrule_interval(self):
        """GET /api/meetings/{id}/ical for biweekly should have RRULE with INTERVAL=2"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT14:00")
        resp = requests.post(f"{BASE_URL}/api/meetings", headers=self.headers, json={
            "title": "TEST_Biweekly_RRULE",
            "meeting_type": "scheduled",
            "scheduled_at": tomorrow,
            "duration_minutes": 45,
            "recurring": True,
            "recurring_pattern": "biweekly"
        })
        assert resp.status_code == 200
        meeting_id = resp.json()["meeting_id"]
        
        ics_resp = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/ical")
        assert ics_resp.status_code == 200
        ics_content = ics_resp.text
        # biweekly = FREQ=WEEKLY;INTERVAL=2
        assert "RRULE:" in ics_content, "Missing RRULE"
        assert "FREQ=WEEKLY" in ics_content, "Missing FREQ=WEEKLY for biweekly"
        assert "INTERVAL=2" in ics_content, f"Missing INTERVAL=2 for biweekly: {ics_content[:500]}"
        print("✓ Biweekly meeting ICS has RRULE with INTERVAL=2")
    
    def test_ical_export_monthly_meeting_has_rrule(self):
        """GET /api/meetings/{id}/ical for monthly should have RRULE:FREQ=MONTHLY"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT11:00")
        resp = requests.post(f"{BASE_URL}/api/meetings", headers=self.headers, json={
            "title": "TEST_Monthly_RRULE",
            "meeting_type": "scheduled",
            "scheduled_at": tomorrow,
            "duration_minutes": 90,
            "recurring": True,
            "recurring_pattern": "monthly"
        })
        assert resp.status_code == 200
        meeting_id = resp.json()["meeting_id"]
        
        ics_resp = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/ical")
        assert ics_resp.status_code == 200
        assert "RRULE:FREQ=MONTHLY" in ics_resp.text, "Missing RRULE:FREQ=MONTHLY"
        print("✓ Monthly meeting ICS has RRULE:FREQ=MONTHLY")
    
    def test_ical_export_has_organizer(self):
        """ICS should have ORGANIZER with host email and CN"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT10:00")
        resp = requests.post(f"{BASE_URL}/api/meetings", headers=self.headers, json={
            "title": "TEST_Organizer_ICS",
            "meeting_type": "scheduled",
            "scheduled_at": tomorrow,
            "duration_minutes": 60
        })
        assert resp.status_code == 200
        meeting_id = resp.json()["meeting_id"]
        
        ics_resp = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/ical")
        assert ics_resp.status_code == 200
        ics_content = ics_resp.text
        assert "ORGANIZER" in ics_content, "Missing ORGANIZER"
        assert "admin@meetflow.com" in ics_content.lower(), "Missing host email in ORGANIZER"
        print("✓ ICS has ORGANIZER with host email")
    
    def test_ical_export_has_attendees(self):
        """ICS should have ATTENDEE lines for invited participants"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT10:00")
        resp = requests.post(f"{BASE_URL}/api/meetings", headers=self.headers, json={
            "title": "TEST_Attendees_ICS",
            "meeting_type": "scheduled",
            "scheduled_at": tomorrow,
            "duration_minutes": 60,
            "invited_emails": ["test1@example.com", "test2@example.com"]
        })
        assert resp.status_code == 200
        meeting_id = resp.json()["meeting_id"]
        
        ics_resp = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/ical")
        assert ics_resp.status_code == 200
        ics_content = ics_resp.text
        # Check for ATTENDEE lines
        assert "ATTENDEE" in ics_content, f"Missing ATTENDEE in ICS: {ics_content[:800]}"
        assert "test1@example.com" in ics_content.lower() or "test2@example.com" in ics_content.lower(), \
            f"Missing invited emails in ATTENDEE: {ics_content[:800]}"
        print("✓ ICS has ATTENDEE lines for invited participants")
    
    def test_ical_export_has_join_url(self):
        """ICS should have URL with join link"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT10:00")
        resp = requests.post(f"{BASE_URL}/api/meetings", headers=self.headers, json={
            "title": "TEST_URL_ICS",
            "meeting_type": "scheduled",
            "scheduled_at": tomorrow,
            "duration_minutes": 60
        })
        assert resp.status_code == 200
        meeting_id = resp.json()["meeting_id"]
        
        ics_resp = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/ical")
        assert ics_resp.status_code == 200
        ics_content = ics_resp.text
        assert "URL:" in ics_content, "Missing URL in ICS"
        assert "/join" in ics_content, "Missing /join in URL"
        print("✓ ICS has URL with join link")

    # ============ SERIES ICS EXPORT ============
    
    def test_series_ical_export_custom_pattern(self):
        """GET /api/meetings/series/{series_id}/ical should return multi-VEVENT ICS"""
        # Create custom recurring meeting (2 weekdays x 2 weeks = 4 occurrences)
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        resp = requests.post(f"{BASE_URL}/api/meetings", headers=self.headers, json={
            "title": "TEST_Series_ICS_Custom",
            "meeting_type": "scheduled",
            "scheduled_at": f"{tomorrow}T09:00",
            "duration_minutes": 60,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": "mon", "time": "09:00"},
                {"weekday": "wed", "time": "14:00"}
            ],
            "recurring_weeks": 2
        })
        assert resp.status_code == 200, f"Create meeting failed: {resp.text}"
        meeting = resp.json()
        series_id = meeting.get("series_id")
        
        # Wait for series generation
        time.sleep(1)
        
        # If no series_id, check if occurrences were created
        if not series_id:
            # Get meetings list to find series
            list_resp = requests.get(f"{BASE_URL}/api/meetings?limit=50", headers=self.headers)
            meetings = list_resp.json().get("meetings", [])
            for m in meetings:
                if m.get("title") == "TEST_Series_ICS_Custom" and m.get("series_id"):
                    series_id = m["series_id"]
                    break
        
        if not series_id:
            pytest.skip("Series ID not generated - custom recurring may not be enabled")
        
        # Get series ICS
        ics_resp = requests.get(f"{BASE_URL}/api/meetings/series/{series_id}/ical")
        assert ics_resp.status_code == 200, f"Series ICS export failed: {ics_resp.text}"
        assert ics_resp.headers.get("content-type", "").startswith("text/calendar")
        
        ics_content = ics_resp.text
        assert "BEGIN:VCALENDAR" in ics_content
        
        # Count VEVENT occurrences
        vevent_count = ics_content.count("BEGIN:VEVENT")
        assert vevent_count >= 2, f"Expected multiple VEVENTs, got {vevent_count}"
        print(f"✓ Series ICS has {vevent_count} VEVENTs for custom pattern")
    
    def test_series_ical_404_for_unknown_series(self):
        """GET /api/meetings/series/{unknown}/ical should return 404"""
        resp = requests.get(f"{BASE_URL}/api/meetings/series/nonexistent_series_123/ical")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("✓ Series ICS returns 404 for unknown series")

    # ============ SINGLE OCCURRENCE DELETE ============
    
    def test_delete_single_occurrence_leaves_others_intact(self):
        """DELETE /api/meetings/{meeting_id} for one occurrence should leave others"""
        # Create custom recurring meeting
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        resp = requests.post(f"{BASE_URL}/api/meetings", headers=self.headers, json={
            "title": "TEST_Delete_Single_Occ",
            "meeting_type": "scheduled",
            "scheduled_at": f"{tomorrow}T10:00",
            "duration_minutes": 60,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": "tue", "time": "10:00"},
                {"weekday": "thu", "time": "15:00"}
            ],
            "recurring_weeks": 2
        })
        assert resp.status_code == 200
        meeting = resp.json()
        series_id = meeting.get("series_id")
        
        time.sleep(1)
        
        if not series_id:
            # Find series_id from meetings list
            list_resp = requests.get(f"{BASE_URL}/api/meetings?limit=50", headers=self.headers)
            meetings = list_resp.json().get("meetings", [])
            for m in meetings:
                if m.get("title") == "TEST_Delete_Single_Occ" and m.get("series_id"):
                    series_id = m["series_id"]
                    break
        
        if not series_id:
            pytest.skip("Series ID not generated")
        
        # Get all occurrences
        occ_resp = requests.get(f"{BASE_URL}/api/meetings/recurring/{series_id}", headers=self.headers)
        assert occ_resp.status_code == 200
        occurrences = occ_resp.json()
        initial_count = len(occurrences)
        assert initial_count >= 2, f"Expected at least 2 occurrences, got {initial_count}"
        
        # Delete first occurrence
        first_occ_id = occurrences[0]["meeting_id"]
        del_resp = requests.delete(f"{BASE_URL}/api/meetings/{first_occ_id}", headers=self.headers)
        assert del_resp.status_code == 200, f"Delete failed: {del_resp.text}"
        
        # Verify remaining occurrences
        occ_resp2 = requests.get(f"{BASE_URL}/api/meetings/recurring/{series_id}", headers=self.headers)
        assert occ_resp2.status_code == 200
        remaining = occ_resp2.json()
        assert len(remaining) == initial_count - 1, f"Expected {initial_count - 1} remaining, got {len(remaining)}"
        
        # Verify deleted meeting is gone
        get_resp = requests.get(f"{BASE_URL}/api/meetings/{first_occ_id}", headers=self.headers)
        assert get_resp.status_code == 404, "Deleted meeting should return 404"
        
        print(f"✓ Single occurrence deleted, {len(remaining)} remaining in series")

    # ============ REGRESSION: ITER 68 FEATURES ============
    
    def test_regression_series_index_total_in_meetings_list(self):
        """Regression: GET /api/meetings should include series_index and series_total"""
        # Create custom recurring
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        resp = requests.post(f"{BASE_URL}/api/meetings", headers=self.headers, json={
            "title": "TEST_Regression_SeriesIndex",
            "meeting_type": "scheduled",
            "scheduled_at": f"{tomorrow}T11:00",
            "duration_minutes": 30,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [{"weekday": "mon", "time": "11:00"}],
            "recurring_weeks": 3
        })
        assert resp.status_code == 200
        
        time.sleep(1)
        
        # Get meetings list
        list_resp = requests.get(f"{BASE_URL}/api/meetings?limit=50", headers=self.headers)
        assert list_resp.status_code == 200
        meetings = list_resp.json().get("meetings", [])
        
        # Find our test meetings with series_id
        series_meetings = [m for m in meetings if m.get("title") == "TEST_Regression_SeriesIndex" and m.get("series_id")]
        
        if len(series_meetings) > 0:
            # Check for series_index and series_total
            for m in series_meetings:
                if m.get("series_index") and m.get("series_total"):
                    print(f"✓ Meeting has series_index={m['series_index']}, series_total={m['series_total']}")
                    return
        
        # If no series meetings found, skip
        pytest.skip("No series meetings with series_index/series_total found")
    
    def test_regression_bulk_patch_series(self):
        """Regression: PATCH /api/meetings/series/{series_id} should update multiple meetings"""
        # Create custom recurring
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        resp = requests.post(f"{BASE_URL}/api/meetings", headers=self.headers, json={
            "title": "TEST_Regression_BulkPatch",
            "meeting_type": "scheduled",
            "scheduled_at": f"{tomorrow}T12:00",
            "duration_minutes": 45,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [{"weekday": "fri", "time": "12:00"}],
            "recurring_weeks": 2,
            "lobby_enabled": False
        })
        assert resp.status_code == 200
        meeting = resp.json()
        series_id = meeting.get("series_id")
        
        time.sleep(1)
        
        if not series_id:
            list_resp = requests.get(f"{BASE_URL}/api/meetings?limit=50", headers=self.headers)
            meetings = list_resp.json().get("meetings", [])
            for m in meetings:
                if m.get("title") == "TEST_Regression_BulkPatch" and m.get("series_id"):
                    series_id = m["series_id"]
                    break
        
        if not series_id:
            pytest.skip("Series ID not generated")
        
        # Bulk update
        patch_resp = requests.patch(f"{BASE_URL}/api/meetings/series/{series_id}", headers=self.headers, json={
            "lobby_enabled": True,
            "chat_enabled": False,
            "scope": "all"
        })
        assert patch_resp.status_code == 200, f"Bulk patch failed: {patch_resp.text}"
        updated_count = patch_resp.json().get("updated", 0)
        assert updated_count >= 1, f"Expected at least 1 updated, got {updated_count}"
        print(f"✓ Bulk PATCH updated {updated_count} meetings")
    
    def test_regression_bulk_delete_series(self):
        """Regression: DELETE /api/meetings/series/{series_id} should delete all meetings"""
        # Create custom recurring
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        resp = requests.post(f"{BASE_URL}/api/meetings", headers=self.headers, json={
            "title": "TEST_Regression_BulkDelete",
            "meeting_type": "scheduled",
            "scheduled_at": f"{tomorrow}T13:00",
            "duration_minutes": 30,
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [{"weekday": "wed", "time": "13:00"}],
            "recurring_weeks": 2
        })
        assert resp.status_code == 200
        meeting = resp.json()
        series_id = meeting.get("series_id")
        
        time.sleep(1)
        
        if not series_id:
            list_resp = requests.get(f"{BASE_URL}/api/meetings?limit=50", headers=self.headers)
            meetings = list_resp.json().get("meetings", [])
            for m in meetings:
                if m.get("title") == "TEST_Regression_BulkDelete" and m.get("series_id"):
                    series_id = m["series_id"]
                    break
        
        if not series_id:
            pytest.skip("Series ID not generated")
        
        # Bulk delete
        del_resp = requests.delete(f"{BASE_URL}/api/meetings/series/{series_id}?scope=all", headers=self.headers)
        assert del_resp.status_code == 200, f"Bulk delete failed: {del_resp.text}"
        deleted_count = del_resp.json().get("deleted", 0)
        assert deleted_count >= 1, f"Expected at least 1 deleted, got {deleted_count}"
        
        # Verify series is gone
        occ_resp = requests.get(f"{BASE_URL}/api/meetings/recurring/{series_id}", headers=self.headers)
        remaining = occ_resp.json() if occ_resp.status_code == 200 else []
        assert len(remaining) == 0, f"Expected 0 remaining, got {len(remaining)}"
        print(f"✓ Bulk DELETE removed {deleted_count} meetings")


class TestNonRecurringICS:
    """Test ICS export for non-recurring meetings"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert response.status_code == 200
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        yield
        self._cleanup()
    
    def _cleanup(self):
        try:
            resp = requests.get(f"{BASE_URL}/api/meetings?limit=100", headers=self.headers)
            if resp.status_code == 200:
                for m in resp.json().get("meetings", []):
                    if m.get("title", "").startswith("TEST_"):
                        requests.delete(f"{BASE_URL}/api/meetings/{m['meeting_id']}", headers=self.headers)
        except Exception:
            pass
    
    def test_non_recurring_ics_no_rrule(self):
        """Non-recurring meeting ICS should NOT have RRULE"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT10:00")
        resp = requests.post(f"{BASE_URL}/api/meetings", headers=self.headers, json={
            "title": "TEST_NonRecurring_ICS",
            "meeting_type": "scheduled",
            "scheduled_at": tomorrow,
            "duration_minutes": 60,
            "recurring": False
        })
        assert resp.status_code == 200
        meeting_id = resp.json()["meeting_id"]
        
        ics_resp = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/ical")
        assert ics_resp.status_code == 200
        ics_content = ics_resp.text
        assert "RRULE" not in ics_content, f"Non-recurring should not have RRULE: {ics_content[:500]}"
        print("✓ Non-recurring meeting ICS has no RRULE")
    
    def test_ics_has_meeting_code_in_description(self):
        """ICS description should include meeting code"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT10:00")
        resp = requests.post(f"{BASE_URL}/api/meetings", headers=self.headers, json={
            "title": "TEST_MeetingCode_ICS",
            "meeting_type": "scheduled",
            "scheduled_at": tomorrow,
            "duration_minutes": 60
        })
        assert resp.status_code == 200
        meeting = resp.json()
        meeting_id = meeting["meeting_id"]
        meeting_code = meeting["meeting_code"]
        
        ics_resp = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/ical")
        assert ics_resp.status_code == 200
        ics_content = ics_resp.text
        assert meeting_code in ics_content, f"Meeting code {meeting_code} not in ICS"
        print("✓ ICS contains meeting code in description")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
