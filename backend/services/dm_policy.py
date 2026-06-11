"""
Iter 323 — DM Opt-In Gate.

Centralised check for "may A send a DM to B?". The same function is used by
the conversation-create endpoint (blocks creation) and the user-search
endpoint (renders a lock icon next to blocked users in the picker).

Rules:
  • Admins are ALWAYS allowed to DM anyone (so the leadership can never be
    locked out by a personal preference setting).
  • Group chats are NOT affected — once you're in a group, the policy of
    other members doesn't constrain group activity.
  • Existing DMs keep working in both directions; the gate fires only on
    CREATION of a new direct conversation.

Recipient's `dm_policy` value:
  ┌──────────────────┬──────────────────────────────────────────────────────┐
  │ everyone         │ Anyone may DM (default for new users).               │
  │ same_department  │ Sender's `department` must match recipient's.        │
  │                  │ Empty/missing department on either side → blocked.   │
  │ managers_plus    │ Sender's role must be moderator OR admin.            │
  │ nobody           │ Nobody may start a new DM (admins still pass via    │
  │                  │ the always-allow override above).                    │
  └──────────────────┴──────────────────────────────────────────────────────┘
"""
from typing import Tuple, Optional

DM_POLICY_VALUES = ("everyone", "same_department", "managers_plus", "nobody")


def may_dm(sender: dict, recipient: dict) -> Tuple[bool, Optional[str]]:
    """Return (allowed, blocked_reason).

    `sender` and `recipient` are user dicts as loaded by `get_current_user` /
    `db.users.find_one({"_id": 0})` — they must include at minimum `user_id`,
    `role`, `department`, and optionally `dm_policy`.

    `blocked_reason` is a short German string suitable for tooltip / toast.
    It is `None` when `allowed` is True.
    """
    # Self-DM is always allowed (the UI uses this for "Notes to self" etc.)
    if sender.get("user_id") == recipient.get("user_id"):
        return True, None

    # Admin override — leadership can always reach anyone
    if (sender.get("role") or "").lower() == "admin":
        return True, None

    policy = (recipient.get("dm_policy") or "everyone").lower()
    if policy not in DM_POLICY_VALUES:
        policy = "everyone"

    if policy == "everyone":
        return True, None

    if policy == "nobody":
        return False, "Akzeptiert derzeit keine neuen Direkt-Nachrichten"

    if policy == "managers_plus":
        sender_role = (sender.get("role") or "").lower()
        if sender_role in ("admin", "moderator"):
            return True, None
        return False, "Akzeptiert nur Direkt-Nachrichten von Moderatoren oder Admins"

    if policy == "same_department":
        s_dept = (sender.get("department") or "").strip().lower()
        r_dept = (recipient.get("department") or "").strip().lower()
        if s_dept and r_dept and s_dept == r_dept:
            return True, None
        if not s_dept or not r_dept:
            return False, "Akzeptiert nur DMs aus derselben Abteilung — Ihre Abteilung ist nicht hinterlegt"
        return False, f"Akzeptiert nur DMs aus derselben Abteilung ({recipient.get('department')})"

    # Defensive default — unknown values fall back to permissive
    return True, None
