"""
Test Document Thumbnail Feature
Tests PDF and image upload, document listing, and thumbnail rendering endpoints
"""
import pytest
import requests
import os
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from PIL import Image

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDocumentThumbnails:
    """Document thumbnail feature tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        
        # Login as admin (don't set Content-Type for multipart uploads)
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.user = login_response.json()
        print(f"Logged in as: {self.user.get('email')}")
        
        # Create a test meeting for document uploads
        meeting_response = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Thumbnail_Test_Meeting",
            "scheduled_time": "2026-04-15T10:00:00Z"
        })
        assert meeting_response.status_code in [200, 201], f"Meeting creation failed: {meeting_response.text}"
        self.meeting = meeting_response.json()
        self.meeting_id = self.meeting.get('meeting_id')
        print(f"Created test meeting: {self.meeting_id}")
        
        yield
        
        # Cleanup - delete test meeting
        try:
            self.session.delete(f"{BASE_URL}/api/meetings/{self.meeting_id}")
        except:
            pass
    
    def create_test_pdf(self):
        """Create a simple test PDF in memory"""
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        c.drawString(100, 750, 'Test PDF Document')
        c.drawString(100, 700, 'This is a test PDF for thumbnail testing')
        c.save()
        buffer.seek(0)
        return buffer
    
    def create_test_image(self):
        """Create a simple test image in memory"""
        img = Image.new('RGB', (400, 300), color='#4A5D4E')
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.text((100, 130), 'Test Image', fill='white')
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer
    
    def test_upload_pdf_document(self):
        """Test uploading a PDF document"""
        pdf_buffer = self.create_test_pdf()
        
        files = {'file': ('test_thumbnail.pdf', pdf_buffer, 'application/pdf')}
        response = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents",
            files=files
        )
        
        assert response.status_code in [200, 201], f"PDF upload failed: {response.text}"
        doc = response.json()
        
        # Verify document structure
        assert 'doc_id' in doc, "Document should have doc_id"
        assert 'filename' in doc, "Document should have filename"
        assert doc['filename'] == 'test_thumbnail.pdf', f"Filename mismatch: {doc['filename']}"
        
        # file_ext may not be in upload response, but should be in list
        print(f"PDF uploaded successfully: {doc['doc_id']}")
        
        # Verify file_ext is available in document list
        list_response = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents")
        docs = list_response.json()
        uploaded_doc = next((d for d in docs if d['doc_id'] == doc['doc_id']), None)
        assert uploaded_doc is not None, "Uploaded document should be in list"
        assert uploaded_doc.get('file_ext') == 'pdf', f"File extension should be pdf: {uploaded_doc.get('file_ext')}"
        
        return doc
    
    def test_upload_image_document(self):
        """Test uploading an image document"""
        img_buffer = self.create_test_image()
        
        files = {'file': ('test_thumbnail.png', img_buffer, 'image/png')}
        response = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents",
            files=files
        )
        
        assert response.status_code in [200, 201], f"Image upload failed: {response.text}"
        doc = response.json()
        
        # Verify document structure
        assert 'doc_id' in doc, "Document should have doc_id"
        assert 'filename' in doc, "Document should have filename"
        assert doc['filename'] == 'test_thumbnail.png', f"Filename mismatch: {doc['filename']}"
        
        # file_ext may not be in upload response, but should be in list
        print(f"Image uploaded successfully: {doc['doc_id']}")
        
        # Verify file_ext is available in document list
        list_response = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents")
        docs = list_response.json()
        uploaded_doc = next((d for d in docs if d['doc_id'] == doc['doc_id']), None)
        assert uploaded_doc is not None, "Uploaded document should be in list"
        assert uploaded_doc.get('file_ext') == 'png', f"File extension should be png: {uploaded_doc.get('file_ext')}"
        
        return doc
    
    def test_list_documents_with_file_ext(self):
        """Test that document listing includes file_ext for thumbnail rendering"""
        # Upload a PDF first
        pdf_buffer = self.create_test_pdf()
        files = {'file': ('test_list.pdf', pdf_buffer, 'application/pdf')}
        self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents", files=files)
        
        # Get document list
        response = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents")
        assert response.status_code == 200, f"Document list failed: {response.text}"
        
        docs = response.json()
        assert isinstance(docs, list), "Response should be a list"
        assert len(docs) > 0, "Should have at least one document"
        
        # Verify each document has required fields for thumbnail
        for doc in docs:
            assert 'doc_id' in doc, "Document should have doc_id"
            assert 'filename' in doc, "Document should have filename"
            assert 'file_ext' in doc, "Document should have file_ext for thumbnail rendering"
            print(f"Document: {doc['filename']} (ext: {doc['file_ext']})")
        
        return docs
    
    def test_view_document_for_thumbnail(self):
        """Test document view endpoint used for thumbnail generation"""
        # Upload a PDF
        pdf_buffer = self.create_test_pdf()
        files = {'file': ('test_view.pdf', pdf_buffer, 'application/pdf')}
        upload_response = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents",
            files=files
        )
        doc = upload_response.json()
        doc_id = doc['doc_id']
        
        # View the document (this is what DocThumbnail uses)
        response = self.session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc_id}/view"
        )
        
        assert response.status_code == 200, f"Document view failed: {response.text}"
        assert len(response.content) > 0, "Document content should not be empty"
        
        # Check content type
        content_type = response.headers.get('content-type', '')
        assert 'pdf' in content_type.lower() or 'octet-stream' in content_type.lower(), \
            f"Content type should indicate PDF: {content_type}"
        
        print(f"Document view successful, content size: {len(response.content)} bytes")
    
    def test_view_image_for_thumbnail(self):
        """Test image view endpoint used for thumbnail generation"""
        # Upload an image
        img_buffer = self.create_test_image()
        files = {'file': ('test_view.png', img_buffer, 'image/png')}
        upload_response = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents",
            files=files
        )
        doc = upload_response.json()
        doc_id = doc['doc_id']
        
        # View the image
        response = self.session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc_id}/view"
        )
        
        assert response.status_code == 200, f"Image view failed: {response.text}"
        assert len(response.content) > 0, "Image content should not be empty"
        
        print(f"Image view successful, content size: {len(response.content)} bytes")
    
    def test_document_download(self):
        """Test document download functionality"""
        # Upload a PDF
        pdf_buffer = self.create_test_pdf()
        files = {'file': ('test_download.pdf', pdf_buffer, 'application/pdf')}
        upload_response = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents",
            files=files
        )
        doc = upload_response.json()
        doc_id = doc['doc_id']
        
        # Download the document (same as view endpoint)
        response = self.session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc_id}/view"
        )
        
        assert response.status_code == 200, f"Document download failed: {response.text}"
        assert len(response.content) > 0, "Downloaded content should not be empty"
        
        print("Document download successful")
    
    def test_document_present(self):
        """Test document presentation functionality"""
        # Upload a PDF
        pdf_buffer = self.create_test_pdf()
        files = {'file': ('test_present.pdf', pdf_buffer, 'application/pdf')}
        upload_response = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents",
            files=files
        )
        doc = upload_response.json()
        doc_id = doc['doc_id']
        
        # Start presenting
        response = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc_id}/present",
            json={"presenting": True, "page": 1}
        )
        
        assert response.status_code == 200, f"Present document failed: {response.text}"
        print("Document presentation started successfully")
        
        # Stop presenting
        response = self.session.post(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc_id}/present",
            json={"presenting": False, "page": 1}
        )
        
        assert response.status_code == 200, f"Stop presentation failed: {response.text}"
        print("Document presentation stopped successfully")


class TestDocumentPanelUI:
    """Tests for DocumentPanel UI elements"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        
        # Login
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200
        
        yield
    
    def test_document_action_buttons_available(self):
        """Verify document action buttons are available via API"""
        # Get meetings list
        response = self.session.get(f"{BASE_URL}/api/meetings?page=1&limit=10")
        assert response.status_code == 200
        
        meetings = response.json()
        if isinstance(meetings, dict):
            meetings = meetings.get('meetings', [])
        
        # Find a meeting with documents
        for meeting in meetings:
            meeting_id = meeting.get('meeting_id')
            docs_response = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}/documents")
            if docs_response.status_code == 200:
                docs = docs_response.json()
                if len(docs) > 0:
                    print(f"Found meeting {meeting_id} with {len(docs)} documents")
                    
                    # Verify document structure supports all action buttons
                    doc = docs[0]
                    assert 'doc_id' in doc, "doc_id needed for action buttons"
                    assert 'filename' in doc, "filename needed for display"
                    assert 'file_ext' in doc, "file_ext needed for thumbnail"
                    
                    # Test view endpoint (for Download button)
                    view_response = self.session.get(
                        f"{BASE_URL}/api/meetings/{meeting_id}/documents/{doc['doc_id']}/view"
                    )
                    assert view_response.status_code == 200, "View endpoint should work for Download"
                    
                    # Test present endpoint (for Present button)
                    present_response = self.session.post(
                        f"{BASE_URL}/api/meetings/{meeting_id}/documents/{doc['doc_id']}/present",
                        json={"presenting": False, "page": 1}
                    )
                    assert present_response.status_code == 200, "Present endpoint should work"
                    
                    print("All document action endpoints verified")
                    return
        
        print("No meetings with documents found - skipping action button test")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
