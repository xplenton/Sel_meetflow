"""
Iteration 286 — Catering-Inbox UX Fixes + Date-Validation Tests

Tests:
1. GET /api/catering-requests returns hydrated data:
   - items[i].item_name + item_unit filled
   - booking{title, start_at, end_at, resource_name}
   - requester{name, email}

2. GET /api/resource-bookings with catering_request_id returns:
   - catering_status (e.g., 'rejected')
   - catering_rejection_reason when applicable

3. Backward-compat: Bookings without catering_request_id have no catering_status field
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestCateringRequestsHydration:
    """Test that GET /api/catering-requests returns fully hydrated data"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin to get auth token"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
    
    def test_catering_requests_returns_item_names(self):
        """Verify items[i].item_name and item_unit are populated"""
        resp = self.session.get(f"{BASE_URL}/api/catering-requests")
        assert resp.status_code == 200, f"Failed to get catering requests: {resp.text}"
        
        data = resp.json()
        assert isinstance(data, list), "Expected list of catering requests"
        
        # Find a request with items
        requests_with_items = [cr for cr in data if cr.get("items") and len(cr.get("items", [])) > 0]
        
        if requests_with_items:
            cr = requests_with_items[0]
            print(f"Testing catering request: {cr.get('request_id')}")
            
            for item in cr.get("items", []):
                # item_name should be populated (not just item_id)
                if item.get("item_id"):
                    print(f"  Item: {item.get('item_id')} -> name: {item.get('item_name')}, unit: {item.get('item_unit')}")
                    # item_name should exist if item_id exists
                    assert "item_name" in item or item.get("item_name") is not None, \
                        f"item_name missing for item_id {item.get('item_id')}"
        else:
            print("No catering requests with items found - skipping item_name check")
    
    def test_catering_requests_returns_booking_info(self):
        """Verify booking{title, start_at, end_at, resource_name} is populated"""
        resp = self.session.get(f"{BASE_URL}/api/catering-requests")
        assert resp.status_code == 200
        
        data = resp.json()
        
        # Find a request with booking_id
        requests_with_booking = [cr for cr in data if cr.get("booking_id")]
        
        if requests_with_booking:
            cr = requests_with_booking[0]
            print(f"Testing catering request with booking: {cr.get('request_id')}")
            
            # booking object should be present
            booking = cr.get("booking")
            assert booking is not None, f"booking object missing for request with booking_id {cr.get('booking_id')}"
            
            print(f"  Booking: title={booking.get('title')}, resource_name={booking.get('resource_name')}")
            print(f"  Time: {booking.get('start_at')} - {booking.get('end_at')}")
            
            # Verify booking fields
            assert "title" in booking, "booking.title missing"
            assert "start_at" in booking, "booking.start_at missing"
            assert "end_at" in booking, "booking.end_at missing"
            assert "resource_name" in booking, "booking.resource_name missing"
        else:
            print("No catering requests with booking_id found - skipping booking check")
    
    def test_catering_requests_returns_requester_info(self):
        """Verify requester{name, email} is populated"""
        resp = self.session.get(f"{BASE_URL}/api/catering-requests")
        assert resp.status_code == 200
        
        data = resp.json()
        
        # Find a request with user_id
        requests_with_user = [cr for cr in data if cr.get("user_id")]
        
        if requests_with_user:
            cr = requests_with_user[0]
            print(f"Testing catering request with user: {cr.get('request_id')}")
            
            # requester object should be present
            requester = cr.get("requester")
            assert requester is not None, f"requester object missing for request with user_id {cr.get('user_id')}"
            
            print(f"  Requester: name={requester.get('name')}, email={requester.get('email')}")
            
            # Verify requester fields
            assert "name" in requester or "email" in requester, "requester should have name or email"
        else:
            print("No catering requests with user_id found - skipping requester check")


class TestBookingsCateringStatus:
    """Test that GET /api/resource-bookings returns catering_status for bookings with catering"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin to get auth token"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
    
    def test_bookings_with_catering_have_status(self):
        """Verify bookings with catering_request_id have catering_status field"""
        resp = self.session.get(f"{BASE_URL}/api/resource-bookings")
        assert resp.status_code == 200, f"Failed to get bookings: {resp.text}"
        
        data = resp.json()
        assert isinstance(data, list), "Expected list of bookings"
        
        # Find bookings with catering_request_id
        bookings_with_catering = [b for b in data if b.get("catering_request_id")]
        
        if bookings_with_catering:
            for bk in bookings_with_catering[:5]:  # Check first 5
                print(f"Booking {bk.get('booking_id')}: catering_request_id={bk.get('catering_request_id')}, catering_status={bk.get('catering_status')}")
                
                # catering_status should be present
                assert "catering_status" in bk, \
                    f"catering_status missing for booking {bk.get('booking_id')} with catering_request_id"
        else:
            print("No bookings with catering_request_id found - skipping catering_status check")
    
    def test_rejected_bookings_have_rejection_reason(self):
        """Verify rejected catering bookings have catering_rejection_reason"""
        resp = self.session.get(f"{BASE_URL}/api/resource-bookings")
        assert resp.status_code == 200
        
        data = resp.json()
        
        # Find bookings with rejected catering
        rejected_bookings = [b for b in data if b.get("catering_status") == "rejected"]
        
        if rejected_bookings:
            for bk in rejected_bookings[:3]:  # Check first 3
                print(f"Rejected booking {bk.get('booking_id')}: reason={bk.get('catering_rejection_reason')}")
                
                # catering_rejection_reason should be present for rejected status
                # Note: It might be empty string if no reason was provided
                assert "catering_rejection_reason" in bk or bk.get("catering_rejection_reason") is not None, \
                    f"catering_rejection_reason missing for rejected booking {bk.get('booking_id')}"
        else:
            print("No rejected catering bookings found - skipping rejection_reason check")
    
    def test_bookings_without_catering_no_status(self):
        """Verify bookings without catering_request_id don't have catering_status"""
        resp = self.session.get(f"{BASE_URL}/api/resource-bookings")
        assert resp.status_code == 200
        
        data = resp.json()
        
        # Find bookings without catering_request_id
        bookings_without_catering = [b for b in data if not b.get("catering_request_id")]
        
        if bookings_without_catering:
            for bk in bookings_without_catering[:5]:  # Check first 5
                # catering_status should NOT be present (or be None)
                status = bk.get("catering_status")
                print(f"Booking {bk.get('booking_id')} (no catering): catering_status={status}")
                
                assert status is None, \
                    f"catering_status should be None for booking {bk.get('booking_id')} without catering"
        else:
            print("All bookings have catering - skipping backward-compat check")


class TestCateringRequestsFiltering:
    """Test catering requests filtering by status"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin to get auth token"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
    
    def test_filter_by_status_requested(self):
        """Test filtering catering requests by status=requested"""
        resp = self.session.get(f"{BASE_URL}/api/catering-requests?status=requested")
        assert resp.status_code == 200
        
        data = resp.json()
        for cr in data:
            assert cr.get("status") == "requested", f"Expected status=requested, got {cr.get('status')}"
        print(f"Found {len(data)} catering requests with status=requested")
    
    def test_filter_by_status_confirmed(self):
        """Test filtering catering requests by status=confirmed"""
        resp = self.session.get(f"{BASE_URL}/api/catering-requests?status=confirmed")
        assert resp.status_code == 200
        
        data = resp.json()
        for cr in data:
            assert cr.get("status") == "confirmed", f"Expected status=confirmed, got {cr.get('status')}"
        print(f"Found {len(data)} catering requests with status=confirmed")
    
    def test_filter_by_status_rejected(self):
        """Test filtering catering requests by status=rejected"""
        resp = self.session.get(f"{BASE_URL}/api/catering-requests?status=rejected")
        assert resp.status_code == 200
        
        data = resp.json()
        for cr in data:
            assert cr.get("status") == "rejected", f"Expected status=rejected, got {cr.get('status')}"
        print(f"Found {len(data)} catering requests with status=rejected")


class TestCateringItemsEndpoint:
    """Test catering items endpoint for item names"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin to get auth token"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
    
    def test_catering_items_have_name_and_unit(self):
        """Verify catering items have name and unit fields"""
        resp = self.session.get(f"{BASE_URL}/api/catering-items")
        assert resp.status_code == 200
        
        data = resp.json()
        assert isinstance(data, list), "Expected list of catering items"
        
        if data:
            for item in data[:5]:  # Check first 5
                print(f"Item: {item.get('item_id')} -> name={item.get('name')}, unit={item.get('unit')}")
                assert "name" in item, f"name missing for item {item.get('item_id')}"
                assert "unit" in item, f"unit missing for item {item.get('item_id')}"
        else:
            print("No catering items found")


class TestRejectionReasons:
    """Test catering rejection reasons endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin to get auth token"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
    
    def test_rejection_reasons_endpoint(self):
        """Verify rejection reasons endpoint returns list"""
        resp = self.session.get(f"{BASE_URL}/api/catering-requests/rejection-reasons")
        assert resp.status_code == 200
        
        data = resp.json()
        assert "reasons" in data, "Expected 'reasons' key in response"
        assert isinstance(data["reasons"], list), "Expected list of reasons"
        
        print(f"Available rejection reasons: {data['reasons']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
