from __future__ import annotations

from enum import StrEnum

QUEUE_CLASS_ORDER = ("scout", "soldier", "demo", "medic")
QUEUE_CLASS_LIMITS = {
    "scout": 4,
    "soldier": 4,
    "demo": 2,
    "medic": 2,
}
TEAM_ORDER = ("RED", "BLU")


class QueueBucket(StrEnum):
    ACTIVE = "active"
    NEXT = "next"


class MatchStatus(StrEnum):
    FORMING = "forming"
    READY_CHECK = "ready_check"
    LIVE = "live"
    AWAITING_LOG = "awaiting_log"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class JobStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    RUNNING = "running"

