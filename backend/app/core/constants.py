from __future__ import annotations

from enum import StrEnum

QUEUE_CLASS_ORDER = ("scout", "soldier", "demo", "medic")
QUEUE_CLASS_LIMITS = {
    "scout": 4,
    "soldier": 4,
    "demo": 2,
    "medic": 2,
}
PUG_MAP_POOL = (
    "cp_sunshine",
    "cp_process_f12",
    "cp_gullywash_f9",
    "cp_metalworks_f7",
    "cp_subbase_b3a",
    "cp_granary_pro_rc17a3",
)
ELO_ROLE_RATINGS = {
    "1363181710463860826": 1600,
    "1363181641014575425": 1400,
    "1363181525939519709": 1200,
    "1367534417303703703": 1000,
    "1363541855668666459": 900,
    "1375873812679364798": 800,
}
TEAM_ORDER = ("RED", "BLU")


class QueueBucket(StrEnum):
    ACTIVE = "active"
    NEXT = "next"


class MatchStatus(StrEnum):
    FORMING = "forming"
    READY_CHECK = "ready_check"
    READY = "ready"
    LIVE = "live"
    AWAITING_LOG = "awaiting_log"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class JobStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    RUNNING = "running"
