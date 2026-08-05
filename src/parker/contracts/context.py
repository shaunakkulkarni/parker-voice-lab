"""Conversation, room, and system status contracts."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from parker.contracts._time import utc_now
from parker.contracts.actions import ActionRequest
from parker.contracts.voice import VoiceTurn


class DeviceState(BaseModel):
    """Current state of a Home Assistant entity."""

    entity_id: str
    domain: str
    friendly_name: str
    state: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    area_id: str | None = None
    last_changed: datetime | None = None


class RoomContext(BaseModel):
    """Context for a specific room/area."""

    area_id: str
    area_name: str
    devices: list[DeviceState] = Field(default_factory=list)
    voice_device_id: str | None = None
    last_activity: datetime | None = None


class ConversationContext(BaseModel):
    """Tracks the state of an ongoing conversation."""

    id: UUID = Field(default_factory=uuid4)
    area_id: str
    voice_device_id: str
    turns: list[VoiceTurn] = Field(default_factory=list)
    last_action: ActionRequest | None = None
    pending_confirmation: ActionRequest | None = None
    started_at: datetime = Field(default_factory=utc_now)
    last_active: datetime = Field(default_factory=utc_now)
    expires_after_seconds: int = 120
    # Topic hint for follow-ups like "And tomorrow?"
    last_topic: str | None = None

    @property
    def is_expired(self) -> bool:
        last = self.last_active
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        return (now - last).total_seconds() > self.expires_after_seconds


class PARKERState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    CONFIRMING = "confirming"
    ACTING = "acting"
    SPEAKING = "speaking"
    ERROR = "error"


class SystemStatus(BaseModel):
    """Overall PARKER system status for the display."""

    state: PARKERState = PARKERState.IDLE
    current_room: str | None = None
    current_device: str | None = None
    last_transcript: str | None = None
    last_response: str | None = None
    last_action: ActionRequest | None = None
    pending_confirmation: ActionRequest | None = None
    active_conversations: int = 0
    uptime_seconds: float = 0
    errors: list[str] = Field(default_factory=list)
