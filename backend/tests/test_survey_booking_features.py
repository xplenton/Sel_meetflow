"""
Test Survey Results Fix and Booking Overview Features
- Survey/Umfrage results showing after voting (selected_options field)
- Booking overview endpoints (GET /api/booking/all-bookings, GET /api/booking/pages/{page_id}/bookings)
- Cancel booking functionality
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSurveyResultsFix:
    """Test that survey results are correctly returned with selected_options field"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Test survey share_token from context
        self.test_share_token = "fef907b258e3"
    
    def test_get_public_survey_returns_votes_with_selected_options(self):
        """GET /api/general-polls/public/{share_token} returns votes with selected_options field"""
        response = self.session.get(f"{BASE_URL}/api/general-polls/public/{self.test_share_token}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "poll_id" in data, "Response should contain poll_id"
        assert "votes" in data, "Response should contain votes array"
        assert "options" in data, "Response should contain options array"
        
        # Check that votes have selected_options field
        if len(data["votes"]) > 0:
            vote = data["votes"][0]
            # Vote should have selected_options field (the fix)
            assert "selected_options" in vote or "selected" in vote, "Vote should have selected_options or selected field"
            print(f"✓ Survey has {len(data['votes'])} votes with proper structure")
            print(f"  Vote fields: {list(vote.keys())}")
        else:
            print("⚠ No votes in survey yet")
    
    def test_vote_on_survey_stores_selected_options(self):
        """POST /api/general-polls/public/{share_token}/vote stores selected_options correctly"""
        # First get the survey to know the options
        get_response = self.session.get(f"{BASE_URL}/api/general-polls/public/{self.test_share_token}")
        assert get_response.status_code == 200
        survey = get_response.json()
        
        if survey.get("status") == "closed":
            pytest.skip("Survey is closed, cannot vote")
        
        options = survey.get("options", [])
        if not options:
            pytest.skip("No options in survey")
        
        # Vote with selected_options
        vote_payload = {
            "voter_name": "TEST_VoterPytest",
            "voter_email": "test@pytest.com",
            "selected_options": [options[0]],  # Select first option
            "selected": [options[0]],
            "priority_order": []
        }
        
        vote_response = self.session.post(
            f"{BASE_URL}/api/general-polls/public/{self.test_share_token}/vote",
            json=vote_payload
        )
        assert vote_response.status_code == 200, f"Vote failed: {vote_response.text}"
        
        vote_data = vote_response.json()
        assert "vote_id" in vote_data, "Response should contain vote_id"
        print(f"✓ Vote recorded with vote_id: {vote_data['vote_id']}")
        
        # Verify vote was stored with selected_options
        verify_response = self.session.get(f"{BASE_URL}/api/general-polls/public/{self.test_share_token}")
        assert verify_response.status_code == 200
        
        updated_survey = verify_response.json()
        test_vote = next((v for v in updated_survey.get("votes", []) if v.get("voter_name") == "TEST_VoterPytest"), None)
        assert test_vote is not None, "Test vote should be found in survey"
        assert "selected_options" in test_vote, "Vote should have selected_options field stored"
        assert test_vote["selected_options"] == [options[0]], f"selected_options should match: {test_vote['selected_options']}"
        print(f"✓ Vote stored with selected_options: {test_vote['selected_options']}")


class TestBookingOverview:
    """Test booking overview endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup authenticated session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        print("✓ Logged in as admin@meetflow.com")
        
        # Known booking page IDs from context
        self.page_id_intern = "bp_7cf6a729a6"
        self.page_id_extern = "bp_55441eb29e"
    
    def test_get_all_bookings_returns_bookings(self):
        """GET /api/booking/all-bookings returns all bookings for authenticated user"""
        response = self.session.get(f"{BASE_URL}/api/booking/all-bookings")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "bookings" in data, "Response should contain bookings array"
        
        bookings = data["bookings"]
        print(f"✓ GET /api/booking/all-bookings returned {len(bookings)} bookings")
        
        # Verify booking structure
        if len(bookings) > 0:
            booking = bookings[0]
            required_fields = ["booking_id", "guest_name", "date", "start_time", "end_time", "status"]
            for field in required_fields:
                assert field in booking, f"Booking should have {field} field"
            print(f"  Sample booking: {booking.get('guest_name')} on {booking.get('date')} at {booking.get('start_time')}")
    
    def test_get_page_bookings_returns_filtered_bookings(self):
        """GET /api/booking/pages/{page_id}/bookings returns bookings filtered by page"""
        response = self.session.get(f"{BASE_URL}/api/booking/pages/{self.page_id_intern}/bookings")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "bookings" in data, "Response should contain bookings array"
        assert "page" in data, "Response should contain page info"
        
        bookings = data["bookings"]
        page = data["page"]
        print(f"✓ GET /api/booking/pages/{self.page_id_intern}/bookings returned {len(bookings)} bookings")
        print(f"  Page: {page.get('title', page.get('slug'))}")
        
        # Verify all bookings belong to this page (if they have page_id)
        for booking in bookings:
            if booking.get("page_id"):
                assert booking["page_id"] == self.page_id_intern or booking.get("page_slug") == page.get("slug"), \
                    f"Booking should belong to page {self.page_id_intern}"
    
    def test_get_page_bookings_extern(self):
        """GET /api/booking/pages/{page_id}/bookings for extern page"""
        response = self.session.get(f"{BASE_URL}/api/booking/pages/{self.page_id_extern}/bookings")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "bookings" in data
        print(f"✓ GET /api/booking/pages/{self.page_id_extern}/bookings returned {len(data['bookings'])} bookings")
    
    def test_get_page_bookings_invalid_page_returns_404(self):
        """GET /api/booking/pages/{invalid_page_id}/bookings returns 404"""
        response = self.session.get(f"{BASE_URL}/api/booking/pages/bp_invalid123/bookings")
        assert response.status_code == 404, f"Expected 404 for invalid page, got {response.status_code}"
        print("✓ Invalid page_id returns 404 as expected")
    
    def test_cancel_booking(self):
        """DELETE /api/booking/{booking_id} cancels a booking"""
        # First get all bookings to find one to cancel
        all_response = self.session.get(f"{BASE_URL}/api/booking/all-bookings")
        assert all_response.status_code == 200
        
        bookings = all_response.json().get("bookings", [])
        confirmed_booking = next((b for b in bookings if b.get("status") == "confirmed"), None)
        
        if not confirmed_booking:
            pytest.skip("No confirmed bookings to cancel")
        
        booking_id = confirmed_booking["booking_id"]
        print(f"  Cancelling booking: {booking_id} ({confirmed_booking.get('guest_name')})")
        
        # Cancel the booking
        cancel_response = self.session.delete(f"{BASE_URL}/api/booking/{booking_id}")
        assert cancel_response.status_code == 200, f"Cancel failed: {cancel_response.text}"
        
        cancel_data = cancel_response.json()
        assert "message" in cancel_data
        print(f"✓ Booking cancelled: {cancel_data.get('message')}")
        
        # Verify booking status changed
        verify_response = self.session.get(f"{BASE_URL}/api/booking/all-bookings")
        assert verify_response.status_code == 200
        
        updated_bookings = verify_response.json().get("bookings", [])
        cancelled_booking = next((b for b in updated_bookings if b.get("booking_id") == booking_id), None)
        assert cancelled_booking is not None, "Cancelled booking should still exist"
        assert cancelled_booking.get("status") == "cancelled", f"Booking status should be 'cancelled', got {cancelled_booking.get('status')}"
        print("✓ Booking status verified as 'cancelled'")


class TestBookingPages:
    """Test booking pages list endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup authenticated session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200
    
    def test_get_booking_pages(self):
        """GET /api/booking/pages returns user's booking pages"""
        response = self.session.get(f"{BASE_URL}/api/booking/pages")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        pages = response.json()
        assert isinstance(pages, list), "Response should be a list of pages"
        print(f"✓ GET /api/booking/pages returned {len(pages)} pages")
        
        # Verify page structure
        if len(pages) > 0:
            page = pages[0]
            required_fields = ["page_id", "slug", "title", "weekdays", "slot_duration", "enabled"]
            for field in required_fields:
                assert field in page, f"Page should have {field} field"
            print(f"  Sample page: {page.get('title')} (slug: {page.get('slug')}, enabled: {page.get('enabled')})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
