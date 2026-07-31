from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.constants import QUEUE_CLASS_ORDER


def _classes(value: list[str]) -> list[str]:
    cleaned = list(dict.fromkeys(item.lower() for item in value))
    invalid = [item for item in cleaned if item not in QUEUE_CLASS_ORDER]
    if invalid:
        raise ValueError(f"Invalid classes: {', '.join(invalid)}")
    return cleaned


class QueuePrimaryRequest(BaseModel):
    primary_class: str
    flex_classes: list[str] = Field(default_factory=list)

    @field_validator("primary_class")
    @classmethod
    def validate_primary(cls, value: str) -> str:
        value = value.lower()
        if value not in QUEUE_CLASS_ORDER:
            raise ValueError("Invalid primary class.")
        return value

    @field_validator("flex_classes")
    @classmethod
    def validate_flex(cls, value: list[str]) -> list[str]:
        return _classes(value)


class QueueFlexRequest(BaseModel):
    flex_classes: list[str] = Field(default_factory=list)

    @field_validator("flex_classes")
    @classmethod
    def validate_flex(cls, value: list[str]) -> list[str]:
        return _classes(value)


class QueueJoinRequest(BaseModel):
    primary_class: str | None = None
    flex_classes: list[str] = Field(default_factory=list)
    classes: list[str] | None = None
    queue_bucket: str = "active"


class QueuePlayerRead(BaseModel):
    player_id: int
    discord_username: str
    display_name: str | None
    steam_name: str | None
    pug_rating: int | None
    elo_rating: int | None
    ready: bool
    joined_at: datetime
    primary_class: str
    flex_classes: list[str]
    classes: list[str]
    pre_ready_expires_at: datetime | None


class QueueBucketRead(BaseModel):
    queue_bucket: str = "active"
    players: list[QueuePlayerRead]
    count: int


class QueueStateResponse(BaseModel):
    match_id: int
    queue: QueueBucketRead
    active: QueueBucketRead
    matchable: bool
    needed_by_class: dict[str, int]
    phase: str = "forming"
    ready_check_id: str | None = None
    ready_check_expires_at: datetime | None = None
    map_candidates: list[str] = Field(default_factory=list)
    map_votes: dict[str, int] = Field(default_factory=dict)
    blocked_classes: list[str] = Field(default_factory=list)


class MapVoteRequest(BaseModel):
    map_name: str
