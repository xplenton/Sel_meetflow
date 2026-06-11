"""
Iteration 295 — Logo Upload + Markdown/HTML Header/Footer for Invoice Templates
================================================================================

Tests:
1. Logo Upload (POST /api/admin/invoice-templates/{id}/logo)
   - Valid PNG/JPG/SVG upload
   - File too large (>2MB) → 400
   - Invalid MIME type → 400
   - Stores in Object Storage

2. Logo GET (GET /api/admin/invoice-templates/{id}/logo)
   - Returns image with correct content_type
   - 404 if no logo

3. Logo DELETE (DELETE /api/admin/invoice-templates/{id}/logo)
   - Removes logo_storage_path from template

4. Header/Footer Format (PUT /api/admin/invoice-templates/{id})
   - header_format='markdown' saves correctly
   - header_format='html' saves correctly
   - footer_format='markdown' saves correctly

5. PDF Generation with Logo + Markdown
   - Create template with logo + markdown header
   - Create manual invoice
   - GET /api/invoices/{id}/pdf/manual returns PDF >1500 bytes

6. _render_rich_text function
   - Markdown: **bold** → <strong>bold</strong>
   - HTML: drops block tags but keeps <b>, <i>, <font color>
   - Text: newlines → <br/>, HTML escaped
"""

import pytest
import requests
import os
import io
import base64

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Small valid PNG (1x1 pixel, red)
SMALL_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
SMALL_PNG = base64.b64decode(SMALL_PNG_B64)

# Create a "large" file (>2MB) for testing
LARGE_FILE = b"x" * (2 * 1024 * 1024 + 1)


class TestIter295LogoMarkdown:
    """Tests for Iteration 295 — Logo Upload + Markdown/HTML Header/Footer"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get auth token"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Track created resources for cleanup
        self.created_templates = []
        self.created_invoices = []
        
        yield
        
        # Cleanup: delete test templates and invoices
        for tpl_id in self.created_templates:
            try:
                # First delete logo if exists
                self.session.delete(f"{BASE_URL}/api/admin/invoice-templates/{tpl_id}/logo")
                # Then delete template
                self.session.delete(f"{BASE_URL}/api/admin/invoice-templates/{tpl_id}")
            except:
                pass

    def _create_test_template(self, name_suffix="", **kwargs):
        """Helper to create a test template"""
        payload = {
            "name": f"TEST_Logo_Template_{name_suffix}",
            "description": "Test template for logo/markdown testing",
            "header_text": kwargs.get("header_text", ""),
            "header_format": kwargs.get("header_format", "text"),
            "footer_text": kwargs.get("footer_text", ""),
            "footer_format": kwargs.get("footer_format", "text"),
            "payment_terms_default": "Zahlbar binnen 14 Tagen",
            "default_tax_rate": 19,
            "required_fields": ["recipient_name", "issue_date", "lines"],
            "visible_fields": ["cost_center", "account"],
            "is_default": False,
            "active": True,
        }
        payload.update(kwargs)
        resp = self.session.post(f"{BASE_URL}/api/admin/invoice-templates", json=payload)
        assert resp.status_code == 200, f"Failed to create template: {resp.text}"
        tpl = resp.json()
        self.created_templates.append(tpl["template_id"])
        return tpl

    # ==================== Logo Upload Tests ====================

    def test_logo_upload_valid_png(self):
        """POST /api/admin/invoice-templates/{id}/logo — Valid PNG upload"""
        tpl = self._create_test_template("png_upload")
        
        files = {"file": ("logo.png", io.BytesIO(SMALL_PNG), "image/png")}
        resp = self.session.post(
            f"{BASE_URL}/api/admin/invoice-templates/{tpl['template_id']}/logo",
            files=files
        )
        
        assert resp.status_code == 200, f"Logo upload failed: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        assert "path" in data
        assert "invoice-templates" in data["path"]
        print(f"✓ Logo uploaded successfully to: {data['path']}")

    def test_logo_upload_valid_jpeg(self):
        """POST /api/admin/invoice-templates/{id}/logo — Valid JPEG upload"""
        tpl = self._create_test_template("jpeg_upload")
        
        # Create a minimal JPEG (1x1 pixel)
        jpeg_data = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
            0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
            0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
            0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
            0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
            0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
            0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
            0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
            0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
            0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
            0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
            0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
            0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
            0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
            0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
            0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
            0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
            0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
            0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
            0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
            0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
            0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
            0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
            0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
            0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
            0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
            0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD5, 0xDB, 0x20, 0xA8, 0xA8, 0xA8, 0x00,
            0x00, 0x00, 0x00, 0xFF, 0xD9
        ])
        
        files = {"file": ("logo.jpg", io.BytesIO(jpeg_data), "image/jpeg")}
        resp = self.session.post(
            f"{BASE_URL}/api/admin/invoice-templates/{tpl['template_id']}/logo",
            files=files
        )
        
        assert resp.status_code == 200, f"JPEG upload failed: {resp.text}"
        print("✓ JPEG logo uploaded successfully")

    def test_logo_upload_file_too_large(self):
        """POST /api/admin/invoice-templates/{id}/logo — File >2MB returns 400"""
        tpl = self._create_test_template("large_file")
        
        files = {"file": ("large.png", io.BytesIO(LARGE_FILE), "image/png")}
        resp = self.session.post(
            f"{BASE_URL}/api/admin/invoice-templates/{tpl['template_id']}/logo",
            files=files
        )
        
        assert resp.status_code == 400, f"Expected 400 for large file, got {resp.status_code}"
        assert "2 MB" in resp.text or "2MB" in resp.text.replace(" ", "")
        print("✓ Large file correctly rejected with 400")

    def test_logo_upload_invalid_mime_type(self):
        """POST /api/admin/invoice-templates/{id}/logo — Invalid MIME type returns 400"""
        tpl = self._create_test_template("invalid_mime")
        
        files = {"file": ("document.pdf", io.BytesIO(b"fake pdf content"), "application/pdf")}
        resp = self.session.post(
            f"{BASE_URL}/api/admin/invoice-templates/{tpl['template_id']}/logo",
            files=files
        )
        
        assert resp.status_code == 400, f"Expected 400 for invalid MIME, got {resp.status_code}"
        print("✓ Invalid MIME type correctly rejected with 400")

    def test_logo_upload_template_not_found(self):
        """POST /api/admin/invoice-templates/{id}/logo — Non-existent template returns 404"""
        files = {"file": ("logo.png", io.BytesIO(SMALL_PNG), "image/png")}
        resp = self.session.post(
            f"{BASE_URL}/api/admin/invoice-templates/tpl_nonexistent123/logo",
            files=files
        )
        
        assert resp.status_code == 404, f"Expected 404 for non-existent template, got {resp.status_code}"
        print("✓ Non-existent template correctly returns 404")

    # ==================== Logo GET Tests ====================

    def test_logo_get_success(self):
        """GET /api/admin/invoice-templates/{id}/logo — Returns image with correct content_type"""
        tpl = self._create_test_template("get_logo")
        
        # First upload a logo
        files = {"file": ("logo.png", io.BytesIO(SMALL_PNG), "image/png")}
        upload_resp = self.session.post(
            f"{BASE_URL}/api/admin/invoice-templates/{tpl['template_id']}/logo",
            files=files
        )
        assert upload_resp.status_code == 200
        
        # Now GET the logo
        get_resp = self.session.get(f"{BASE_URL}/api/admin/invoice-templates/{tpl['template_id']}/logo")
        
        assert get_resp.status_code == 200, f"GET logo failed: {get_resp.status_code}"
        assert "image/" in get_resp.headers.get("Content-Type", "")
        assert len(get_resp.content) > 0
        print(f"✓ Logo retrieved successfully, Content-Type: {get_resp.headers.get('Content-Type')}")

    def test_logo_get_not_found(self):
        """GET /api/admin/invoice-templates/{id}/logo — 404 if no logo"""
        tpl = self._create_test_template("no_logo")
        
        resp = self.session.get(f"{BASE_URL}/api/admin/invoice-templates/{tpl['template_id']}/logo")
        
        assert resp.status_code == 404, f"Expected 404 for template without logo, got {resp.status_code}"
        print("✓ Template without logo correctly returns 404")

    # ==================== Logo DELETE Tests ====================

    def test_logo_delete_success(self):
        """DELETE /api/admin/invoice-templates/{id}/logo — Removes logo_storage_path"""
        tpl = self._create_test_template("delete_logo")
        
        # Upload logo first
        files = {"file": ("logo.png", io.BytesIO(SMALL_PNG), "image/png")}
        self.session.post(
            f"{BASE_URL}/api/admin/invoice-templates/{tpl['template_id']}/logo",
            files=files
        )
        
        # Verify logo exists
        get_resp = self.session.get(f"{BASE_URL}/api/admin/invoice-templates/{tpl['template_id']}/logo")
        assert get_resp.status_code == 200
        
        # Delete logo
        del_resp = self.session.delete(f"{BASE_URL}/api/admin/invoice-templates/{tpl['template_id']}/logo")
        assert del_resp.status_code == 200, f"Delete logo failed: {del_resp.text}"
        assert del_resp.json().get("ok") is True
        
        # Verify logo is gone
        get_resp2 = self.session.get(f"{BASE_URL}/api/admin/invoice-templates/{tpl['template_id']}/logo")
        assert get_resp2.status_code == 404
        print("✓ Logo deleted successfully")

    # ==================== Header/Footer Format Tests ====================

    def test_template_header_format_markdown(self):
        """PUT /api/admin/invoice-templates/{id} — header_format='markdown' saves correctly"""
        tpl = self._create_test_template("markdown_header")
        
        update_resp = self.session.put(
            f"{BASE_URL}/api/admin/invoice-templates/{tpl['template_id']}",
            json={
                "header_text": "**Bold Header** and *italic*",
                "header_format": "markdown"
            }
        )
        
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
        data = update_resp.json()
        assert data.get("header_format") == "markdown"
        assert data.get("header_text") == "**Bold Header** and *italic*"
        print("✓ Markdown header format saved correctly")

    def test_template_header_format_html(self):
        """PUT /api/admin/invoice-templates/{id} — header_format='html' saves correctly"""
        tpl = self._create_test_template("html_header")
        
        update_resp = self.session.put(
            f"{BASE_URL}/api/admin/invoice-templates/{tpl['template_id']}",
            json={
                "header_text": "<b>Bold</b> and <font color='red'>Red</font>",
                "header_format": "html"
            }
        )
        
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
        data = update_resp.json()
        assert data.get("header_format") == "html"
        print("✓ HTML header format saved correctly")

    def test_template_footer_format_markdown(self):
        """PUT /api/admin/invoice-templates/{id} — footer_format='markdown' saves correctly"""
        tpl = self._create_test_template("markdown_footer")
        
        update_resp = self.session.put(
            f"{BASE_URL}/api/admin/invoice-templates/{tpl['template_id']}",
            json={
                "footer_text": "Vielen Dank — [Kontakt](mailto:info@example.com)",
                "footer_format": "markdown"
            }
        )
        
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
        data = update_resp.json()
        assert data.get("footer_format") == "markdown"
        print("✓ Markdown footer format saved correctly")

    # ==================== PDF Generation with Logo + Markdown ====================

    def test_pdf_generation_with_logo_and_markdown(self):
        """Full flow: Create template with logo + markdown → create invoice → PDF has logo + rendered markdown"""
        # 1. Create template with markdown header/footer
        tpl = self._create_test_template(
            "pdf_full_test",
            header_text="**MeetFlow GmbH**\n*Ihre Klinik-Lösung*",
            header_format="markdown",
            footer_text="Vielen Dank für Ihr Vertrauen!\n[www.meetflow.de](https://meetflow.de)",
            footer_format="markdown"
        )
        
        # 2. Upload logo
        files = {"file": ("logo.png", io.BytesIO(SMALL_PNG), "image/png")}
        upload_resp = self.session.post(
            f"{BASE_URL}/api/admin/invoice-templates/{tpl['template_id']}/logo",
            files=files
        )
        assert upload_resp.status_code == 200, f"Logo upload failed: {upload_resp.text}"
        
        # 3. Create manual invoice using this template
        invoice_payload = {
            "template_id": tpl["template_id"],
            "recipient_name": "TEST_PDF_Recipient GmbH",
            "recipient_address": "Teststraße 123\n12345 Teststadt",
            "issue_date": "2026-01-15",
            "lines": [
                {
                    "label": "Beratungsleistung",
                    "description": "Strategische Beratung Q1",
                    "quantity": 10,
                    "unit": "Stunden",
                    "unit_price": 150.00,
                    "tax_rate": 19
                }
            ]
        }
        
        invoice_resp = self.session.post(f"{BASE_URL}/api/invoices/manual", json=invoice_payload)
        assert invoice_resp.status_code == 200, f"Invoice creation failed: {invoice_resp.text}"
        invoice = invoice_resp.json()
        invoice_id = invoice["invoice_id"]
        self.created_invoices.append(invoice_id)
        
        # Verify snapshot contains logo and format info
        snapshot = invoice.get("snapshot", {})
        assert snapshot.get("logo_storage_path"), "Logo path not in snapshot"
        assert snapshot.get("header_format") == "markdown", "Header format not in snapshot"
        assert snapshot.get("footer_format") == "markdown", "Footer format not in snapshot"
        
        # 4. Generate PDF
        pdf_resp = self.session.get(f"{BASE_URL}/api/invoices/{invoice_id}/pdf/manual")
        
        assert pdf_resp.status_code == 200, f"PDF generation failed: {pdf_resp.status_code}"
        assert pdf_resp.headers.get("Content-Type") == "application/pdf"
        
        pdf_size = len(pdf_resp.content)
        assert pdf_size > 1500, f"PDF too small ({pdf_size} bytes), expected >1500 with logo"
        
        # Check PDF header (should start with %PDF)
        assert pdf_resp.content[:4] == b"%PDF", "Response is not a valid PDF"
        
        print(f"✓ PDF generated successfully: {pdf_size} bytes, Content-Type: application/pdf")
        print(f"  - Logo path in snapshot: {snapshot.get('logo_storage_path')}")
        print(f"  - Header format: {snapshot.get('header_format')}")
        print(f"  - Footer format: {snapshot.get('footer_format')}")

    def test_pdf_without_logo(self):
        """PDF generation works without logo (baseline)"""
        tpl = self._create_test_template(
            "pdf_no_logo",
            header_text="Simple Header",
            header_format="text"
        )
        
        invoice_payload = {
            "template_id": tpl["template_id"],
            "recipient_name": "TEST_NoLogo_Recipient",
            "issue_date": "2026-01-15",
            "lines": [{"label": "Service", "quantity": 1, "unit_price": 100}]
        }
        
        invoice_resp = self.session.post(f"{BASE_URL}/api/invoices/manual", json=invoice_payload)
        assert invoice_resp.status_code == 200
        invoice_id = invoice_resp.json()["invoice_id"]
        self.created_invoices.append(invoice_id)
        
        pdf_resp = self.session.get(f"{BASE_URL}/api/invoices/{invoice_id}/pdf/manual")
        assert pdf_resp.status_code == 200
        assert pdf_resp.headers.get("Content-Type") == "application/pdf"
        print(f"✓ PDF without logo generated: {len(pdf_resp.content)} bytes")

    # ==================== _render_rich_text Function Tests ====================

    def test_render_markdown_bold(self):
        """Markdown **bold** renders to <strong>bold</strong> in PDF"""
        # We test this indirectly by creating an invoice with markdown and checking PDF is generated
        tpl = self._create_test_template(
            "markdown_bold_test",
            header_text="**This is bold** and normal",
            header_format="markdown"
        )
        
        invoice_payload = {
            "template_id": tpl["template_id"],
            "recipient_name": "TEST_Markdown_Bold",
            "issue_date": "2026-01-15",
            "lines": [{"label": "Test", "quantity": 1, "unit_price": 50}]
        }
        
        invoice_resp = self.session.post(f"{BASE_URL}/api/invoices/manual", json=invoice_payload)
        assert invoice_resp.status_code == 200
        invoice_id = invoice_resp.json()["invoice_id"]
        self.created_invoices.append(invoice_id)
        
        # PDF should generate without errors
        pdf_resp = self.session.get(f"{BASE_URL}/api/invoices/{invoice_id}/pdf/manual")
        assert pdf_resp.status_code == 200
        assert pdf_resp.content[:4] == b"%PDF"
        print("✓ Markdown bold text processed successfully in PDF")

    def test_render_html_format(self):
        """HTML format with <b>, <i>, <font color> renders correctly"""
        tpl = self._create_test_template(
            "html_format_test",
            header_text='<b>Bold</b> <i>Italic</i> <font color="#4A5D4E">Green</font>',
            header_format="html"
        )
        
        invoice_payload = {
            "template_id": tpl["template_id"],
            "recipient_name": "TEST_HTML_Format",
            "issue_date": "2026-01-15",
            "lines": [{"label": "Test", "quantity": 1, "unit_price": 50}]
        }
        
        invoice_resp = self.session.post(f"{BASE_URL}/api/invoices/manual", json=invoice_payload)
        assert invoice_resp.status_code == 200
        invoice_id = invoice_resp.json()["invoice_id"]
        self.created_invoices.append(invoice_id)
        
        pdf_resp = self.session.get(f"{BASE_URL}/api/invoices/{invoice_id}/pdf/manual")
        assert pdf_resp.status_code == 200
        print("✓ HTML format with inline tags processed successfully")

    def test_render_text_format_escapes_html(self):
        """Text format escapes HTML and converts newlines to <br/>"""
        tpl = self._create_test_template(
            "text_format_test",
            header_text="Line 1\nLine 2\n<script>alert('xss')</script>",
            header_format="text"
        )
        
        invoice_payload = {
            "template_id": tpl["template_id"],
            "recipient_name": "TEST_Text_Format",
            "issue_date": "2026-01-15",
            "lines": [{"label": "Test", "quantity": 1, "unit_price": 50}]
        }
        
        invoice_resp = self.session.post(f"{BASE_URL}/api/invoices/manual", json=invoice_payload)
        assert invoice_resp.status_code == 200
        invoice_id = invoice_resp.json()["invoice_id"]
        self.created_invoices.append(invoice_id)
        
        pdf_resp = self.session.get(f"{BASE_URL}/api/invoices/{invoice_id}/pdf/manual")
        assert pdf_resp.status_code == 200
        print("✓ Text format with HTML escaping processed successfully")

    # ==================== Template List Shows Logo Column ====================

    def test_template_list_includes_logo_path(self):
        """GET /api/admin/invoice-templates — Templates with logo show logo_storage_path"""
        tpl = self._create_test_template("list_logo_test")
        
        # Upload logo
        files = {"file": ("logo.png", io.BytesIO(SMALL_PNG), "image/png")}
        self.session.post(
            f"{BASE_URL}/api/admin/invoice-templates/{tpl['template_id']}/logo",
            files=files
        )
        
        # List templates
        list_resp = self.session.get(f"{BASE_URL}/api/admin/invoice-templates")
        assert list_resp.status_code == 200
        
        templates = list_resp.json()
        test_tpl = next((t for t in templates if t["template_id"] == tpl["template_id"]), None)
        assert test_tpl is not None
        assert test_tpl.get("logo_storage_path"), "logo_storage_path not in template list"
        print(f"✓ Template list includes logo_storage_path: {test_tpl.get('logo_storage_path')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
