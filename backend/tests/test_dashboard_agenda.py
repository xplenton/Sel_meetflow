"""
Test Dashboard Agenda and Stats API endpoints
Tests the new /api/dashboard/agenda endpoint and verifies /api/dashboard/stats still works
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDashboardAgenda:
    """Tests for the new dashboard agenda endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login with admin credentials
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        data = login_response.json()
        self.token = data.get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
    
    def test_dashboard_stats_endpoint_works(self):
        """GET /api/dashboard/stats - should return stats data"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/stats")
        assert response.status_code == 200, f"Stats endpoint failed: {response.text}"
        
        data = response.json()
        # Verify expected fields
        assert "total_meetings" in data
        assert "active_meetings" in data
        assert "upcoming_meetings" in data
        assert "ended_meetings" in data
        assert "total_recordings" in data
        assert "conversations_count" in data
        assert "total_hours" in data
        assert "next_meetings" in data
        assert "daily_counts" in data
        
        # Verify types
        assert isinstance(data["total_meetings"], int)
        assert isinstance(data["active_meetings"], int)
        assert isinstance(data["total_recordings"], int)
        assert isinstance(data["conversations_count"], int)
        print(f"✓ Dashboard stats: {data['total_meetings']} meetings, {data['active_meetings']} active, {data['total_recordings']} recordings")
    
    def test_dashboard_agenda_endpoint_works(self):
        """GET /api/dashboard/agenda - should return agenda data"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/agenda")
        assert response.status_code == 200, f"Agenda endpoint failed: {response.text}"
        
        data = response.json()
        # Verify expected fields
        assert "today" in data, "Missing 'today' field"
        assert "week_days" in data, "Missing 'week_days' field"
        assert "recent" in data, "Missing 'recent' field"
        assert "meetings_today" in data, "Missing 'meetings_today' field"
        assert "meetings_week" in data, "Missing 'meetings_week' field"
        
        # Verify types
        assert isinstance(data["today"], list), "'today' should be a list"
        assert isinstance(data["week_days"], list), "'week_days' should be a list"
        assert isinstance(data["recent"], list), "'recent' should be a list"
        assert isinstance(data["meetings_today"], int), "'meetings_today' should be int"
        assert isinstance(data["meetings_week"], int), "'meetings_week' should be int"
        
        print(f"✓ Dashboard agenda: {data['meetings_today']} today, {data['meetings_week']} this week, {len(data['recent'])} recent activities")
    
    def test_agenda_today_meetings_structure(self):
        """Verify today's meetings have correct structure"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/agenda")
        assert response.status_code == 200
        
        data = response.json()
        for meeting in data["today"]:
            assert "meeting_id" in meeting, "Meeting missing meeting_id"
            assert "title" in meeting, "Meeting missing title"
            assert "status" in meeting, "Meeting missing status"
            # Optional fields that should be present if set
            if meeting.get("scheduled_at"):
                assert isinstance(meeting["scheduled_at"], str)
        
        print(f"✓ Today's meetings structure valid ({len(data['today'])} meetings)")
    
    def test_agenda_week_days_structure(self):
        """Verify week_days have correct grouped structure"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/agenda")
        assert response.status_code == 200
        
        data = response.json()
        for day in data["week_days"]:
            assert "date" in day, "Day missing 'date' field"
            assert "label" in day, "Day missing 'label' field"
            assert "meetings" in day, "Day missing 'meetings' field"
            assert isinstance(day["meetings"], list), "'meetings' should be a list"
            
            for meeting in day["meetings"]:
                assert "meeting_id" in meeting
                assert "title" in meeting
        
        print(f"✓ Week days structure valid ({len(data['week_days'])} days with meetings)")
    
    def test_agenda_recent_activity_structure(self):
        """Verify recent activity has correct structure"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/agenda")
        assert response.status_code == 200
        
        data = response.json()
        for activity in data["recent"]:
            assert "type" in activity, "Activity missing 'type'"
            assert "title" in activity, "Activity missing 'title'"
            assert "time" in activity, "Activity missing 'time'"
            assert "id" in activity, "Activity missing 'id'"
            
            # Type should be one of expected values
            assert activity["type"] in ["meeting_ended", "recording", "chat"], f"Unknown activity type: {activity['type']}"
        
        print(f"✓ Recent activity structure valid ({len(data['recent'])} activities)")
    
    def test_dashboard_stats_requires_auth(self):
        """GET /api/dashboard/stats without auth should fail"""
        no_auth_session = requests.Session()
        response = no_auth_session.get(f"{BASE_URL}/api/dashboard/stats")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✓ Dashboard stats requires authentication")
    
    def test_dashboard_agenda_requires_auth(self):
        """GET /api/dashboard/agenda without auth should fail"""
        no_auth_session = requests.Session()
        response = no_auth_session.get(f"{BASE_URL}/api/dashboard/agenda")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✓ Dashboard agenda requires authentication")


class TestMeetingsEndpoint:
    """Tests for the meetings list endpoint used by MeetingsPage"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200
        data = login_response.json()
        self.token = data.get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
    
    def test_meetings_list_upcoming(self):
        """GET /api/meetings?meeting_type=upcoming - should return upcoming meetings"""
        response = self.session.get(f"{BASE_URL}/api/meetings?meeting_type=upcoming&page=1&limit=10")
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "meetings" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data
        
        print(f"✓ Upcoming meetings: {data['total']} total, page {data['page']} of {data['pages']}")
    
    def test_meetings_list_past(self):
        """GET /api/meetings?meeting_type=past - should return past meetings"""
        response = self.session.get(f"{BASE_URL}/api/meetings?meeting_type=past&page=1&limit=10")
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "meetings" in data
        assert "total" in data
        
        print(f"✓ Past meetings: {data['total']} total")
    
    def test_meetings_search(self):
        """GET /api/meetings?search=test - should filter by search term"""
        response = self.session.get(f"{BASE_URL}/api/meetings?search=test&page=1&limit=10")
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "meetings" in data
        print(f"✓ Search meetings: {data['total']} results for 'test'")
    
    def test_meetings_pagination(self):
        """GET /api/meetings with pagination - should return paginated results"""
        response = self.session.get(f"{BASE_URL}/api/meetings?page=1&limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert data["page"] == 1
        assert data["limit"] == 5
        assert len(data["meetings"]) <= 5
        
        print(f"✓ Pagination works: {len(data['meetings'])} meetings on page 1 (limit 5)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
