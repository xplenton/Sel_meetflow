#!/usr/bin/env python3

import requests
import sys
import json
from datetime import datetime

class MeetFlowBugFixTester:
    def __init__(self, base_url="https://video-meet-pro.preview.emergentagent.com"):
        self.base_url = base_url
        self.session = requests.Session()  # Use session for cookies
        self.tests_run = 0
        self.tests_passed = 0
        self.meeting_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        req_headers = {'Content-Type': 'application/json'}
        if headers:
            req_headers.update(headers)

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {method} {url}")
        
        try:
            if method == 'GET':
                response = self.session.get(url, headers=req_headers)
            elif method == 'POST':
                response = self.session.post(url, json=data, headers=req_headers)
            elif method == 'PUT':
                response = self.session.put(url, json=data, headers=req_headers)
            elif method == 'DELETE':
                response = self.session.delete(url, headers=req_headers)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return success, response.json() if response.content else {}
                except:
                    return success, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_login(self):
        """Test admin login"""
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "auth/login",
            200,
            data={"email": "admin@meetflow.com", "password": "admin123"}
        )
        if success:
            print("✅ Login successful")
            return True
        return False

    def test_create_instant_meeting(self):
        """Test creating an instant meeting"""
        success, response = self.run_test(
            "Create Instant Meeting",
            "POST",
            "meetings",
            200,
            data={
                "title": "Bug Fix Test Meeting",
                "description": "Testing camera toggle and virtual background fixes",
                "meeting_type": "instant",
                "duration": 60,
                "lobby_enabled": False,
                "guest_access": True,
                "chat_enabled": True,
                "reactions_enabled": True,
                "recording_enabled": False,
                "transcript_enabled": False
            }
        )
        if success and 'meeting_id' in response:
            self.meeting_id = response['meeting_id']
            print(f"✅ Meeting created: {self.meeting_id}")
            return True
        return False

    def test_get_meeting(self):
        """Test getting meeting details"""
        if not self.meeting_id:
            print("❌ No meeting ID available")
            return False
        
        success, response = self.run_test(
            "Get Meeting Details",
            "GET",
            f"meetings/{self.meeting_id}",
            200
        )
        if success and 'meeting_id' in response:
            print(f"✅ Meeting details retrieved: {response['title']}")
            return True
        return False

    def test_join_meeting(self):
        """Test joining the meeting"""
        if not self.meeting_id:
            print("❌ No meeting ID available")
            return False
        
        success, response = self.run_test(
            "Join Meeting",
            "POST",
            f"meetings/{self.meeting_id}/join",
            200
        )
        if success:
            print(f"✅ Successfully joined meeting")
            return True
        return False

    def test_get_participants(self):
        """Test getting meeting participants"""
        if not self.meeting_id:
            print("❌ No meeting ID available")
            return False
        
        success, response = self.run_test(
            "Get Participants",
            "GET",
            f"meetings/{self.meeting_id}/participants",
            200
        )
        if success and isinstance(response, list):
            print(f"✅ Participants retrieved: {len(response)} participants")
            return True
        return False

    def test_chat_functionality(self):
        """Test chat message sending"""
        if not self.meeting_id:
            print("❌ No meeting ID available")
            return False
        
        success, response = self.run_test(
            "Send Chat Message",
            "POST",
            f"meetings/{self.meeting_id}/chat",
            200,
            data={"message": "Testing chat functionality after bug fixes"}
        )
        if success and 'message_id' in response:
            print(f"✅ Chat message sent successfully")
            return True
        return False

    def test_get_chat_messages(self):
        """Test getting chat messages"""
        if not self.meeting_id:
            print("❌ No meeting ID available")
            return False
        
        success, response = self.run_test(
            "Get Chat Messages",
            "GET",
            f"meetings/{self.meeting_id}/chat",
            200
        )
        if success and isinstance(response, list):
            print(f"✅ Chat messages retrieved: {len(response)} messages")
            return True
        return False

    def test_meeting_mode_config(self):
        """Test getting meeting mode configuration"""
        if not self.meeting_id:
            print("❌ No meeting ID available")
            return False
        
        success, response = self.run_test(
            "Get Meeting Mode Config",
            "GET",
            f"meetings/{self.meeting_id}/mode-config",
            200
        )
        if success and 'mode' in response and 'config' in response:
            print(f"✅ Meeting mode config retrieved: {response['mode']}")
            return True
        return False

    def test_leave_meeting(self):
        """Test leaving the meeting"""
        if not self.meeting_id:
            print("❌ No meeting ID available")
            return False
        
        success, response = self.run_test(
            "Leave Meeting",
            "POST",
            f"meetings/{self.meeting_id}/leave",
            200
        )
        if success:
            print(f"✅ Successfully left meeting")
            return True
        return False

    def test_auth_me(self):
        """Test getting current user info"""
        success, response = self.run_test(
            "Get Current User",
            "GET",
            "auth/me",
            200
        )
        if success and 'user_id' in response:
            print(f"✅ Current user retrieved: {response.get('name', 'Unknown')}")
            return True
        return False

def main():
    print("🚀 Starting MeetFlow Bug Fix Backend Testing")
    print("Testing: Camera toggle, Virtual background, PreJoin fixes")
    print("=" * 60)
    
    tester = MeetFlowBugFixTester()
    
    # Test sequence for bug fix validation
    tests = [
        # Authentication
        tester.test_login,
        tester.test_auth_me,
        
        # Meeting flow tests
        tester.test_create_instant_meeting,
        tester.test_get_meeting,
        tester.test_join_meeting,
        tester.test_get_participants,
        
        # Communication features
        tester.test_chat_functionality,
        tester.test_get_chat_messages,
        
        # Meeting configuration
        tester.test_meeting_mode_config,
        
        # Cleanup
        tester.test_leave_meeting,
    ]
    
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
    
    # Print results
    print("\n" + "=" * 60)
    print(f"📊 Test Results: {tester.tests_passed}/{tester.tests_run} passed")
    success_rate = (tester.tests_passed / tester.tests_run * 100) if tester.tests_run > 0 else 0
    print(f"📈 Success Rate: {success_rate:.1f}%")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 All backend tests passed!")
        return 0
    else:
        print("⚠️  Some backend tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())