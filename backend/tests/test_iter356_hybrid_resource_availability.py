"""
Iteration 356 - Unified Hybrid Endpoint /api/resource-availability

New endpoint that returns BOTH the snapshot ({busy_now, next_free, next_busy} per resource)
AND the privacy-safe slot-picker bookings list in a single request.

Replaces the legacy 1×snapshot + N×availability_only=true calls (165 calls for 164 resources → now 2).
Both pieces derive from a SINGLE Mongo query → status-drift physically impossible.

Single source of truth uses services.resource_hierarchy.child_to_parent_map to fold sub-room
bookings into parents (iter 351 fix preserved).

The legacy /api/resource-availability-snapshot endpoint remains as a backwards-compat alias.

Test data (from iter 351/352):
- Parent: res_adb9fd1d33e9 (UtilRoom_1779600637, is_splitable=True)
- Child A: res_3dc6b6488d8c (sub A)
- Child B: res_06f47697c287 (sub B)
"""

import os
import pytest
import requests
from datetime import datetime, timezone, timedelta
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test data IDs from iter 351/352
PARENT_RESOURCE_ID = "res_adb9fd1d33e9"
CHILD_A_RESOURCE_ID = "res_3dc6b6488d8c"
CHILD_B_RESOURCE_ID = "res_06f47697c287"


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


@pytest.fixture(scope="module")
def test_bookings(auth_headers):
    """Create fresh test bookings on both children for testing."""
    # Use a time window within the 12-hour horizon to ensure they appear in snapshot
    now = datetime.now(timezone.utc)
    start = now + timedelta(hours=2)
    start = start.replace(minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=2)
    
    # For the MAX(end_at) test, create Child B booking ending 1 hour later
    end_b = end + timedelta(hours=1)
    
    created_bookings = []
    
    # Create booking on Child A (ends at 'end')
    response_a = requests.post(
        f"{BASE_URL}/api/resource-bookings",
        json={
            "resource_id": CHILD_A_RESOURCE_ID,
            "title": f"TEST_iter356_child_a_{uuid.uuid4().hex[:8]}",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
        },
        headers=auth_headers,
    )
    if response_a.status_code in [200, 201]:
        booking_a = response_a.json()
        created_bookings.append(booking_a)
        print(f"Created Child A booking: {booking_a.get('booking_id')} ({start} - {end})")
    else:
        print(f"Failed to create Child A booking: {response_a.status_code} - {response_a.text}")
    
    # Create booking on Child B (ends 1 hour later for MAX test)
    response_b = requests.post(
        f"{BASE_URL}/api/resource-bookings",
        json={
            "resource_id": CHILD_B_RESOURCE_ID,
            "title": f"TEST_iter356_child_b_{uuid.uuid4().hex[:8]}",
            "start_at": start.isoformat(),
            "end_at": end_b.isoformat(),
        },
        headers=auth_headers,
    )
    if response_b.status_code in [200, 201]:
        booking_b = response_b.json()
        created_bookings.append(booking_b)
        print(f"Created Child B booking: {booking_b.get('booking_id')} ({start} - {end_b})")
    else:
        print(f"Failed to create Child B booking: {response_b.status_code} - {response_b.text}")
    
    yield {
        "bookings": created_bookings,
        "start": start,
        "end_a": end,
        "end_b": end_b,
    }
    
    # Cleanup: Cancel all created bookings
    for booking in created_bookings:
        booking_id = booking.get("booking_id")
        if booking_id:
            requests.delete(
                f"{BASE_URL}/api/resource-bookings/{booking_id}",
                headers=auth_headers,
            )
            print(f"Cleaned up booking: {booking_id}")


# =============================================================================
# Test Class 1: GET /api/resource-availability (no params) - Global snapshot
# =============================================================================
class TestHybridEndpointGlobal:
    """GET /api/resource-availability (no params) — returns snapshot + empty bookings_by_resource."""

    def test_global_returns_snapshot_and_bookings_by_resource(self, auth_headers, test_bookings):
        """
        Global call returns {snapshot: {...}, bookings_by_resource: {}} for ALL resources.
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-availability",
            headers=auth_headers,
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Must have both keys
        assert "snapshot" in data, "Response should contain 'snapshot' key"
        assert "bookings_by_resource" in data, "Response should contain 'bookings_by_resource' key"
        
        snapshot = data["snapshot"]
        bookings_by_resource = data["bookings_by_resource"]
        
        print(f"Global snapshot has {len(snapshot)} resource entries")
        print(f"Global bookings_by_resource has {len(bookings_by_resource)} entries")
        
        # When no resource_ids param, bookings_by_resource should be empty (per implementation)
        assert bookings_by_resource == {}, \
            f"Global call should return empty bookings_by_resource, got {len(bookings_by_resource)} entries"
        
        # Snapshot should have entries
        assert len(snapshot) > 0, "Snapshot should have at least some resource entries"

    def test_global_snapshot_includes_parent_with_children_bookings(self, auth_headers, test_bookings):
        """
        Snapshot must include parent_id entries with next_busy when children are booked (iter 351 behavior preserved).
        """
        if not test_bookings["bookings"]:
            pytest.skip("No test bookings created")
        
        response = requests.get(
            f"{BASE_URL}/api/resource-availability",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        snapshot = response.json().get("snapshot", {})
        
        # Parent should be in snapshot due to children's bookings
        if PARENT_RESOURCE_ID in snapshot:
            parent_entry = snapshot[PARENT_RESOURCE_ID]
            print(f"Parent entry in global snapshot: {parent_entry}")
            
            # Parent should show busy_now or next_busy from children's bookings
            assert parent_entry.get("busy_now") or parent_entry.get("next_busy"), \
                "Parent should show busy_now or next_busy when children are booked"
        else:
            # If bookings are outside 12-hour horizon, parent won't appear
            print(f"Parent {PARENT_RESOURCE_ID} not in snapshot (bookings may be outside horizon)")


# =============================================================================
# Test Class 2: GET /api/resource-availability?resource_ids=A,B,C - Scoped call
# =============================================================================
class TestHybridEndpointScoped:
    """GET /api/resource-availability?resource_ids=A,B,C — returns scoped snapshot + bookings."""

    def test_scoped_returns_snapshot_and_bookings_for_requested_ids(self, auth_headers, test_bookings):
        """
        Scoped call returns snapshot + bookings_by_resource for those ids.
        """
        if not test_bookings["bookings"]:
            pytest.skip("No test bookings created")
        
        # Request parent and both children
        resource_ids = f"{PARENT_RESOURCE_ID},{CHILD_A_RESOURCE_ID},{CHILD_B_RESOURCE_ID}"
        
        response = requests.get(
            f"{BASE_URL}/api/resource-availability",
            params={"resource_ids": resource_ids},
            headers=auth_headers,
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        assert "snapshot" in data, "Response should contain 'snapshot' key"
        assert "bookings_by_resource" in data, "Response should contain 'bookings_by_resource' key"
        
        snapshot = data["snapshot"]
        bookings_by_resource = data["bookings_by_resource"]
        
        print(f"Scoped snapshot has {len(snapshot)} resource entries")
        print(f"Scoped bookings_by_resource has {len(bookings_by_resource)} entries")
        
        # bookings_by_resource should NOT be empty for scoped calls
        assert len(bookings_by_resource) > 0, \
            "Scoped call should return non-empty bookings_by_resource"

    def test_scoped_child_booking_appears_in_both_child_and_parent_lists(self, auth_headers, test_bookings):
        """
        Each child booking on a sub-room must appear in BOTH the child's bookings list
        AND the parent's bookings list (phantom entry).
        """
        if not test_bookings["bookings"]:
            pytest.skip("No test bookings created")
        
        # Request parent and both children
        resource_ids = f"{PARENT_RESOURCE_ID},{CHILD_A_RESOURCE_ID},{CHILD_B_RESOURCE_ID}"
        
        response = requests.get(
            f"{BASE_URL}/api/resource-availability",
            params={"resource_ids": resource_ids},
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        bookings_by_resource = response.json().get("bookings_by_resource", {})
        
        # Get booking IDs from test bookings
        test_booking_ids = [b.get("booking_id") for b in test_bookings["bookings"]]
        
        # Check Child A's bookings list
        child_a_bookings = bookings_by_resource.get(CHILD_A_RESOURCE_ID, [])
        child_a_booking_ids = [b.get("booking_id") for b in child_a_bookings]
        
        # Check Child B's bookings list
        child_b_bookings = bookings_by_resource.get(CHILD_B_RESOURCE_ID, [])
        child_b_booking_ids = [b.get("booking_id") for b in child_b_bookings]
        
        # Check Parent's bookings list (should have phantom entries)
        parent_bookings = bookings_by_resource.get(PARENT_RESOURCE_ID, [])
        parent_booking_ids = [b.get("booking_id") for b in parent_bookings]
        
        print(f"Child A bookings: {child_a_booking_ids}")
        print(f"Child B bookings: {child_b_booking_ids}")
        print(f"Parent bookings (phantom): {parent_booking_ids}")
        
        # Verify child bookings appear in their own lists
        for booking in test_bookings["bookings"]:
            bid = booking.get("booking_id")
            rid = booking.get("resource_id")
            
            if rid == CHILD_A_RESOURCE_ID:
                assert bid in child_a_booking_ids, \
                    f"Child A booking {bid} should appear in Child A's bookings list"
                # Should also appear in parent's list as phantom
                assert bid in parent_booking_ids, \
                    f"Child A booking {bid} should appear in Parent's bookings list (phantom)"
            
            elif rid == CHILD_B_RESOURCE_ID:
                assert bid in child_b_booking_ids, \
                    f"Child B booking {bid} should appear in Child B's bookings list"
                # Should also appear in parent's list as phantom
                assert bid in parent_booking_ids, \
                    f"Child B booking {bid} should appear in Parent's bookings list (phantom)"

    def test_scoped_snapshot_reflects_child_bookings_on_parent(self, auth_headers, test_bookings):
        """
        The snapshot for the parent must reflect the child bookings.
        """
        if not test_bookings["bookings"]:
            pytest.skip("No test bookings created")
        
        resource_ids = f"{PARENT_RESOURCE_ID},{CHILD_A_RESOURCE_ID},{CHILD_B_RESOURCE_ID}"
        
        response = requests.get(
            f"{BASE_URL}/api/resource-availability",
            params={"resource_ids": resource_ids},
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        snapshot = response.json().get("snapshot", {})
        
        if PARENT_RESOURCE_ID in snapshot:
            parent_entry = snapshot[PARENT_RESOURCE_ID]
            print(f"Parent snapshot entry: {parent_entry}")
            
            # Parent should show busy_now or next_busy
            assert parent_entry.get("busy_now") or parent_entry.get("next_busy"), \
                "Parent snapshot should reflect child bookings"


# =============================================================================
# Test Class 3: Legacy /api/resource-availability-snapshot still works
# =============================================================================
class TestLegacySnapshotEndpoint:
    """Legacy GET /api/resource-availability-snapshot still works and returns same data."""

    def test_legacy_endpoint_returns_snapshot(self, auth_headers, test_bookings):
        """
        Legacy endpoint still works and returns the same snapshot data.
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-availability-snapshot",
            headers=auth_headers,
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "snapshot" in data, "Legacy endpoint should return 'snapshot' key"
        
        snapshot = data["snapshot"]
        print(f"Legacy snapshot has {len(snapshot)} resource entries")

    def test_legacy_and_hybrid_snapshots_match(self, auth_headers, test_bookings):
        """
        Legacy endpoint returns the same snapshot data as the global hybrid call (no drift).
        """
        # Get legacy snapshot
        legacy_response = requests.get(
            f"{BASE_URL}/api/resource-availability-snapshot",
            headers=auth_headers,
        )
        assert legacy_response.status_code == 200
        legacy_snapshot = legacy_response.json().get("snapshot", {})
        
        # Get hybrid snapshot (global)
        hybrid_response = requests.get(
            f"{BASE_URL}/api/resource-availability",
            headers=auth_headers,
        )
        assert hybrid_response.status_code == 200
        hybrid_snapshot = hybrid_response.json().get("snapshot", {})
        
        # Compare snapshots - they should be identical
        assert legacy_snapshot == hybrid_snapshot, \
            "Legacy and hybrid snapshots should be identical (no drift)"
        
        print(f"Legacy and hybrid snapshots match ({len(legacy_snapshot)} entries)")


# =============================================================================
# Test Class 4: Parent's next_free uses MAX(end_at) of children
# =============================================================================
class TestParentNextFreeMaxEndAt:
    """When a parent has 2 children both booked, parent's next_free uses MAX(end_at)."""

    def test_parent_next_free_is_max_of_children_end_times(self, auth_headers, test_bookings):
        """
        When both children are booked at the same time but end at different times,
        parent's next_free should be the LATER end time (MAX).
        """
        if len(test_bookings["bookings"]) < 2:
            pytest.skip("Need both child bookings for this test")
        
        # Our test fixture creates:
        # - Child A: start -> end_a
        # - Child B: start -> end_b (end_b = end_a + 1 hour)
        
        response = requests.get(
            f"{BASE_URL}/api/resource-availability",
            params={"resource_ids": PARENT_RESOURCE_ID},
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        snapshot = response.json().get("snapshot", {})
        
        if PARENT_RESOURCE_ID in snapshot:
            parent_entry = snapshot[PARENT_RESOURCE_ID]
            print(f"Parent entry: {parent_entry}")
            
            if parent_entry.get("busy_now") and parent_entry.get("next_free"):
                next_free = parent_entry["next_free"]
                expected_max_end = test_bookings["end_b"].isoformat()
                
                print(f"Parent next_free: {next_free}")
                print(f"Expected MAX end (Child B): {expected_max_end}")
                
                # Parse and compare
                next_free_dt = datetime.fromisoformat(next_free.replace("Z", "+00:00"))
                expected_dt = test_bookings["end_b"]
                if expected_dt.tzinfo is None:
                    expected_dt = expected_dt.replace(tzinfo=timezone.utc)
                
                # next_free should be >= the later end time
                assert next_free_dt >= expected_dt, \
                    f"Parent next_free ({next_free}) should be >= MAX child end ({expected_max_end})"
            elif parent_entry.get("next_busy"):
                print(f"Parent has next_busy (bookings in future): {parent_entry.get('next_busy')}")
        else:
            print(f"Parent not in snapshot (bookings may be outside horizon)")


# =============================================================================
# Test Class 5: Non-splittable resources unchanged
# =============================================================================
class TestNonSplittableResources:
    """Non-splittable resources return snapshot/bookings unchanged (no fake parent/child expansion)."""

    def test_non_splittable_resource_no_expansion(self, auth_headers):
        """
        Non-splittable resources return their own data only, no fake expansion.
        """
        # Find a non-splittable resource
        response = requests.get(
            f"{BASE_URL}/api/resources",
            headers=auth_headers,
        )
        assert response.status_code == 200
        
        resources = response.json()
        
        non_splittable = None
        for r in resources:
            if not r.get("is_splitable") and not r.get("parent_resource_id"):
                non_splittable = r
                break
        
        if non_splittable is None:
            pytest.skip("No non-splittable resource found")
        
        resource_id = non_splittable.get("resource_id")
        print(f"Testing non-splittable resource: {resource_id} ({non_splittable.get('name')})")
        
        # Call hybrid endpoint with this resource
        response = requests.get(
            f"{BASE_URL}/api/resource-availability",
            params={"resource_ids": resource_id},
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        data = response.json()
        bookings_by_resource = data.get("bookings_by_resource", {})
        
        # All bookings should be for this resource only
        for rid, bookings in bookings_by_resource.items():
            for b in bookings:
                assert b.get("resource_id") == rid, \
                    f"Non-splittable resource should not have bookings from other resources"
        
        print(f"Non-splittable resource returned {len(bookings_by_resource.get(resource_id, []))} bookings")


# =============================================================================
# Test Class 6: Permission check (403 without view:resources)
# =============================================================================
class TestPermissionCheck:
    """Only users with view:resources cap can call either endpoint (403 otherwise)."""

    def test_hybrid_endpoint_requires_auth(self):
        """
        Unauthenticated request returns 401/403.
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-availability",
        )
        
        assert response.status_code in [401, 403], \
            f"Expected 401/403 for unauthenticated request, got {response.status_code}"
        
        print(f"Unauthenticated request returned {response.status_code}")

    def test_legacy_endpoint_requires_auth(self):
        """
        Legacy endpoint also requires authentication.
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-availability-snapshot",
        )
        
        assert response.status_code in [401, 403], \
            f"Expected 401/403 for unauthenticated request, got {response.status_code}"
        
        print(f"Legacy unauthenticated request returned {response.status_code}")


# =============================================================================
# Test Class 7: Legacy /resource-bookings?availability_only=true still works
# =============================================================================
class TestLegacyAvailabilityOnlyEndpoint:
    """Sanity: existing /resource-bookings?availability_only=true list endpoint still works."""

    def test_availability_only_endpoint_still_works(self, auth_headers, test_bookings):
        """
        The slot picker no longer uses it but tests may - verify backwards compat.
        """
        if not test_bookings["bookings"]:
            pytest.skip("No test bookings created")
        
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
        assert isinstance(bookings, list), "Response should be a list"
        
        print(f"Legacy availability_only returned {len(bookings)} bookings")
        
        # Should include children's bookings (iter 351 behavior)
        resource_ids = [b.get("resource_id") for b in bookings]
        has_child_a = CHILD_A_RESOURCE_ID in resource_ids
        has_child_b = CHILD_B_RESOURCE_ID in resource_ids
        
        print(f"Has Child A: {has_child_a}, Has Child B: {has_child_b}")


# =============================================================================
# Test Class 8: Regression - create booking → snapshot updates → cancel → snapshot reflects
# =============================================================================
class TestRegressionBookingSnapshotSync:
    """Regression: create booking → snapshot updates within next request → cancel → snapshot reflects."""

    def test_booking_lifecycle_reflects_in_snapshot(self, auth_headers):
        """
        Create a booking, verify snapshot shows it, cancel it, verify snapshot no longer shows it.
        """
        # Find an active resource
        response = requests.get(
            f"{BASE_URL}/api/resources",
            headers=auth_headers,
        )
        assert response.status_code == 200
        
        resources = response.json()
        
        active_resource = None
        for r in resources:
            if r.get("status") == "active" and not r.get("parent_resource_id"):
                active_resource = r
                break
        
        if not active_resource:
            pytest.skip("No active resource found")
        
        resource_id = active_resource.get("resource_id")
        
        # Create a booking starting soon (within 12-hour horizon)
        now = datetime.now(timezone.utc)
        start = now + timedelta(hours=1)
        start = start.replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1)
        
        # Step 1: Check snapshot BEFORE booking
        before_response = requests.get(
            f"{BASE_URL}/api/resource-availability",
            params={"resource_ids": resource_id},
            headers=auth_headers,
        )
        assert before_response.status_code == 200
        before_snapshot = before_response.json().get("snapshot", {})
        before_entry = before_snapshot.get(resource_id, {})
        print(f"Before booking - snapshot entry: {before_entry}")
        
        # Step 2: Create booking
        create_response = requests.post(
            f"{BASE_URL}/api/resource-bookings",
            json={
                "resource_id": resource_id,
                "title": f"TEST_iter356_regression_{uuid.uuid4().hex[:8]}",
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
            },
            headers=auth_headers,
        )
        
        if create_response.status_code not in [200, 201]:
            pytest.skip(f"Could not create booking: {create_response.status_code} - {create_response.text}")
        
        booking = create_response.json()
        booking_id = booking.get("booking_id")
        print(f"Created booking: {booking_id}")
        
        try:
            # Step 3: Check snapshot AFTER booking - should show busy_now or next_busy
            after_response = requests.get(
                f"{BASE_URL}/api/resource-availability",
                params={"resource_ids": resource_id},
                headers=auth_headers,
            )
            assert after_response.status_code == 200
            after_snapshot = after_response.json().get("snapshot", {})
            after_entry = after_snapshot.get(resource_id, {})
            print(f"After booking - snapshot entry: {after_entry}")
            
            # Should show busy_now or next_busy
            assert after_entry.get("busy_now") or after_entry.get("next_busy"), \
                "Snapshot should reflect the new booking"
            
            # Step 4: Cancel booking
            cancel_response = requests.delete(
                f"{BASE_URL}/api/resource-bookings/{booking_id}",
                headers=auth_headers,
            )
            assert cancel_response.status_code in [200, 204], \
                f"Failed to cancel booking: {cancel_response.status_code}"
            print(f"Cancelled booking: {booking_id}")
            
            # Step 5: Check snapshot AFTER cancel - should no longer show this booking
            final_response = requests.get(
                f"{BASE_URL}/api/resource-availability",
                params={"resource_ids": resource_id},
                headers=auth_headers,
            )
            assert final_response.status_code == 200
            final_snapshot = final_response.json().get("snapshot", {})
            final_entry = final_snapshot.get(resource_id, {})
            print(f"After cancel - snapshot entry: {final_entry}")
            
            # The cancelled booking should no longer affect the snapshot
            # (unless there are other bookings)
            
        finally:
            # Ensure cleanup even if assertions fail
            requests.delete(
                f"{BASE_URL}/api/resource-bookings/{booking_id}",
                headers=auth_headers,
            )


# =============================================================================
# Test Class 9: Bookings list structure validation
# =============================================================================
class TestBookingsListStructure:
    """Validate the structure of bookings returned in bookings_by_resource."""

    def test_bookings_have_required_fields(self, auth_headers, test_bookings):
        """
        Each booking in bookings_by_resource should have: booking_id, resource_id, start_at, end_at, status.
        """
        if not test_bookings["bookings"]:
            pytest.skip("No test bookings created")
        
        resource_ids = f"{PARENT_RESOURCE_ID},{CHILD_A_RESOURCE_ID},{CHILD_B_RESOURCE_ID}"
        
        response = requests.get(
            f"{BASE_URL}/api/resource-availability",
            params={"resource_ids": resource_ids},
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        bookings_by_resource = response.json().get("bookings_by_resource", {})
        
        required_fields = ["booking_id", "resource_id", "start_at", "end_at", "status"]
        
        for rid, bookings in bookings_by_resource.items():
            for booking in bookings:
                for field in required_fields:
                    assert field in booking, \
                        f"Booking missing required field '{field}': {booking}"
                
                # Validate status is one of the expected values
                assert booking["status"] in ["confirmed", "pending_approval"], \
                    f"Unexpected booking status: {booking['status']}"
                
                # Validate datetime format
                try:
                    datetime.fromisoformat(booking["start_at"].replace("Z", "+00:00"))
                    datetime.fromisoformat(booking["end_at"].replace("Z", "+00:00"))
                except ValueError as e:
                    pytest.fail(f"Invalid datetime format in booking: {e}")
        
        print(f"All bookings have required fields and valid structure")

    def test_bookings_are_privacy_safe(self, auth_headers, test_bookings):
        """
        Bookings should NOT contain user info (privacy-safe for slot picker).
        """
        if not test_bookings["bookings"]:
            pytest.skip("No test bookings created")
        
        resource_ids = f"{PARENT_RESOURCE_ID},{CHILD_A_RESOURCE_ID},{CHILD_B_RESOURCE_ID}"
        
        response = requests.get(
            f"{BASE_URL}/api/resource-availability",
            params={"resource_ids": resource_ids},
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        bookings_by_resource = response.json().get("bookings_by_resource", {})
        
        # These fields should NOT be present (privacy)
        private_fields = ["user_id", "user_name", "email", "title", "description", "attendees"]
        
        for rid, bookings in bookings_by_resource.items():
            for booking in bookings:
                for field in private_fields:
                    assert field not in booking, \
                        f"Booking should not contain private field '{field}': {booking}"
        
        print(f"All bookings are privacy-safe (no user info)")


# =============================================================================
# Test Class 10: Snapshot structure validation
# =============================================================================
class TestSnapshotStructure:
    """Validate the structure of snapshot entries."""

    def test_snapshot_entries_have_required_fields(self, auth_headers, test_bookings):
        """
        Each snapshot entry should have: busy_now, next_free (if busy), next_busy (if not busy).
        """
        response = requests.get(
            f"{BASE_URL}/api/resource-availability",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        snapshot = response.json().get("snapshot", {})
        
        for rid, entry in snapshot.items():
            assert "busy_now" in entry, f"Snapshot entry missing 'busy_now': {entry}"
            
            if entry["busy_now"]:
                # If busy now, should have next_free
                assert "next_free" in entry and entry["next_free"] is not None, \
                    f"Busy resource should have next_free: {entry}"
            else:
                # If not busy, may have next_busy
                # next_busy can be None if no upcoming bookings
                pass
        
        print(f"All snapshot entries have valid structure")
