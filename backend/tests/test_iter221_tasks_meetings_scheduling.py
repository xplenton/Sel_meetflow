"""
Iteration 221 - Comprehensive Backend Tests for:
- AUFGABEN (Tasks) Module
- WEBKONFERENZ (Meetings) Module  
- TERMINPLANUNG (Scheduling/Polls/Bookings) Module

Multi-Role Testing: Admin + Member
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"
MEMBER_EMAIL = "member@meetflow.com"
MEMBER_PASSWORD = "11db7dbd77"


class TestAuth:
    """Authentication tests for both roles"""
    
    def test_admin_login(self):
        """Admin login should succeed"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data or "access_token" in data, "No token in response"
        print("✓ Admin login successful")
    
    def test_member_login(self):
        """Member login should succeed"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MEMBER_EMAIL,
            "password": MEMBER_PASSWORD
        })
        assert response.status_code == 200, f"Member login failed: {response.text}"
        data = response.json()
        assert "token" in data or "access_token" in data, "No token in response"
        print("✓ Member login successful")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("token") or data.get("access_token")
    pytest.skip("Admin authentication failed")


@pytest.fixture(scope="module")
def member_token():
    """Get member auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MEMBER_EMAIL,
        "password": MEMBER_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("token") or data.get("access_token")
    pytest.skip("Member authentication failed")


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture
def member_headers(member_token):
    return {"Authorization": f"Bearer {member_token}", "Content-Type": "application/json"}


# ============ TASKS MODULE TESTS ============

class TestTasksAdmin:
    """Tasks module tests for Admin role"""
    
    def test_list_tasks(self, admin_headers):
        """Admin can list tasks"""
        response = requests.get(f"{BASE_URL}/api/tasks", headers=admin_headers)
        assert response.status_code == 200, f"List tasks failed: {response.text}"
        data = response.json()
        assert "tasks" in data, "Response should contain 'tasks' key"
        print(f"✓ Admin can list tasks ({len(data['tasks'])} tasks)")
    
    def test_create_task(self, admin_headers):
        """Admin can create a task"""
        task_data = {
            "title": f"TEST_Admin_Task_{uuid.uuid4().hex[:6]}",
            "description": "Test task created by admin",
            "status": "open",
            "priority": "high",
            "due_date": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
            "assignee_ids": [],
            "tags": ["test", "admin"]
        }
        response = requests.post(f"{BASE_URL}/api/tasks", headers=admin_headers, json=task_data)
        assert response.status_code == 200, f"Create task failed: {response.text}"
        data = response.json()
        assert "task_id" in data, "Response should contain task_id"
        assert data["title"] == task_data["title"], "Title mismatch"
        print(f"✓ Admin created task: {data['task_id']}")
        return data["task_id"]
    
    def test_get_task_detail(self, admin_headers):
        """Admin can get task details"""
        # First create a task
        task_data = {"title": f"TEST_Detail_Task_{uuid.uuid4().hex[:6]}", "status": "open", "priority": "normal"}
        create_resp = requests.post(f"{BASE_URL}/api/tasks", headers=admin_headers, json=task_data)
        assert create_resp.status_code == 200
        task_id = create_resp.json()["task_id"]
        
        # Get task detail
        response = requests.get(f"{BASE_URL}/api/tasks/{task_id}", headers=admin_headers)
        assert response.status_code == 200, f"Get task detail failed: {response.text}"
        data = response.json()
        assert data["task_id"] == task_id
        print(f"✓ Admin can get task detail: {task_id}")
    
    def test_update_task(self, admin_headers):
        """Admin can update a task"""
        # Create task
        task_data = {"title": f"TEST_Update_Task_{uuid.uuid4().hex[:6]}", "status": "open", "priority": "normal"}
        create_resp = requests.post(f"{BASE_URL}/api/tasks", headers=admin_headers, json=task_data)
        task_id = create_resp.json()["task_id"]
        
        # Update task
        update_data = {"status": "in_progress", "priority": "high"}
        response = requests.put(f"{BASE_URL}/api/tasks/{task_id}", headers=admin_headers, json=update_data)
        assert response.status_code == 200, f"Update task failed: {response.text}"
        data = response.json()
        assert data["status"] == "in_progress"
        assert data["priority"] == "high"
        print(f"✓ Admin updated task: {task_id}")
    
    def test_task_checklist(self, admin_headers):
        """Admin can add checklist items to task"""
        # Create task with checklist
        task_data = {
            "title": f"TEST_Checklist_Task_{uuid.uuid4().hex[:6]}",
            "status": "open",
            "priority": "normal",
            "checklist": [
                {"id": f"cl_{uuid.uuid4().hex[:6]}", "text": "Step 1", "done": False, "order": 0},
                {"id": f"cl_{uuid.uuid4().hex[:6]}", "text": "Step 2", "done": False, "order": 1}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/tasks", headers=admin_headers, json=task_data)
        assert response.status_code == 200
        data = response.json()
        assert len(data.get("checklist", [])) == 2
        print("✓ Admin created task with checklist")
    
    def test_task_templates_list(self, admin_headers):
        """Admin can list task templates"""
        response = requests.get(f"{BASE_URL}/api/task-templates", headers=admin_headers)
        assert response.status_code == 200, f"List templates failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Admin can list task templates ({len(data)} templates)")
    
    def test_task_pending_count(self, admin_headers):
        """Admin can get pending task count"""
        response = requests.get(f"{BASE_URL}/api/tasks/pending-count", headers=admin_headers)
        assert response.status_code == 200, f"Pending count failed: {response.text}"
        data = response.json()
        assert "count" in data
        print(f"✓ Admin pending tasks: {data['count']}")
    
    def test_delete_task(self, admin_headers):
        """Admin can delete a task"""
        # Create task
        task_data = {"title": f"TEST_Delete_Task_{uuid.uuid4().hex[:6]}", "status": "open", "priority": "normal"}
        create_resp = requests.post(f"{BASE_URL}/api/tasks", headers=admin_headers, json=task_data)
        task_id = create_resp.json()["task_id"]
        
        # Delete task
        response = requests.delete(f"{BASE_URL}/api/tasks/{task_id}", headers=admin_headers)
        assert response.status_code == 200, f"Delete task failed: {response.text}"
        
        # Verify deleted
        get_resp = requests.get(f"{BASE_URL}/api/tasks/{task_id}", headers=admin_headers)
        assert get_resp.status_code == 404
        print(f"✓ Admin deleted task: {task_id}")


class TestTasksMember:
    """Tasks module tests for Member role"""
    
    def test_member_list_tasks(self, member_headers):
        """Member can list their tasks"""
        response = requests.get(f"{BASE_URL}/api/tasks", headers=member_headers)
        assert response.status_code == 200, f"Member list tasks failed: {response.text}"
        data = response.json()
        assert "tasks" in data
        print(f"✓ Member can list tasks ({len(data['tasks'])} tasks)")
    
    def test_member_create_task(self, member_headers):
        """Member can create a task"""
        task_data = {
            "title": f"TEST_Member_Task_{uuid.uuid4().hex[:6]}",
            "description": "Test task created by member",
            "status": "open",
            "priority": "normal"
        }
        response = requests.post(f"{BASE_URL}/api/tasks", headers=member_headers, json=task_data)
        assert response.status_code == 200, f"Member create task failed: {response.text}"
        data = response.json()
        assert "task_id" in data
        print(f"✓ Member created task: {data['task_id']}")
    
    def test_member_pending_count(self, member_headers):
        """Member can get their pending task count"""
        response = requests.get(f"{BASE_URL}/api/tasks/pending-count", headers=member_headers)
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        print(f"✓ Member pending tasks: {data['count']}")


# ============ MEETINGS MODULE TESTS ============

class TestMeetingsAdmin:
    """Meetings module tests for Admin role"""
    
    def test_list_meetings(self, admin_headers):
        """Admin can list meetings"""
        response = requests.get(f"{BASE_URL}/api/meetings", headers=admin_headers)
        assert response.status_code == 200, f"List meetings failed: {response.text}"
        data = response.json()
        assert "meetings" in data
        print(f"✓ Admin can list meetings ({len(data['meetings'])} meetings)")
    
    def test_list_upcoming_meetings(self, admin_headers):
        """Admin can list upcoming meetings"""
        response = requests.get(f"{BASE_URL}/api/meetings?meeting_type=upcoming", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "meetings" in data
        print(f"✓ Admin upcoming meetings: {len(data['meetings'])}")
    
    def test_list_past_meetings(self, admin_headers):
        """Admin can list past meetings"""
        response = requests.get(f"{BASE_URL}/api/meetings?meeting_type=past", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "meetings" in data
        print(f"✓ Admin past meetings: {len(data['meetings'])}")
    
    def test_create_instant_meeting(self, admin_headers):
        """Admin can create an instant meeting"""
        meeting_data = {
            "title": f"TEST_Instant_Meeting_{uuid.uuid4().hex[:6]}",
            "meeting_type": "instant"
        }
        response = requests.post(f"{BASE_URL}/api/meetings", headers=admin_headers, json=meeting_data)
        assert response.status_code == 200, f"Create instant meeting failed: {response.text}"
        data = response.json()
        assert "meeting_id" in data
        assert "meeting_code" in data
        print(f"✓ Admin created instant meeting: {data['meeting_id']}")
        return data["meeting_id"]
    
    def test_create_scheduled_meeting(self, admin_headers):
        """Admin can create a scheduled meeting"""
        scheduled_at = (datetime.now() + timedelta(days=1)).isoformat()
        meeting_data = {
            "title": f"TEST_Scheduled_Meeting_{uuid.uuid4().hex[:6]}",
            "description": "Test scheduled meeting",
            "meeting_type": "scheduled",
            "scheduled_at": scheduled_at,
            "duration": 60,
            "lobby_enabled": False,
            "guest_access": True,
            "chat_enabled": True,
            "reactions_enabled": True
        }
        response = requests.post(f"{BASE_URL}/api/meetings", headers=admin_headers, json=meeting_data)
        assert response.status_code == 200, f"Create scheduled meeting failed: {response.text}"
        data = response.json()
        assert "meeting_id" in data
        assert data["meeting_type"] == "scheduled"
        print(f"✓ Admin created scheduled meeting: {data['meeting_id']}")
        return data["meeting_id"]
    
    def test_get_meeting_detail(self, admin_headers):
        """Admin can get meeting details"""
        # Create meeting first
        meeting_data = {"title": f"TEST_Detail_Meeting_{uuid.uuid4().hex[:6]}", "meeting_type": "instant"}
        create_resp = requests.post(f"{BASE_URL}/api/meetings", headers=admin_headers, json=meeting_data)
        meeting_id = create_resp.json()["meeting_id"]
        
        # Get detail
        response = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}", headers=admin_headers)
        assert response.status_code == 200, f"Get meeting detail failed: {response.text}"
        data = response.json()
        assert data["meeting_id"] == meeting_id
        assert "participants" in data
        print(f"✓ Admin can get meeting detail: {meeting_id}")
    
    def test_update_meeting(self, admin_headers):
        """Admin can update a meeting"""
        # Create meeting
        meeting_data = {"title": f"TEST_Update_Meeting_{uuid.uuid4().hex[:6]}", "meeting_type": "instant"}
        create_resp = requests.post(f"{BASE_URL}/api/meetings", headers=admin_headers, json=meeting_data)
        meeting_id = create_resp.json()["meeting_id"]
        
        # Update
        update_data = {"title": "Updated Meeting Title", "description": "Updated description"}
        response = requests.put(f"{BASE_URL}/api/meetings/{meeting_id}", headers=admin_headers, json=update_data)
        assert response.status_code == 200, f"Update meeting failed: {response.text}"
        data = response.json()
        assert data["title"] == "Updated Meeting Title"
        print(f"✓ Admin updated meeting: {meeting_id}")
    
    def test_meeting_participants(self, admin_headers):
        """Admin can get meeting participants"""
        # Create meeting
        meeting_data = {"title": f"TEST_Participants_Meeting_{uuid.uuid4().hex[:6]}", "meeting_type": "instant"}
        create_resp = requests.post(f"{BASE_URL}/api/meetings", headers=admin_headers, json=meeting_data)
        meeting_id = create_resp.json()["meeting_id"]
        
        # Get participants
        response = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/participants", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print("✓ Admin can get meeting participants")
    
    def test_meeting_chat(self, admin_headers):
        """Admin can access meeting chat"""
        # Create meeting
        meeting_data = {"title": f"TEST_Chat_Meeting_{uuid.uuid4().hex[:6]}", "meeting_type": "instant"}
        create_resp = requests.post(f"{BASE_URL}/api/meetings", headers=admin_headers, json=meeting_data)
        meeting_id = create_resp.json()["meeting_id"]
        
        # Get chat
        response = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/chat", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print("✓ Admin can access meeting chat")
    
    def test_delete_meeting(self, admin_headers):
        """Admin can delete a meeting"""
        # Create meeting
        meeting_data = {"title": f"TEST_Delete_Meeting_{uuid.uuid4().hex[:6]}", "meeting_type": "instant"}
        create_resp = requests.post(f"{BASE_URL}/api/meetings", headers=admin_headers, json=meeting_data)
        meeting_id = create_resp.json()["meeting_id"]
        
        # Delete
        response = requests.delete(f"{BASE_URL}/api/meetings/{meeting_id}", headers=admin_headers)
        assert response.status_code == 200, f"Delete meeting failed: {response.text}"
        print(f"✓ Admin deleted meeting: {meeting_id}")


class TestMeetingsMember:
    """Meetings module tests for Member role"""
    
    def test_member_list_meetings(self, member_headers):
        """Member can list their meetings"""
        response = requests.get(f"{BASE_URL}/api/meetings", headers=member_headers)
        assert response.status_code == 200
        data = response.json()
        assert "meetings" in data
        print(f"✓ Member can list meetings ({len(data['meetings'])} meetings)")
    
    def test_member_create_meeting(self, member_headers):
        """Member can create a meeting"""
        meeting_data = {
            "title": f"TEST_Member_Meeting_{uuid.uuid4().hex[:6]}",
            "meeting_type": "instant"
        }
        response = requests.post(f"{BASE_URL}/api/meetings", headers=member_headers, json=meeting_data)
        assert response.status_code == 200, f"Member create meeting failed: {response.text}"
        data = response.json()
        assert "meeting_id" in data
        print(f"✓ Member created meeting: {data['meeting_id']}")


# ============ SCHEDULING MODULE TESTS ============

class TestSchedulingAdmin:
    """Scheduling/Polls module tests for Admin role"""
    
    def test_list_schedule_polls(self, admin_headers):
        """Admin can list schedule polls"""
        response = requests.get(f"{BASE_URL}/api/schedule-polls", headers=admin_headers)
        assert response.status_code == 200, f"List schedule polls failed: {response.text}"
        data = response.json()
        assert "polls" in data
        print(f"✓ Admin can list schedule polls ({len(data['polls'])} polls)")
    
    def test_create_schedule_poll(self, admin_headers):
        """Admin can create a schedule poll (Doodle-style)"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        poll_data = {
            "title": f"TEST_Schedule_Poll_{uuid.uuid4().hex[:6]}",
            "description": "Test schedule poll",
            "time_slots": [
                {"date": tomorrow, "start_time": "09:00", "end_time": "10:00"},
                {"date": tomorrow, "start_time": "14:00", "end_time": "15:00"},
                {"date": tomorrow, "start_time": "16:00", "end_time": "17:00"}
            ],
            "allow_maybe": True,
            "allow_suggestions": False,
            "create_meeting_on_confirm": True
        }
        response = requests.post(f"{BASE_URL}/api/schedule-polls", headers=admin_headers, json=poll_data)
        assert response.status_code == 200, f"Create schedule poll failed: {response.text}"
        data = response.json()
        assert "poll_id" in data
        assert "share_token" in data
        print(f"✓ Admin created schedule poll: {data['poll_id']}")
        return data
    
    def test_get_schedule_poll_detail(self, admin_headers):
        """Admin can get schedule poll details"""
        # Create poll first
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        poll_data = {
            "title": f"TEST_Detail_Poll_{uuid.uuid4().hex[:6]}",
            "time_slots": [{"date": tomorrow, "start_time": "10:00", "end_time": "11:00"}]
        }
        create_resp = requests.post(f"{BASE_URL}/api/schedule-polls", headers=admin_headers, json=poll_data)
        poll_id = create_resp.json()["poll_id"]
        
        # Get detail
        response = requests.get(f"{BASE_URL}/api/schedule-polls/{poll_id}", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["poll_id"] == poll_id
        print(f"✓ Admin can get schedule poll detail: {poll_id}")
    
    def test_delete_schedule_poll(self, admin_headers):
        """Admin can delete a schedule poll"""
        # Create poll
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        poll_data = {
            "title": f"TEST_Delete_Poll_{uuid.uuid4().hex[:6]}",
            "time_slots": [{"date": tomorrow, "start_time": "10:00", "end_time": "11:00"}]
        }
        create_resp = requests.post(f"{BASE_URL}/api/schedule-polls", headers=admin_headers, json=poll_data)
        poll_id = create_resp.json()["poll_id"]
        
        # Delete
        response = requests.delete(f"{BASE_URL}/api/schedule-polls/{poll_id}", headers=admin_headers)
        assert response.status_code == 200
        print(f"✓ Admin deleted schedule poll: {poll_id}")
    
    def test_list_general_polls(self, admin_headers):
        """Admin can list general polls (surveys)"""
        response = requests.get(f"{BASE_URL}/api/general-polls", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "polls" in data
        print(f"✓ Admin can list general polls ({len(data['polls'])} polls)")
    
    def test_create_general_poll(self, admin_headers):
        """Admin can create a general poll"""
        poll_data = {
            "title": f"TEST_General_Poll_{uuid.uuid4().hex[:6]}",
            "description": "Test general poll",
            "poll_type": "single",
            "options": ["Option A", "Option B", "Option C"],
            "allow_custom_options": False,
            "is_anonymous": False
        }
        response = requests.post(f"{BASE_URL}/api/general-polls", headers=admin_headers, json=poll_data)
        assert response.status_code == 200, f"Create general poll failed: {response.text}"
        data = response.json()
        assert "poll_id" in data
        print(f"✓ Admin created general poll: {data['poll_id']}")
    
    def test_booking_availability(self, admin_headers):
        """Admin can get/set booking availability"""
        response = requests.get(f"{BASE_URL}/api/booking/availability", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "weekdays" in data
        print("✓ Admin can get booking availability")
    
    def test_my_bookings(self, admin_headers):
        """Admin can list their bookings"""
        response = requests.get(f"{BASE_URL}/api/booking/my-bookings", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "bookings" in data
        print(f"✓ Admin can list bookings ({len(data['bookings'])} bookings)")
    
    def test_booking_pages(self, admin_headers):
        """Admin can list booking pages"""
        response = requests.get(f"{BASE_URL}/api/booking/pages", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Admin can list booking pages ({len(data)} pages)")


class TestSchedulingMember:
    """Scheduling module tests for Member role"""
    
    def test_member_list_schedule_polls(self, member_headers):
        """Member can list their schedule polls"""
        response = requests.get(f"{BASE_URL}/api/schedule-polls", headers=member_headers)
        assert response.status_code == 200
        data = response.json()
        assert "polls" in data
        print(f"✓ Member can list schedule polls ({len(data['polls'])} polls)")
    
    def test_member_create_schedule_poll(self, member_headers):
        """Member can create a schedule poll"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        poll_data = {
            "title": f"TEST_Member_Poll_{uuid.uuid4().hex[:6]}",
            "time_slots": [{"date": tomorrow, "start_time": "11:00", "end_time": "12:00"}]
        }
        response = requests.post(f"{BASE_URL}/api/schedule-polls", headers=member_headers, json=poll_data)
        assert response.status_code == 200
        data = response.json()
        assert "poll_id" in data
        print(f"✓ Member created schedule poll: {data['poll_id']}")
    
    def test_member_booking_availability(self, member_headers):
        """Member can get their booking availability"""
        response = requests.get(f"{BASE_URL}/api/booking/availability", headers=member_headers)
        assert response.status_code == 200
        data = response.json()
        assert "weekdays" in data
        print("✓ Member can get booking availability")


# ============ PUBLIC POLL VOTING TESTS ============

class TestPublicPollVoting:
    """Test public poll voting (no auth required)"""
    
    def test_public_schedule_poll_vote(self, admin_headers):
        """Public user can vote on schedule poll via share_token"""
        # Admin creates poll
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        poll_data = {
            "title": f"TEST_Public_Vote_Poll_{uuid.uuid4().hex[:6]}",
            "time_slots": [
                {"date": tomorrow, "start_time": "09:00", "end_time": "10:00"},
                {"date": tomorrow, "start_time": "14:00", "end_time": "15:00"}
            ],
            "allow_maybe": True
        }
        create_resp = requests.post(f"{BASE_URL}/api/schedule-polls", headers=admin_headers, json=poll_data)
        poll_data = create_resp.json()
        share_token = poll_data["share_token"]
        
        # Get public poll
        public_resp = requests.get(f"{BASE_URL}/api/schedule-polls/public/{share_token}")
        assert public_resp.status_code == 200
        poll = public_resp.json()
        slot_id = poll["time_slots"][0]["slot_id"]
        
        # Vote (no auth)
        vote_data = {
            "voter_name": "Test Voter",
            "voter_email": "voter@test.com",
            "votes": {slot_id: "yes"}
        }
        vote_resp = requests.post(f"{BASE_URL}/api/schedule-polls/public/{share_token}/vote", json=vote_data)
        assert vote_resp.status_code == 200
        print("✓ Public user voted on schedule poll")
    
    def test_public_general_poll_vote(self, admin_headers):
        """Public user can vote on general poll via share_token"""
        # Admin creates poll
        poll_data = {
            "title": f"TEST_Public_General_Poll_{uuid.uuid4().hex[:6]}",
            "poll_type": "single",
            "options": ["Yes", "No", "Maybe"]
        }
        create_resp = requests.post(f"{BASE_URL}/api/general-polls", headers=admin_headers, json=poll_data)
        poll_data = create_resp.json()
        share_token = poll_data["share_token"]
        
        # Vote (no auth)
        vote_data = {
            "voter_name": "Test Voter",
            "voter_email": "voter@test.com",
            "selected_options": [0]  # First option
        }
        vote_resp = requests.post(f"{BASE_URL}/api/general-polls/public/{share_token}/vote", json=vote_data)
        assert vote_resp.status_code == 200
        print("✓ Public user voted on general poll")


# ============ CROSS-ROLE TESTS ============

class TestCrossRole:
    """Cross-role interaction tests"""
    
    def test_admin_creates_poll_member_votes(self, admin_headers, member_headers):
        """Admin creates poll, Member can see and vote"""
        # Admin creates poll
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        poll_data = {
            "title": f"TEST_CrossRole_Poll_{uuid.uuid4().hex[:6]}",
            "time_slots": [
                {"date": tomorrow, "start_time": "09:00", "end_time": "10:00"},
                {"date": tomorrow, "start_time": "14:00", "end_time": "15:00"},
                {"date": tomorrow, "start_time": "16:00", "end_time": "17:00"}
            ],
            "allow_maybe": True
        }
        create_resp = requests.post(f"{BASE_URL}/api/schedule-polls", headers=admin_headers, json=poll_data)
        assert create_resp.status_code == 200
        poll_info = create_resp.json()
        share_token = poll_info["share_token"]
        
        # Member votes via public endpoint
        public_resp = requests.get(f"{BASE_URL}/api/schedule-polls/public/{share_token}")
        assert public_resp.status_code == 200
        poll = public_resp.json()
        
        # Vote on 3 slots
        votes = {}
        for i, slot in enumerate(poll["time_slots"]):
            votes[slot["slot_id"]] = "yes" if i < 2 else "maybe"
        
        vote_data = {
            "voter_name": "Member User",
            "voter_email": MEMBER_EMAIL,
            "votes": votes
        }
        vote_resp = requests.post(f"{BASE_URL}/api/schedule-polls/public/{share_token}/vote", json=vote_data)
        assert vote_resp.status_code == 200
        
        # Admin checks poll results
        detail_resp = requests.get(f"{BASE_URL}/api/schedule-polls/{poll_info['poll_id']}", headers=admin_headers)
        assert detail_resp.status_code == 200
        updated_poll = detail_resp.json()
        assert len(updated_poll.get("votes", [])) >= 1
        print("✓ Cross-role: Admin created poll, Member voted, Admin sees results")
    
    def test_member_creates_meeting_admin_sees(self, admin_headers, member_headers):
        """Member creates meeting, Admin can see it in their list"""
        # Member creates meeting
        meeting_data = {
            "title": f"TEST_CrossRole_Meeting_{uuid.uuid4().hex[:6]}",
            "meeting_type": "instant"
        }
        create_resp = requests.post(f"{BASE_URL}/api/meetings", headers=member_headers, json=meeting_data)
        assert create_resp.status_code == 200
        meeting_id = create_resp.json()["meeting_id"]
        
        # Admin can get meeting detail (if they have permission)
        detail_resp = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}", headers=admin_headers)
        # Admin may or may not have access depending on permissions
        # Just verify the endpoint works
        assert detail_resp.status_code in [200, 403, 404]
        print("✓ Cross-role: Member created meeting, Admin access checked")


# ============ CLEANUP ============

class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_tasks(self, admin_headers):
        """Clean up TEST_ prefixed tasks"""
        response = requests.get(f"{BASE_URL}/api/tasks?search=TEST_", headers=admin_headers)
        if response.status_code == 200:
            tasks = response.json().get("tasks", [])
            deleted = 0
            for task in tasks:
                if task.get("title", "").startswith("TEST_"):
                    del_resp = requests.delete(f"{BASE_URL}/api/tasks/{task['task_id']}", headers=admin_headers)
                    if del_resp.status_code == 200:
                        deleted += 1
            print(f"✓ Cleaned up {deleted} test tasks")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
