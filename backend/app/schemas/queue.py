from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.constants import QUEUE_CLASS_ORDER


class QueueJoinRequest(BaseModel):
    classes: list[str] = Field(min_length=1)
    queue_bucket: str = "active"

    @field_validator("classes")
    @classmethod
    def validate_classes(cls, value: list[str]) -> list[str]:
        cleaned = sorted(set(item.lower() for item in value))
        invalid = [item for item in cleaned if item not in QUEUE_CLASS_ORDER]
        if invalid:
            raise ValueError(f"Invalid classes: {', '.join(invalid)}")
        return cleaned


class QueueLeaveRequest(BaseModel):
    queue_bucket: str = "active"


class QueuePreferenceRead(BaseModel):
    class_name: str


class QueuePlayerRead(BaseModel):
    player_id: int
    discord_username: str
    display_name: str | None
    steam_name: str | None
    ready: bool
    joined_at: datetime
    classes: list[str]


class QueueBucketRead(BaseModel):
    queue_bucket: str
    players: list[QueuePlayerRead]
    count: int


class QueueStateResponse(BaseModel):
    active: QueueBucketRead
    next: QueueBucketRead
    matchable: bool
    needed_by_class: dict[str, int]
