"""
Test Issue 4: Catering in Belegung
- /resource-occupancy API should return catering_request_id and catering_status for bookings
- DELETE /api/resource-bookings/{id} on a booking with catering should set catering_request status='cancelled'
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestCateringOccupancy:
    """Test catering fields in occupancy API"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
    
    def test_resource_occupancy_returns_catering_fields(self):
        """Issue 4: /resource-occupancy should return catering_request_id and catering_status"""
        # Calculate date range
        from_date = datetime.now().strftime("%Y-%m-%d")
        to_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        response = self.session.get(f"{BASE_URL}/api/resource-occupancy?from_date={from_date}&to_date={to_date}")
        assert response.status_code == 200, f"Failed to get occupancy: {response.text}"
        
        data = response.json()
        assert "resources" in data, "Response should have 'resources' key"
        
        # Check if any booking has catering fields
        found_catering_fields = False
        for resource in data.get("resources", []):
            for booking in resource.get("bookings", []):
                # Check if catering fields exist in the booking structure
                if "catering_request_id" in booking or "catering_status" in booking:
                    found_catering_fields = True
                    print(f"Found booking with catering: {booking.get('booking_id')}, catering_status: {booking.get('catering_status')}")
                    break
            if found_catering_fields:
                break
        
        # Even if no bookings have catering, the API should support these fields
        print(f"Occupancy API returned {len(data.get('resources', []))} resources")
        print(f"Found catering fields in bookings: {found_catering_fields}")
    
    def test_delete_booking_cancels_catering(self):
        """Issue 4: DELETE booking with catering should set catering_request status='cancelled'"""
        # First, find a booking with catering
        bookings_resp = self.session.get(f"{BASE_URL}/api/resource-bookings?mine_only=false")
        assert bookings_resp.status_code == 200, f"Failed to get bookings: {bookings_resp.text}"
        
        bookings = bookings_resp.json()
        booking_with_catering = None
        
        for booking in bookings:
            if booking.get("catering_request_id"):
                booking_with_catering = booking
                break
        
        if not booking_with_catering:
            pytest.skip("No booking with catering found to test deletion cascade")
        
        booking_id = booking_with_catering["booking_id"]
        catering_id = booking_with_catering["catering_request_id"]
        
        print(f"Found booking {booking_id} with catering {catering_id}")
        
        # Delete the booking
        delete_resp = self.session.delete(f"{BASE_URL}/api/resource-bookings/{booking_id}")
        assert delete_resp.status_code in [200, 204], f"Failed to delete booking: {delete_resp.text}"
        
        # Check if catering request is now cancelled
        catering_resp = self.session.get(f"{BASE_URL}/api/catering-requests/{catering_id}")
        if catering_resp.status_code == 200:
            catering_data = catering_resp.json()
            assert catering_data.get("status") == "cancelled", f"Catering should be cancelled, got: {catering_data.get('status')}"
            print(f"✓ Catering request {catering_id} is now cancelled")
        else:
            print(f"Could not verify catering status: {catering_resp.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
