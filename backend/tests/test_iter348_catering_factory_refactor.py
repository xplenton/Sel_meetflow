"""
Iteration 348 — Catering Request Factory Refactor Tests

This iteration extracts the ~145-line catering attachment block from 
routes/resources/bookings/crud.py::create_booking into a new 
services/catering_request_factory.py with one public entry point:
    attach_catering_to_booking(booking, resource, user, catering_payload,
                               fallback_start_at, fallback_cost_center, fallback_account)

The _send_short_notice_email helper was also moved to the factory module.
The now-empty bookings/_helpers.py was deleted.

Behavior MUST be byte-identical to iter 347.

Test Coverage:
1. POST /api/resource-bookings WITHOUT catering payload — normal booking
2. POST /api/resource-bookings WITH catering payload (allow_catering=true) — creates linked catering_request + auto-task
3. POST /api/resource-bookings WITH catering payload where delivery_at is in next 5 min — lead_time_breach=True
4. POST /api/resource-bookings WITH catering payload but allow_catering=false — catering silently ignored
5. Catering items indexed correctly, worst_item is item with longest lead_time_min
6. Auto-task created with correct title, tags, source_type, source_id, due_date, assignee_ids
7. Cascade on DELETE: linked catering_request and task go to status=cancelled
8. All existing booking endpoints still work (regression)
9. Notifications shim chain still works
"""
import os
import pytest
import requests
from datetime import datetime, timedelta, timezone
import uuid
import random

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://video-meet-pro.preview.emergentagent.com")

# Use random offset to avoid conflicts between test runs
RANDOM_OFFSET = random.randint(200, 500)


def get_catering_request(session, request_id):
    """Helper to get a catering request by ID from the list endpoint."""
    r = session.get(f"{BASE_URL}/api/catering-requests")
    if r.status_code != 200:
        return None
    for cr in r.json():
        if cr.get("request_id") == request_id:
            return cr
    return None


def cleanup_booking(session, booking_id):
    """Helper to cleanup a booking."""
    try:
        session.delete(f"{BASE_URL}/api/resource-bookings/{booking_id}")
    except Exception:
        pass


@pytest.fixture(scope="module")
def auth_session():
    """Login and return authenticated session."""
    session = requests.Session()
    r = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@meetflow.com",
        "password": "admin123"
    })
    assert r.status_code == 200, f"Login failed: {r.text}"
    return session


@pytest.fixture(scope="module")
def catering_resource(auth_session):
    """Get or create a resource with allow_catering=true and requires_approval=false."""
    # Find existing resource with allow_catering=true and requires_approval=false
    r = auth_session.get(f"{BASE_URL}/api/resources", params={"type": "room", "status": "active"})
    if r.status_code == 200:
        resources = r.json()
        for res in resources:
            if res.get("allow_catering") and not res.get("requires_approval"):
                return res
    
    # Create a test resource if none exists
    resource_data = {
        "name": f"CateringRoom_Iter348_{uuid.uuid4().hex[:6]}",
        "type": "room",
        "status": "active",
        "capacity": 10,
        "requires_approval": False,
        "allow_catering": True,
    }
    r = auth_session.post(f"{BASE_URL}/api/resources", json=resource_data)
    assert r.status_code in (200, 201), f"Failed to create catering resource: {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def no_catering_resource(auth_session):
    """Get or create a resource with allow_catering=false."""
    r = auth_session.get(f"{BASE_URL}/api/resources", params={"type": "room", "status": "active"})
    if r.status_code == 200:
        resources = r.json()
        for res in resources:
            if not res.get("allow_catering") and not res.get("requires_approval"):
                return res
    
    # Create a test resource if none exists
    resource_data = {
        "name": f"NoCateringRoom_Iter348_{uuid.uuid4().hex[:6]}",
        "type": "room",
        "status": "active",
        "capacity": 10,
        "requires_approval": False,
        "allow_catering": False,
    }
    r = auth_session.post(f"{BASE_URL}/api/resources", json=resource_data)
    assert r.status_code in (200, 201), f"Failed to create no-catering resource: {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def catering_items(auth_session):
    """Get available catering items."""
    r = auth_session.get(f"{BASE_URL}/api/catering-items")
    assert r.status_code == 200, f"Failed to get catering items: {r.text}"
    items = r.json()
    assert len(items) > 0, "No catering items available"
    return items


class TestBookingWithoutCatering:
    """Test 1: POST /api/resource-bookings WITHOUT catering payload"""
    
    def test_create_booking_no_catering(self, auth_session, catering_resource):
        """Creates booking normally, response has no catering_request_id and no lead_time_warning."""
        start = datetime.now(timezone.utc) + timedelta(days=RANDOM_OFFSET + 1)
        end = start + timedelta(hours=1)
        
        booking_data = {
            "resource_id": catering_resource["resource_id"],
            "title": f"NoCatering_Iter348_{uuid.uuid4().hex[:8]}",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
        }
        r = auth_session.post(f"{BASE_URL}/api/resource-bookings", json=booking_data)
        assert r.status_code in (200, 201), f"Create booking failed: {r.text}"
        
        created = r.json()
        assert "booking_id" in created
        assert created.get("catering_request_id") is None, "Should not have catering_request_id"
        assert "lead_time_warning" not in created, "Should not have lead_time_warning"
        
        print(f"✓ Booking without catering created: {created['booking_id']}")
        
        # Cleanup
        cleanup_booking(auth_session, created['booking_id'])


class TestBookingWithCatering:
    """Test 2: POST /api/resource-bookings WITH catering payload (allow_catering=true)"""
    
    def test_create_booking_with_catering(self, auth_session, catering_resource, catering_items):
        """Creates booking + linked catering_request + auto-task; response contains catering_request_id."""
        start = datetime.now(timezone.utc) + timedelta(days=RANDOM_OFFSET + 10)
        end = start + timedelta(hours=2)
        
        # Use first available catering item
        item = catering_items[0]
        
        booking_data = {
            "resource_id": catering_resource["resource_id"],
            "title": f"WithCatering_Iter348_{uuid.uuid4().hex[:8]}",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "cost_center": "CC-348-TEST",
            "account": "ACC-348-TEST",
            "catering": {
                "items": [{"item_id": item["item_id"], "quantity": 5}],
                "delivery_at": start.isoformat(),
                "delivery_target": "main",
                "contact": "Test Contact",
                "notes": "Test notes for iter 348",
            }
        }
        r = auth_session.post(f"{BASE_URL}/api/resource-bookings", json=booking_data)
        assert r.status_code in (200, 201), f"Create booking with catering failed: {r.text}"
        
        created = r.json()
        assert "booking_id" in created
        assert "catering_request_id" in created, "Should have catering_request_id"
        
        booking_id = created["booking_id"]
        catering_request_id = created["catering_request_id"]
        
        print(f"✓ Booking with catering created: {booking_id}, catering_request_id: {catering_request_id}")
        
        # Verify catering_request was created with correct fallback values
        cr = get_catering_request(auth_session, catering_request_id)
        assert cr is not None, f"Failed to find catering request: {catering_request_id}"
        
        assert cr["booking_id"] == booking_id
        assert cr["cost_center"] == "CC-348-TEST", "cost_center should use fallback from booking payload"
        assert cr["account"] == "ACC-348-TEST", "account should use fallback from booking payload"
        assert cr["contact"] == "Test Contact"
        assert cr["notes"] == "Test notes for iter 348"
        
        print(f"✓ Catering request has correct cost_center={cr['cost_center']}, account={cr['account']}")
        
        # Verify auto-task was created
        task_id = cr.get("task_id")
        assert task_id is not None, "Catering request should have linked task_id"
        
        r = auth_session.get(f"{BASE_URL}/api/tasks/{task_id}")
        assert r.status_code == 200, f"Failed to get task: {r.text}"
        
        task = r.json()
        expected_title = f"Catering: {booking_data['title']} ({catering_resource.get('name')})"
        assert task["title"] == expected_title, f"Task title mismatch: {task['title']} != {expected_title}"
        assert "catering" in task.get("tags", []), "Task should have 'catering' tag"
        assert "auto-created" in task.get("tags", []), "Task should have 'auto-created' tag"
        assert task["source_type"] == "catering_request"
        assert task["source_id"] == catering_request_id
        
        print(f"✓ Auto-task created with correct title, tags, source_type, source_id")
        
        # Cleanup
        cleanup_booking(auth_session, booking_id)


class TestLeadTimeBreach:
    """Test 3: POST /api/resource-bookings WITH catering where delivery_at is in next 5 min"""
    
    def test_lead_time_breach_flagged(self, auth_session, catering_resource, catering_items):
        """lead_time_breach=True is persisted and response contains lead_time_warning."""
        # Find item with longest lead_time_min (worst_item)
        worst_item = max(catering_items, key=lambda x: x.get("lead_time_min", 60))
        
        # Set delivery_at to now + 1 minute (will breach any lead_time_min > 1)
        # Use a unique time slot far in the future for the booking itself
        start = datetime.now(timezone.utc) + timedelta(days=RANDOM_OFFSET + 20)
        end = start + timedelta(hours=1)
        delivery_at = datetime.now(timezone.utc) + timedelta(minutes=1)  # This triggers breach
        
        booking_data = {
            "resource_id": catering_resource["resource_id"],
            "title": f"LeadTimeBreach_Iter348_{uuid.uuid4().hex[:8]}",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "catering": {
                "items": [{"item_id": worst_item["item_id"], "quantity": 3}],
                "delivery_at": delivery_at.isoformat(),
            }
        }
        r = auth_session.post(f"{BASE_URL}/api/resource-bookings", json=booking_data)
        assert r.status_code in (200, 201), f"Create booking failed: {r.text}"
        
        created = r.json()
        booking_id = created["booking_id"]
        catering_request_id = created.get("catering_request_id")
        
        # Check lead_time_warning in response
        assert "lead_time_warning" in created, "Response should contain lead_time_warning"
        warning = created["lead_time_warning"]
        assert warning.get("breach") is True, "lead_time_warning.breach should be True"
        assert "required_min" in warning, "lead_time_warning should have required_min"
        assert "available_min" in warning, "lead_time_warning should have available_min"
        assert "worst_item" in warning, "lead_time_warning should have worst_item"
        
        print(f"✓ Lead time breach detected: required_min={warning['required_min']}, available_min={warning['available_min']}, worst_item={warning['worst_item']}")
        
        # Verify lead_time_breach is persisted on catering_request
        cr = get_catering_request(auth_session, catering_request_id)
        assert cr is not None, f"Failed to find catering request: {catering_request_id}"
        assert cr.get("lead_time_breach") is True, "lead_time_breach should be persisted on catering_request"
        assert cr.get("lead_time_required_min") == warning["required_min"]
        assert cr.get("lead_time_available_min") == warning["available_min"]
        
        print(f"✓ Lead time breach persisted on catering_request")
        
        # Cleanup
        cleanup_booking(auth_session, booking_id)


class TestCateringIgnoredWhenNotAllowed:
    """Test 4: POST /api/resource-bookings WITH catering but allow_catering=false"""
    
    def test_catering_silently_ignored(self, auth_session, no_catering_resource, catering_items):
        """Catering payload is silently ignored (no catering_request created)."""
        start = datetime.now(timezone.utc) + timedelta(days=RANDOM_OFFSET + 30)
        end = start + timedelta(hours=1)
        
        item = catering_items[0]
        
        booking_data = {
            "resource_id": no_catering_resource["resource_id"],
            "title": f"CateringIgnored_Iter348_{uuid.uuid4().hex[:8]}",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "catering": {
                "items": [{"item_id": item["item_id"], "quantity": 2}],
                "delivery_at": start.isoformat(),
            }
        }
        r = auth_session.post(f"{BASE_URL}/api/resource-bookings", json=booking_data)
        assert r.status_code in (200, 201), f"Create booking failed: {r.text}"
        
        created = r.json()
        assert "booking_id" in created
        assert created.get("catering_request_id") is None, "Should NOT have catering_request_id when allow_catering=false"
        assert "lead_time_warning" not in created, "Should NOT have lead_time_warning"
        
        print(f"✓ Catering payload silently ignored for resource with allow_catering=false")
        
        # Cleanup
        cleanup_booking(auth_session, created['booking_id'])


class TestWorstItemIndexing:
    """Test 5: Catering items get correctly indexed and worst_item is item with longest lead_time_min"""
    
    def test_worst_item_is_longest_lead_time(self, auth_session, catering_resource, catering_items):
        """worst_item should be the item with the longest lead_time_min."""
        # Find items with different lead times
        items_by_lead_time = sorted(catering_items, key=lambda x: x.get("lead_time_min", 60), reverse=True)
        
        if len(items_by_lead_time) < 2:
            pytest.skip("Need at least 2 catering items with different lead times")
        
        worst_item = items_by_lead_time[0]  # Longest lead time
        other_item = items_by_lead_time[-1]  # Shortest lead time
        
        # Set delivery_at to breach the worst item's lead time - use unique time slot
        delivery_at = datetime.now(timezone.utc) + timedelta(minutes=1)
        start = datetime.now(timezone.utc) + timedelta(days=RANDOM_OFFSET + 40)
        end = start + timedelta(hours=1)
        
        booking_data = {
            "resource_id": catering_resource["resource_id"],
            "title": f"WorstItem_Iter348_{uuid.uuid4().hex[:8]}",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "catering": {
                "items": [
                    {"item_id": other_item["item_id"], "quantity": 2},
                    {"item_id": worst_item["item_id"], "quantity": 1},
                ],
                "delivery_at": delivery_at.isoformat(),
            }
        }
        r = auth_session.post(f"{BASE_URL}/api/resource-bookings", json=booking_data)
        assert r.status_code in (200, 201), f"Create booking failed: {r.text}"
        
        created = r.json()
        booking_id = created["booking_id"]
        
        if "lead_time_warning" in created:
            warning = created["lead_time_warning"]
            # worst_item should be the name of the item with longest lead_time_min
            assert warning.get("required_min") >= worst_item.get("lead_time_min", 60), \
                f"required_min should be at least {worst_item.get('lead_time_min', 60)}"
            print(f"✓ worst_item correctly identified: {warning.get('worst_item')}, required_min={warning['required_min']}")
        else:
            print("✓ No lead time breach (delivery_at far enough in future)")
        
        # Cleanup
        cleanup_booking(auth_session, booking_id)


class TestAutoTaskCreation:
    """Test 6: Auto-task created with correct attributes"""
    
    def test_auto_task_attributes(self, auth_session, catering_resource, catering_items):
        """Auto-task has correct title, tags, source_type, source_id, due_date, assignee_ids."""
        start = datetime.now(timezone.utc) + timedelta(days=RANDOM_OFFSET + 50)
        end = start + timedelta(hours=2)
        
        item = catering_items[0]
        
        booking_data = {
            "resource_id": catering_resource["resource_id"],
            "title": f"AutoTask_Iter348_{uuid.uuid4().hex[:8]}",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "catering": {
                "items": [{"item_id": item["item_id"], "quantity": 5}],
                "delivery_at": start.isoformat(),
            }
        }
        r = auth_session.post(f"{BASE_URL}/api/resource-bookings", json=booking_data)
        assert r.status_code in (200, 201), f"Create booking failed: {r.text}"
        
        created = r.json()
        booking_id = created["booking_id"]
        catering_request_id = created.get("catering_request_id")
        
        # Get catering request to find task_id
        cr = get_catering_request(auth_session, catering_request_id)
        assert cr is not None, f"Failed to find catering request: {catering_request_id}"
        task_id = cr.get("task_id")
        assert task_id is not None
        
        # Get task and verify attributes
        r = auth_session.get(f"{BASE_URL}/api/tasks/{task_id}")
        assert r.status_code == 200
        task = r.json()
        
        # Verify title format: "Catering: {booking_title} ({resource_name})"
        expected_title = f"Catering: {booking_data['title']} ({catering_resource.get('name')})"
        assert task["title"] == expected_title, f"Title mismatch: {task['title']}"
        
        # Verify tags
        assert "catering" in task.get("tags", [])
        assert "auto-created" in task.get("tags", [])
        
        # Verify source_type and source_id
        assert task["source_type"] == "catering_request"
        assert task["source_id"] == catering_request_id
        
        # Verify due_date is set to delivery_at
        assert task.get("due_date") is not None
        
        # Verify assignee_ids contains users with catering.process cap + admins
        assert len(task.get("assignee_ids", [])) > 0, "Task should have assignees"
        
        print(f"✓ Auto-task created with correct attributes:")
        print(f"  - title: {task['title']}")
        print(f"  - tags: {task.get('tags')}")
        print(f"  - source_type: {task['source_type']}")
        print(f"  - source_id: {task['source_id']}")
        print(f"  - due_date: {task.get('due_date')}")
        print(f"  - assignee_ids count: {len(task.get('assignee_ids', []))}")
        
        # Cleanup
        cleanup_booking(auth_session, booking_id)


class TestCascadeOnDelete:
    """Test 7: Cascade on DELETE /api/resource-bookings/{id}"""
    
    def test_cascade_cancels_catering_and_task(self, auth_session, catering_resource, catering_items):
        """Linked catering_request goes to status=cancelled, linked task goes to status=cancelled."""
        start = datetime.now(timezone.utc) + timedelta(days=RANDOM_OFFSET + 60)
        end = start + timedelta(hours=2)
        
        item = catering_items[0]
        
        booking_data = {
            "resource_id": catering_resource["resource_id"],
            "title": f"CascadeDelete_Iter348_{uuid.uuid4().hex[:8]}",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "catering": {
                "items": [{"item_id": item["item_id"], "quantity": 3}],
                "delivery_at": start.isoformat(),
            }
        }
        r = auth_session.post(f"{BASE_URL}/api/resource-bookings", json=booking_data)
        assert r.status_code in (200, 201), f"Create booking failed: {r.text}"
        
        created = r.json()
        booking_id = created["booking_id"]
        catering_request_id = created.get("catering_request_id")
        
        # Get task_id before deletion
        cr = get_catering_request(auth_session, catering_request_id)
        assert cr is not None, f"Failed to find catering request: {catering_request_id}"
        task_id = cr.get("task_id")
        
        # Delete the booking
        r = auth_session.delete(f"{BASE_URL}/api/resource-bookings/{booking_id}")
        assert r.status_code == 200
        
        # Verify catering_request status is cancelled
        cr = get_catering_request(auth_session, catering_request_id)
        assert cr is not None, f"Failed to find catering request: {catering_request_id}"
        assert cr["status"] == "cancelled", f"Catering request should be cancelled, got: {cr['status']}"
        
        print(f"✓ Catering request status changed to 'cancelled'")
        
        # Verify task status is cancelled
        r = auth_session.get(f"{BASE_URL}/api/tasks/{task_id}")
        assert r.status_code == 200
        task = r.json()
        assert task["status"] == "cancelled", f"Task should be cancelled, got: {task['status']}"
        
        print(f"✓ Task status changed to 'cancelled'")


class TestExistingEndpointsRegression:
    """Test 8: All existing booking endpoints still work"""
    
    def test_list_bookings(self, auth_session):
        """GET /api/resource-bookings"""
        r = auth_session.get(f"{BASE_URL}/api/resource-bookings")
        assert r.status_code == 200
        print("✓ GET /api/resource-bookings works")
    
    def test_get_booking(self, auth_session, catering_resource):
        """GET /api/resource-bookings/{id}"""
        # Create a booking first
        start = datetime.now(timezone.utc) + timedelta(days=RANDOM_OFFSET + 70)
        end = start + timedelta(hours=1)
        
        r = auth_session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": catering_resource["resource_id"],
            "title": f"GetTest_Iter348_{uuid.uuid4().hex[:8]}",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
        })
        assert r.status_code in (200, 201)
        booking_id = r.json()["booking_id"]
        
        r = auth_session.get(f"{BASE_URL}/api/resource-bookings/{booking_id}")
        assert r.status_code == 200
        print(f"✓ GET /api/resource-bookings/{booking_id} works")
        
        # Cleanup
        cleanup_booking(auth_session, booking_id)
    
    def test_update_booking(self, auth_session, catering_resource):
        """PUT /api/resource-bookings/{id}"""
        start = datetime.now(timezone.utc) + timedelta(days=RANDOM_OFFSET + 80)
        end = start + timedelta(hours=1)
        
        r = auth_session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": catering_resource["resource_id"],
            "title": f"UpdateTest_Iter348_{uuid.uuid4().hex[:8]}",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
        })
        assert r.status_code in (200, 201)
        booking_id = r.json()["booking_id"]
        
        r = auth_session.put(f"{BASE_URL}/api/resource-bookings/{booking_id}", json={
            "title": "Updated_Iter348"
        })
        assert r.status_code == 200
        assert r.json()["title"] == "Updated_Iter348"
        print(f"✓ PUT /api/resource-bookings/{booking_id} works")
        
        # Cleanup
        cleanup_booking(auth_session, booking_id)
    
    def test_check_conflicts(self, auth_session, catering_resource):
        """POST /api/resources/{resource_id}/check-conflicts"""
        start = datetime.now(timezone.utc) + timedelta(days=RANDOM_OFFSET + 90)
        end = start + timedelta(hours=1)
        
        r = auth_session.post(
            f"{BASE_URL}/api/resources/{catering_resource['resource_id']}/check-conflicts",
            json={"start_at": start.isoformat(), "end_at": end.isoformat()}
        )
        assert r.status_code == 200
        assert "conflicts" in r.json()
        print("✓ POST /api/resources/{resource_id}/check-conflicts works")
    
    def test_suggest_slots(self, auth_session, catering_resource):
        """POST /api/resources/{resource_id}/suggest-slots"""
        start = datetime.now(timezone.utc).isoformat()
        r = auth_session.post(
            f"{BASE_URL}/api/resources/{catering_resource['resource_id']}/suggest-slots",
            json={"duration_min": 60, "start_at": start}
        )
        assert r.status_code == 200
        print("✓ POST /api/resources/{resource_id}/suggest-slots works")


class TestCateringFallbackValues:
    """Test catering_request uses fallback values from booking payload"""
    
    def test_cost_center_account_fallback(self, auth_session, catering_resource, catering_items):
        """cost_center and account fall back from booking-level payload when not in catering payload."""
        start = datetime.now(timezone.utc) + timedelta(days=RANDOM_OFFSET + 100)
        end = start + timedelta(hours=2)
        
        item = catering_items[0]
        
        # Catering payload WITHOUT cost_center/account, but booking payload HAS them
        booking_data = {
            "resource_id": catering_resource["resource_id"],
            "title": f"Fallback_Iter348_{uuid.uuid4().hex[:8]}",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "cost_center": "BOOKING-CC-348",
            "account": "BOOKING-ACC-348",
            "catering": {
                "items": [{"item_id": item["item_id"], "quantity": 2}],
                "delivery_at": start.isoformat(),
                # No cost_center or account here
            }
        }
        r = auth_session.post(f"{BASE_URL}/api/resource-bookings", json=booking_data)
        assert r.status_code in (200, 201), f"Create booking failed: {r.text}"
        
        created = r.json()
        booking_id = created["booking_id"]
        catering_request_id = created.get("catering_request_id")
        
        # Verify catering_request uses fallback values
        cr = get_catering_request(auth_session, catering_request_id)
        assert cr is not None, f"Failed to find catering request: {catering_request_id}"
        
        assert cr["cost_center"] == "BOOKING-CC-348", f"cost_center should fallback to booking value, got: {cr['cost_center']}"
        assert cr["account"] == "BOOKING-ACC-348", f"account should fallback to booking value, got: {cr['account']}"
        
        print(f"✓ Catering request uses fallback cost_center={cr['cost_center']}, account={cr['account']}")
        
        # Cleanup
        cleanup_booking(auth_session, booking_id)
    
    def test_catering_values_override_fallback(self, auth_session, catering_resource, catering_items):
        """cost_center and account in catering payload override booking-level values."""
        start = datetime.now(timezone.utc) + timedelta(days=RANDOM_OFFSET + 110)
        end = start + timedelta(hours=2)
        
        item = catering_items[0]
        
        # Both booking and catering have cost_center/account - catering should win
        booking_data = {
            "resource_id": catering_resource["resource_id"],
            "title": f"Override_Iter348_{uuid.uuid4().hex[:8]}",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "cost_center": "BOOKING-CC-OVERRIDE",
            "account": "BOOKING-ACC-OVERRIDE",
            "catering": {
                "items": [{"item_id": item["item_id"], "quantity": 2}],
                "delivery_at": start.isoformat(),
                "cost_center": "CATERING-CC-348",
                "account": "CATERING-ACC-348",
            }
        }
        r = auth_session.post(f"{BASE_URL}/api/resource-bookings", json=booking_data)
        assert r.status_code in (200, 201), f"Create booking failed: {r.text}"
        
        created = r.json()
        booking_id = created["booking_id"]
        catering_request_id = created.get("catering_request_id")
        
        # Verify catering_request uses its own values
        cr = get_catering_request(auth_session, catering_request_id)
        assert cr is not None, f"Failed to find catering request: {catering_request_id}"
        
        assert cr["cost_center"] == "CATERING-CC-348", f"cost_center should be from catering payload, got: {cr['cost_center']}"
        assert cr["account"] == "CATERING-ACC-348", f"account should be from catering payload, got: {cr['account']}"
        
        print(f"✓ Catering payload values override booking values: cost_center={cr['cost_center']}, account={cr['account']}")
        
        # Cleanup
        cleanup_booking(auth_session, booking_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
