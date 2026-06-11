from typing import List, Optional
from pydantic import BaseModel


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""

class LoginRequest(BaseModel):
    email: str
    password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    password: str

class GoogleSessionRequest(BaseModel):
    session_id: str

class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    avatar: Optional[str] = None
    language: Optional[str] = None
    auto_reply_enabled: Optional[bool] = None
    auto_reply_message: Optional[str] = None
    # Iter 340 — Stammdaten-Erweiterung
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None

class MeetingCreateRequest(BaseModel):
    title: str = "Untitled Meeting"
    description: str = ""
    meeting_type: str = "instant"
    scheduled_at: Optional[str] = None
    duration: int = 60
    duration_minutes: Optional[int] = None
    timezone: str = "UTC"
    max_participants: int = 100
    lobby_enabled: bool = False
    guest_access: bool = True
    meeting_mode: str = "standard"
    chat_enabled: bool = True
    reactions_enabled: bool = True
    recording_enabled: bool = False
    transcript_enabled: bool = False
    # Auto-Nachklingeln — when True, the scheduled-meeting ring fan-out is
    # repeated up to 3× at 30 s intervals while the meeting is active
    # (iter 147). Perfect for time-critical clinical contexts.
    auto_rering: bool = False
    recurring: bool = False
    recurring_pattern: Optional[str] = None  # daily | weekly | biweekly | monthly | custom | custom_dates
    recurring_interval: Optional[int] = None
    recurring_end_date: Optional[str] = None
    # Custom per-weekday schedule: [{weekday: 0-6, start_time: "HH:MM", end_time: "HH:MM"}]
    # Used when recurring_pattern == "custom". weekday 0=Monday..6=Sunday
    recurring_schedule: Optional[List[dict]] = None
    # Number of weeks to generate for custom pattern (default 8)
    recurring_weeks: Optional[int] = 8
    # iter 168 — Explicit-date custom recurrence. Used when
    # recurring_pattern == "custom_dates". Each entry is
    # {date: "YYYY-MM-DD", start_time: "HH:MM", end_time: "HH:MM"}.
    recurring_dates: Optional[List[dict]] = None
    reminder_minutes: int = 0
    invited_emails: Optional[List[str]] = None
    optional_emails: Optional[List[str]] = None

class ChatMessageRequest(BaseModel):
    message: str
    reply_to: Optional[str] = None
    message_type: str = "user"

class PollCreateRequest(BaseModel):
    question: str
    options: list

class PollVoteRequest(BaseModel):
    option_index: int

class QuestionCreateRequest(BaseModel):
    text: str

class QuestionUpdateRequest(BaseModel):
    status: Optional[str] = None
    priority: Optional[int] = None
    answer: Optional[str] = None

class BreakoutRoomCreateRequest(BaseModel):
    name: str
    participant_ids: list = []

class RecordingCreateRequest(BaseModel):
    title: str = ""
    url: str = ""
    duration: int = 0
    size: int = 0

class TranscriptCreateRequest(BaseModel):
    content: str

class AdminUserUpdateRequest(BaseModel):
    role: Optional[str] = None
    name: Optional[str] = None

class MeetingInviteRequest(BaseModel):
    emails: list
    message: str = ""

class RecurringGenerateRequest(BaseModel):
    count: int = 4
    weeks: Optional[int] = None  # For custom pattern: number of weeks to generate
    recurring_schedule: Optional[List[dict]] = None  # Override schedule for custom pattern

class TemplateCreateRequest(BaseModel):
    name: str
    title: str = "Untitled Meeting"
    description: str = ""
    duration: int = 60
    meeting_mode: str = "standard"
    lobby_enabled: bool = False
    guest_access: bool = True
    chat_enabled: bool = True
    reactions_enabled: bool = True
    recording_enabled: bool = False
    transcript_enabled: bool = False
    recurring: bool = False
    recurring_pattern: Optional[str] = None
    recurring_schedule: Optional[list] = None  # list of {weekday:0-6, start_time:"HH:MM", end_time:"HH:MM"}
    recurring_weeks: Optional[int] = None
    invited_emails: Optional[list] = None  # default invitee list baked into the template

class BrandingUpdateRequest(BaseModel):
    company_name: Optional[str] = None
    primary_color: Optional[str] = None
    logo_url: Optional[str] = None
    email_footer: Optional[str] = None
    favicon_url: Optional[str] = None

class LobbyActionRequest(BaseModel):
    action: str

class HostControlRequest(BaseModel):
    action: str

class MeetingPolicyRequest(BaseModel):
    name: str = "Default"
    max_duration: int = 0
    max_participants: int = 0
    allow_recording: bool = True
    allow_guest: bool = True
    require_lobby: bool = False
    default_meeting_mode: str = "standard"
    auto_transcribe: bool = False

class OrganizationRequest(BaseModel):
    name: str
    domain: str = ""
    description: str = ""

# Schedule Poll Models
class SchedulePollTimeSlot(BaseModel):
    date: str
    start_time: str
    end_time: str
    note: str = ""

class SchedulePollCreateRequest(BaseModel):
    title: str
    description: str = ""
    time_slots: List[SchedulePollTimeSlot]
    deadline: Optional[str] = None
    allow_comments: bool = True
    allow_maybe: bool = True
    allow_suggestions: bool = False
    is_private: bool = False
    password: Optional[str] = ""
    create_meeting_on_confirm: bool = False
    require_login: bool = False
    multiple_votes: bool = True
    timezone: str = "Europe/Berlin"

class SchedulePollVoteRequest(BaseModel):
    voter_name: str
    voter_email: str = ""
    votes: dict

class SchedulePollCommentRequest(BaseModel):
    author_name: str
    text: str

class BookingAvailabilityRequest(BaseModel):
    weekdays: dict = {}
    slot_duration: int = 30
    buffer_time: int = 10
    blocked_dates: List[str] = []
    booking_enabled: bool = True
    timezone: str = "Europe/Berlin"

class GeneralPollCreateRequest(BaseModel):
    title: str
    description: str = ""
    poll_type: str = "single"
    options: List[str]
    deadline: Optional[str] = None
    allow_comments: bool = True
    allow_custom_options: bool = False
    is_anonymous: bool = False

class GeneralPollVoteRequest(BaseModel):
    voter_name: str
    voter_email: str = ""
    selected_options: list = []
    selected: list = []
    priority_order: Optional[list] = []

class ActionItemRequest(BaseModel):
    title: str
    assignee: str = ""
    due_date: Optional[str] = None
    status: str = "open"
