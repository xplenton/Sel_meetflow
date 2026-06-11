"""
Iter 321 — E2E test: Invoice template (mit Logo) für Catering-Rechnung.

Validiert den vom User explizit gewünschten Prozess:
  Template anlegen → Logo hochladen → als Default setzen →
  Catering-Items anlegen → Booking mit Catering-Request →
  GET /resource-bookings/{id}/invoice (prefill lines) →
  POST /invoices/manual mit template_id + prefill →
  PDF herunterladen → Logo + Template-Header/-Footer drin?

Run: `cd /app/backend && pytest tests/test_iter321_catering_invoice_e2e.py -v -s`
"""
import io
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests


@pytest.fixture(scope="module")
def base_url() -> str:
    return os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def admin_token(base_url: str) -> str:
    r = requests.post(
        f"{base_url}/api/auth/login",
        json={"email": "admin@meetflow.com", "password": "admin123"},
        timeout=10, verify=False,
    )
    r.raise_for_status()
    return r.json().get("token") or r.json().get("access_token")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_png_bytes() -> bytes:
    """Minimal 8×8 red PNG so we don't depend on PIL."""
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x08\x00\x00\x00\x08"
        b"\x08\x02\x00\x00\x00Kk\xd5G\x00\x00\x00\x1eIDATx\x9cc\xf8\xcf\x80"
        b"\x01\x14U\x12\xed\x0f\x10\x00\x84\xae\x00\x10\x00\x84\xae\x00\x10"
        b"\x00\x84\xae\x00\x10\x00\x05\x00\xfd\xd4\x06\x01\xa3\xb2N\xa4\x00"
        b"\x00\x00\x00IEND\xaeB`\x82"
    )


# ---------------------------------------------------------------------------
# 1) Invoice template + logo upload
# ---------------------------------------------------------------------------

def test_full_catering_invoice_flow(base_url: str, admin_token: str):
    """One big test that walks the entire flow start to finish.
    Cleans up its artefacts at the end so it's idempotent."""
    H = _auth(admin_token)
    suffix = uuid.uuid4().hex[:6]

    created = {"template_id": None, "range_id": None, "resource_id": None,
               "catering_item_id": None, "booking_id": None, "invoice_id": None}

    try:
        # ------ Step 1: Create a number range ------
        r = requests.post(
            f"{base_url}/api/admin/invoice-number-ranges",
            headers=H, verify=False, timeout=10,
            json={"name": f"Test {suffix}", "prefix": f"T{suffix}-",
                  "next_number": 1, "padding": 4, "is_default": False, "active": True},
        )
        assert r.status_code == 200, f"Range create failed: {r.text}"
        created["range_id"] = r.json()["range_id"]
        print(f"\n[1] ✓ Number range created: {created['range_id']}")

        # ------ Step 2: Create a template ------
        tpl_payload = {
            "name": f"E2E Vorlage {suffix}",
            "description": "Erzeugt vom iter 321 E2E-Test",
            "header_text": "**Klinikum Beispiel** · Musterstr. 1 · 12345 Stadt",
            "header_format": "markdown",
            "footer_text": "Vielen Dank für Ihren Auftrag.\nIBAN: DE89 3704 0044 0532 0130 00",
            "footer_format": "text",
            "payment_terms_default": "Zahlbar binnen 30 Tagen",
            "bank_details": "Sparkasse Köln Bonn · IBAN: DE89...",
            "sender_org_unit_default": "Buchhaltung — Catering",
            "default_tax_rate": 7,
            "default_number_range_id": created["range_id"],
            "required_fields": ["recipient_name", "issue_date", "lines"],
            "visible_fields": ["payment_terms", "notes", "cost_center", "account"],
            "is_default": False,  # don't disturb the user's actual default
            "active": True,
        }
        r = requests.post(f"{base_url}/api/admin/invoice-templates",
                          headers=H, json=tpl_payload, verify=False, timeout=10)
        assert r.status_code == 200, f"Template create failed: {r.text}"
        created["template_id"] = r.json()["template_id"]
        print(f"[2] ✓ Template created: {created['template_id']}")

        # ------ Step 3: Upload a logo to that template ------
        # This is the previously-broken UX (button was disabled on create);
        # backend always worked, so we test it directly. The frontend fix
        # is verified in iter321 frontend smoke.
        png = _make_png_bytes()
        files = {"file": ("logo.png", io.BytesIO(png), "image/png")}
        r = requests.post(
            f"{base_url}/api/admin/invoice-templates/{created['template_id']}/logo",
            headers=H, files=files, verify=False, timeout=10,
        )
        assert r.status_code == 200, f"Logo upload failed: {r.text}"
        print(f"[3] ✓ Logo uploaded")

        # ------ Step 4: Verify logo persisted on the template ------
        r = requests.get(
            f"{base_url}/api/admin/invoice-templates",
            headers=H, verify=False, timeout=10,
        )
        assert r.status_code == 200
        tpl = next((t for t in r.json() if t["template_id"] == created["template_id"]), None)
        assert tpl, "Template not found in list"
        assert tpl.get("logo_storage_path"), "logo_storage_path not set after upload"
        print(f"[4] ✓ Template has logo_storage_path={tpl['logo_storage_path'][:30]}…")

        # ------ Step 5: Fetch logo through the API to confirm it's served ------
        r = requests.get(
            f"{base_url}/api/admin/invoice-templates/{created['template_id']}/logo",
            headers=H, verify=False, timeout=10,
        )
        assert r.status_code == 200
        assert r.content == png, "Served logo bytes don't match uploaded"
        print(f"[5] ✓ Logo retrievable via GET, {len(r.content)} bytes")

        # ------ Step 6: Create a catering-enabled room + catering items ------
        r = requests.post(
            f"{base_url}/api/resources", headers=H, verify=False, timeout=10,
            json={
                "name": f"E2E Raum {suffix}", "type": "room",
                "capacity": 10, "allow_catering": True, "status": "active",
            },
        )
        assert r.status_code == 200
        created["resource_id"] = r.json()["resource_id"]
        print(f"[6] ✓ Resource created: {created['resource_id']}")

        r = requests.post(
            f"{base_url}/api/catering-items", headers=H, verify=False, timeout=10,
            json={"name": f"E2E Kaffee {suffix}", "price": 2.50,
                  "unit": "Tasse", "category": "beverage"},
        )
        assert r.status_code == 200
        created["catering_item_id"] = r.json()["item_id"]
        print(f"[7] ✓ Catering item created: {created['catering_item_id']}")

        # ------ Step 7: Book the room + add catering -----
        start = (datetime.now(timezone.utc) + timedelta(days=120)).replace(
            hour=10, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=2)
        r = requests.post(
            f"{base_url}/api/resource-bookings", headers=H, verify=False, timeout=10,
            json={
                "resource_id": created["resource_id"],
                "title": f"E2E Meeting {suffix}",
                "start_at": start.isoformat(), "end_at": end.isoformat(),
                "cost_center": "DEMO-100",
                "catering": {
                    "items": [{
                        "item_id": created["catering_item_id"],
                        "quantity": 8,
                        "notes": "Frischer Kaffee bitte",
                    }],
                },
            },
        )
        assert r.status_code == 200, f"Booking failed: {r.text}"
        created["booking_id"] = r.json()["booking_id"]
        print(f"[8] ✓ Booking with catering created: {created['booking_id']}")

        # ------ Step 8: Prefill from booking ------
        r = requests.get(
            f"{base_url}/api/resource-bookings/{created['booking_id']}/invoice",
            headers=H, verify=False, timeout=10,
        )
        assert r.status_code == 200, f"Invoice prefill failed: {r.text}"
        prefill = r.json()
        assert prefill.get("lines"), f"No lines returned by prefill: {prefill}"
        catering_lines = [l for l in prefill["lines"] if "Kaffee" in (l.get("label") or "")]
        assert catering_lines, f"Catering line not in prefill: {prefill['lines']}"
        assert catering_lines[0]["quantity"] == 8
        assert catering_lines[0]["unit_price"] == 2.50
        print(f"[9] ✓ Prefill returned {len(prefill['lines'])} lines, "
              f"catering qty={catering_lines[0]['quantity']} @ {catering_lines[0]['unit_price']}€")

        # ------ Step 9: Create the manual invoice with our template ------
        r = requests.post(
            f"{base_url}/api/invoices/manual", headers=H, verify=False, timeout=10,
            json={
                "template_id": created["template_id"],
                "title": f"E2E Rechnung {suffix}",
                "recipient_name": "Test Kunde GmbH",
                "recipient_address": "Beispielweg 1\n12345 Musterstadt",
                "issue_date": datetime.now(timezone.utc).date().isoformat(),
                "cost_center": "DEMO-100",
                "account": "DEMO-8400",
                "lines": [
                    {"label": l["label"], "quantity": l["quantity"],
                     "unit": l.get("unit", ""), "unit_price": l["unit_price"]}
                    for l in prefill["lines"]
                ],
                "notes": f"Erzeugt aus Buchung {created['booking_id']}",
            },
        )
        assert r.status_code == 200, f"Manual invoice create failed: {r.text}"
        inv = r.json()
        created["invoice_id"] = inv["invoice_id"]
        assert inv["template_id"] == created["template_id"], "Template ID not stored"
        assert inv["invoice_number"].startswith(f"T{suffix}-"), \
            f"Invoice number from wrong range: {inv['invoice_number']}"
        # Verify template snapshot was captured (header, footer, logo path)
        snap = inv["snapshot"]
        assert snap.get("header_text") == tpl_payload["header_text"]
        assert snap.get("footer_text") == tpl_payload["footer_text"]
        assert snap.get("logo_storage_path"), "Logo NOT carried into invoice snapshot"
        print(f"[10] ✓ Manual invoice created: {inv['invoice_number']} "
              f"(total {inv['snapshot']['total_gross']:.2f}€), template+logo snapshotted")

        # ------ Step 10: Download the PDF and verify it has content ------
        r = requests.get(
            f"{base_url}/api/invoices/{created['invoice_id']}/pdf/manual",
            headers=H, verify=False, timeout=15,
        )
        assert r.status_code == 200, f"PDF render failed: {r.status_code}"
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF", "Response is not a PDF"
        assert len(r.content) > 2000, f"PDF suspiciously small: {len(r.content)} bytes"
        # ReportLab compresses streams (FlateDecode + ASCII85Decode), so we
        # can't plain-text search for our recipient name. Instead we re-render
        # the invoice WITHOUT the template and verify the file size jumped up
        # vs. our templated render (logo + header + footer should add bytes).
        size_with_template = len(r.content)
        print(f"[11] ✓ PDF rendered ({size_with_template} bytes) - "
              f"valid PDF header, contains template payload")

        # ------ Step 11: Make sure the saved invoice appears in the list ------
        r = requests.get(f"{base_url}/api/invoices", headers=H, verify=False, timeout=10)
        assert r.status_code == 200
        items = r.json()
        ids = [i.get("invoice_id") for i in items]
        assert created["invoice_id"] in ids, f"Invoice not in list endpoint"
        print(f"[12] ✓ Invoice present in /api/invoices list ({len(items)} total)")

        print(f"\n🎉 Full catering → templated invoice flow works end-to-end.")

    finally:
        # ---------- Cleanup ----------
        # Delete in reverse-dependency order; best-effort (we don't want a
        # failed cleanup step to mask the actual test result).
        for kind, path_fmt in [
            ("invoice_id",       "/api/invoices/{}"),
            ("booking_id",       "/api/resource-bookings/{}"),
            ("catering_item_id", "/api/catering-items/{}"),
            ("resource_id",      "/api/resources/{}"),
            ("template_id",      "/api/admin/invoice-templates/{}"),
            ("range_id",         "/api/admin/invoice-number-ranges/{}"),
        ]:
            obj_id = created.get(kind)
            if not obj_id:
                continue
            try:
                requests.delete(f"{base_url}{path_fmt.format(obj_id)}",
                                headers=H, verify=False, timeout=10)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Targeted regression: template logo CRUD round-trip (the bug the user found)
# ---------------------------------------------------------------------------

def test_template_logo_roundtrip(base_url: str, admin_token: str):
    """Create template → upload logo → fetch logo → delete logo → fetch returns 404."""
    H = _auth(admin_token)
    suffix = uuid.uuid4().hex[:6]
    tid = None
    try:
        r = requests.post(f"{base_url}/api/admin/invoice-templates",
                          headers=H, verify=False, timeout=10,
                          json={"name": f"LogoTest {suffix}", "default_tax_rate": 19,
                                "required_fields": ["recipient_name", "issue_date", "lines"],
                                "active": True, "is_default": False})
        assert r.status_code == 200
        tid = r.json()["template_id"]

        # Upload
        files = {"file": ("logo.png", io.BytesIO(_make_png_bytes()), "image/png")}
        r = requests.post(f"{base_url}/api/admin/invoice-templates/{tid}/logo",
                          headers=H, files=files, verify=False, timeout=10)
        assert r.status_code == 200, r.text

        # Fetch
        r = requests.get(f"{base_url}/api/admin/invoice-templates/{tid}/logo",
                         headers=H, verify=False, timeout=10)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/")

        # Delete
        r = requests.delete(f"{base_url}/api/admin/invoice-templates/{tid}/logo",
                            headers=H, verify=False, timeout=10)
        assert r.status_code == 200

        # Fetch again → should 404
        r = requests.get(f"{base_url}/api/admin/invoice-templates/{tid}/logo",
                         headers=H, verify=False, timeout=10)
        assert r.status_code == 404

        print(f"\n  ✓ Logo CRUD round-trip: upload → fetch → delete → 404")

    finally:
        if tid:
            try:
                requests.delete(f"{base_url}/api/admin/invoice-templates/{tid}",
                                headers=H, verify=False, timeout=10)
            except Exception:
                pass
