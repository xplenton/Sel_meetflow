"""
Test PUT /api/meetings/{id}/documents/{doc_id}/signature-fields/{field_id}
Tests drag-resize feature for signature fields on documents.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test data from review request
TEST_MEETING_ID = "meet_52fc559f2c"
TEST_DOC_ID = "doc_c97e549714"
SIGNED_FIELD_ID = "sf_2262e600"  # Already signed
PENDING_FIELD_ID = "sf_bff96249"  # Pending, can be updated

@pytest.fixture(scope="module")
def session():
    """Create authenticated session"""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    # Login
    resp = s.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@meetflow.com",
        "password": "admin123"
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return s


class TestSignatureFieldUpdateEndpoint:
    """Tests for PUT /api/meetings/{id}/documents/{doc_id}/signature-fields/{field_id}"""
    
    def test_update_field_position_x_y(self, session):
        """Test updating field position (x, y) - drag move"""
        # Get current field state
        resp = session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields")
        assert resp.status_code == 200
        fields = resp.json().get("fields", [])
        pending_field = next((f for f in fields if f["field_id"] == PENDING_FIELD_ID), None)
        assert pending_field is not None, "Pending field not found"
        
        original_x = pending_field["x"]
        original_y = pending_field["y"]
        
        # Update position
        new_x = original_x + 50
        new_y = original_y + 30
        resp = session.put(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields/{PENDING_FIELD_ID}",
            json={"x": new_x, "y": new_y}
        )
        assert resp.status_code == 200, f"PUT failed: {resp.text}"
        assert resp.json().get("updated") == PENDING_FIELD_ID
        
        # Verify persistence via GET
        resp = session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields")
        assert resp.status_code == 200
        fields = resp.json().get("fields", [])
        updated_field = next((f for f in fields if f["field_id"] == PENDING_FIELD_ID), None)
        assert updated_field["x"] == new_x, f"X not updated: expected {new_x}, got {updated_field['x']}"
        assert updated_field["y"] == new_y, f"Y not updated: expected {new_y}, got {updated_field['y']}"
        
        # Restore original position
        session.put(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields/{PENDING_FIELD_ID}",
            json={"x": original_x, "y": original_y}
        )
        print("PASSED: Update field position (x, y)")
    
    def test_update_field_dimensions_width_height(self, session):
        """Test updating field dimensions (width, height) - drag resize"""
        # Get current field state
        resp = session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields")
        assert resp.status_code == 200
        fields = resp.json().get("fields", [])
        pending_field = next((f for f in fields if f["field_id"] == PENDING_FIELD_ID), None)
        assert pending_field is not None
        
        original_width = pending_field.get("width", 200)
        original_height = pending_field.get("height", 60)
        
        # Update dimensions
        new_width = 300
        new_height = 100
        resp = session.put(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields/{PENDING_FIELD_ID}",
            json={"width": new_width, "height": new_height}
        )
        assert resp.status_code == 200, f"PUT failed: {resp.text}"
        
        # Verify persistence via GET
        resp = session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields")
        assert resp.status_code == 200
        fields = resp.json().get("fields", [])
        updated_field = next((f for f in fields if f["field_id"] == PENDING_FIELD_ID), None)
        assert updated_field["width"] == new_width, f"Width not updated: expected {new_width}, got {updated_field['width']}"
        assert updated_field["height"] == new_height, f"Height not updated: expected {new_height}, got {updated_field['height']}"
        
        # Restore original dimensions
        session.put(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields/{PENDING_FIELD_ID}",
            json={"width": original_width, "height": original_height}
        )
        print("PASSED: Update field dimensions (width, height)")
    
    def test_update_field_page(self, session):
        """Test updating field page number"""
        resp = session.put(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields/{PENDING_FIELD_ID}",
            json={"page": 2}
        )
        assert resp.status_code == 200
        
        # Verify
        resp = session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields")
        fields = resp.json().get("fields", [])
        updated_field = next((f for f in fields if f["field_id"] == PENDING_FIELD_ID), None)
        assert updated_field["page"] == 2
        
        # Restore
        session.put(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields/{PENDING_FIELD_ID}",
            json={"page": 1}
        )
        print("PASSED: Update field page")
    
    def test_update_field_label(self, session):
        """Test updating field label"""
        new_label = "TEST_Updated_Label"
        resp = session.put(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields/{PENDING_FIELD_ID}",
            json={"label": new_label}
        )
        assert resp.status_code == 200
        
        # Verify
        resp = session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields")
        fields = resp.json().get("fields", [])
        updated_field = next((f for f in fields if f["field_id"] == PENDING_FIELD_ID), None)
        assert updated_field["label"] == new_label
        
        # Restore
        session.put(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields/{PENDING_FIELD_ID}",
            json={"label": "Unterschrift Zeuge"}
        )
        print("PASSED: Update field label")
    
    def test_update_field_assigned_to(self, session):
        """Test updating assigned_to and assigned_name"""
        resp = session.put(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields/{PENDING_FIELD_ID}",
            json={"assigned_to": "user_test123", "assigned_name": "Test User"}
        )
        assert resp.status_code == 200
        
        # Verify
        resp = session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields")
        fields = resp.json().get("fields", [])
        updated_field = next((f for f in fields if f["field_id"] == PENDING_FIELD_ID), None)
        assert updated_field["assigned_to"] == "user_test123"
        assert updated_field["assigned_name"] == "Test User"
        
        # Restore
        session.put(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields/{PENDING_FIELD_ID}",
            json={"assigned_to": "", "assigned_name": ""}
        )
        print("PASSED: Update field assigned_to and assigned_name")
    
    def test_update_requires_authentication(self):
        """Test that PUT requires authentication"""
        # Create unauthenticated session
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        
        resp = s.put(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields/{PENDING_FIELD_ID}",
            json={"x": 100}
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASSED: PUT requires authentication")
    
    def test_update_combined_position_and_size(self, session):
        """Test updating both position and size in single request (real drag-resize scenario)"""
        # Get current state
        resp = session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields")
        fields = resp.json().get("fields", [])
        pending_field = next((f for f in fields if f["field_id"] == PENDING_FIELD_ID), None)
        
        original = {
            "x": pending_field["x"],
            "y": pending_field["y"],
            "width": pending_field.get("width", 200),
            "height": pending_field.get("height", 60)
        }
        
        # Update all at once
        new_values = {"x": 500, "y": 600, "width": 280, "height": 90}
        resp = session.put(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields/{PENDING_FIELD_ID}",
            json=new_values
        )
        assert resp.status_code == 200
        
        # Verify all values
        resp = session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields")
        fields = resp.json().get("fields", [])
        updated_field = next((f for f in fields if f["field_id"] == PENDING_FIELD_ID), None)
        
        assert updated_field["x"] == new_values["x"]
        assert updated_field["y"] == new_values["y"]
        assert updated_field["width"] == new_values["width"]
        assert updated_field["height"] == new_values["height"]
        
        # Restore
        session.put(
            f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/signature-fields/{PENDING_FIELD_ID}",
            json=original
        )
        print("PASSED: Combined position and size update")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
