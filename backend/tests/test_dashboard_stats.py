"""
Test Dashboard Stats API - Tests for the new /api/dashboard/stats endpoint
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDashboardStats:
    """Tests for the dashboard stats endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get auth cookie
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        print("✓ Logged in successfully")
    
    def test_dashboard_stats_returns_200(self):
        """Test that /api/dashboard/stats returns 200 OK"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/stats")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ Dashboard stats endpoint returns 200")
    
    def test_dashboard_stats_has_required_fields(self):
        """Test that response contains all required fields"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/stats")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = [
            "total_meetings",
            "active_meetings",
            "upcoming_meetings",
            "ended_meetings",
            "total_recordings",
            "conversations_count",
            "total_hours",
            "next_meetings",
            "daily_counts"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
            print(f"✓ Field '{field}' present in response")
    
    def test_dashboard_stats_field_types(self):
        """Test that fields have correct types"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/stats")
        assert response.status_code == 200
        
        data = response.json()
        
        # Integer fields
        assert isinstance(data["total_meetings"], int), "total_meetings should be int"
        assert isinstance(data["active_meetings"], int), "active_meetings should be int"
        assert isinstance(data["upcoming_meetings"], int), "upcoming_meetings should be int"
        assert isinstance(data["ended_meetings"], int), "ended_meetings should be int"
        assert isinstance(data["total_recordings"], int), "total_recordings should be int"
        assert isinstance(data["conversations_count"], int), "conversations_count should be int"
        
        # Float field
        assert isinstance(data["total_hours"], (int, float)), "total_hours should be numeric"
        
        # List fields
        assert isinstance(data["next_meetings"], list), "next_meetings should be list"
        assert isinstance(data["daily_counts"], list), "daily_counts should be list"
        
        print("✓ All field types are correct")
    
    def test_dashboard_stats_next_meetings_structure(self):
        """Test that next_meetings has correct structure"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/stats")
        assert response.status_code == 200
        
        data = response.json()
        next_meetings = data["next_meetings"]
        
        # Should have at most 5 meetings
        assert len(next_meetings) <= 5, "next_meetings should have at most 5 items"
        
        if len(next_meetings) > 0:
            meeting = next_meetings[0]
            expected_fields = ["meeting_id", "title", "status"]
            for field in expected_fields:
                assert field in meeting, f"next_meeting missing field: {field}"
            print(f"✓ next_meetings structure is correct (found {len(next_meetings)} meetings)")
        else:
            print("Note: No upcoming meetings found")
    
    def test_dashboard_stats_daily_counts_structure(self):
        """Test that daily_counts has correct structure (7 days)"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/stats")
        assert response.status_code == 200
        
        data = response.json()
        daily_counts = data["daily_counts"]
        
        # Should have exactly 7 days
        assert len(daily_counts) == 7, f"daily_counts should have 7 items, got {len(daily_counts)}"
        
        for day in daily_counts:
            assert "date" in day, "daily_count missing 'date' field"
            assert "count" in day, "daily_count missing 'count' field"
            assert isinstance(day["count"], int), "count should be int"
        
        print("✓ daily_counts structure is correct (7 days)")
    
    def test_dashboard_stats_requires_auth(self):
        """Test that endpoint requires authentication"""
        # Create new session without auth
        unauth_session = requests.Session()
        response = unauth_session.get(f"{BASE_URL}/api/dashboard/stats")
        
        # Should return 401 or 403
        assert response.status_code in [401, 403], f"Expected 401/403 for unauthenticated request, got {response.status_code}"
        print("✓ Endpoint correctly requires authentication")
    
    def test_dashboard_stats_values_are_non_negative(self):
        """Test that all numeric values are non-negative"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/stats")
        assert response.status_code == 200
        
        data = response.json()
        
        assert data["total_meetings"] >= 0, "total_meetings should be non-negative"
        assert data["active_meetings"] >= 0, "active_meetings should be non-negative"
        assert data["upcoming_meetings"] >= 0, "upcoming_meetings should be non-negative"
        assert data["ended_meetings"] >= 0, "ended_meetings should be non-negative"
        assert data["total_recordings"] >= 0, "total_recordings should be non-negative"
        assert data["conversations_count"] >= 0, "conversations_count should be non-negative"
        assert data["total_hours"] >= 0, "total_hours should be non-negative"
        
        print("✓ All numeric values are non-negative")


class TestMeetingsEndpoint:
    """Tests for meetings list endpoint with tabs"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get auth cookie
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200
    
    def test_meetings_list_upcoming(self):
        """Test meetings list with upcoming filter"""
        response = self.session.get(f"{BASE_URL}/api/meetings?meeting_type=upcoming")
        assert response.status_code == 200
        
        data = response.json()
        assert "meetings" in data
        assert "total" in data
        assert "pages" in data
        
        print(f"✓ Upcoming meetings: {data['total']} total")
    
    def test_meetings_list_past(self):
        """Test meetings list with past filter"""
        response = self.session.get(f"{BASE_URL}/api/meetings?meeting_type=past")
        assert response.status_code == 200
        
        data = response.json()
        assert "meetings" in data
        assert "total" in data
        
        print(f"✓ Past meetings: {data['total']} total")
    
    def test_meetings_list_pagination(self):
        """Test meetings list pagination"""
        response = self.session.get(f"{BASE_URL}/api/meetings?page=1&limit=10")
        assert response.status_code == 200
        
        data = response.json()
        assert "meetings" in data
        assert "page" in data
        assert "pages" in data
        assert data["page"] == 1
        assert len(data["meetings"]) <= 10
        
        print(f"✓ Pagination works: page {data['page']} of {data['pages']}")
    
    def test_meetings_list_search(self):
        """Test meetings list search"""
        response = self.session.get(f"{BASE_URL}/api/meetings?search=Test")
        assert response.status_code == 200
        
        data = response.json()
        assert "meetings" in data
        
        print(f"✓ Search works: found {data['total']} meetings matching 'Test'")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
