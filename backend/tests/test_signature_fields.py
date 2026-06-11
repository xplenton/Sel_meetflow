"""
Test suite for DocuSign-style Signature Fields feature
Tests: CRUD operations for signature fields, field status enrichment, sign with field_id
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSignatureFieldsCRUD:
    """Test signature fields CRUD operations"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session, create test meeting and document"""
        self.session = requests.Session()
        # Login
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.user = login_resp.json()
        
        # Create test meeting
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": f"TEST_SigFields_{uuid.uuid4().hex[:6]}",
            "meeting_type": "instant"
        })
        assert meeting_resp.status_code == 200, f"Meeting creation failed: {meeting_resp.text}"
        self.meeting = meeting_resp.json()
        self.meeting_id = self.meeting["meeting_id"]
        
        # Upload a test document (create a simple PNG)
        import io
        from PIL import Image
        img = Image.new('RGB', (800, 600), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        files = {'file': ('test_doc.png', img_bytes, 'image/png')}
        doc_resp = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents", files=files)
        assert doc_resp.status_code == 200, f"Document upload failed: {doc_resp.text}"
        self.doc = doc_resp.json()
        self.doc_id = self.doc["doc_id"]
        
        yield
        
        # Cleanup - delete meeting
        self.session.delete(f"{BASE_URL}/api/meetings/{self.meeting_id}")
    
    def test_create_signature_field(self):
        """POST /api/meetings/{id}/documents/{doc_id}/signature-fields - Create field"""
        field_data = {
            "x": 100,
            "y": 400,
            "page": 1,
            "label": "Unterschrift Auftragnehmer",
            "assigned_to": "",
            "assigned_name": ""
        }
        resp = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/signature-fields",
            json=field_data
        )
        assert resp.status_code == 200, f"Create field failed: {resp.text}"
        field = resp.json()
        
        # Verify field structure
        assert "field_id" in field, "field_id missing"
        assert field["field_id"].startswith("sf_"), f"field_id format wrong: {field['field_id']}"
        assert field["x"] == 100, f"x mismatch: {field['x']}"
        assert field["y"] == 400, f"y mismatch: {field['y']}"
        assert field["page"] == 1, f"page mismatch: {field['page']}"
        assert field["label"] == "Unterschrift Auftragnehmer", f"label mismatch: {field['label']}"
        assert field["status"] == "pending", f"status should be pending: {field['status']}"
        print(f"✓ Created signature field: {field['field_id']}")
    
    def test_create_field_with_assignment(self):
        """Create field assigned to specific participant"""
        field_data = {
            "x": 200,
            "y": 500,
            "page": 1,
            "label": "Unterschrift Kunde",
            "assigned_to": self.user["user_id"],
            "assigned_name": self.user["name"]
        }
        resp = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/signature-fields",
            json=field_data
        )
        assert resp.status_code == 200, f"Create assigned field failed: {resp.text}"
        field = resp.json()
        
        assert field["assigned_to"] == self.user["user_id"], "assigned_to mismatch"
        assert field["assigned_name"] == self.user["name"], "assigned_name mismatch"
        print(f"✓ Created assigned signature field: {field['field_id']} -> {field['assigned_name']}")
    
    def test_get_signature_fields_empty(self):
        """GET /api/meetings/{id}/documents/{doc_id}/signature-fields - Returns empty initially"""
        resp = self.session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/signature-fields"
        )
        assert resp.status_code == 200, f"Get fields failed: {resp.text}"
        data = resp.json()
        
        assert "fields" in data, "fields key missing"
        assert "total" in data, "total key missing"
        assert "signed" in data, "signed key missing"
        assert data["total"] == 0, f"Expected 0 total, got {data['total']}"
        assert data["signed"] == 0, f"Expected 0 signed, got {data['signed']}"
        print(f"✓ Get fields returns correct structure: {data}")
    
    def test_get_signature_fields_with_data(self):
        """GET returns fields with total/signed count"""
        # Create 2 fields
        for i in range(2):
            self.session.post(
                f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/signature-fields",
                json={"x": 100 + i*100, "y": 400, "page": 1, "label": f"Field {i+1}"}
            )
        
        resp = self.session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/signature-fields"
        )
        assert resp.status_code == 200
        data = resp.json()
        
        assert data["total"] == 2, f"Expected 2 total, got {data['total']}"
        assert data["signed"] == 0, f"Expected 0 signed, got {data['signed']}"
        assert len(data["fields"]) == 2, f"Expected 2 fields, got {len(data['fields'])}"
        print(f"✓ Get fields returns correct counts: total={data['total']}, signed={data['signed']}")
    
    def test_delete_signature_field(self):
        """DELETE /api/meetings/{id}/documents/{doc_id}/signature-fields/{field_id}"""
        # Create a field first
        create_resp = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/signature-fields",
            json={"x": 100, "y": 400, "page": 1, "label": "To Delete"}
        )
        field = create_resp.json()
        field_id = field["field_id"]
        
        # Delete it
        del_resp = self.session.delete(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/signature-fields/{field_id}"
        )
        assert del_resp.status_code == 200, f"Delete failed: {del_resp.text}"
        assert del_resp.json()["deleted"] == field_id
        
        # Verify it's gone
        get_resp = self.session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/signature-fields"
        )
        data = get_resp.json()
        field_ids = [f["field_id"] for f in data["fields"]]
        assert field_id not in field_ids, f"Field {field_id} still exists after delete"
        print(f"✓ Deleted signature field: {field_id}")
    
    def test_sign_with_field_id(self):
        """Sign endpoint accepts field_id parameter and marks field as signed"""
        # Create a field
        create_resp = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/signature-fields",
            json={"x": 150, "y": 450, "page": 1, "label": "Sign Here"}
        )
        field = create_resp.json()
        field_id = field["field_id"]
        
        # Sign with field_id
        sign_resp = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/sign",
            json={
                "type": "typed",
                "signature_data": "Test Signer",
                "pos_x": 150,
                "pos_y": 450,
                "page": 1,
                "field_id": field_id
            }
        )
        assert sign_resp.status_code == 200, f"Sign failed: {sign_resp.text}"
        
        # Verify field is now marked as signed
        get_resp = self.session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/signature-fields"
        )
        data = get_resp.json()
        
        signed_field = next((f for f in data["fields"] if f["field_id"] == field_id), None)
        assert signed_field is not None, f"Field {field_id} not found"
        assert signed_field["status"] == "signed", f"Field status should be 'signed', got: {signed_field['status']}"
        assert "signed_by" in signed_field, "signed_by missing"
        assert data["signed"] == 1, f"Expected 1 signed, got {data['signed']}"
        print(f"✓ Field {field_id} marked as signed by {signed_field.get('signed_by')}")
    
    def test_field_enrichment_with_signature_status(self):
        """Fields are enriched with 'signed' status when matching signature has field_id"""
        # Create 2 fields
        field1_resp = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/signature-fields",
            json={"x": 100, "y": 400, "page": 1, "label": "Field 1"}
        )
        field1_id = field1_resp.json()["field_id"]
        
        field2_resp = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/signature-fields",
            json={"x": 300, "y": 400, "page": 1, "label": "Field 2"}
        )
        field2_id = field2_resp.json()["field_id"]
        
        # Sign only field 1
        self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/sign",
            json={
                "type": "typed",
                "signature_data": "Signer Name",
                "pos_x": 100,
                "pos_y": 400,
                "page": 1,
                "field_id": field1_id
            }
        )
        
        # Get fields and verify enrichment
        get_resp = self.session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/signature-fields"
        )
        data = get_resp.json()
        
        f1 = next((f for f in data["fields"] if f["field_id"] == field1_id), None)
        f2 = next((f for f in data["fields"] if f["field_id"] == field2_id), None)
        
        assert f1["status"] == "signed", f"Field 1 should be signed: {f1['status']}"
        assert f2["status"] == "pending", f"Field 2 should be pending: {f2['status']}"
        assert data["total"] == 2
        assert data["signed"] == 1
        print("✓ Field enrichment correct: Field1=signed, Field2=pending, total=2, signed=1")
    
    def test_requires_auth(self):
        """Signature fields endpoints require authentication"""
        no_auth_session = requests.Session()
        
        # Test create
        resp = no_auth_session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/signature-fields",
            json={"x": 100, "y": 400, "page": 1, "label": "Test"}
        )
        assert resp.status_code == 401, f"Create should require auth, got {resp.status_code}"
        
        # Test get
        resp = no_auth_session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/signature-fields"
        )
        assert resp.status_code == 401, f"Get should require auth, got {resp.status_code}"
        
        # Test delete
        resp = no_auth_session.delete(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/signature-fields/sf_test"
        )
        assert resp.status_code == 401, f"Delete should require auth, got {resp.status_code}"
        
        print("✓ All signature fields endpoints require authentication")


class TestSignatureFieldsWithExistingData:
    """Test with the provided test data: meet_52fc559f2c, doc_c97e549714"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and use existing test data"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        
        self.meeting_id = "meet_52fc559f2c"
        self.doc_id = "doc_c97e549714"
        yield
    
    def test_existing_test_data_fields(self):
        """Verify test data has expected fields: sf_2262e600 signed, sf_bff96249 pending"""
        resp = self.session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/signature-fields"
        )
        
        if resp.status_code == 404:
            pytest.skip("Test data not found - may have been cleaned up")
        
        assert resp.status_code == 200, f"Get fields failed: {resp.text}"
        data = resp.json()
        
        print(f"Test data fields: total={data['total']}, signed={data['signed']}")
        print(f"Fields: {[f['field_id'] + ':' + f['status'] for f in data['fields']]}")
        
        # Check if expected fields exist
        field_ids = {f["field_id"]: f["status"] for f in data["fields"]}
        
        if "sf_2262e600" in field_ids:
            assert field_ids["sf_2262e600"] == "signed", "sf_2262e600 should be signed"
            print("✓ sf_2262e600 is signed")
        
        if "sf_bff96249" in field_ids:
            assert field_ids["sf_bff96249"] == "pending", "sf_bff96249 should be pending"
            print("✓ sf_bff96249 is pending")
        
        # Verify progress calculation
        if data["total"] > 0:
            assert data["signed"] <= data["total"], "signed should not exceed total"
            print(f"✓ Progress: {data['signed']}/{data['total']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
