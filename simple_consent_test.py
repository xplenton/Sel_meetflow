#!/usr/bin/env python3

import requests
import sys
import json
import time
from datetime import datetime

class SimpleConsentTester:
    def __init__(self, base_url="https://video-meet-pro.preview.emergentagent.com"):
        self.base_url = base_url
        self.session = requests.Session()
        self.tests_run = 0
        self.tests_passed = 0
        self.meeting_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = self.session.get(url, headers=headers)
            elif method == 'POST':
                response = self.session.post(url, json=data, headers=headers)

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
                    error_data = response.json()
                    print(f"   Response: {error_data}")
                except:
                    print(f"   Response: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_basic_consent_endpoints(self):
        """Test basic consent endpoints without complex flows"""
        
        # Login as admin
        success, _ = self.run_test(
            "Admin Login",
            "POST",
            "auth/login",
            200,
            data={"email": "admin@meetflow.com", "password": "admin123"}
        )
        if not success:
            return False

        # Create meeting
        success, response = self.run_test(
            "Create Meeting",
            "POST",
            "meetings",
            200,
            data={
                "title": "Consent Test Meeting",
                "meeting_type": "instant"
            }
        )
        if not success:
            return False
        
        self.meeting_id = response.get('meeting_id')
        print(f"   Created meeting: {self.meeting_id}")

        # Test recording request (solo host - should start immediately)
        success, response = self.run_test(
            "Recording Request (Solo)",
            "POST",
            f"meetings/{self.meeting_id}/recording/request",
            200
        )
        if success and response.get('immediate'):
            print("   ✅ Solo host recording started immediately")
        
        # Test recording stop
        success, response = self.run_test(
            "Recording Stop",
            "POST",
            f"meetings/{self.meeting_id}/recording/stop",
            200
        )
        if success:
            print(f"   ✅ Recording stopped: {response.get('recording_id')}")

        # Test transcript request (solo host - should start immediately)
        success, response = self.run_test(
            "Transcript Request (Solo)",
            "POST",
            f"meetings/{self.meeting_id}/transcript/request",
            200
        )
        if success and response.get('immediate'):
            print("   ✅ Solo host transcript started immediately")

        # Test transcript stop
        success, response = self.run_test(
            "Transcript Stop",
            "POST",
            f"meetings/{self.meeting_id}/transcript/stop",
            200
        )
        if success:
            print(f"   ✅ Transcript stopped: {response.get('transcript_id')}")

        # Test get active consents (should be empty)
        success, response = self.run_test(
            "Get Active Consents",
            "GET",
            f"meetings/{self.meeting_id}/consent/active",
            200
        )
        if success:
            print(f"   ✅ Found {len(response)} active consents")

        return True

    def test_consent_endpoints_with_fake_consent(self):
        """Test consent response endpoints with a fake consent ID"""
        if not self.meeting_id:
            return False

        # Try to respond to a non-existent consent (should fail gracefully)
        success, response = self.run_test(
            "Respond to Non-existent Consent",
            "POST",
            f"meetings/{self.meeting_id}/consent/fake_consent_id/respond",
            404,  # Expecting 404 for non-existent consent
            data={"response": "accepted"}
        )
        if success:
            print("   ✅ Correctly handled non-existent consent")

        return True

def main():
    print("🚀 Starting Simple Consent Flow Tests")
    print("=" * 50)
    
    tester = SimpleConsentTester()
    
    # Test basic endpoints
    if not tester.test_basic_consent_endpoints():
        print("❌ Basic consent tests failed")
        return 1
    
    # Test edge cases
    if not tester.test_consent_endpoints_with_fake_consent():
        print("❌ Edge case tests failed")
        return 1
    
    # Results
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {tester.tests_passed}/{tester.tests_run} passed")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())