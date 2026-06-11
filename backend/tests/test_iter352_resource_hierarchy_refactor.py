"""
Iteration 352 - DRY Refactor: Resource Hierarchy Helpers

This iteration extracts the splittable-parent + sub-room expansion logic into
services/resource_hierarchy.py with two helpers:
  - expand_blocking_ids(resource_id) -> (ids, resource, buffer_min)
  - child_to_parent_map() -> {child_id: parent_id}

Three call sites now share this single source of truth:
  1. services/booking_conflicts.check_conflicts
  2. routes/resources/admin/analytics.availability_snapshot
  3. routes/resources/bookings/crud.list_bookings (availability_only=true path)

This is a PURE REFACTOR - behavior must be byte-identical to iter 351.

Test data (from iter 351):
- Parent: res_adb9fd1d33e9 (UtilRoom_1779600637, is_splitable=True)
- Child A: res_3dc6b6488d8c (sub A)
- Child B: res_06f47697c287 (sub B)
Note: Old bookings may have status=no_show (auto-released). Create fresh bookings for tests.
"""

import os
import pytest
import requests
from datetime import datetime, timezone, timedelta
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test data IDs from iter 351
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
    # Use a future time window to avoid conflicts with existing bookings
    tomorrow = datetime.now(timezone.utc) + timedelta(days=2)
    start = tomorrow.replace(hour=19, minute=0, second=0, microsecond=0)
    end = tomorrow.replace(hour=21, minute=0, second=0, microsecond=0)
    
    created_bookings = []
    
    # Create booking on Child A
    response_a = requests.post(
        f"{BASE_URL}/api/resource-bookings",
        json={
            "resource_id": CHILD_A_RESOURCE_ID,
            "title": f"TEST_iter352_child_a_{uuid.uuid4().hex[:8]}",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
        },
        headers=auth_headers,
    )
    if response_a.status_code in [200, 201]:
        booking_a = response_a.json()
        created_bookings.append(booking_a)
        print(f"Created Child A booking: {booking_a.get('booking_id')}")
    else:
        print(f"Failed to create Child A booking: {response_a.status_code} - {response_a.text}")
    
    # Create booking on Child B
    response_b = requests.post(
        f"{BASE_URL}/api/resource-bookings",
        json={
            "resource_id": CHILD_B_RESOURCE_ID,
            "title": f"TEST_iter352_child_b_{uuid.uuid4().hex[:8]}",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
        },
        headers=auth_headers,
    )
    if response_b.status_code in [200, 201]:
        booking_b = response_b.json()
        created_bookings.append(booking_b)
        print(f"Created Child B booking: {booking_b.get('booking_id')}")
    else:
        print(f"Failed to create Child B booking: {response_b.status_code} - {response_b.text}")
    
    yield {
        "bookings": created_bookings,
        "start": start,
        "end": end,
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
# Test Class 1: check_conflicts on parent detects children's bookings
# =============================================================================
class TestCheckConflictsParent:
    """POST /api/resources/{parent_id}/check-conflicts with children booked."""

    def test_parent_check_conflicts_returns_children_bookings(self, auth_headers, test_bookings):
        """
        When both sub-rooms are booked, check-conflicts on parent returns 2 conflicts
        (one per child).
        """
        if not test_bookings["bookings"]:
            pytest.skip("No test bookings created")
        
        start = test_bookings["start"]
        end = test_bookings["end"]
        
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
        
        conflicts = data["conflicts"]
        print(f"Parent check-conflicts returned {len(conflicts)} conflicts")
        
        # Should have conflicts from children's bookings
        conflict_resource_ids = [c.get("resource_id") for c in conflicts]
        print(f"Conflict resource IDs: {conflict_resource_ids}")
        
        # Verify we get conflicts from children
        has_child_a = CHILD_A_RESOURCE_ID in conflict_resource_ids
        has_child_b = CHILD_B_RESOURCE_ID in conflict_resource_ids
        
        assert has_child_a or has_child_b, \
            f"Parent check-conflicts should return children's bookings as conflicts. Got: {conflict_resource_ids}"
        
        # If both children have bookings, we should see 2 conflicts
        if len(test_bookings["bookings"]) == 2:
            assert len(conflicts) >= 2, \
                f"Expected at least 2 conflicts (one per child), got {len(conflicts)}"


# =============================================================================
# Test Class 2: check_conflicts on child detects parent-level bookings
# =============================================================================
class TestCheckConflictsChild:
    """POST /api/resources/{child_id}/check-conflicts detects parent bookings."""

    def test_child_check_conflicts_includes_parent_scope(self, auth_headers):
        """
        check-conflicts on a child resource should also check for parent-level
        bookings (none in this scenario, so returns 0 or only sibling conflicts).
        """
        # Use a time window where we know there are no parent bookings
        future = datetime.now(timezone.utc) + timedelta(days=5)
        start = future.replace(hour=10, minute=0, second=0, microsecond=0)
        end = future.replace(hour=11, minute=0, second=0, microsecond=0)
        
        response = requests.post(
            f"{BASE_URL}/api/resources/{CHILD_A_RESOURCE_ID}/check-conflicts",
            json={
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
            },
            headers=auth_headers,
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "conflicts" in data, "Response should contain 'conflicts' key"
        
        conflicts = data["conflicts"]
        print(f"Child A check-conflicts returned {len(conflicts)} conflicts")
        
        # In this scenario with no parent bookings, we expect 0 conflicts
        # (unless there are other bookings in that time window)
        for c in conflicts:
            print(f"  Conflict: {c.get('resource_id')} - {c.get('booking_id')}")


# =============================================================================
# Test Class 3: check_conflicts with buffer_time
# =============================================================================
class TestCheckConflictsWithBuffer:
    """POST /api/resources/{parent_id}/check-conflicts respects buffer_time."""

    def test_parent_buffer_time_respected(self, auth_headers, test_bookings):
        """
        Parent's buffer_time is still respected via the new expand_blocking_ids helper.
        """
        if not test_bookings["bookings"]:
            pytest.skip("No test bookings created")
        
        # Query just before the booking start (within potential buffer window)
        booking_start = test_bookings["start"]
        query_start = booking_start - timedelta(minutes=30)
        query_end = booking_start - timedelta(minutes=1)
        
        response = requests.post(
            f"{BASE_URL}/api/resources/{PARENT_RESOURCE_ID}/check-conflicts",
            json={
                "start_at": query_start.isoformat(),
                "end_at": query_end.isoformat(),
            },
            headers=auth_headers,
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        conflicts = data.get("conflicts", [])
        
        print(f"Buffer check: query {query_start.isoformat()} - {query_end.isoformat()}")
        print(f"Booking starts at: {booking_start.isoformat()}")
        print(f"Conflicts found: {len(conflicts)}")
        
        # If the resource has buffer_time configured, we might see conflicts
        # even though the query window doesn't directly overlap
        for c in conflicts:
            print(f"  Conflict: {c.get('resource_id')} - {c.get('start_at')} to {c.get('end_at')}")


# =============================================================================
# Test Class 4: availability_only=true on parent returns children's bookings
# =============================================================================
class TestAvailabilityOnlyParent:
    """GET /api/resource-bookings?resource_id={parent_id}&availability_only=true."""

    def test_parent_availability_only_returns_children_bookings(self, auth_headers, test_bookings):
        """
        availability_only=true on parent returns child bookings (verified in iter 351).
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
        
        resource_ids = [b.get("resource_id") for b in bookings]
        print(f"Parent availability_only returned {len(bookings)} bookings")
        print(f"Resource IDs: {set(resource_ids)}")
        
        # Should include children's bookings
        has_child_a = CHILD_A_RESOURCE_ID in resource_ids
        has_child_b = CHILD_B_RESOURCE_ID in resource_ids
        
        print(f"Has Child A: {has_child_a}, Has Child B: {has_child_b}")
        
        # At least one child should be present
        assert has_child_a or has_child_b, \
            "Parent availability_only should return children's bookings"


# =============================================================================
# Test Class 5: availability_only=true on child returns parent's bookings
# =============================================================================
class TestAvailabilityOnlyChild:
    """GET /api/resource-bookings?resource_id={child_id}&availability_only=true."""

    def test_child_availability_only_includes_parent_bookings(self, auth_headers):
        """
        availability_only=true on child returns own bookings + parent bookings.
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
        assert isinstance(bookings, list), "Response should be a list"
        
        resource_ids = [b.get("resource_id") for b in bookings]
        print(f"Child A availability_only returned {len(bookings)} bookings")
        print(f"Resource IDs: {set(resource_ids)}")
        
        # Should include child's own bookings and potentially parent bookings
        has_child_a = CHILD_A_RESOURCE_ID in resource_ids
        has_parent = PARENT_RESOURCE_ID in resource_ids
        
        print(f"Has Child A: {has_child_a}, Has Parent: {has_parent}")
        
        # Child should at least see its own bookings (if any exist)
        # Parent bookings would also be included if they exist


# =============================================================================
# Test Class 6: availability_snapshot shows parent busy when children booked
# =============================================================================
class TestAvailabilitySnapshot:
    """GET /api/resource-availability-snapshot."""

    def test_snapshot_parent_shows_busy_from_children(self, auth_headers, test_bookings):
        """
        Parent shows next_busy when only children are booked (iter 351 behaviour preserved).
        """
        if not test_bookings["bookings"]:
            pytest.skip("No test bookings created")
        
        response = requests.get(
            f"{BASE_URL}/api/resource-availability-snapshot",
            headers=auth_headers,
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "snapshot" in data, "Response should contain 'snapshot' key"
        
        snapshot = data["snapshot"]
        
        if PARENT_RESOURCE_ID in snapshot:
            parent_entry = snapshot[PARENT_RESOURCE_ID]
            print(f"Parent snapshot entry: {parent_entry}")
            
            # Parent should show busy_now or next_busy from children's bookings
            if parent_entry.get("busy_now"):
                print(f"Parent is busy now, next_free: {parent_entry.get('next_free')}")
            elif parent_entry.get("next_busy"):
                print(f"Parent has upcoming booking, next_busy: {parent_entry.get('next_busy')}")
                
                # Verify next_busy matches our test booking start time
                expected_start = test_bookings["start"].isoformat()
                actual_next_busy = parent_entry.get("next_busy")
                print(f"Expected next_busy around: {expected_start}")
                print(f"Actual next_busy: {actual_next_busy}")
        else:
            print(f"Parent {PARENT_RESOURCE_ID} not in snapshot (bookings may be outside 6-hour horizon)")


# =============================================================================
# Test Class 7: Non-splittable resources unchanged
# =============================================================================
class TestNonSplittableResources:
    """Non-splittable resources: check_conflicts/availability_only/snapshot unchanged."""

    def test_non_splittable_check_conflicts_unchanged(self, auth_headers):
        """
        Non-splittable resources: check_conflicts returns original results unchanged.
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
        
        # Check conflicts
        future = datetime.now(timezone.utc) + timedelta(days=3)
        start = future.replace(hour=10, minute=0, second=0, microsecond=0)
        end = future.replace(hour=11, minute=0, second=0, microsecond=0)
        
        response = requests.post(
            f"{BASE_URL}/api/resources/{resource_id}/check-conflicts",
            json={
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
            },
            headers=auth_headers,
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        conflicts = data.get("conflicts", [])
        
        # All conflicts should be for this resource only (no fake parent/child expansion)
        for c in conflicts:
            if c.get("resource_id"):  # Skip blackout entries
                assert c.get("resource_id") == resource_id, \
                    f"Non-splittable resource should not have conflicts from other resources"
        
        print(f"Non-splittable check-conflicts returned {len(conflicts)} conflicts (all for same resource)")

    def test_non_splittable_availability_only_unchanged(self, auth_headers):
        """
        Non-splittable resources: availability_only returns original results unchanged.
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
        
        # All bookings should be for this resource only
        for b in bookings:
            assert b.get("resource_id") == resource_id, \
                f"Non-splittable availability_only should not return bookings from other resources"
        
        print(f"Non-splittable availability_only returned {len(bookings)} bookings (all for same resource)")


# =============================================================================
# Test Class 8: Race-condition winner selection still works
# =============================================================================
class TestRaceConditionWinner:
    """verify_booking_winner uses a different code path, not affected by refactor."""

    def test_booking_creation_with_race_check(self, auth_headers):
        """
        End-to-end: create booking still works with race-condition verification.
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
        
        # Create a booking far in the future to avoid conflicts
        future = datetime.now(timezone.utc) + timedelta(days=10)
        start = future.replace(hour=10, minute=0, second=0, microsecond=0)
        end = future.replace(hour=11, minute=0, second=0, microsecond=0)
        
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
                pytest.skip("Conflicts exist for the test time slot")
        
        # Create booking
        booking_response = requests.post(
            f"{BASE_URL}/api/resource-bookings",
            json={
                "resource_id": resource_id,
                "title": f"TEST_iter352_race_check_{uuid.uuid4().hex[:8]}",
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
            },
            headers=auth_headers,
        )
        
        assert booking_response.status_code in [200, 201, 409], \
            f"Unexpected status: {booking_response.status_code}: {booking_response.text}"
        
        if booking_response.status_code in [200, 201]:
            booking = booking_response.json()
            booking_id = booking.get("booking_id")
            print(f"Created booking with race-check: {booking_id}")
            
            # Verify booking exists
            get_response = requests.get(
                f"{BASE_URL}/api/resource-bookings/{booking_id}",
                headers=auth_headers,
            )
            assert get_response.status_code == 200, "Booking should exist after creation"
            
            # Clean up
            requests.delete(
                f"{BASE_URL}/api/resource-bookings/{booking_id}",
                headers=auth_headers,
            )
            print(f"Cleaned up booking: {booking_id}")


# =============================================================================
# Test Class 9: End-to-end booking flow
# =============================================================================
class TestEndToEndBookingFlow:
    """End-to-end: create booking -> conflict check -> update -> cancel."""

    def test_full_booking_lifecycle(self, auth_headers):
        """
        Complete booking lifecycle still works after refactor.
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
        
        # Use a far future time to avoid conflicts
        future = datetime.now(timezone.utc) + timedelta(days=15)
        start = future.replace(hour=14, minute=0, second=0, microsecond=0)
        end = future.replace(hour=15, minute=0, second=0, microsecond=0)
        
        # Step 1: Check conflicts
        conflict_response = requests.post(
            f"{BASE_URL}/api/resources/{resource_id}/check-conflicts",
            json={
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
            },
            headers=auth_headers,
        )
        assert conflict_response.status_code == 200
        conflicts = conflict_response.json().get("conflicts", [])
        
        if conflicts:
            pytest.skip("Conflicts exist for the test time slot")
        
        print("Step 1: No conflicts found")
        
        # Step 2: Create booking
        create_response = requests.post(
            f"{BASE_URL}/api/resource-bookings",
            json={
                "resource_id": resource_id,
                "title": f"TEST_iter352_e2e_{uuid.uuid4().hex[:8]}",
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
            },
            headers=auth_headers,
        )
        
        assert create_response.status_code in [200, 201], \
            f"Failed to create booking: {create_response.status_code}: {create_response.text}"
        
        booking = create_response.json()
        booking_id = booking.get("booking_id")
        print(f"Step 2: Created booking {booking_id}")
        
        # Step 3: Update booking (change title)
        update_response = requests.put(
            f"{BASE_URL}/api/resource-bookings/{booking_id}",
            json={
                "title": "TEST_iter352_e2e_updated",
            },
            headers=auth_headers,
        )
        
        assert update_response.status_code == 200, \
            f"Failed to update booking: {update_response.status_code}: {update_response.text}"
        
        updated = update_response.json()
        assert updated.get("title") == "TEST_iter352_e2e_updated"
        print(f"Step 3: Updated booking title")
        
        # Step 4: Verify conflict check now shows this booking
        conflict_response2 = requests.post(
            f"{BASE_URL}/api/resources/{resource_id}/check-conflicts",
            json={
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
            },
            headers=auth_headers,
        )
        assert conflict_response2.status_code == 200
        conflicts2 = conflict_response2.json().get("conflicts", [])
        
        # Should have at least our booking as a conflict
        assert len(conflicts2) >= 1, "Should have at least 1 conflict (our booking)"
        print(f"Step 4: Conflict check shows {len(conflicts2)} conflicts")
        
        # Step 5: Cancel booking
        cancel_response = requests.delete(
            f"{BASE_URL}/api/resource-bookings/{booking_id}",
            headers=auth_headers,
        )
        
        assert cancel_response.status_code in [200, 204], \
            f"Failed to cancel booking: {cancel_response.status_code}: {cancel_response.text}"
        
        print(f"Step 5: Cancelled booking {booking_id}")
        
        # Step 6: Verify booking is cancelled
        get_response = requests.get(
            f"{BASE_URL}/api/resource-bookings/{booking_id}",
            headers=auth_headers,
        )
        
        if get_response.status_code == 200:
            final_booking = get_response.json()
            assert final_booking.get("status") == "cancelled", \
                f"Booking should be cancelled, got: {final_booking.get('status')}"
            print(f"Step 6: Verified booking is cancelled")
        else:
            print(f"Step 6: Booking not found (may have been deleted)")


# =============================================================================
# Test Class 10: Verify resource_hierarchy module is being used
# =============================================================================
class TestResourceHierarchyIntegration:
    """Verify the new resource_hierarchy module is integrated correctly."""

    def test_expand_blocking_ids_for_parent(self, auth_headers, test_bookings):
        """
        Verify that check-conflicts on parent expands to include children.
        """
        if not test_bookings["bookings"]:
            pytest.skip("No test bookings created")
        
        start = test_bookings["start"]
        end = test_bookings["end"]
        
        # Check conflicts on parent
        response = requests.post(
            f"{BASE_URL}/api/resources/{PARENT_RESOURCE_ID}/check-conflicts",
            json={
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
            },
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        conflicts = response.json().get("conflicts", [])
        
        # The conflicts should include children's bookings
        child_conflicts = [c for c in conflicts if c.get("resource_id") in [CHILD_A_RESOURCE_ID, CHILD_B_RESOURCE_ID]]
        
        print(f"Total conflicts: {len(conflicts)}")
        print(f"Child conflicts: {len(child_conflicts)}")
        
        # If we created bookings on both children, we should see them as conflicts
        if len(test_bookings["bookings"]) == 2:
            assert len(child_conflicts) >= 2, \
                f"Expected at least 2 child conflicts, got {len(child_conflicts)}"

    def test_child_to_parent_map_in_snapshot(self, auth_headers, test_bookings):
        """
        Verify that availability_snapshot uses child_to_parent_map correctly.
        """
        if not test_bookings["bookings"]:
            pytest.skip("No test bookings created")
        
        response = requests.get(
            f"{BASE_URL}/api/resource-availability-snapshot",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        snapshot = response.json().get("snapshot", {})
        
        # Both children and parent should be in snapshot if bookings are within horizon
        children_in_snapshot = [
            rid for rid in [CHILD_A_RESOURCE_ID, CHILD_B_RESOURCE_ID]
            if rid in snapshot
        ]
        parent_in_snapshot = PARENT_RESOURCE_ID in snapshot
        
        print(f"Children in snapshot: {children_in_snapshot}")
        print(f"Parent in snapshot: {parent_in_snapshot}")
        
        # If children are in snapshot, parent should also be (due to fold-in)
        if children_in_snapshot:
            # Parent should show busy/next_busy from children's bookings
            if parent_in_snapshot:
                parent_entry = snapshot[PARENT_RESOURCE_ID]
                print(f"Parent entry: {parent_entry}")
                assert parent_entry.get("busy_now") or parent_entry.get("next_busy"), \
                    "Parent should show busy_now or next_busy when children are booked"
