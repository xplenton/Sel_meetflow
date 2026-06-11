"""
Iteration 222 - Comprehensive Backend Tests for:
- CHAT (1:1 DM + Group Chat + WS features)
- PROFILE (Avatar, CalDAV, iCal, DSGVO, Permissions)
- CALENDAR (Events, External CalDAV)
- SURVEYS (Surveys, Pulse-Checks, Feedback, Public Share Links)

Multi-Role: Admin + Member
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"
MEMBER_EMAIL = "member@meetflow.com"
MEMBER_PASSWORD = "11db7dbd77"


class TestAuth:
    """Authentication tests"""
    
    def test_admin_login(self):
        """Admin login returns token and user data"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        assert data.get("role") == "admin", f"Expected admin role, got {data.get('role')}"
        print(f"✓ Admin login successful: {data.get('name')}")
    
    def test_member_login(self):
        """Member login returns token and user data"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MEMBER_EMAIL,
            "password": MEMBER_PASSWORD
        })
        assert response.status_code == 200, f"Member login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        assert data.get("role") == "member", f"Expected member role, got {data.get('role')}"
        print(f"✓ Member login successful: {data.get('name')}")


@pytest.fixture(scope="class")
def admin_session():
    """Get admin session with auth token"""
    session = requests.Session()
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    session.headers.update({
        "Authorization": f"Bearer {data['token']}",
        "Content-Type": "application/json"
    })
    session.user_data = data
    return session


@pytest.fixture(scope="class")
def member_session():
    """Get member session with auth token"""
    session = requests.Session()
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": MEMBER_EMAIL,
        "password": MEMBER_PASSWORD
    })
    assert response.status_code == 200, f"Member login failed: {response.text}"
    data = response.json()
    session.headers.update({
        "Authorization": f"Bearer {data['token']}",
        "Content-Type": "application/json"
    })
    session.user_data = data
    return session


# ============ CHAT MODULE TESTS ============

class TestChatConversations:
    """Chat conversations CRUD tests"""
    
    def test_list_conversations_admin(self, admin_session):
        """Admin can list chat conversations"""
        response = admin_session.get(f"{BASE_URL}/api/chat/conversations")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of conversations"
        print(f"✓ Admin has {len(data)} conversations")
    
    def test_list_conversations_member(self, member_session):
        """Member can list chat conversations"""
        response = member_session.get(f"{BASE_URL}/api/chat/conversations")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of conversations"
        print(f"✓ Member has {len(data)} conversations")
    
    def test_list_chat_users(self, admin_session):
        """Admin can list users for new chat"""
        response = admin_session.get(f"{BASE_URL}/api/chat/users")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of users"
        assert len(data) > 0, "Expected at least one user"
        print(f"✓ Found {len(data)} users for chat")
    
    def test_create_direct_message(self, admin_session, member_session):
        """Admin creates DM with member"""
        member_id = member_session.user_data.get("user_id")
        response = admin_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [member_id]
        })
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        data = response.json()
        assert "conversation_id" in data, "No conversation_id in response"
        assert data.get("type") == "direct", "Expected direct type"
        print(f"✓ Created DM conversation: {data.get('conversation_id')}")
        return data.get("conversation_id")
    
    def test_create_group_chat(self, admin_session, member_session):
        """Admin creates group chat"""
        member_id = member_session.user_data.get("user_id")
        response = admin_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "group",
            "member_ids": [member_id],
            "name": f"TEST_Group_{uuid.uuid4().hex[:6]}"
        })
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        data = response.json()
        assert "conversation_id" in data, "No conversation_id in response"
        assert data.get("type") == "group", "Expected group type"
        print(f"✓ Created group chat: {data.get('name')}")
        return data.get("conversation_id")


class TestChatMessages:
    """Chat messages tests"""
    
    def test_send_message(self, admin_session, member_session):
        """Admin sends message to member"""
        # First create or get a DM
        member_id = member_session.user_data.get("user_id")
        conv_resp = admin_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [member_id]
        })
        assert conv_resp.status_code in [200, 201], f"Failed to create conv: {conv_resp.text}"
        conv_id = conv_resp.json().get("conversation_id")
        
        # Send message
        response = admin_session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", json={
            "content": f"TEST_Message_{uuid.uuid4().hex[:6]}",
            "mentions": [],
            "priority": "normal"
        })
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        data = response.json()
        assert "message_id" in data, "No message_id in response"
        assert "content" in data, "No content in response"
        print(f"✓ Sent message: {data.get('message_id')}")
        return data.get("message_id"), conv_id
    
    def test_get_messages(self, admin_session, member_session):
        """Get messages from conversation"""
        # Create DM and send message first
        member_id = member_session.user_data.get("user_id")
        conv_resp = admin_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [member_id]
        })
        conv_id = conv_resp.json().get("conversation_id")
        
        response = admin_session.get(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages?limit=50")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of messages"
        print(f"✓ Retrieved {len(data)} messages")
    
    def test_edit_message(self, admin_session, member_session):
        """Admin edits own message"""
        # Create DM and send message
        member_id = member_session.user_data.get("user_id")
        conv_resp = admin_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [member_id]
        })
        conv_id = conv_resp.json().get("conversation_id")
        
        msg_resp = admin_session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", json={
            "content": "Original message"
        })
        msg_id = msg_resp.json().get("message_id")
        
        # Edit message
        response = admin_session.put(f"{BASE_URL}/api/chat/messages/{msg_id}", json={
            "content": "Edited message"
        })
        assert response.status_code == 200, f"Failed: {response.text}"
        print(f"✓ Edited message: {msg_id}")
    
    def test_delete_message(self, admin_session, member_session):
        """Admin deletes own message"""
        # Create DM and send message
        member_id = member_session.user_data.get("user_id")
        conv_resp = admin_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [member_id]
        })
        conv_id = conv_resp.json().get("conversation_id")
        
        msg_resp = admin_session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", json={
            "content": "Message to delete"
        })
        msg_id = msg_resp.json().get("message_id")
        
        # Delete message
        response = admin_session.delete(f"{BASE_URL}/api/chat/messages/{msg_id}")
        assert response.status_code in [200, 204], f"Failed: {response.text}"
        print(f"✓ Deleted message: {msg_id}")
    
    def test_add_reaction(self, admin_session, member_session):
        """Add reaction to message"""
        # Create DM and send message
        member_id = member_session.user_data.get("user_id")
        conv_resp = admin_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [member_id]
        })
        conv_id = conv_resp.json().get("conversation_id")
        
        msg_resp = admin_session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", json={
            "content": "Message for reaction"
        })
        msg_id = msg_resp.json().get("message_id")
        
        # Add reaction
        response = admin_session.post(f"{BASE_URL}/api/chat/messages/{msg_id}/reactions", json={
            "emoji": "👍"
        })
        assert response.status_code == 200, f"Failed: {response.text}"
        print(f"✓ Added reaction to message: {msg_id}")


class TestChatFeatures:
    """Chat advanced features tests"""
    
    def test_pin_conversation(self, admin_session, member_session):
        """Pin a conversation"""
        # Create DM
        member_id = member_session.user_data.get("user_id")
        conv_resp = admin_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [member_id]
        })
        conv_id = conv_resp.json().get("conversation_id")
        
        response = admin_session.put(f"{BASE_URL}/api/chat/conversations/{conv_id}/pin")
        assert response.status_code == 200, f"Failed: {response.text}"
        print(f"✓ Pinned conversation: {conv_id}")
    
    def test_mute_conversation(self, admin_session, member_session):
        """Mute a conversation"""
        member_id = member_session.user_data.get("user_id")
        conv_resp = admin_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [member_id]
        })
        conv_id = conv_resp.json().get("conversation_id")
        
        response = admin_session.put(f"{BASE_URL}/api/chat/conversations/{conv_id}/mute")
        assert response.status_code == 200, f"Failed: {response.text}"
        print(f"✓ Muted conversation: {conv_id}")
    
    def test_search_messages(self, admin_session):
        """Search messages"""
        response = admin_session.get(f"{BASE_URL}/api/chat/search?q=test")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of search results"
        print(f"✓ Search returned {len(data)} results")
    
    def test_get_my_status(self, admin_session):
        """Get own chat status"""
        response = admin_session.get(f"{BASE_URL}/api/chat/my-status")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "status_mode" in data or "status" in data, "No status in response"
        print(f"✓ Got status: {data}")
    
    def test_read_status(self, admin_session, member_session):
        """Get read status for conversation"""
        member_id = member_session.user_data.get("user_id")
        conv_resp = admin_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [member_id]
        })
        conv_id = conv_resp.json().get("conversation_id")
        
        response = admin_session.get(f"{BASE_URL}/api/chat/conversations/{conv_id}/read-status")
        assert response.status_code == 200, f"Failed: {response.text}"
        print("✓ Got read status for conversation")


# ============ PROFILE MODULE TESTS ============

class TestProfile:
    """Profile management tests"""
    
    def test_get_profile(self, admin_session):
        """Get current user profile"""
        response = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "user_id" in data, "No user_id in response"
        assert "email" in data, "No email in response"
        print(f"✓ Got profile: {data.get('name')}")
    
    def test_update_profile(self, admin_session):
        """Update profile name and language"""
        response = admin_session.put(f"{BASE_URL}/api/users/me", json={
            "name": "Test Admin 418",
            "language": "de"
        })
        assert response.status_code == 200, f"Failed: {response.text}"
        print("✓ Updated profile")
    
    def test_update_auto_reply(self, admin_session):
        """Update auto-reply settings"""
        response = admin_session.put(f"{BASE_URL}/api/users/me", json={
            "auto_reply_enabled": True,
            "auto_reply_message": "Bin in Fokus-Modus, antworte spaeter!"
        })
        assert response.status_code == 200, f"Failed: {response.text}"
        print("✓ Updated auto-reply settings")
    
    def test_get_permissions(self, admin_session):
        """Get user permissions/capabilities"""
        response = admin_session.get(f"{BASE_URL}/api/users/me/permissions")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "role" in data or "capabilities" in data, "No permissions data"
        print(f"✓ Got permissions: role={data.get('role')}")
    
    def test_email_preferences(self, admin_session):
        """Update email preferences"""
        response = admin_session.put(f"{BASE_URL}/api/users/me/email-preferences", json={
            "newsletter_enabled": True,
            "meeting_invites_enabled": True,
            "digest_frequency": "daily"
        })
        assert response.status_code == 200, f"Failed: {response.text}"
        print("✓ Updated email preferences")
    
    def test_notification_preferences(self, admin_session):
        """Get notification preferences"""
        response = admin_session.get(f"{BASE_URL}/api/users/me/notification-prefs")
        assert response.status_code == 200, f"Failed: {response.text}"
        print("✓ Got notification preferences")


class TestCalDAV:
    """CalDAV/ICS integration tests"""
    
    def test_get_caldav_config(self, admin_session):
        """Get CalDAV configuration"""
        response = admin_session.get(f"{BASE_URL}/api/users/me/caldav")
        assert response.status_code == 200, f"Failed: {response.text}"
        print("✓ Got CalDAV config")
    
    def test_save_caldav_config(self, admin_session):
        """Save CalDAV configuration"""
        response = admin_session.put(f"{BASE_URL}/api/users/me/caldav", json={
            "enabled": False,
            "url": "",
            "username": "",
            "auto_sync": True
        })
        assert response.status_code == 200, f"Failed: {response.text}"
        print("✓ Saved CalDAV config")
    
    def test_get_ical_feed(self, admin_session):
        """Get iCal feed URL"""
        response = admin_session.get(f"{BASE_URL}/api/users/me/ical-feed")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "subscribe_url" in data or "webcal_url" in data, "No feed URL"
        print("✓ Got iCal feed URL")
    
    def test_regenerate_ical_feed(self, admin_session):
        """Regenerate iCal feed token"""
        response = admin_session.post(f"{BASE_URL}/api/users/me/ical-feed/rotate")
        assert response.status_code == 200, f"Failed: {response.text}"
        print("✓ Regenerated iCal feed")


class TestDSGVO:
    """DSGVO/Privacy tests"""
    
    def test_data_export(self, admin_session):
        """Export user data (DSGVO Art. 20)"""
        response = admin_session.get(f"{BASE_URL}/api/users/me/export")
        assert response.status_code == 200, f"Failed: {response.text}"
        # Should return JSON data
        data = response.json()
        assert "user" in data or "email" in data, "No user data in export"
        print("✓ Data export successful")


# ============ CALENDAR MODULE TESTS ============

class TestCalendar:
    """Calendar events tests"""
    
    def test_get_calendar_events(self, admin_session):
        """Get calendar events"""
        response = admin_session.get(f"{BASE_URL}/api/calendar/events")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of events"
        print(f"✓ Got {len(data)} calendar events")
    
    def test_get_caldav_events(self, admin_session):
        """Get external CalDAV events"""
        response = admin_session.get(f"{BASE_URL}/api/users/me/caldav-events?days=90")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "events" in data, "No events key in response"
        print(f"✓ Got {len(data.get('events', []))} external events")
    
    def test_get_busy_slots(self, admin_session):
        """Get busy slots"""
        response = admin_session.get(f"{BASE_URL}/api/users/me/busy-slots")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "slots" in data, "No slots key in response"
        print(f"✓ Got {len(data.get('slots', []))} busy slots")


# ============ SURVEYS MODULE TESTS ============

class TestSurveys:
    """Surveys CRUD tests"""
    
    def test_list_surveys(self, admin_session):
        """List published surveys"""
        response = admin_session.get(f"{BASE_URL}/api/surveys?status=published")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of surveys"
        print(f"✓ Got {len(data)} surveys")
    
    def test_create_survey(self, admin_session):
        """Admin creates survey"""
        response = admin_session.post(f"{BASE_URL}/api/surveys", json={
            "title": f"TEST_Survey_{uuid.uuid4().hex[:6]}",
            "description": "Test survey description",
            "survey_type": "survey",
            "anonymous": True,
            "status": "published",
            "target_all": True,
            "questions": [
                {
                    "question_id": f"q_{uuid.uuid4().hex[:6]}",
                    "text": "Test question?",
                    "type": "single_choice",
                    "options": ["Option A", "Option B", "Option C"],
                    "required": True
                }
            ]
        })
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        data = response.json()
        assert "survey_id" in data, "No survey_id in response"
        print(f"✓ Created survey: {data.get('survey_id')}")
        return data.get("survey_id")
    
    def test_get_survey_detail(self, admin_session):
        """Get survey detail"""
        # First create a survey
        create_resp = admin_session.post(f"{BASE_URL}/api/surveys", json={
            "title": f"TEST_Survey_{uuid.uuid4().hex[:6]}",
            "survey_type": "survey",
            "status": "published",
            "target_all": True,
            "questions": [{"question_id": "q1", "text": "Q?", "type": "free_text"}]
        })
        survey_id = create_resp.json().get("survey_id")
        
        response = admin_session.get(f"{BASE_URL}/api/surveys/{survey_id}")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data.get("survey_id") == survey_id, "Survey ID mismatch"
        print(f"✓ Got survey detail: {survey_id}")
    
    def test_surveys_pending_count(self, admin_session):
        """Get pending surveys count"""
        response = admin_session.get(f"{BASE_URL}/api/surveys/pending-count")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "count" in data, "No count in response"
        print(f"✓ Pending surveys: {data.get('count')}")


class TestPulseChecks:
    """Pulse-check tests"""
    
    def test_list_pulse_checks(self, admin_session):
        """List pulse checks"""
        response = admin_session.get(f"{BASE_URL}/api/pulse-checks")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of pulse checks"
        print(f"✓ Got {len(data)} pulse checks")
    
    def test_create_pulse_check(self, admin_session):
        """Admin creates pulse check"""
        response = admin_session.post(f"{BASE_URL}/api/surveys", json={
            "title": f"TEST_Pulse_{uuid.uuid4().hex[:6]}",
            "description": "How are you feeling?",
            "survey_type": "pulse_check",
            "anonymous": True,
            "status": "published",
            "target_all": True,
            "questions": [
                {
                    "question_id": f"q_{uuid.uuid4().hex[:6]}",
                    "text": "Wie geht es dir heute?",
                    "type": "scale",
                    "scale_min": 1,
                    "scale_max": 5,
                    "required": True
                }
            ]
        })
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        data = response.json()
        assert data.get("survey_type") == "pulse_check", "Wrong survey type"
        print(f"✓ Created pulse check: {data.get('survey_id')}")


class TestFeedback:
    """Feedback module tests"""
    
    def test_submit_feedback(self, member_session):
        """Member submits feedback"""
        response = member_session.post(f"{BASE_URL}/api/feedback/submit", json={
            "category": "ideas",
            "subject": f"TEST_Feedback_{uuid.uuid4().hex[:6]}",
            "content": "This is test feedback content",
            "anonymous": True
        })
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        data = response.json()
        # Anonymous feedback should return tracking code
        print(f"✓ Submitted feedback, tracking_code: {data.get('tracking_code')}")
        return data.get("tracking_code")
    
    def test_list_feedback_entries_admin(self, admin_session):
        """Admin lists feedback entries"""
        response = admin_session.get(f"{BASE_URL}/api/feedback/entries")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of feedback"
        print(f"✓ Admin sees {len(data)} feedback entries")
    
    def test_list_feedback_entries_member_forbidden(self, member_session):
        """Member cannot list all feedback entries"""
        response = member_session.get(f"{BASE_URL}/api/feedback/entries")
        # Should be forbidden for non-admin
        assert response.status_code in [403, 401], f"Expected 403, got {response.status_code}"
        print("✓ Member correctly forbidden from feedback list")
    
    def test_track_feedback(self, member_session):
        """Track feedback by code"""
        # First submit feedback
        submit_resp = member_session.post(f"{BASE_URL}/api/feedback/submit", json={
            "category": "improvements",
            "content": "Test feedback for tracking",
            "anonymous": True
        })
        tracking_code = submit_resp.json().get("tracking_code")
        
        if tracking_code:
            response = member_session.post(f"{BASE_URL}/api/feedback/track", json={
                "tracking_code": tracking_code
            })
            assert response.status_code == 200, f"Failed: {response.text}"
            data = response.json()
            assert "status" in data, "No status in tracking response"
            print(f"✓ Tracked feedback: status={data.get('status')}")
        else:
            print("⚠ No tracking code returned, skipping track test")


class TestSurveyResponse:
    """Survey response flow tests"""
    
    def test_member_responds_to_survey(self, admin_session, member_session):
        """Member responds to admin's survey"""
        # Admin creates survey
        create_resp = admin_session.post(f"{BASE_URL}/api/surveys", json={
            "title": f"TEST_Survey_Response_{uuid.uuid4().hex[:6]}",
            "survey_type": "survey",
            "anonymous": False,
            "status": "published",
            "target_all": True,
            "questions": [
                {
                    "question_id": "q1",
                    "text": "What is your favorite color?",
                    "type": "single_choice",
                    "options": ["Red", "Blue", "Green"],
                    "required": True
                }
            ]
        })
        survey_id = create_resp.json().get("survey_id")
        
        # Member responds
        response = member_session.post(f"{BASE_URL}/api/surveys/{survey_id}/respond", json={
            "answers": {"q1": "Blue"}
        })
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        print(f"✓ Member responded to survey: {survey_id}")
    
    def test_get_survey_results(self, admin_session):
        """Admin gets survey results"""
        # Create survey with response
        create_resp = admin_session.post(f"{BASE_URL}/api/surveys", json={
            "title": f"TEST_Survey_Results_{uuid.uuid4().hex[:6]}",
            "survey_type": "survey",
            "status": "published",
            "target_all": True,
            "questions": [{"question_id": "q1", "text": "Q?", "type": "free_text"}]
        })
        survey_id = create_resp.json().get("survey_id")
        
        response = admin_session.get(f"{BASE_URL}/api/surveys/{survey_id}/results")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "total_responses" in data or "results" in data, "No results data"
        print(f"✓ Got survey results: {data.get('total_responses', 0)} responses")


class TestInteractionStats:
    """Interaction stats tests (admin only)"""
    
    def test_get_interaction_stats_admin(self, admin_session):
        """Admin gets interaction stats"""
        response = admin_session.get(f"{BASE_URL}/api/interaction-stats")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        print("✓ Got interaction stats")
    
    def test_get_interaction_stats_member_forbidden(self, member_session):
        """Member cannot get interaction stats"""
        response = member_session.get(f"{BASE_URL}/api/interaction-stats")
        assert response.status_code in [403, 401], f"Expected 403, got {response.status_code}"
        print("✓ Member correctly forbidden from interaction stats")


# ============ CROSS-ROLE TESTS ============

class TestCrossRole:
    """Cross-role interaction tests"""
    
    def test_admin_dm_to_member_member_sees(self, admin_session, member_session):
        """Admin sends DM, member can see it"""
        member_id = member_session.user_data.get("user_id")
        
        # Admin creates DM
        conv_resp = admin_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [member_id]
        })
        conv_id = conv_resp.json().get("conversation_id")
        
        # Admin sends message
        admin_session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", json={
            "content": f"TEST_CrossRole_{uuid.uuid4().hex[:6]}"
        })
        
        # Member checks conversations
        member_convs = member_session.get(f"{BASE_URL}/api/chat/conversations").json()
        found = any(c.get("conversation_id") == conv_id for c in member_convs)
        assert found, "Member should see the DM conversation"
        print("✓ Member sees admin's DM conversation")
    
    def test_admin_creates_survey_member_participates(self, admin_session, member_session):
        """Admin creates survey, member participates, admin sees aggregated results"""
        # Admin creates anonymous survey
        create_resp = admin_session.post(f"{BASE_URL}/api/surveys", json={
            "title": f"TEST_CrossRole_Survey_{uuid.uuid4().hex[:6]}",
            "survey_type": "survey",
            "anonymous": True,
            "status": "published",
            "target_all": True,
            "questions": [
                {
                    "question_id": "q1",
                    "text": "Rate this feature",
                    "type": "scale",
                    "scale_min": 1,
                    "scale_max": 5,
                    "required": True
                }
            ]
        })
        survey_id = create_resp.json().get("survey_id")
        
        # Member responds
        member_session.post(f"{BASE_URL}/api/surveys/{survey_id}/respond", json={
            "answers": {"q1": 4}
        })
        
        # Admin checks results
        results_resp = admin_session.get(f"{BASE_URL}/api/surveys/{survey_id}/results")
        assert results_resp.status_code == 200
        results = results_resp.json()
        assert results.get("total_responses", 0) >= 1, "Should have at least 1 response"
        print("✓ Cross-role survey flow: Admin creates → Member responds → Admin sees results")


# ============ CLEANUP ============

class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_surveys(self, admin_session):
        """Delete TEST_ prefixed surveys"""
        surveys = admin_session.get(f"{BASE_URL}/api/surveys?status=published").json()
        deleted = 0
        for s in surveys:
            if s.get("title", "").startswith("TEST_"):
                admin_session.delete(f"{BASE_URL}/api/surveys/{s['survey_id']}")
                deleted += 1
        print(f"✓ Cleaned up {deleted} test surveys")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
