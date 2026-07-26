from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.constants import QUEUE_CLASS_ORDER


class QueueJoinRequest(BaseModel):
    primary_class: str | None = None
    flex_classes: list[str] = Field(default_factory=list)
    classes: list[str] | None = None
    queue_bucket: str = "active"

    @field_validator("flex_classes", "classes")
    @classmethod
    def validate_classes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = sorted(set(item.lower() for item in value))
        invalid = [item for item in cleaned if item not in QUEUE_CLASS_ORDER]
        if invalid:
            raise ValueError(f"Invalid classes: {', '.join(invalid)}")
        return cleaned

    @field_validator("primary_class")
    @classmethod
    def validate_primary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.lower()
        if value not in QUEUE_CLASS_ORDER:
            raise ValueError("Invalid primary class.")
        return value


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
    primary_class: str
    flex_classes: list[str]
    pre_ready_expires_at: datetime | None


class QueueBucketRead(BaseModel):
    queue_bucket: str
    players: list[QueuePlayerRead]
    count: int


class QueueStateResponse(BaseModel):
    active: QueueBucketRead
    next: QueueBucketRead
    matchable: bool
    needed_by_class: dict[str, int]
    phase: str = "waiting"
    ready_check_id: str | None = None
    ready_check_expires_at: datetime | None = None
    map_candidates: list[str] = Field(default_factory=list)
    map_votes: dict[str, int] = Field(default_factory=dict)
    blocked_classes: list[str] = Field(default_factory=list)


class MapVoteRequest(BaseModel):
    map_name: str


class MapCandidatesRequest(BaseModel):
    maps: list[str] = Field(min_length=3, max_length=3)
