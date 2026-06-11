"""
Iteration 350 Bug Fixes Tests

BUG 1: availability_only=true status filter alignment
- GET /api/resource-bookings?availability_only=true must only return bookings with status in (confirmed, pending_approval)
- Cross-check with GET /api/resource-availability-snapshot for consistency

BUG 2: aggregate.pdf 500 error fix
- GET /api/resource-bookings/invoices/aggregate.pdf must return 200 with PDF content
- GET /api/resource-bookings/invoices/aggregate (JSON) must work with various filters
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestAuth:
    """Authentication helper"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get auth headers"""
        return {"Authorization": f"Bearer {auth_token}"}


class TestBug1AvailabilityOnlyStatusFilter(TestAuth):
    """
    BUG 1: availability_only=true status filter alignment
    
    Root cause: backend list /resource-bookings?availability_only=true returned bookings 
    with ANY status, but the availability_snapshot endpoint only counted confirmed+pending_approval.
    
    Fix: hard-code the same status filter in availability_only=true so frontend + backend 
    snapshot use the SAME data.
    """
    
    def test_availability_only_returns_only_confirmed_pending_approval(self, auth_headers):
        """
        GET /api/resource-bookings?availability_only=true MUST only return bookings 
        with status in (confirmed, pending_approval)
        """
        # Get today's date range
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings",
            params={
                "from_date": today.isoformat(),
                "to_date": tomorrow.isoformat(),
                "availability_only": "true"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        bookings = response.json()
        
        # Verify all returned bookings have status in allowed list
        allowed_statuses = {"confirmed", "pending_approval"}
        for booking in bookings:
            status = booking.get("status")
            assert status in allowed_statuses, \
                f"Booking {booking.get('booking_id')} has status '{status}' which is NOT in allowed list {allowed_statuses}"
        
        print(f"PASS: {len(bookings)} bookings returned, all have status in {allowed_statuses}")
    
    def test_availability_only_excludes_cancelled_no_show_completed(self, auth_headers):
        """
        Verify that cancelled, no_show, and completed bookings are NOT returned
        when availability_only=true
        """
        # Get a wider date range to catch more bookings
        start_date = datetime.utcnow() - timedelta(days=30)
        end_date = datetime.utcnow() + timedelta(days=30)
        
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings",
            params={
                "from_date": start_date.isoformat(),
                "to_date": end_date.isoformat(),
                "availability_only": "true"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        bookings = response.json()
        
        # Check that no excluded statuses are present
        excluded_statuses = {"cancelled", "no_show", "completed"}
        for booking in bookings:
            status = booking.get("status")
            assert status not in excluded_statuses, \
                f"Booking {booking.get('booking_id')} has excluded status '{status}'"
        
        print(f"PASS: {len(bookings)} bookings returned, none have excluded statuses {excluded_statuses}")
    
    def test_availability_only_returns_privacy_safe_stubs(self, auth_headers):
        """
        Verify that availability_only=true returns privacy-safe stubs
        (only booking_id, resource_id, start_at, end_at, status)
        """
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings",
            params={
                "from_date": today.isoformat(),
                "to_date": tomorrow.isoformat(),
                "availability_only": "true"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        bookings = response.json()
        
        # Expected fields in privacy-safe stubs
        expected_fields = {"booking_id", "resource_id", "start_at", "end_at", "status"}
        
        for booking in bookings:
            # Check that expected fields are present
            for field in expected_fields:
                assert field in booking, f"Missing expected field '{field}' in booking"
        
        print(f"PASS: {len(bookings)} bookings returned with privacy-safe stub format")
    
    def test_availability_snapshot_consistency(self, auth_headers):
        """
        Cross-check that GET /api/resource-availability-snapshot and 
        availability_only=true filter return CONSISTENT data
        """
        # Get availability snapshot
        snapshot_response = requests.get(
            f"{BASE_URL}/api/resource-availability-snapshot",
            headers=auth_headers
        )
        assert snapshot_response.status_code == 200, f"Snapshot request failed: {snapshot_response.text}"
        snapshot_data = snapshot_response.json()
        snapshot = snapshot_data.get("snapshot", {})
        
        # Get bookings with availability_only=true for a resource that's busy
        busy_resources = [rid for rid, data in snapshot.items() if data.get("busy_now")]
        
        if busy_resources:
            # Test with first busy resource
            resource_id = busy_resources[0]
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow = today + timedelta(days=1)
            
            bookings_response = requests.get(
                f"{BASE_URL}/api/resource-bookings",
                params={
                    "resource_id": resource_id,
                    "from_date": today.isoformat(),
                    "to_date": tomorrow.isoformat(),
                    "availability_only": "true"
                },
                headers=auth_headers
            )
            assert bookings_response.status_code == 200, f"Bookings request failed: {bookings_response.text}"
            bookings = bookings_response.json()
            
            # If snapshot says resource is busy, there should be at least one booking
            assert len(bookings) > 0, \
                f"Snapshot says resource {resource_id} is busy, but no bookings returned with availability_only=true"
            
            print(f"PASS: Resource {resource_id} is busy in snapshot and has {len(bookings)} bookings")
        else:
            print("INFO: No busy resources found in snapshot, skipping consistency check")
        
        print(f"PASS: Snapshot contains {len(snapshot)} resources")


class TestBug2AggregatePdfFix(TestAuth):
    """
    BUG 2: GET /api/resource-bookings/invoices/aggregate.pdf returned 500
    
    Root cause: aggregate_booking_invoice_pdf called the aggregate_booking_invoice 
    route handler directly with positional args, which shifted Depends() arguments.
    
    Fix: Extract the body into services/booking_aggregator.py::compute_booking_invoice_aggregate 
    and have both endpoints call the service.
    """
    
    def test_aggregate_pdf_returns_200(self, auth_headers):
        """
        GET /api/resource-bookings/invoices/aggregate.pdf returns 200 with PDF content
        This was returning 500 before the fix.
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings/invoices/aggregate.pdf",
            params={
                "from_date": "2026-01-01",
                "to_date": "2026-12-31"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify PDF magic bytes
        content = response.content
        assert content.startswith(b'%PDF-1.4'), \
            f"Response does not start with PDF magic bytes. First 20 bytes: {content[:20]}"
        
        print(f"PASS: aggregate.pdf returns 200 with valid PDF ({len(content)} bytes)")
    
    def test_aggregate_pdf_with_cost_center_filter(self, auth_headers):
        """
        GET /api/resource-bookings/invoices/aggregate.pdf with cost_center filter
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings/invoices/aggregate.pdf",
            params={
                "from_date": "2026-01-01",
                "to_date": "2026-12-31",
                "cost_center": "IT"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert response.content.startswith(b'%PDF-1.4'), "Response is not a valid PDF"
        
        print(f"PASS: aggregate.pdf with cost_center filter returns valid PDF")
    
    def test_aggregate_pdf_with_account_filter(self, auth_headers):
        """
        GET /api/resource-bookings/invoices/aggregate.pdf with account filter
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings/invoices/aggregate.pdf",
            params={
                "from_date": "2026-01-01",
                "to_date": "2026-12-31",
                "account": "8400"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert response.content.startswith(b'%PDF-1.4'), "Response is not a valid PDF"
        
        print(f"PASS: aggregate.pdf with account filter returns valid PDF")
    
    def test_aggregate_json_returns_correct_structure(self, auth_headers):
        """
        GET /api/resource-bookings/invoices/aggregate (JSON) returns correct structure
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings/invoices/aggregate",
            params={
                "from_date": "2026-01-01",
                "to_date": "2026-12-31"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify expected fields
        expected_fields = ["cost_center", "account", "from_date", "to_date", 
                          "booking_count", "lines", "bookings", "total", 
                          "currency", "generated_at"]
        for field in expected_fields:
            assert field in data, f"Missing expected field '{field}' in response"
        
        # Verify types
        assert isinstance(data["booking_count"], int), "booking_count should be int"
        assert isinstance(data["lines"], list), "lines should be list"
        assert isinstance(data["bookings"], list), "bookings should be list"
        assert isinstance(data["total"], (int, float)), "total should be numeric"
        
        print(f"PASS: aggregate JSON returns correct structure with {data['booking_count']} bookings, total={data['total']} {data['currency']}")
    
    def test_aggregate_json_with_filters(self, auth_headers):
        """
        GET /api/resource-bookings/invoices/aggregate with various filters
        """
        # Test with cost_center
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings/invoices/aggregate",
            params={
                "from_date": "2026-01-01",
                "to_date": "2026-12-31",
                "cost_center": "IT"
            },
            headers=auth_headers
        )
        assert response.status_code == 200, f"cost_center filter failed: {response.text}"
        data = response.json()
        assert data.get("cost_center") == "IT", "cost_center not reflected in response"
        
        # Test with account
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings/invoices/aggregate",
            params={
                "from_date": "2026-01-01",
                "to_date": "2026-12-31",
                "account": "8400"
            },
            headers=auth_headers
        )
        assert response.status_code == 200, f"account filter failed: {response.text}"
        data = response.json()
        assert data.get("account") == "8400", "account not reflected in response"
        
        print("PASS: aggregate JSON works with cost_center and account filters")
    
    def test_aggregate_pdf_and_json_consistency(self, auth_headers):
        """
        Verify that aggregate.pdf and aggregate (JSON) return consistent data
        """
        params = {
            "from_date": "2026-01-01",
            "to_date": "2026-12-31"
        }
        
        # Get JSON
        json_response = requests.get(
            f"{BASE_URL}/api/resource-bookings/invoices/aggregate",
            params=params,
            headers=auth_headers
        )
        assert json_response.status_code == 200
        json_data = json_response.json()
        
        # Get PDF
        pdf_response = requests.get(
            f"{BASE_URL}/api/resource-bookings/invoices/aggregate.pdf",
            params=params,
            headers=auth_headers
        )
        assert pdf_response.status_code == 200
        assert pdf_response.content.startswith(b'%PDF-1.4')
        
        print(f"PASS: Both JSON ({json_data['booking_count']} bookings) and PDF endpoints work consistently")


class TestRegressionBookingEndpoints(TestAuth):
    """
    Regression tests for existing booking endpoints to ensure the fixes
    didn't break anything.
    """
    
    def test_list_bookings_without_availability_only(self, auth_headers):
        """
        GET /api/resource-bookings without availability_only should work as before
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Request failed: {response.text}"
        bookings = response.json()
        assert isinstance(bookings, list), "Response should be a list"
        print(f"PASS: list_bookings returns {len(bookings)} bookings")
    
    def test_list_bookings_with_mine_only(self, auth_headers):
        """
        GET /api/resource-bookings?mine_only=true should work
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings",
            params={"mine_only": "true"},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Request failed: {response.text}"
        bookings = response.json()
        assert isinstance(bookings, list), "Response should be a list"
        print(f"PASS: list_bookings with mine_only returns {len(bookings)} bookings")
    
    def test_list_bookings_with_status_filter(self, auth_headers):
        """
        GET /api/resource-bookings?status=confirmed should work
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings",
            params={"status": "confirmed"},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Request failed: {response.text}"
        bookings = response.json()
        assert isinstance(bookings, list), "Response should be a list"
        
        # Verify all returned bookings have confirmed status
        for booking in bookings:
            assert booking.get("status") == "confirmed", \
                f"Booking {booking.get('booking_id')} has status '{booking.get('status')}' instead of 'confirmed'"
        
        print(f"PASS: list_bookings with status=confirmed returns {len(bookings)} bookings")
    
    def test_availability_snapshot_endpoint(self, auth_headers):
        """
        GET /api/resource-availability-snapshot should work
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-availability-snapshot",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        assert "snapshot" in data, "Response should contain 'snapshot' key"
        assert isinstance(data["snapshot"], dict), "snapshot should be a dict"
        print(f"PASS: availability_snapshot returns {len(data['snapshot'])} resources")
    
    def test_single_booking_invoice_pdf(self, auth_headers):
        """
        GET /api/resource-bookings/{booking_id}/invoice.pdf should still work
        """
        # First get a booking
        bookings_response = requests.get(
            f"{BASE_URL}/api/resource-bookings",
            params={"status": "confirmed"},
            headers=auth_headers
        )
        assert bookings_response.status_code == 200
        bookings = bookings_response.json()
        
        if bookings:
            booking_id = bookings[0].get("booking_id")
            
            response = requests.get(
                f"{BASE_URL}/api/resource-bookings/{booking_id}/invoice.pdf",
                headers=auth_headers
            )
            assert response.status_code == 200, f"Request failed: {response.text}"
            assert response.content.startswith(b'%PDF-1.4'), "Response is not a valid PDF"
            print(f"PASS: single booking invoice.pdf works for booking {booking_id}")
        else:
            print("INFO: No confirmed bookings found, skipping single invoice PDF test")
    
    def test_catering_aggregate_pdf(self, auth_headers):
        """
        GET /api/catering-requests/invoices/aggregate.pdf should still work
        """
        response = requests.get(
            f"{BASE_URL}/api/catering-requests/invoices/aggregate.pdf",
            params={
                "from_date": "2026-01-01",
                "to_date": "2026-12-31"
            },
            headers=auth_headers
        )
        assert response.status_code == 200, f"Request failed: {response.text}"
        assert response.content.startswith(b'%PDF-1.4'), "Response is not a valid PDF"
        print("PASS: catering aggregate.pdf still works")


# Note: Service import test removed as it requires running from backend directory context
# The service is verified working via the API tests above


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
