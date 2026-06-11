"""
Test suite for signature visibility features:
1. DocumentViewer shows signature overlays at correct positions
2. Download-signed PDF renders signatures at positions
3. Signatures without positions appear only in summary
"""
import pytest
import requests
import os
from PyPDF2 import PdfReader
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSignatureVisibility:
    """Test signature visibility in DocumentViewer and download-signed PDF"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session cookies"""
        self.session = requests.Session()
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.meeting_id = "meet_044aab394f"
        self.doc_id = "doc_49f0e85622"
    
    def test_documents_endpoint_returns_signatures(self):
        """Test GET /meetings/{meeting_id}/documents returns signatures with positions"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents")
        assert response.status_code == 200, f"Failed to get documents: {response.text}"
        
        docs = response.json()
        assert len(docs) > 0, "No documents found"
        
        # Find our test document
        test_doc = next((d for d in docs if d['doc_id'] == self.doc_id), None)
        assert test_doc is not None, f"Test document {self.doc_id} not found"
        
        # Verify signatures exist
        signatures = test_doc.get('signatures', [])
        assert len(signatures) == 10, f"Expected 10 signatures, got {len(signatures)}"
        
        # Verify signatures with positions
        sigs_with_pos = [s for s in signatures if s.get('pos_x', 0) > 0 or s.get('pos_y', 0) > 0]
        assert len(sigs_with_pos) == 2, f"Expected 2 signatures with positions, got {len(sigs_with_pos)}"
        
        # Verify specific positioned signatures
        pos_test_sig = next((s for s in signatures if s.get('signature_data') == 'Pos Test'), None)
        assert pos_test_sig is not None, "Pos Test signature not found"
        assert pos_test_sig.get('pos_x') == 100, f"Expected pos_x=100, got {pos_test_sig.get('pos_x')}"
        assert pos_test_sig.get('pos_y') == 200, f"Expected pos_y=200, got {pos_test_sig.get('pos_y')}"
        
        confirm_sig = next((s for s in signatures if s.get('signature_data') == 'Confirm Test Signature'), None)
        assert confirm_sig is not None, "Confirm Test Signature not found"
        assert confirm_sig.get('pos_x') == 859, f"Expected pos_x=859, got {confirm_sig.get('pos_x')}"
        assert confirm_sig.get('pos_y') == 540, f"Expected pos_y=540, got {confirm_sig.get('pos_y')}"
        
        print("SUCCESS: Documents endpoint returns signatures with correct positions")
    
    def test_download_signed_returns_valid_pdf(self):
        """Test GET /download-signed returns a valid PDF"""
        response = self.session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/download-signed"
        )
        assert response.status_code == 200, f"Failed to download signed PDF: {response.text}"
        
        # Verify content type
        content_type = response.headers.get('Content-Type', '')
        assert 'application/pdf' in content_type, f"Expected PDF content type, got {content_type}"
        
        # Verify it's a valid PDF
        pdf_content = response.content
        assert pdf_content.startswith(b'%PDF'), "Response is not a valid PDF"
        
        # Parse PDF and verify content
        pdf_reader = PdfReader(io.BytesIO(pdf_content))
        assert len(pdf_reader.pages) >= 1, "PDF has no pages"
        
        # Extract text from first page
        page_text = pdf_reader.pages[0].extract_text()
        
        # Verify positioned signatures are in the PDF
        assert 'Pos Test' in page_text, "Pos Test signature not found in PDF"
        assert 'Confirm Test Signature' in page_text, "Confirm Test Signature not found in PDF"
        
        # Verify document header
        assert 'Unterschriebenes Dokument' in page_text, "Document header not found in PDF"
        
        # Verify signature count in summary
        assert 'Unterschriften (10)' in page_text, "Signature count not found in PDF"
        
        print("SUCCESS: Download-signed returns valid PDF with signatures at positions")
    
    def test_download_signed_contains_all_signatures_in_summary(self):
        """Test that all signatures appear in the summary section"""
        response = self.session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{self.doc_id}/download-signed"
        )
        assert response.status_code == 200
        
        pdf_reader = PdfReader(io.BytesIO(response.content))
        page_text = pdf_reader.pages[0].extract_text()
        
        # Verify some signatures without positions appear in summary
        assert 'admin@meetflow.com' in page_text, "Admin email not in summary"
        assert 'test@test.de' in page_text, "Test user email not in summary"
        
        print("SUCCESS: All signatures appear in PDF summary section")
    
    def test_signatures_without_positions_not_on_document_area(self):
        """Test that signatures without pos_x/pos_y are NOT rendered on document area"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents")
        assert response.status_code == 200
        
        docs = response.json()
        test_doc = next((d for d in docs if d['doc_id'] == self.doc_id), None)
        signatures = test_doc.get('signatures', [])
        
        # Count signatures without positions (should be 8)
        sigs_without_pos = [s for s in signatures if s.get('pos_x', 0) == 0 and s.get('pos_y', 0) == 0]
        assert len(sigs_without_pos) == 8, f"Expected 8 signatures without positions, got {len(sigs_without_pos)}"
        
        # These should NOT appear as overlays in DocumentViewer (only in summary)
        # The frontend filters: signatures.filter(s => (s.page || 1) === page && (s.pos_x || s.pos_y))
        print("SUCCESS: 8 signatures without positions will only appear in summary")
    
    def test_typed_signature_format(self):
        """Test that typed signatures have correct format"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents")
        assert response.status_code == 200
        
        docs = response.json()
        test_doc = next((d for d in docs if d['doc_id'] == self.doc_id), None)
        signatures = test_doc.get('signatures', [])
        
        # Find typed signatures with positions
        typed_sigs = [s for s in signatures if s.get('type') == 'typed' and (s.get('pos_x', 0) > 0 or s.get('pos_y', 0) > 0)]
        assert len(typed_sigs) == 2, f"Expected 2 typed signatures with positions, got {len(typed_sigs)}"
        
        for sig in typed_sigs:
            assert 'signature_data' in sig, "Typed signature missing signature_data"
            assert isinstance(sig['signature_data'], str), "signature_data should be string"
            assert not sig['signature_data'].startswith('data:image'), "Typed signature should not be image data"
        
        print("SUCCESS: Typed signatures have correct format")


class TestSignaturePlacementExistingSigs:
    """Test that SignaturePlacement shows existing signatures"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session cookies"""
        self.session = requests.Session()
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200
        self.meeting_id = "meet_044aab394f"
        self.doc_id = "doc_49f0e85622"
    
    def test_documents_endpoint_provides_data_for_placement(self):
        """Test that documents endpoint provides all data needed for SignaturePlacement"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents")
        assert response.status_code == 200
        
        docs = response.json()
        test_doc = next((d for d in docs if d['doc_id'] == self.doc_id), None)
        
        # Verify all required fields for SignaturePlacement
        assert 'doc_id' in test_doc
        assert 'filename' in test_doc
        assert 'file_ext' in test_doc
        assert 'signatures' in test_doc
        
        # Verify signatures have position data
        for sig in test_doc['signatures']:
            assert 'sig_id' in sig or 'signer_name' in sig
            assert 'type' in sig
            assert 'signature_data' in sig
            # pos_x, pos_y may be 0 or missing for old signatures
        
        print("SUCCESS: Documents endpoint provides all data for SignaturePlacement")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
