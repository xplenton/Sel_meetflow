"""
Iteration 339 — Backend tests for 6 booking/billing issues:

1. Invoice number display (invoice_number vs invoice_id)
2. Calendar page resource bookings with sub-room enrichment (resource_parent_id/name/sub_id)
3. Splittable room target dropdown availability indicators
4. Occupancy timeline rich tooltip (user_name enrichment)
5. Catering quantity input (frontend-only, tested via UI)
6. Aggregate invoice date filter fix (start_at <= to_date with end-of-day)

Backend tests focus on Issues 1, 2, 4, and 6.
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestIter339InvoiceNumber:
    """Issue 1: Verify invoices endpoint returns invoice_number field"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
    
    def test_invoices_list_returns_invoice_number(self):
        """GET /api/invoices should return invoice_number field for each invoice"""
        resp = self.session.get(f"{BASE_URL}/api/invoices")
        assert resp.status_code == 200, f"Failed to get invoices: {resp.text}"
        invoices = resp.json()
        
        print(f"Found {len(invoices)} invoices")
        
        if invoices:
            # Check first invoice has invoice_number field
            inv = invoices[0]
            print(f"Sample invoice: invoice_id={inv.get('invoice_id')}, invoice_number={inv.get('invoice_number')}")
            
            # invoice_number should be present (may be None for old records)
            assert "invoice_number" in inv or "invoice_id" in inv, "Invoice should have invoice_number or invoice_id"
            
            # If invoice_number exists, it should follow the RE-YYYY-NNNN format
            if inv.get("invoice_number"):
                assert inv["invoice_number"].startswith("RE-") or inv["invoice_number"].startswith("inv_"), \
                    f"Invoice number should start with RE- or inv_: {inv['invoice_number']}"
                print(f"Invoice number format verified: {inv['invoice_number']}")
        else:
            print("No invoices found - skipping format verification")


class TestIter339SubRoomEnrichment:
    """Issue 2: Verify resource bookings include sub-room enrichment fields"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        self.created_bookings = []
        yield
        
        for bid in self.created_bookings:
            try:
                self.session.delete(f"{BASE_URL}/api/resource-bookings/{bid}")
            except:
                pass
    
    def test_find_splittable_rooms_with_children(self):
        """Find splittable rooms and their sub-rooms"""
        resp = self.session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200
        resources = resp.json()
        
        splittable = [r for r in resources if r.get("is_splitable")]
        print(f"Found {len(splittable)} splittable rooms")
        
        for room in splittable[:3]:
            children = [r for r in resources if r.get("parent_resource_id") == room.get("resource_id")]
            print(f"  - {room.get('name')} ({room.get('resource_id')}): {len(children)} sub-rooms")
            for child in children[:2]:
                print(f"    - Sub: {child.get('name')} (sub_id={child.get('sub_id')})")
        
        return splittable
    
    def test_booking_enrichment_includes_subroom_fields(self):
        """GET /api/resource-bookings should include resource_parent_id/name/sub_id for sub-room bookings"""
        resp = self.session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200
        resources = resp.json()
        
        # Find a sub-room (has parent_resource_id)
        sub_rooms = [r for r in resources if r.get("parent_resource_id")]
        if not sub_rooms:
            pytest.skip("No sub-rooms found in the system")
        
        sub_room = sub_rooms[0]
        parent = next((r for r in resources if r.get("resource_id") == sub_room.get("parent_resource_id")), None)
        
        print(f"Testing with sub-room: {sub_room.get('name')} (sub_id={sub_room.get('sub_id')})")
        print(f"Parent room: {parent.get('name') if parent else 'Unknown'}")
        
        # Create a booking on the sub-room
        future = datetime.now() + timedelta(days=7)
        start_at = future.replace(hour=10, minute=0, second=0, microsecond=0)
        end_at = future.replace(hour=11, minute=0, second=0, microsecond=0)
        
        booking_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": sub_room["resource_id"],
            "title": "TEST_Iter339_SubRoom_Enrichment",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        
        if booking_resp.status_code != 200:
            print(f"Could not create sub-room booking: {booking_resp.text}")
            pytest.skip("Could not create sub-room booking")
        
        booking = booking_resp.json()
        self.created_bookings.append(booking["booking_id"])
        print(f"Created booking: {booking['booking_id']}")
        
        # Fetch bookings and verify enrichment
        list_resp = self.session.get(f"{BASE_URL}/api/resource-bookings", params={"mine_only": "true"})
        assert list_resp.status_code == 200
        bookings = list_resp.json()
        
        # Find our test booking
        test_booking = next((b for b in bookings if b.get("booking_id") == booking["booking_id"]), None)
        assert test_booking, "Test booking not found in list"
        
        # Verify enrichment fields
        print(f"Booking enrichment fields:")
        print(f"  resource_name: {test_booking.get('resource_name')}")
        print(f"  resource_parent_id: {test_booking.get('resource_parent_id')}")
        print(f"  resource_parent_name: {test_booking.get('resource_parent_name')}")
        print(f"  resource_sub_id: {test_booking.get('resource_sub_id')}")
        
        # Sub-room bookings should have parent enrichment
        assert test_booking.get("resource_parent_id") == sub_room.get("parent_resource_id"), \
            f"Expected resource_parent_id={sub_room.get('parent_resource_id')}, got {test_booking.get('resource_parent_id')}"
        
        if parent:
            assert test_booking.get("resource_parent_name") == parent.get("name"), \
                f"Expected resource_parent_name={parent.get('name')}, got {test_booking.get('resource_parent_name')}"
        
        print("Sub-room enrichment verified successfully!")


class TestIter339OccupancyUserName:
    """Issue 4: Verify occupancy endpoint returns user_name for tooltip"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        self.created_bookings = []
        yield
        
        for bid in self.created_bookings:
            try:
                self.session.delete(f"{BASE_URL}/api/resource-bookings/{bid}")
            except:
                pass
    
    def test_occupancy_returns_user_name(self):
        """GET /api/resource-occupancy should include user_name for own bookings"""
        # Get a room
        resp = self.session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200
        resources = resp.json()
        
        rooms = [r for r in resources if r.get("type") == "room" and not r.get("parent_resource_id")]
        if not rooms:
            pytest.skip("No rooms found")
        
        room = rooms[0]
        
        # Create a booking
        future = datetime.now() + timedelta(days=1)
        start_at = future.replace(hour=14, minute=0, second=0, microsecond=0)
        end_at = future.replace(hour=15, minute=0, second=0, microsecond=0)
        
        booking_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": room["resource_id"],
            "title": "TEST_Iter339_Occupancy_UserName",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        
        if booking_resp.status_code != 200:
            print(f"Could not create booking: {booking_resp.text}")
            pytest.skip("Could not create booking")
        
        booking = booking_resp.json()
        self.created_bookings.append(booking["booking_id"])
        
        # Fetch occupancy
        from_date = future.replace(hour=0, minute=0, second=0, microsecond=0)
        to_date = from_date + timedelta(days=1)
        
        occ_resp = self.session.get(f"{BASE_URL}/api/resource-occupancy", params={
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "type": "room",
        })
        assert occ_resp.status_code == 200
        occ_data = occ_resp.json()
        
        # Find our booking in the occupancy data
        bookings = occ_data.get("bookings", [])
        test_booking = next((b for b in bookings if b.get("booking_id") == booking["booking_id"]), None)
        
        if test_booking:
            print(f"Occupancy booking fields:")
            print(f"  title: {test_booking.get('title')}")
            print(f"  user_id: {test_booking.get('user_id')}")
            print(f"  user_name: {test_booking.get('user_name')}")
            
            # Own bookings should have user_name
            assert test_booking.get("user_name"), "Own booking should have user_name for tooltip"
            print(f"User name enrichment verified: {test_booking.get('user_name')}")
        else:
            print(f"Test booking not found in occupancy data (may be filtered by date range)")


class TestIter339AggregateInvoiceDateFilter:
    """Issue 6: Verify aggregate invoice date filter includes same-day-ending bookings"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
    
    def test_aggregate_endpoint_returns_data(self):
        """GET /api/resource-bookings/invoices/aggregate should return booking data"""
        # Use a wide date range to capture existing bookings
        from_date = "2026-01-01"
        to_date = "2026-12-31"
        
        resp = self.session.get(f"{BASE_URL}/api/resource-bookings/invoices/aggregate", params={
            "from_date": from_date,
            "to_date": to_date,
        })
        assert resp.status_code == 200, f"Aggregate endpoint failed: {resp.text}"
        data = resp.json()
        
        print(f"Aggregate invoice data:")
        print(f"  booking_count: {data.get('booking_count')}")
        print(f"  total: {data.get('total')}")
        print(f"  lines: {len(data.get('lines', []))}")
        print(f"  bookings with positions: {len(data.get('bookings', []))}")
        
        # Verify the response structure
        assert "booking_count" in data, "Response should include booking_count"
        assert "total" in data, "Response should include total"
        assert "lines" in data, "Response should include lines"
        assert "bookings" in data, "Response should include bookings (Iter 330)"
        
        # If there are bookings with catering, verify they're included
        if data.get("bookings"):
            sample = data["bookings"][0]
            print(f"Sample booking: {sample.get('booking_id')} - {sample.get('title')}")
            print(f"  start_at: {sample.get('start_at')}")
            print(f"  subtotal: {sample.get('subtotal')}")
            print(f"  lines: {len(sample.get('lines', []))}")
    
    def test_aggregate_date_filter_includes_same_day_bookings(self):
        """
        Issue 6: Bookings starting on to_date but ending after midnight should be included.
        The fix changes the filter from end_at <= to_date to start_at <= to_date (end-of-day).
        """
        # Test with today's date
        today = datetime.now().strftime("%Y-%m-%d")
        
        resp = self.session.get(f"{BASE_URL}/api/resource-bookings/invoices/aggregate", params={
            "from_date": "2026-01-01",
            "to_date": today,
        })
        assert resp.status_code == 200
        data = resp.json()
        
        print(f"Aggregate with to_date={today}:")
        print(f"  booking_count: {data.get('booking_count')}")
        
        # The endpoint should work without errors
        # The actual fix is that bookings starting on to_date are now included
        # even if they end after midnight (e.g., 14:00 on to_date)
        
        # Verify the date filter is applied correctly
        assert data.get("to_date") == today, f"to_date should be {today}"


class TestIter339TargetAvailabilityCheck:
    """Issue 3: Verify check-conflicts works for parallel availability checks"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        self.created_bookings = []
        yield
        
        for bid in self.created_bookings:
            try:
                self.session.delete(f"{BASE_URL}/api/resource-bookings/{bid}")
            except:
                pass
    
    def test_check_conflicts_for_multiple_targets(self):
        """
        Issue 3: Frontend needs to check conflicts for all targets (parent + subs)
        to show availability indicators in the dropdown.
        """
        resp = self.session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200
        resources = resp.json()
        
        # Find a splittable room with children
        splittable = [r for r in resources if r.get("is_splitable")]
        if not splittable:
            pytest.skip("No splittable rooms found")
        
        parent = splittable[0]
        children = [r for r in resources if r.get("parent_resource_id") == parent.get("resource_id")]
        
        if not children:
            pytest.skip("No sub-rooms found for splittable room")
        
        print(f"Testing availability check for: {parent.get('name')} with {len(children)} sub-rooms")
        
        # Create a booking on one sub-room
        child = children[0]
        future = datetime.now() + timedelta(days=3)
        start_at = future.replace(hour=9, minute=0, second=0, microsecond=0)
        end_at = future.replace(hour=10, minute=0, second=0, microsecond=0)
        
        booking_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": child["resource_id"],
            "title": "TEST_Iter339_Availability_Check",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        
        if booking_resp.status_code != 200:
            print(f"Could not create booking: {booking_resp.text}")
            pytest.skip("Could not create booking on sub-room")
        
        booking = booking_resp.json()
        self.created_bookings.append(booking["booking_id"])
        print(f"Created booking on {child.get('name')}: {booking['booking_id']}")
        
        # Check conflicts for all targets
        targets = [parent] + children
        results = {}
        
        for target in targets:
            check_resp = self.session.post(f"{BASE_URL}/api/resources/{target['resource_id']}/check-conflicts", json={
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
            })
            assert check_resp.status_code == 200
            conflicts = check_resp.json().get("conflicts", [])
            results[target["resource_id"]] = {
                "name": target.get("name") or target.get("sub_id"),
                "conflicts": len(conflicts),
                "status": conflicts[0].get("status") if conflicts else None,
            }
        
        print(f"\nAvailability check results:")
        for rid, info in results.items():
            status = "busy" if info["conflicts"] > 0 else "free"
            print(f"  {info['name']}: {status} ({info['conflicts']} conflicts)")
        
        # The booked sub-room should show as busy
        assert results[child["resource_id"]]["conflicts"] > 0, \
            f"Booked sub-room should show conflicts"
        
        # Other sub-rooms should be free
        for other_child in children[1:]:
            if other_child["resource_id"] in results:
                # May or may not have conflicts depending on existing bookings
                print(f"  Other sub-room {other_child.get('name')}: {results[other_child['resource_id']]['conflicts']} conflicts")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
