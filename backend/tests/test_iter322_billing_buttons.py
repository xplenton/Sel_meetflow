"""
Iter 322 — Bugfix-Validation: 3 billing buttons + template-aware Save.

User-reported:
  1. "Sammelrechnung PDF" Button funktioniert nicht
  2. "Nur Catering PDF" Button funktioniert nicht
  3. "Als Rechnung speichern" funktioniert nicht
  4. Beim Speichern soll eine Vorlage auswählbar sein

Root cause for (1)+(2): Frontend used `window.open(URL)` which doesn't carry
the JWT → 401. Fix: blob-download helper (`lib/authedDownload.js`).

This test validates the BACKEND-side of the fix:
  - PDF endpoints serve valid PDFs when called WITH auth
  - PDF endpoints return 401 when called WITHOUT auth (proves the
    frontend bug repro)
  - POST /invoices now accepts template_id and snapshots template data
  - GET /invoices/{id}/pdf for template-attached invoices renders the
    richer template-aware PDF (logo + header + footer)
"""
import io
import os
import uuid

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


def _png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x08\x00\x00\x00\x08"
        b"\x08\x02\x00\x00\x00Kk\xd5G\x00\x00\x00\x1eIDATx\x9cc\xf8\xcf\x80"
        b"\x01\x14U\x12\xed\x0f\x10\x00\x84\xae\x00\x10\x00\x84\xae\x00\x10"
        b"\x00\x84\xae\x00\x10\x00\x05\x00\xfd\xd4\x06\x01\xa3\xb2N\xa4\x00"
        b"\x00\x00\x00IEND\xaeB`\x82"
    )


# ---------------------------------------------------------------------------
# 1) Repro of the frontend bug: PDF endpoints reject unauthenticated requests
# ---------------------------------------------------------------------------

def test_pdf_endpoints_reject_without_token(base_url: str):
    """`window.open` bug repro — these endpoints MUST require auth, otherwise
    the frontend fix wouldn't be needed (and the production data would be
    publicly readable)."""
    paths = [
        "/api/resource-bookings/invoices/aggregate.pdf",
        "/api/catering-requests/invoices/aggregate.pdf",
        "/api/resource-bookings/export/erp.csv?format=datev&days=30",
    ]
    for p in paths:
        r = requests.get(f"{base_url}{p}", timeout=10, verify=False)
        assert r.status_code == 401, f"Expected 401 (auth req), got {r.status_code} for {p}"
    print(f"\n  ✓ All {len(paths)} endpoints correctly reject unauthenticated requests")


# ---------------------------------------------------------------------------
# 2) PDF endpoints serve valid PDFs with auth (proves the frontend blob fix
#    will actually deliver content)
# ---------------------------------------------------------------------------

def test_pdf_endpoints_work_with_token(base_url: str, admin_token: str):
    """Server-side: with the JWT, all 3 endpoints serve valid PDFs."""
    H = _auth(admin_token)
    cases = [
        ("/api/resource-bookings/invoices/aggregate.pdf", "Sammelrechnung-PDF"),
        ("/api/catering-requests/invoices/aggregate.pdf", "Catering-PDF"),
    ]
    for path, label in cases:
        r = requests.get(f"{base_url}{path}?from_date=2025-01-01&to_date=2026-12-31",
                         headers=H, timeout=15, verify=False)
        assert r.status_code == 200, f"{label} returned {r.status_code}: {r.text[:200]}"
        assert r.headers.get("content-type", "").startswith("application/pdf"), \
            f"{label} content-type: {r.headers.get('content-type')}"
        assert r.content[:4] == b"%PDF", f"{label} not a valid PDF"
        assert len(r.content) > 1000, f"{label} suspiciously small: {len(r.content)}"
        print(f"  ✓ {label}: {len(r.content)} bytes, valid PDF")


# ---------------------------------------------------------------------------
# 3) "Als Rechnung speichern" with template — POST /invoices snapshots template
# ---------------------------------------------------------------------------

def test_save_invoice_with_template(base_url: str, admin_token: str):
    """End-to-end: configure template with logo → save aggregate invoice with
    that template_id → fetch PDF → should be the template-aware layout (large)."""
    H = _auth(admin_token)
    suffix = uuid.uuid4().hex[:6]
    tpl_id = None
    inv_id_template = None
    inv_id_plain = None

    try:
        # ---- Setup: create a template with logo ----
        r = requests.post(
            f"{base_url}/api/admin/invoice-templates",
            headers=H, verify=False, timeout=10,
            json={
                "name": f"BugFixTest {suffix}",
                "header_text": "**Klinikum Beispiel** — Rechnungsstelle",
                "header_format": "markdown",
                "footer_text": "IBAN: DE89 3704 0044 0532 0130 00\nVielen Dank für Ihren Auftrag.",
                "footer_format": "text",
                "payment_terms_default": "Zahlbar binnen 30 Tagen",
                "bank_details": "Sparkasse — IBAN: DE89...",
                "default_tax_rate": 7,
                "required_fields": ["recipient_name", "issue_date", "lines"],
                "active": True, "is_default": False,
            },
        )
        assert r.status_code == 200, r.text
        tpl_id = r.json()["template_id"]

        files = {"file": ("logo.png", io.BytesIO(_png()), "image/png")}
        r = requests.post(
            f"{base_url}/api/admin/invoice-templates/{tpl_id}/logo",
            headers=H, files=files, timeout=10, verify=False,
        )
        assert r.status_code == 200, r.text

        # ---- Save WITHOUT template (plain layout, for size comparison) ----
        r = requests.post(
            f"{base_url}/api/invoices", headers=H, verify=False, timeout=10,
            json={"kind": "catering_aggregate",
                  "from_date": "2025-01-01", "to_date": "2026-12-31",
                  "title": f"Test-Plain {suffix}"},
        )
        assert r.status_code == 200, f"Save without template failed: {r.text}"
        inv_id_plain = r.json()["invoice_id"]
        assert r.json().get("template_id") is None
        print(f"\n  ✓ Plain invoice saved: {inv_id_plain}")

        # ---- Save WITH template (the new dialog flow) ----
        r = requests.post(
            f"{base_url}/api/invoices", headers=H, verify=False, timeout=10,
            json={
                "kind": "catering_aggregate",
                "template_id": tpl_id,
                "from_date": "2025-01-01", "to_date": "2026-12-31",
                "title": f"Test-Templated {suffix}",
            },
        )
        assert r.status_code == 200, f"Save with template failed: {r.text}"
        inv = r.json()
        inv_id_template = inv["invoice_id"]
        assert inv.get("template_id") == tpl_id, "Template ID not stored on invoice"
        # Verify template data is in the snapshot (so changes to template
        # later don't affect the saved invoice)
        snap = inv["snapshot"]
        assert snap.get("template_id") == tpl_id
        assert snap.get("template_name") == f"BugFixTest {suffix}"
        assert snap.get("logo_storage_path"), "Logo path missing from snapshot"
        assert "Klinikum Beispiel" in (snap.get("header_text") or "")
        assert "IBAN" in (snap.get("footer_text") or "")
        print(f"  ✓ Templated invoice saved: {inv_id_template}, "
              f"logo + header + footer snapshotted")

        # ---- Verify "__none__" sentinel is respected (UI selection
        #      "ohne Vorlage" sends "__none__") ----
        r = requests.post(
            f"{base_url}/api/invoices", headers=H, verify=False, timeout=10,
            json={"kind": "catering_aggregate", "template_id": "__none__",
                  "from_date": "2025-01-01", "to_date": "2026-12-31",
                  "title": f"Test-None {suffix}"},
        )
        assert r.status_code == 200
        none_id = r.json()["invoice_id"]
        assert r.json().get("template_id") is None
        print(f"  ✓ '__none__' sentinel correctly treated as no template")

        # ---- Render BOTH PDFs and confirm the templated one is bigger ----
        r1 = requests.get(f"{base_url}/api/invoices/{inv_id_plain}/pdf",
                          headers=H, timeout=15, verify=False)
        assert r1.status_code == 200, r1.text
        plain_size = len(r1.content)

        r2 = requests.get(f"{base_url}/api/invoices/{inv_id_template}/pdf",
                          headers=H, timeout=15, verify=False)
        assert r2.status_code == 200, r2.text
        tpl_size = len(r2.content)

        assert r1.content[:4] == b"%PDF"
        assert r2.content[:4] == b"%PDF"
        # The templated PDF embeds a logo + header + footer, so it must be
        # at least somewhat bigger. (Empirically: ~400-2000 bytes more depending
        # on whether there are line items + how big the logo is.)
        assert tpl_size > plain_size + 200, \
            f"Templated PDF ({tpl_size}B) should be larger than plain ({plain_size}B)"
        print(f"  ✓ Plain PDF: {plain_size} bytes  →  Templated PDF: {tpl_size} bytes "
              f"(+{tpl_size - plain_size}B)")

        # ---- Cleanup invoices ----
        for iid in [inv_id_plain, inv_id_template, none_id]:
            try:
                requests.delete(f"{base_url}/api/invoices/{iid}",
                                headers=H, timeout=10, verify=False)
            except Exception:
                pass
        inv_id_plain = inv_id_template = None

        print(f"\n  🎉 Full save-with-template flow works end-to-end")

    finally:
        for iid in (inv_id_plain, inv_id_template):
            if iid:
                try:
                    requests.delete(f"{base_url}/api/invoices/{iid}",
                                    headers=H, timeout=10, verify=False)
                except Exception:
                    pass
        if tpl_id:
            try:
                requests.delete(f"{base_url}/api/admin/invoice-templates/{tpl_id}",
                                headers=H, timeout=10, verify=False)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 4) Single-booking PDF endpoint also needs auth (regression for other buttons)
# ---------------------------------------------------------------------------

def test_single_booking_invoice_auth(base_url: str, admin_token: str):
    """The per-row 'Rechnung anzeigen' button uses the same authedDownload
    helper. Confirm endpoint requires auth and serves PDF with auth."""
    H = _auth(admin_token)
    # Find any existing booking
    r = requests.get(f"{base_url}/api/resource-bookings?mine_only=false",
                     headers=H, timeout=10, verify=False)
    assert r.status_code == 200
    bookings = r.json()
    if not bookings:
        pytest.skip("No bookings to test single-invoice endpoint")
    bid = bookings[0]["booking_id"]

    # No auth → 401
    r = requests.get(f"{base_url}/api/resource-bookings/{bid}/invoice.pdf",
                     timeout=10, verify=False)
    assert r.status_code == 401

    # With auth → 200 PDF
    r = requests.get(f"{base_url}/api/resource-bookings/{bid}/invoice.pdf",
                     headers=H, timeout=15, verify=False)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    print(f"\n  ✓ Per-booking PDF endpoint: auth required, serves PDF with token")
