"""
Sprint 7 (iter 229) — final 5 micro-gaps for the 19-point resource spec:
  §10 — configurable upload limits (size + MIME whitelist)
  §13 — ERP/DATEV CSV export
  §14 — Floorplan metadata + backdrop upload
  §15 — Vehicle Tankkarte + Antriebsart
  §18 — Utilization per Teilbereich (sub-room aware)
"""
import io
import time
import requests
import pytest


with open("/app/frontend/.env") as f:
    API = next(
        line.split("=", 1)[1].strip().rstrip("/")
        for line in f
        if line.startswith("REACT_APP_BACKEND_URL")
    )


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(
        f"{API}/api/auth/login",
        json={"email": "admin@meetflow.com", "password": "admin123"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    yield s


# ------------------ §10 Upload-Limits ----------------------------------------
def test_upload_config_default(admin_session):
    r = admin_session.get(f"{API}/api/resource-upload-config", timeout=10)
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["max_size_mb"] >= 1
    assert "application/pdf" in cfg["allowed_mimes"]


def test_upload_config_update_and_persist(admin_session):
    r = admin_session.put(
        f"{API}/api/resource-upload-config",
        json={"max_size_mb": 7, "allowed_mimes": ["application/pdf", "image/png"]},
        timeout=10,
    )
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["max_size_mb"] == 7
    assert sorted(cfg["allowed_mimes"]) == ["application/pdf", "image/png"]
    # Read-back
    r2 = admin_session.get(f"{API}/api/resource-upload-config", timeout=10)
    assert r2.json()["max_size_mb"] == 7
    # Reset
    admin_session.put(
        f"{API}/api/resource-upload-config",
        json={"max_size_mb": 10, "allowed_mimes": None},
        timeout=10,
    )


def test_upload_config_rejects_invalid_size(admin_session):
    r = admin_session.put(
        f"{API}/api/resource-upload-config",
        json={"max_size_mb": 999},
        timeout=10,
    )
    assert r.status_code == 400


def test_link_catering_attachment_validates_mime(admin_session):
    """Linking an attachment with disallowed MIME must 415."""
    # 1) tighten the config to only allow image/png
    admin_session.put(
        f"{API}/api/resource-upload-config",
        json={"max_size_mb": 10, "allowed_mimes": ["image/png"]},
        timeout=10,
    )
    # 2) Upload a TXT file via the generic attachments endpoint
    files = {"file": ("note.txt", io.BytesIO(b"hello"), "text/plain")}
    r_up = admin_session.post(f"{API}/api/attachments/upload", files=files, timeout=10)
    assert r_up.status_code == 200, r_up.text
    att_id = r_up.json()["attachment_id"]

    # 3) Create a tiny resource + booking + catering request to link against
    suffix = int(time.time())
    res = admin_session.post(
        f"{API}/api/resources",
        json={"name": f"AttRoom_{suffix}", "type": "room", "allow_catering": True},
        timeout=10,
    ).json()
    bk = admin_session.post(
        f"{API}/api/resource-bookings",
        json={
            "resource_id": res["resource_id"],
            "title": "Cat-Link",
            "start_at": "2029-03-15T09:00:00Z",
            "end_at": "2029-03-15T10:00:00Z",
            "catering": {"items": [], "delivery_at": "2029-03-15T09:00:00Z"},
        },
        timeout=10,
    ).json()
    cr_id = bk["catering_request_id"]

    # 4) Linking text/plain attachment must fail with 415
    r = admin_session.post(
        f"{API}/api/catering-requests/{cr_id}/attachments/{att_id}",
        timeout=10,
    )
    assert r.status_code == 415, r.text

    # 5) Restore default config + clean up
    admin_session.put(
        f"{API}/api/resource-upload-config",
        json={"max_size_mb": 10, "allowed_mimes": None},
        timeout=10,
    )
    admin_session.delete(f"{API}/api/resource-bookings/{bk['booking_id']}", timeout=10)
    admin_session.delete(f"{API}/api/resources/{res['resource_id']}", timeout=10)


def test_link_catering_attachment_success(admin_session):
    """Image PNG within size limit must succeed and append to attachments list."""
    # tiny 1x1 PNG
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
    assert r_up.status_code == 200, r_up.text
    att_id = r_up.json()["attachment_id"]

    suffix = int(time.time())
    res = admin_session.post(
        f"{API}/api/resources",
        json={"name": f"AttRoom2_{suffix}", "type": "room", "allow_catering": True},
        timeout=10,
    ).json()
    bk = admin_session.post(
        f"{API}/api/resource-bookings",
        json={
            "resource_id": res["resource_id"],
            "title": "Cat-Link2",
            "start_at": "2029-04-15T09:00:00Z",
            "end_at": "2029-04-15T10:00:00Z",
            "catering": {"items": [], "delivery_at": "2029-04-15T09:00:00Z"},
        },
        timeout=10,
    ).json()
    cr_id = bk["catering_request_id"]

    r = admin_session.post(
        f"{API}/api/catering-requests/{cr_id}/attachments/{att_id}",
        timeout=10,
    )
    assert r.status_code == 200, r.text
    assert att_id in r.json()["attachments"]


# ------------------ §13 ERP-Export -------------------------------------------
def test_erp_export_csv_datev_format(admin_session):
    r = admin_session.get(
        f"{API}/api/resource-bookings/export/erp.csv?days=365&format=datev",
        timeout=10,
    )
    assert r.status_code == 200
    body = r.text
    # First line = DATEV header
    lines = [ln for ln in body.split("\n") if ln.strip()]
    header = lines[0].lstrip("\ufeff")
    assert header.startswith("Belegdatum;Belegnummer;Konto;Gegenkonto;Betrag")
    assert "USt-Schluessel" in header


def test_erp_export_csv_generic_format(admin_session):
    r = admin_session.get(
        f"{API}/api/resource-bookings/export/erp.csv?days=30&format=generic",
        timeout=10,
    )
    assert r.status_code == 200
    header = r.text.lstrip("\ufeff").split("\n")[0]
    assert "Soll" in header and "Haben" in header


# ------------------ §14 Floorplan metadata + backdrop ------------------------
def test_floorplan_metadata_crud(admin_session):
    plan_id = f"plan_{int(time.time())}"
    # PUT name only
    r = admin_session.put(
        f"{API}/api/floorplans/{plan_id}",
        json={"name": "Test-Etage", "building": "Haus A", "floor": "2"},
        timeout=10,
    )
    assert r.status_code == 200
    p = r.json()
    assert p["name"] == "Test-Etage"
    assert p["floor_plan_id"] == plan_id

    # GET single
    r2 = admin_session.get(f"{API}/api/floorplans/{plan_id}", timeout=10)
    assert r2.status_code == 200
    assert r2.json()["building"] == "Haus A"

    # LIST contains it
    r3 = admin_session.get(f"{API}/api/floorplans", timeout=10)
    assert any(it.get("floor_plan_id") == plan_id for it in r3.json())

    # DELETE
    admin_session.delete(f"{API}/api/floorplans/{plan_id}", timeout=10)


def test_floorplan_backdrop_requires_image_mime(admin_session):
    plan_id = f"plan_bg_{int(time.time())}"
    # Upload a TXT file
    files = {"file": ("note.txt", io.BytesIO(b"hi"), "text/plain")}
    txt = admin_session.post(f"{API}/api/attachments/upload", files=files, timeout=10).json()
    r = admin_session.put(
        f"{API}/api/floorplans/{plan_id}",
        json={"background_attachment_id": txt["attachment_id"]},
        timeout=10,
    )
    assert r.status_code == 415
    admin_session.delete(f"{API}/api/floorplans/{plan_id}", timeout=10)


def test_floorplan_backdrop_image_ok(admin_session):
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
    plan_id = f"plan_img_{int(time.time())}"
    r = admin_session.put(
        f"{API}/api/floorplans/{plan_id}",
        json={"background_attachment_id": att["attachment_id"]},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["background_attachment_id"] == att["attachment_id"]
    assert body["background_url"].endswith(att["attachment_id"])
    admin_session.delete(f"{API}/api/floorplans/{plan_id}", timeout=10)


# ------------------ §15 Vehicle Tankkarte + Antriebsart ----------------------
def test_vehicle_fields_persisted(admin_session):
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

    # PUT updates
    r2 = admin_session.put(
        f"{API}/api/resources/{res['resource_id']}",
        json={"drive_type": "hybrid", "fuel_card_number": "DKV 111222"},
        timeout=10,
    )
    assert r2.status_code == 200
    assert r2.json()["drive_type"] == "hybrid"
    assert r2.json()["fuel_card_number"] == "DKV 111222"
    admin_session.delete(f"{API}/api/resources/{res['resource_id']}", timeout=10)


def test_vehicle_rejects_invalid_drive_type(admin_session):
    r = admin_session.post(
        f"{API}/api/resources",
        json={"name": "Bad", "type": "vehicle", "drive_type": "atomkraft"},
        timeout=10,
    )
    assert r.status_code in (400, 422)


# ------------------ §18 Utilization per Teilbereich --------------------------
def test_utilization_by_sub_for_split_room(admin_session):
    # Build splitable room with A/B
    suffix = int(time.time())
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

    # Resolve child ids (parent's GET returns `children` for splitable rooms)
    parent_full = admin_session.get(
        f"{API}/api/resources/{parent['resource_id']}", timeout=10
    ).json()
    children = parent_full.get("children", [])
    a = next(c for c in children if c.get("sub_id") == "A")
    # Book Bereich A for 2 hours (today + 2 days to be in window)
    from datetime import datetime, timezone, timedelta
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

    r = admin_session.get(
        f"{API}/api/resources/{parent['resource_id']}/utilization-by-sub?days=30",
        timeout=10,
    )
    assert r.status_code == 200
    data = r.json()
    by_sub = {row["sub_id"]: row for row in data["sub_rows"]}
    assert "A" in by_sub and "B" in by_sub
    assert by_sub["A"]["bookings"] >= 1
    assert by_sub["A"]["total_minutes"] >= 120
    # B got nothing fresh
    assert by_sub["B"]["bookings"] == 0

    admin_session.delete(f"{API}/api/resource-bookings/{r_bk.json()['booking_id']}", timeout=10)
    admin_session.delete(f"{API}/api/resources/{parent['resource_id']}", timeout=10)


def test_utilization_by_sub_rejects_non_splitable(admin_session):
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
    admin_session.delete(f"{API}/api/resources/{res['resource_id']}", timeout=10)
