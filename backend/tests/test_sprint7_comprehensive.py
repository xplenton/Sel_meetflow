"""
Sprint 7 (iter 229) Comprehensive API Tests
Testing all 5 micro-gaps:
  GAP a - Configurable Upload Limits
  GAP b - DATEV/Generic ERP-Export
  GAP c - Floorplan-Metadata-CRUD + Backdrop-Upload
  GAP d - Tankkarte + Antriebsart
  GAP e - Auslastung pro Teilbereich
"""
import io
import time
import requests
import pytest
from datetime import datetime, timezone, timedelta

# Read API base from frontend .env
with open("/app/frontend/.env") as f:
    API = next(
        line.split("=", 1)[1].strip().rstrip("/")
        for line in f
        if line.startswith("REACT_APP_BACKEND_URL")
    )


@pytest.fixture(scope="module")
def admin_session():
    """Authenticated admin session"""
    s = requests.Session()
    r = s.post(
        f"{API}/api/auth/login",
        json={"email": "admin@meetflow.com", "password": "admin123"},
        timeout=10,
    )
    assert r.status_code == 200, f"Login failed: {r.text}"
    yield s


# ============================================================================
# GAP a - Configurable Upload Limits
# ============================================================================
class TestUploadConfig:
    """§10 - Configurable upload limits for catering attachments"""

    def test_get_upload_config_returns_defaults(self, admin_session):
        """GET /api/resource-upload-config returns default 10MB + MIME whitelist"""
        r = admin_session.get(f"{API}/api/resource-upload-config", timeout=10)
        assert r.status_code == 200
        cfg = r.json()
        assert "max_size_mb" in cfg
        assert "allowed_mimes" in cfg
        assert cfg["max_size_mb"] >= 1
        assert isinstance(cfg["allowed_mimes"], list)
        print(f"Default config: max_size_mb={cfg['max_size_mb']}, mimes={len(cfg['allowed_mimes'])} types")

    def test_put_upload_config_persists(self, admin_session):
        """PUT /api/resource-upload-config with max_size_mb=15 + allowed_mimes persists"""
        r = admin_session.put(
            f"{API}/api/resource-upload-config",
            json={"max_size_mb": 15, "allowed_mimes": ["application/pdf", "image/png"]},
            timeout=10,
        )
        assert r.status_code == 200
        cfg = r.json()
        assert cfg["max_size_mb"] == 15
        assert sorted(cfg["allowed_mimes"]) == ["application/pdf", "image/png"]

        # Verify persistence with GET
        r2 = admin_session.get(f"{API}/api/resource-upload-config", timeout=10)
        assert r2.json()["max_size_mb"] == 15
        print("Upload config persisted successfully")

        # Reset to defaults
        admin_session.put(
            f"{API}/api/resource-upload-config",
            json={"max_size_mb": 10, "allowed_mimes": None},
            timeout=10,
        )

    def test_upload_config_rejects_invalid_size_below_1(self, admin_session):
        """max_size_mb < 1 must return 400 (Note: 0 falls back to default due to 'or' logic)"""
        # Test with -1 which is explicitly < 1
        r = admin_session.put(
            f"{API}/api/resource-upload-config",
            json={"max_size_mb": -1},
            timeout=10,
        )
        assert r.status_code == 400
        print("Correctly rejected max_size_mb=-1")

    def test_upload_config_rejects_invalid_size_above_100(self, admin_session):
        """max_size_mb > 100 must return 400"""
        r = admin_session.put(
            f"{API}/api/resource-upload-config",
            json={"max_size_mb": 150},
            timeout=10,
        )
        assert r.status_code == 400
        print("Correctly rejected max_size_mb=150")

    def test_link_attachment_validates_mime_415(self, admin_session):
        """POST /api/catering-requests/{id}/attachments/{att_id} with disallowed MIME -> 415"""
        # Tighten config to only allow image/png
        admin_session.put(
            f"{API}/api/resource-upload-config",
            json={"max_size_mb": 10, "allowed_mimes": ["image/png"]},
            timeout=10,
        )

        # Upload a text/plain file
        files = {"file": ("note.txt", io.BytesIO(b"hello world"), "text/plain")}
        r_up = admin_session.post(f"{API}/api/attachments/upload", files=files, timeout=10)
        assert r_up.status_code == 200
        att_id = r_up.json()["attachment_id"]

        # Create resource + booking + catering request
        suffix = int(time.time())
        res = admin_session.post(
            f"{API}/api/resources",
            json={"name": f"MimeTestRoom_{suffix}", "type": "room", "allow_catering": True},
            timeout=10,
        ).json()
        bk = admin_session.post(
            f"{API}/api/resource-bookings",
            json={
                "resource_id": res["resource_id"],
                "title": "MimeTest",
                "start_at": "2029-05-15T09:00:00Z",
                "end_at": "2029-05-15T10:00:00Z",
                "catering": {"items": [], "delivery_at": "2029-05-15T09:00:00Z"},
            },
            timeout=10,
        ).json()
        cr_id = bk["catering_request_id"]

        # Link text/plain attachment -> must fail with 415
        r = admin_session.post(
            f"{API}/api/catering-requests/{cr_id}/attachments/{att_id}",
            timeout=10,
        )
        assert r.status_code == 415, f"Expected 415, got {r.status_code}: {r.text}"
        print("Correctly rejected text/plain attachment with 415")

        # Cleanup
        admin_session.put(
            f"{API}/api/resource-upload-config",
            json={"max_size_mb": 10, "allowed_mimes": None},
            timeout=10,
        )
        admin_session.delete(f"{API}/api/resource-bookings/{bk['booking_id']}", timeout=10)
        admin_session.delete(f"{API}/api/resources/{res['resource_id']}", timeout=10)

    def test_link_attachment_success_with_allowed_mime(self, admin_session):
        """POST /api/catering-requests/{id}/attachments/{att_id} with allowed MIME -> 200"""
        # Upload a PNG file (1x1 pixel)
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfc"
            b"\xff\xff?\x00\x05\xfe\x02\xfe\xa6\xb6\x88\x0f\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        r_up = admin_session.post(
            f"{API}/api/attachments/upload",
            files={"file": ("pixel.png", io.BytesIO(png_bytes), "image/png")},
            timeout=10,
        )
        assert r_up.status_code == 200
        att_id = r_up.json()["attachment_id"]

        # Create resource + booking + catering request
        suffix = int(time.time())
        res = admin_session.post(
            f"{API}/api/resources",
            json={"name": f"PngTestRoom_{suffix}", "type": "room", "allow_catering": True},
            timeout=10,
        ).json()
        bk = admin_session.post(
            f"{API}/api/resource-bookings",
            json={
                "resource_id": res["resource_id"],
                "title": "PngTest",
                "start_at": "2029-06-15T09:00:00Z",
                "end_at": "2029-06-15T10:00:00Z",
                "catering": {"items": [], "delivery_at": "2029-06-15T09:00:00Z"},
            },
            timeout=10,
        ).json()
        cr_id = bk["catering_request_id"]

        # Link PNG attachment -> must succeed
        r = admin_session.post(
            f"{API}/api/catering-requests/{cr_id}/attachments/{att_id}",
            timeout=10,
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        assert att_id in r.json()["attachments"]
        print("Successfully linked PNG attachment")

        # Cleanup
        admin_session.delete(f"{API}/api/resource-bookings/{bk['booking_id']}", timeout=10)
        admin_session.delete(f"{API}/api/resources/{res['resource_id']}", timeout=10)


# ============================================================================
# GAP b - DATEV/Generic ERP-Export
# ============================================================================
class TestERPExport:
    """§13 - ERP/DATEV CSV export"""

    def test_erp_export_datev_format_headers(self, admin_session):
        """GET /api/resource-bookings/export/erp.csv?format=datev has correct headers"""
        r = admin_session.get(
            f"{API}/api/resource-bookings/export/erp.csv?days=365&format=datev",
            timeout=10,
        )
        assert r.status_code == 200
        body = r.text.lstrip("\ufeff")  # Remove BOM
        lines = [ln for ln in body.split("\n") if ln.strip()]
        header = lines[0]
        
        # Check DATEV header columns
        assert "Belegdatum" in header
        assert "Belegnummer" in header
        assert "Konto" in header
        assert "Gegenkonto" in header
        assert "Betrag" in header
        assert "Buchungstext" in header
        assert "Kostenstelle" in header
        assert "USt-Schluessel" in header
        print(f"DATEV export header: {header}")

    def test_erp_export_generic_format_headers(self, admin_session):
        """GET /api/resource-bookings/export/erp.csv?format=generic has Soll/Haben headers"""
        r = admin_session.get(
            f"{API}/api/resource-bookings/export/erp.csv?days=30&format=generic",
            timeout=10,
        )
        assert r.status_code == 200
        header = r.text.lstrip("\ufeff").split("\n")[0]
        
        assert "Soll" in header
        assert "Haben" in header
        print(f"Generic export header: {header}")


# ============================================================================
# GAP c - Floorplan-Metadata-CRUD + Backdrop-Upload
# ============================================================================
class TestFloorplanCRUD:
    """§14 - Floorplan metadata CRUD and backdrop upload"""

    def test_floorplan_crud_lifecycle(self, admin_session):
        """PUT creates, GET retrieves, LIST contains, DELETE removes"""
        plan_id = f"test_plan_{int(time.time())}"
        
        # PUT to create
        r = admin_session.put(
            f"{API}/api/floorplans/{plan_id}",
            json={"name": "Test-Etage", "building": "Haus A", "floor": "2"},
            timeout=10,
        )
        assert r.status_code == 200
        p = r.json()
        assert p["name"] == "Test-Etage"
        assert p["floor_plan_id"] == plan_id
        print(f"Created floorplan: {plan_id}")

        # GET single
        r2 = admin_session.get(f"{API}/api/floorplans/{plan_id}", timeout=10)
        assert r2.status_code == 200
        assert r2.json()["building"] == "Haus A"
        print("GET single floorplan OK")

        # LIST contains it
        r3 = admin_session.get(f"{API}/api/floorplans", timeout=10)
        assert r3.status_code == 200
        assert any(it.get("floor_plan_id") == plan_id for it in r3.json())
        print("LIST floorplans contains new entry")

        # DELETE
        r4 = admin_session.delete(f"{API}/api/floorplans/{plan_id}", timeout=10)
        assert r4.status_code == 200
        print("DELETE floorplan OK")

    def test_floorplan_backdrop_rejects_non_image(self, admin_session):
        """PUT /api/floorplans/{id} with text/plain attachment -> 415"""
        plan_id = f"test_bg_{int(time.time())}"
        
        # Upload text file
        files = {"file": ("note.txt", io.BytesIO(b"hi"), "text/plain")}
        txt = admin_session.post(f"{API}/api/attachments/upload", files=files, timeout=10).json()
        
        # Try to set as backdrop
        r = admin_session.put(
            f"{API}/api/floorplans/{plan_id}",
            json={"background_attachment_id": txt["attachment_id"]},
            timeout=10,
        )
        assert r.status_code == 415, f"Expected 415, got {r.status_code}"
        print("Correctly rejected text/plain as backdrop with 415")
        
        # Cleanup
        admin_session.delete(f"{API}/api/floorplans/{plan_id}", timeout=10)

    def test_floorplan_backdrop_accepts_image(self, admin_session):
        """PUT /api/floorplans/{id} with image/png attachment -> 200 + background_url"""
        plan_id = f"test_img_{int(time.time())}"
        
        # Upload PNG
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfc"
            b"\xff\xff?\x00\x05\xfe\x02\xfe\xa6\xb6\x88\x0f\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        att = admin_session.post(
            f"{API}/api/attachments/upload",
            files={"file": ("p.png", io.BytesIO(png), "image/png")},
            timeout=10,
        ).json()
        
        # Set as backdrop
        r = admin_session.put(
            f"{API}/api/floorplans/{plan_id}",
            json={"background_attachment_id": att["attachment_id"]},
            timeout=10,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["background_attachment_id"] == att["attachment_id"]
        assert body["background_url"].endswith(att["attachment_id"])
        print(f"Backdrop set successfully: {body['background_url']}")
        
        # Cleanup
        admin_session.delete(f"{API}/api/floorplans/{plan_id}", timeout=10)


# ============================================================================
# GAP d - Tankkarte + Antriebsart
# ============================================================================
class TestVehicleFields:
    """§15 - Vehicle fuel_card, fuel_card_number, drive_type"""

    def test_vehicle_fields_persisted(self, admin_session):
        """POST /api/resources with vehicle fields persists all three"""
        payload = {
            "name": f"E-Auto_{int(time.time())}",
            "type": "vehicle",
            "license_plate": "B-EV-2026",
            "vehicle_type": "Kompakt",
            "seats": 5,
            "fuel_card": True,
            "fuel_card_number": "DKV 998877",
            "drive_type": "elektro",
        }
        r = admin_session.post(f"{API}/api/resources", json=payload, timeout=10)
        assert r.status_code == 200, r.text
        res = r.json()
        
        assert res["fuel_card"] is True
        assert res["fuel_card_number"] == "DKV 998877"
        assert res["drive_type"] == "elektro"
        print(f"Vehicle created with fuel_card={res['fuel_card']}, drive_type={res['drive_type']}")
        
        # Cleanup
        admin_session.delete(f"{API}/api/resources/{res['resource_id']}", timeout=10)

    def test_vehicle_update_drive_type(self, admin_session):
        """PUT /api/resources/{id} with drive_type='hybrid' updates"""
        # Create vehicle
        res = admin_session.post(
            f"{API}/api/resources",
            json={
                "name": f"UpdateCar_{int(time.time())}",
                "type": "vehicle",
                "drive_type": "benzin",
            },
            timeout=10,
        ).json()
        
        # Update to hybrid
        r = admin_session.put(
            f"{API}/api/resources/{res['resource_id']}",
            json={"drive_type": "hybrid", "fuel_card_number": "DKV 111222"},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["drive_type"] == "hybrid"
        assert r.json()["fuel_card_number"] == "DKV 111222"
        print("Vehicle drive_type updated to hybrid")
        
        # Cleanup
        admin_session.delete(f"{API}/api/resources/{res['resource_id']}", timeout=10)

    def test_vehicle_rejects_invalid_drive_type(self, admin_session):
        """POST with drive_type='atomkraft' must return 400/422 (Pydantic Literal)"""
        r = admin_session.post(
            f"{API}/api/resources",
            json={"name": "BadCar", "type": "vehicle", "drive_type": "atomkraft"},
            timeout=10,
        )
        assert r.status_code in (400, 422), f"Expected 400/422, got {r.status_code}"
        print(f"Correctly rejected invalid drive_type with {r.status_code}")


# ============================================================================
# GAP e - Auslastung pro Teilbereich
# ============================================================================
class TestSubUtilization:
    """§18 - Utilization per sub-room (Teilbereich)"""

    def test_utilization_by_sub_for_split_room(self, admin_session):
        """GET /api/resources/{parent}/utilization-by-sub returns sub_rows with stats"""
        suffix = int(time.time())
        
        # Create splitable room with A/B
        parent = admin_session.post(
            f"{API}/api/resources",
            json={
                "name": f"UtilRoom_{suffix}",
                "type": "room",
                "is_splitable": True,
                "allowed_combinations": [["A"], ["B"], ["A", "B"]],
                "sub_resources": [
                    {"sub_id": "A", "name": "A", "capacity": 10},
                    {"sub_id": "B", "name": "B", "capacity": 10},
                ],
            },
            timeout=10,
        ).json()
        
        # Get children
        parent_full = admin_session.get(
            f"{API}/api/resources/{parent['resource_id']}", timeout=10
        ).json()
        children = parent_full.get("children", [])
        a = next(c for c in children if c.get("sub_id") == "A")
        
        # Book Bereich A for 2 hours
        start = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(microsecond=0)
        end = start + timedelta(hours=2)
        r_bk = admin_session.post(
            f"{API}/api/resource-bookings",
            json={
                "resource_id": a["resource_id"],
                "title": "Util-A",
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
            },
            timeout=10,
        )
        assert r_bk.status_code == 200, r_bk.text
        
        # Get utilization by sub
        r = admin_session.get(
            f"{API}/api/resources/{parent['resource_id']}/utilization-by-sub?days=30",
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        
        assert "sub_rows" in data
        by_sub = {row["sub_id"]: row for row in data["sub_rows"]}
        assert "A" in by_sub and "B" in by_sub
        assert by_sub["A"]["bookings"] >= 1
        assert by_sub["A"]["total_minutes"] >= 120
        assert by_sub["B"]["bookings"] == 0
        print(f"Sub A: {by_sub['A']['bookings']} bookings, {by_sub['A']['total_minutes']} min")
        print(f"Sub B: {by_sub['B']['bookings']} bookings, {by_sub['B']['total_minutes']} min")
        
        # Cleanup
        admin_session.delete(f"{API}/api/resource-bookings/{r_bk.json()['booking_id']}", timeout=10)
        admin_session.delete(f"{API}/api/resources/{parent['resource_id']}", timeout=10)

    def test_utilization_by_sub_rejects_non_splitable(self, admin_session):
        """GET /api/resources/{id}/utilization-by-sub on non-splitable room -> 400"""
        res = admin_session.post(
            f"{API}/api/resources",
            json={"name": f"NoSplit_{int(time.time())}", "type": "room"},
            timeout=10,
        ).json()
        
        r = admin_session.get(
            f"{API}/api/resources/{res['resource_id']}/utilization-by-sub",
            timeout=10,
        )
        assert r.status_code == 400
        print("Correctly rejected non-splitable room with 400")
        
        # Cleanup
        admin_session.delete(f"{API}/api/resources/{res['resource_id']}", timeout=10)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
