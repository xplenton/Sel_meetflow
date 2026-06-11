"""
Meeting-Mode policies — extracted from routes/meetings.py.

Each mode defines which features are enabled:
  * standard  — default, everything enabled
  * moderated — host-controlled, participants muted by default, no screen share
  * webinar   — like moderated but for big audiences, no screen share for attendees
  * training  — interactive training, everything enabled but guided
"""
from __future__ import annotations

from typing import Dict, Any


MEETING_MODE_CONFIG: Dict[str, Dict[str, Any]] = {
    "standard": {
        "auto_mute": False, "allow_unmute": True, "allow_chat": True,
        "allow_reactions": True, "allow_screen_share": True, "allow_hand_raise": True,
    },
    "moderated": {
        "auto_mute": True, "allow_unmute": False, "allow_chat": True,
        "allow_reactions": True, "allow_screen_share": False, "allow_hand_raise": True,
    },
    "webinar": {
        "auto_mute": True, "allow_unmute": False, "allow_chat": True,
        "allow_reactions": True, "allow_screen_share": False, "allow_hand_raise": True,
    },
    "training": {
        "auto_mute": False, "allow_unmute": True, "allow_chat": True,
        "allow_reactions": True, "allow_screen_share": True, "allow_hand_raise": True,
    },
}


def get_mode_config_for(mode: str) -> Dict[str, Any]:
    """Return the effective config dict for a given mode, falling back to 'standard'."""
    return MEETING_MODE_CONFIG.get(mode, MEETING_MODE_CONFIG["standard"])


def is_valid_mode(mode: str) -> bool:
    return mode in MEETING_MODE_CONFIG


def list_modes() -> Dict[str, Dict[str, Any]]:
    return dict(MEETING_MODE_CONFIG)
