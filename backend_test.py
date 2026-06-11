#!/usr/bin/env python3

import requests
import sys
import json
import time
from datetime import datetime

class ConsentFlowTester:
    def __init__(self, base_url="https://video-meet-pro.preview.emergentagent.com"):
        self.base_url = base_url
        self.admin_session = requests.Session()
        self.user2_session = requests.Session()
        self.current_session = self.admin_session
        self.tests_run = 0
        self.tests_passed = 0
        self.meeting_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        if headers:
            test_headers.update(headers)

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = self.current_session.get(url, headers=test_headers)
            elif method == 'POST':
                response = self.current_session.post(url, json=data, headers=test_headers)
            elif method == 'PUT':
                response = self.current_session.put(url, json=data, headers=test_headers)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return success, response.json()
                except:
                    return success, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    print(f"   Response: {response.json()}")
                except:
                    print(f"   Response: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def login_admin(self):
        """Login as admin"""
        self.current_session = self.admin_session
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "auth/login",
            200,
            data={"email": "admin@meetflow.com", "password": "admin123"}
        )
        return success

    def login_user2(self):
        """Login as user2"""
        self.current_session = self.user2_session
        success, response = self.run_test(
            "User2 Login",
            "POST", 
            "auth/login",
            200,
            data={"email": "user2@test.com", "password": "test123"}
        )
        return success

    def create_test_meeting(self):
        """Create a test meeting"""
        success, response = self.run_test(
            "Create Test Meeting",
            "POST",
            "meetings",
            200,
            data={
                "title": "Consent Flow Test Meeting",
                "description": "Testing recording/transcript consent",
                "meeting_type": "instant",
                "invited_emails": ["user2@test.com"]
            }
        )
        if success and 'meeting_id' in response:
            self.meeting_id = response['meeting_id']
            print(f"   Created meeting: {self.meeting_id}")
            return True
        return False

    def join_meeting_as_user2(self):
        """Join meeting as user2"""
        if not self.meeting_id:
            return False
        
        success, response = self.run_test(
            "User2 Join Meeting",
            "POST",
            f"meetings/{self.meeting_id}/join",
            200
        )
        return success

    def test_recording_consent_solo_host(self):
        """Test recording consent with solo host (should start immediately)"""
        if not self.meeting_id:
            return False
            
        success, response = self.run_test(
            "Recording Request (Solo Host)",
            "POST",
            f"meetings/{self.meeting_id}/recording/request",
            200
        )
        
        if success:
            if response.get('immediate'):
                print("   ✅ Solo host recording started immediately")
                return True
            else:
                print("   ❌ Expected immediate start for solo host")
                return False
        return False

    def test_recording_consent_multiple_participants(self):
        """Test recording consent with multiple participants"""
        if not self.meeting_id:
            return False
            
        success, response = self.run_test(
            "Recording Request (Multiple Participants)",
            "POST",
            f"meetings/{self.meeting_id}/recording/request",
            200
        )
        
        if success:
            if response.get('status') == 'consent_pending':
                print(f"   ✅ Consent pending for {response.get('awaiting', 0)} participants")
                return response.get('consent_id')
            else:
                print("   ❌ Expected consent_pending status")
                return False
        return False

    def test_transcript_consent_multiple_participants(self):
        """Test transcript consent with multiple participants"""
        if not self.meeting_id:
            return False
            
        success, response = self.run_test(
            "Transcript Request (Multiple Participants)",
            "POST",
            f"meetings/{self.meeting_id}/transcript/request",
            200
        )
        
        if success:
            if response.get('status') == 'consent_pending':
                print(f"   ✅ Consent pending for {response.get('awaiting', 0)} participants")
                return response.get('consent_id')
            else:
                print("   ❌ Expected consent_pending status")
                return False
        return False

    def test_consent_accept(self, consent_id):
        """Test accepting a consent request"""
        if not consent_id:
            return False
            
        success, response = self.run_test(
            "Accept Consent",
            "POST",
            f"meetings/{self.meeting_id}/consent/{consent_id}/respond",
            200,
            data={"response": "accepted"}
        )
        
        if success:
            print(f"   ✅ Consent response: {response.get('status', 'unknown')}")
            return response.get('status') == 'approved'
        return False

    def test_consent_decline(self, consent_id):
        """Test declining a consent request"""
        if not consent_id:
            return False
            
        success, response = self.run_test(
            "Decline Consent",
            "POST",
            f"meetings/{self.meeting_id}/consent/{consent_id}/respond",
            200,
            data={"response": "declined"}
        )
        
        if success:
            print(f"   ✅ Consent response: {response.get('status', 'unknown')}")
            return response.get('status') == 'rejected'
        return False

    def debug_meeting_state(self):
        """Debug meeting state"""
        if not self.meeting_id:
            return False
            
        success, response = self.run_test(
            "Debug Meeting State",
            "GET",
            f"meetings/{self.meeting_id}",
            200
        )
        
        if success:
            print(f"   Meeting participants: {len(response.get('participants', []))}")
            for p in response.get('participants', []):
                print(f"   - {p.get('name', 'Unknown')} ({p.get('role', 'unknown')}) - Joined: {p.get('joined_at') is not None}")
            return True
        return False

    def test_get_active_consents(self):
        """Test getting active consent requests"""
        if not self.meeting_id:
            return False
            
        success, response = self.run_test(
            "Get Active Consents",
            "GET",
            f"meetings/{self.meeting_id}/consent/active",
            200
        )
        
        if success:
            print(f"   ✅ Found {len(response)} active consent(s)")
            return True
        return False

    def test_recording_stop(self):
        """Test stopping recording"""
        if not self.meeting_id:
            return False
            
        success, response = self.run_test(
            "Stop Recording",
            "POST",
            f"meetings/{self.meeting_id}/recording/stop",
            200
        )
        
        if success:
            print(f"   ✅ Recording stopped: {response.get('recording_id', 'unknown')}")
            return True
        return False

    def test_transcript_stop(self):
        """Test stopping transcript"""
        if not self.meeting_id:
            return False
            
        success, response = self.run_test(
            "Stop Transcript",
            "POST",
            f"meetings/{self.meeting_id}/transcript/stop",
            200
        )
        
        if success:
            print(f"   ✅ Transcript stopped: {response.get('transcript_id', 'unknown')}")
            return True
        return False

def main():
    print("🚀 Starting Recording/Transcript Consent Flow Tests")
    print("=" * 60)
    
    tester = ConsentFlowTester()
    
    # Login tests
    if not tester.login_admin():
        print("❌ Admin login failed, stopping tests")
        return 1
    
    if not tester.login_user2():
        print("❌ User2 login failed, stopping tests")
        return 1
    
    # Create meeting
    if not tester.create_test_meeting():
        print("❌ Meeting creation failed, stopping tests")
        return 1
    
    # Test solo host recording (should start immediately)
    print("\n📹 Testing Solo Host Recording...")
    tester.test_recording_consent_solo_host()
    
    # Stop recording to reset state
    tester.test_recording_stop()
    
    # Test multiple participant consent flow
    print("\n👥 Testing Multiple Participant Consent Flow...")
    
    # Switch to user2 session for joining
    print("\n🔄 Switching to User2 session...")
    tester.current_session = tester.user2_session
    tester.join_meeting_as_user2()
    
    # Switch back to admin for host actions
    print("\n🔄 Switching back to Admin session...")
    tester.current_session = tester.admin_session
    
    # Test recording consent with multiple participants
    recording_consent_id = tester.test_recording_consent_multiple_participants()
    
    # Test transcript consent with multiple participants  
    transcript_consent_id = tester.test_transcript_consent_multiple_participants()
    
    # Test getting active consents
    tester.debug_meeting_state()
    tester.test_get_active_consents()
    
    # Test consent responses
    if recording_consent_id:
        print("\n✅ Testing Consent Accept...")
        # Switch to user2 to accept consent
        tester.current_session = tester.user2_session
        tester.test_consent_accept(recording_consent_id)
        
        # Switch back to admin
        tester.current_session = tester.admin_session
        tester.test_recording_stop()
    
    if transcript_consent_id:
        print("\n❌ Testing Consent Decline...")
        # Switch to user2 to decline consent
        tester.current_session = tester.user2_session
        tester.test_consent_decline(transcript_consent_id)
        
        # Switch back to admin
        tester.current_session = tester.admin_session
    
    # Final results
    print("\n" + "=" * 60)
    print(f"📊 Test Results: {tester.tests_passed}/{tester.tests_run} passed")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())