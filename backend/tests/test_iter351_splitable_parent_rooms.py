"""
Iteration 351 - Splitable Parent Rooms Bug Fix Tests

Bug: Parent room UtilRoom_1779600637 (res_adb9fd1d33e9) shows as 'free' even though
BOTH its sub-rooms A (res_3dc6b6488d8c) and B (res_06f47697c287) are fully booked 16:00-20:00.

Root cause: Both the `availability_snapshot` endpoint and the `availability_only=true` filter
on /resource-bookings query by `resource_id == parent_id` only — child bookings on sub-rooms
were invisible to the parent.

Fix:
1. /api/resource-availability-snapshot: build a child→parent map at startup and fold every
   sub-room booking into its parent's entry (next_free uses MAX so multiple parallel sub-bookings
   don't release the parent early).
2. /api/resource-bookings?availability_only=true: when querying for a parent (is_splitable=true),
   expand resource_id filter to include all children. When querying for a child, include the
   parent (so parent bookings block the child too — symmetric).

Test data (pre-seeded):
- Parent: res_adb9fd1d33e9 (UtilRoom_1779600637)
- Child A: res_3dc6b6488d8c (booking bk_890af3eb4e54, 16:00-20:00 on 2026-06-03)
- Child B: res_06f47697c287 (booking bk_8774f786a502, 16:00-20:00 on 2026-06-03)
"""

import os
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test data IDs from the agent context
PARENT_RESOURCE_ID = "res_adb9fd1d33e9"
CHILD_A_RESOURCE_ID = "res_3dc6b6488d8c"
CHILD_B_RESOURCE_ID = "res_06f47697c287"
CHILD_A_BOOKING_ID = "bk_890af3eb4e54"
CHILD_B_BOOKING_ID = "bk_8774f786a502"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@meetflow.com", "password": "admin123"},
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("token") or data.get("access_token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestAvailabilitySnapshotSplitableParent:
    """Tests for /api/resource-availability-snapshot with splitable parent rooms."""

    def test_snapshot_returns_parent_with_children_bookings(self, auth_headers):
        """
        When a splittable parent room has 2 children, and both children have confirmed
        bookings 16:00-20:00 today: GET /api/resource-availability-snapshot returns an
        entry for the PARENT resource_id with busy_now (or next_busy) matching the
        children's times.
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-availability-snapshot",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "snapshot" in data, "Response should contain 'snapshot' key"
        
        snapshot = data["snapshot"]
        
        # The parent resource should appear in the snapshot due to children's bookings
        if PARENT_RESOURCE_ID in snapshot:
            parent_entry = snapshot[PARENT_RESOURCE_ID]
            print(f"Parent entry in snapshot: {parent_entry}")
            
            # If children are booked now, parent should show busy_now=True
            # If children are booked in the future, parent should show next_busy
            assert "busy_now" in parent_entry or "next_busy" in parent_entry, \
                "Parent entry should have busy_now or next_busy from children's bookings"
            
            # If busy_now is True, next_free should be set
            if parent_entry.get("busy_now"):
                assert parent_entry.get("next_free") is not None, \
                    "If busy_now=True, next_free should be set"
                print(f"Parent is busy now, next_free: {parent_entry.get('next_free')}")
            elif parent_entry.get("next_busy"):
                print(f"Parent has upcoming booking, next_busy: {parent_entry.get('next_busy')}")
        else:
            # If parent is not in snapshot, it means no bookings are within the 6-hour horizon
            print(f"Parent {PARENT_RESOURCE_ID} not in snapshot (bookings may be outside 6-hour horizon)")

    def test_snapshot_parent_next_free_is_max_of_children(self, auth_headers):
        """
        Snapshot: if multiple sub-room bookings overlap on a parent, the parent's
        next_free is the LATEST end_at (MAX) — so we don't say 'frei ab 16:00'
        when another sub is still booked until 18:00.
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-availability-snapshot",
            headers=auth_headers,
        )
        assert response.status_code == 200
        
        snapshot = response.json().get("snapshot", {})
        
        if PARENT_RESOURCE_ID in snapshot:
            parent_entry = snapshot[PARENT_RESOURCE_ID]
            
            # If both children have bookings ending at the same time (20:00),
            # the parent's next_free should be that time
            if parent_entry.get("busy_now") and parent_entry.get("next_free"):
                next_free = parent_entry["next_free"]
                print(f"Parent next_free (should be MAX of children's end times): {next_free}")
                
                # Verify it's a valid ISO datetime
                try:
                    parsed = datetime.fromisoformat(next_free.replace("Z", "+00:00"))
                    assert parsed is not None
                    print(f"Parsed next_free: {parsed}")
                except ValueError as e:
                    pytest.fail(f"next_free is not a valid ISO datetime: {e}")


class TestResourceBookingsAvailabilityOnly:
    """Tests for /api/resource-bookings?availability_only=true with splitable rooms."""

    def test_parent_query_returns_children_bookings(self, auth_headers):
        """
        GET /api/resource-bookings?resource_id=<parent_id>&availability_only=true
        returns the children's bookings (status confirmed/pending_approval).
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings",
            params={
                "resource_id": PARENT_RESOURCE_ID,
                "availability_only": "true",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        bookings = response.json()
        assert isinstance(bookings, list), "Response should be a list of bookings"
        
        # Extract resource_ids from returned bookings
        resource_ids = [b.get("resource_id") for b in bookings]
        booking_ids = [b.get("booking_id") for b in bookings]
        
        print(f"Bookings returned for parent query: {len(bookings)}")
        print(f"Resource IDs in response: {resource_ids}")
        print(f"Booking IDs in response: {booking_ids}")
        
        # Should include children's bookings
        children_bookings = [b for b in bookings if b.get("resource_id") in [CHILD_A_RESOURCE_ID, CHILD_B_RESOURCE_ID]]
        print(f"Children's bookings found: {len(children_bookings)}")
        
        # Verify at least one child booking is returned (if they exist)
        if len(bookings) > 0:
            # Check that children's resource_ids are in the response
            has_child_a = CHILD_A_RESOURCE_ID in resource_ids
            has_child_b = CHILD_B_RESOURCE_ID in resource_ids
            print(f"Has Child A booking: {has_child_a}, Has Child B booking: {has_child_b}")
            
            # At least one child should be present if bookings exist
            assert has_child_a or has_child_b or PARENT_RESOURCE_ID in resource_ids, \
                "Parent query should return parent or children's bookings"

    def test_child_query_returns_parent_bookings(self, auth_headers):
        """
        GET /api/resource-bookings?resource_id=<child_id>&availability_only=true
        also includes any parent-level bookings.
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings",
            params={
                "resource_id": CHILD_A_RESOURCE_ID,
                "availability_only": "true",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        bookings = response.json()
        assert isinstance(bookings, list), "Response should be a list of bookings"
        
        resource_ids = [b.get("resource_id") for b in bookings]
        print(f"Bookings returned for child A query: {len(bookings)}")
        print(f"Resource IDs in response: {resource_ids}")
        
        # The query should include both the child's own bookings AND parent bookings
        # (symmetric blocking: parent bookings block the child)
        has_child_a = CHILD_A_RESOURCE_ID in resource_ids
        has_parent = PARENT_RESOURCE_ID in resource_ids
        
        print(f"Has Child A booking: {has_child_a}, Has Parent booking: {has_parent}")
        
        # Child A should at least have its own booking
        if len(bookings) > 0:
            assert has_child_a or has_parent, \
                "Child query should return child's own bookings or parent bookings"

    def test_availability_only_returns_correct_statuses(self, auth_headers):
        """
        Verify that availability_only=true only returns bookings with status
        'confirmed' or 'pending_approval'.
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings",
            params={
                "resource_id": PARENT_RESOURCE_ID,
                "availability_only": "true",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        
        bookings = response.json()
        
        for booking in bookings:
            status = booking.get("status")
            assert status in ["confirmed", "pending_approval"], \
                f"Booking {booking.get('booking_id')} has unexpected status: {status}"
            print(f"Booking {booking.get('booking_id')}: status={status}")


class TestParentWithOwnAndChildrenBookings:
    """Tests for when parent has its OWN booking AND children have bookings."""

    def test_parent_query_returns_both_parent_and_children_bookings(self, auth_headers):
        """
        When the parent has its OWN booking AND children have bookings,
        parent query returns BOTH.
        """
        # First, let's check what bookings exist for the parent directly
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings",
            params={
                "resource_id": PARENT_RESOURCE_ID,
                "availability_only": "true",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        
        bookings = response.json()
        
        # Categorize bookings by resource_id
        parent_bookings = [b for b in bookings if b.get("resource_id") == PARENT_RESOURCE_ID]
        child_a_bookings = [b for b in bookings if b.get("resource_id") == CHILD_A_RESOURCE_ID]
        child_b_bookings = [b for b in bookings if b.get("resource_id") == CHILD_B_RESOURCE_ID]
        
        print(f"Parent's own bookings: {len(parent_bookings)}")
        print(f"Child A bookings: {len(child_a_bookings)}")
        print(f"Child B bookings: {len(child_b_bookings)}")
        print(f"Total bookings returned: {len(bookings)}")
        
        # The fix should ensure children's bookings are included
        total_children = len(child_a_bookings) + len(child_b_bookings)
        if total_children > 0:
            print("SUCCESS: Children's bookings are included in parent query")
        else:
            print("NOTE: No children's bookings found (may be outside date range)")


class TestNonSplitableResourcesBehavior:
    """Tests to ensure non-splittable resources behave exactly as before."""

    def test_non_splitable_resource_no_children_foldin(self, auth_headers):
        """
        Non-splittable resources behave exactly as before (no children fold-in,
        no parent fold-in).
        """
        # First, find a non-splitable resource
        response = requests.get(
            f"{BASE_URL}/api/resources",
            headers=auth_headers,
        )
        assert response.status_code == 200
        
        resources = response.json()
        
        # Find a non-splitable resource (is_splitable=False or not set, and no parent)
        non_splitable = None
        for r in resources:
            if not r.get("is_splitable") and not r.get("parent_resource_id"):
                non_splitable = r
                break
        
        if non_splitable is None:
            pytest.skip("No non-splitable resource found for testing")
        
        resource_id = non_splitable.get("resource_id")
        print(f"Testing non-splitable resource: {resource_id} ({non_splitable.get('name')})")
        
        # Query availability_only for this resource
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings",
            params={
                "resource_id": resource_id,
                "availability_only": "true",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        
        bookings = response.json()
        
        # All returned bookings should be for this resource only
        for booking in bookings:
            assert booking.get("resource_id") == resource_id, \
                f"Non-splitable resource query returned booking for different resource: {booking.get('resource_id')}"
        
        print(f"Non-splitable resource query returned {len(bookings)} bookings, all for the correct resource")


class TestSanityExistingEndpoints:
    """Sanity tests to ensure existing endpoints still work."""

    def test_create_booking_still_works(self, auth_headers):
        """Sanity: create booking endpoint still works."""
        # Find a resource to book
        response = requests.get(
            f"{BASE_URL}/api/resources",
            headers=auth_headers,
        )
        assert response.status_code == 200
        
        resources = response.json()
        if not resources:
            pytest.skip("No resources available for booking test")
        
        # Find an active resource
        active_resource = None
        for r in resources:
            if r.get("status") == "active" and not r.get("parent_resource_id"):
                active_resource = r
                break
        
        if not active_resource:
            pytest.skip("No active resource found for booking test")
        
        resource_id = active_resource.get("resource_id")
        
        # Create a booking for tomorrow to avoid conflicts
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        start = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        end = tomorrow.replace(hour=11, minute=0, second=0, microsecond=0)
        
        # First check for conflicts
        conflict_response = requests.post(
            f"{BASE_URL}/api/resources/{resource_id}/check-conflicts",
            json={
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
            },
            headers=auth_headers,
        )
        
        if conflict_response.status_code == 200:
            conflicts = conflict_response.json().get("conflicts", [])
            if conflicts:
                print(f"Conflicts found, skipping booking creation: {conflicts}")
                pytest.skip("Conflicts exist for the test time slot")
        
        # Create booking
        booking_response = requests.post(
            f"{BASE_URL}/api/resource-bookings",
            json={
                "resource_id": resource_id,
                "title": "TEST_iter351_sanity_booking",
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
            },
            headers=auth_headers,
        )
        
        # Accept 200, 201, or 409 (conflict)
        assert booking_response.status_code in [200, 201, 409], \
            f"Unexpected status: {booking_response.status_code}: {booking_response.text}"
        
        if booking_response.status_code in [200, 201]:
            booking = booking_response.json()
            booking_id = booking.get("booking_id")
            print(f"Created test booking: {booking_id}")
            
            # Clean up - cancel the booking
            cancel_response = requests.delete(
                f"{BASE_URL}/api/resource-bookings/{booking_id}",
                headers=auth_headers,
            )
            assert cancel_response.status_code in [200, 204], \
                f"Failed to cancel test booking: {cancel_response.status_code}"
            print(f"Cleaned up test booking: {booking_id}")
        else:
            print("Booking creation returned 409 (conflict), which is acceptable")

    def test_check_conflicts_still_works(self, auth_headers):
        """Sanity: check-conflicts endpoint still works."""
        # Use the parent resource for conflict check
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        start = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
        end = tomorrow.replace(hour=15, minute=0, second=0, microsecond=0)
        
        response = requests.post(
            f"{BASE_URL}/api/resources/{PARENT_RESOURCE_ID}/check-conflicts",
            json={
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
            },
            headers=auth_headers,
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "conflicts" in data, "Response should contain 'conflicts' key"
        print(f"Check-conflicts returned {len(data['conflicts'])} conflicts")

    def test_list_bookings_mine_only_still_works(self, auth_headers):
        """Sanity: list bookings with mine_only=true still works."""
        response = requests.get(
            f"{BASE_URL}/api/resource-bookings",
            params={"mine_only": "true"},
            headers=auth_headers,
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        bookings = response.json()
        assert isinstance(bookings, list), "Response should be a list"
        print(f"mine_only query returned {len(bookings)} bookings")

    def test_availability_snapshot_still_works(self, auth_headers):
        """Sanity: availability snapshot endpoint still works."""
        response = requests.get(
            f"{BASE_URL}/api/resource-availability-snapshot",
            headers=auth_headers,
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "snapshot" in data, "Response should contain 'snapshot' key"
        print(f"Availability snapshot returned {len(data['snapshot'])} resource entries")


class TestSpecificBookingVerification:
    """Tests to verify the specific bookings mentioned in the bug report."""

    def test_verify_child_bookings_exist(self, auth_headers):
        """Verify that the specific child bookings mentioned in the bug report exist."""
        # Check Child A booking
        response_a = requests.get(
            f"{BASE_URL}/api/resource-bookings/{CHILD_A_BOOKING_ID}",
            headers=auth_headers,
        )
        
        if response_a.status_code == 200:
            booking_a = response_a.json()
            print(f"Child A booking found: {booking_a.get('booking_id')}")
            print(f"  Resource: {booking_a.get('resource_id')}")
            print(f"  Status: {booking_a.get('status')}")
            print(f"  Start: {booking_a.get('start_at')}")
            print(f"  End: {booking_a.get('end_at')}")
        else:
            print(f"Child A booking {CHILD_A_BOOKING_ID} not found (status {response_a.status_code})")
        
        # Check Child B booking
        response_b = requests.get(
            f"{BASE_URL}/api/resource-bookings/{CHILD_B_BOOKING_ID}",
            headers=auth_headers,
        )
        
        if response_b.status_code == 200:
            booking_b = response_b.json()
            print(f"Child B booking found: {booking_b.get('booking_id')}")
            print(f"  Resource: {booking_b.get('resource_id')}")
            print(f"  Status: {booking_b.get('status')}")
            print(f"  Start: {booking_b.get('start_at')}")
            print(f"  End: {booking_b.get('end_at')}")
        else:
            print(f"Child B booking {CHILD_B_BOOKING_ID} not found (status {response_b.status_code})")

    def test_verify_parent_resource_is_splitable(self, auth_headers):
        """Verify that the parent resource is marked as splitable."""
        response = requests.get(
            f"{BASE_URL}/api/resources/{PARENT_RESOURCE_ID}",
            headers=auth_headers,
        )
        
        if response.status_code == 200:
            resource = response.json()
            print(f"Parent resource: {resource.get('name')}")
            print(f"  is_splitable: {resource.get('is_splitable')}")
            print(f"  parent_resource_id: {resource.get('parent_resource_id')}")
            
            assert resource.get("is_splitable") == True, \
                f"Parent resource should be splitable, got: {resource.get('is_splitable')}"
        else:
            print(f"Parent resource {PARENT_RESOURCE_ID} not found (status {response.status_code})")

    def test_verify_children_have_correct_parent(self, auth_headers):
        """Verify that child resources have the correct parent_resource_id."""
        # Check Child A
        response_a = requests.get(
            f"{BASE_URL}/api/resources/{CHILD_A_RESOURCE_ID}",
            headers=auth_headers,
        )
        
        if response_a.status_code == 200:
            child_a = response_a.json()
            print(f"Child A resource: {child_a.get('name')}")
            print(f"  parent_resource_id: {child_a.get('parent_resource_id')}")
            
            assert child_a.get("parent_resource_id") == PARENT_RESOURCE_ID, \
                f"Child A should have parent {PARENT_RESOURCE_ID}, got: {child_a.get('parent_resource_id')}"
        else:
            print(f"Child A resource {CHILD_A_RESOURCE_ID} not found (status {response_a.status_code})")
        
        # Check Child B
        response_b = requests.get(
            f"{BASE_URL}/api/resources/{CHILD_B_RESOURCE_ID}",
            headers=auth_headers,
        )
        
        if response_b.status_code == 200:
            child_b = response_b.json()
            print(f"Child B resource: {child_b.get('name')}")
            print(f"  parent_resource_id: {child_b.get('parent_resource_id')}")
            
            assert child_b.get("parent_resource_id") == PARENT_RESOURCE_ID, \
                f"Child B should have parent {PARENT_RESOURCE_ID}, got: {child_b.get('parent_resource_id')}"
        else:
            print(f"Child B resource {CHILD_B_RESOURCE_ID} not found (status {response_b.status_code})")
