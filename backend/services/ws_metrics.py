"""In-memory ring buffer for WebSocket authentication events.

Recording every accept/reject right where auth happens (websocket.py) lets
the Admin Health-Dashboard surface subtle bugs like the 2026-02 Chat-Call
incident (browsers dropping HttpOnly cookies on wss:// upgrade).

We keep the data in memory because: (a) this hot path must stay fast, and
(b) a 5-minute rolling window does not warrant a TTL collection. If the
process restarts the counters reset — acceptable for ops visibility.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, List

_MAX_EVENTS = 500
_events: Deque[dict] = deque(maxlen=_MAX_EVENTS)


def record(event: str, user_id: str = "", reason: str = "") -> None:
    """event ∈ {'accept', 'reject_no_token', 'reject_invalid', 'reject_spoof', 'reject_stale_tv', 'reject_user_missing'}"""
    _events.append({"ts": time.time(), "event": event, "user_id": user_id, "reason": reason})


def _window(seconds: int) -> List[dict]:
    cutoff = time.time() - seconds
    return [e for e in _events if e["ts"] >= cutoff]


def snapshot() -> Dict:
    """Summary for the Admin dashboard. Safe to call often (O(n), n ≤ 500)."""
    w5 = _window(300)    # last 5 minutes
    w60 = _window(3600)  # last hour
    by_event: Dict[str, int] = {}
    for e in w5:
        by_event[e["event"]] = by_event.get(e["event"], 0) + 1

    accepts_5 = by_event.get("accept", 0)
    rejects_5 = sum(v for k, v in by_event.items() if k != "accept")
    accepts_60 = sum(1 for e in w60 if e["event"] == "accept")
    rejects_60 = sum(1 for e in w60 if e["event"] != "accept")

    total_5 = accepts_5 + rejects_5
    reject_rate_5 = (rejects_5 / total_5) if total_5 else 0.0

    if total_5 == 0:
        status = "idle"          # nothing to report
    elif reject_rate_5 >= 0.5:
        status = "fail"
    elif reject_rate_5 >= 0.2:
        status = "warn"
    else:
        status = "ok"

    # Last 20 events (newest first) — for operator inspection
    recent = list(_events)[-20:][::-1]

    return {
        "status": status,
        "last_5min": {
            "accepts": accepts_5,
            "rejects": rejects_5,
            "total": total_5,
            "reject_rate": round(reject_rate_5, 3),
            "by_event": by_event,
        },
        "last_1h": {
            "accepts": accepts_60,
            "rejects": rejects_60,
        },
        "recent": recent,
        "buffer_size": len(_events),
        "buffer_max": _MAX_EVENTS,
    }


def reset() -> None:
    """Testing helper — clear the buffer."""
    _events.clear()
