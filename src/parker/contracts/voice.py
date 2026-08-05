"""Voice pipeline contracts: wake events, transcripts, and turns."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from parker.contracts._time import utc_now


class WakeWordSource(StrEnum):
    NABU = "nabu"
    CUSTOM = "custom"
    MANUAL = "manual"


class WakeEvent(BaseModel):
    """A wake-word detection event."""

    id: UUID = Field(default_factory=uuid4)
    source: WakeWordSource
    confidence: float = Field(ge=0.0, le=1.0)
    device_id: str
    area_id: str
    timestamp: datetime = Field(default_factory=utc_now)


class Transcript(BaseModel):
    """The result of speech-to-text processing."""

    id: UUID = Field(default_factory=uuid4)
    wake_event_id: UUID
    text: str
    language: str = "en"
    confidence: float = Field(ge=0.0, le=1.0)
    processing_time_ms: float
    engine: str


class VoiceTurnState(StrEnum):
    WAKE_DETECTED = "wake_detected"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    CONFIRMING = "confirming"
    ACTING = "acting"
    SPEAKING = "speaking"
    COMPLETE = "complete"
    ERROR = "error"


class VoiceTurn(BaseModel):
    """A complete voice interaction from wake to response."""

    id: UUID = Field(default_factory=uuid4)
    wake_event: WakeEvent
    transcript: Transcript | None = None
    state: VoiceTurnState = VoiceTurnState.WAKE_DETECTED
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    error: str | None = None
    wake_to_transcript_ms: float | None = None
    transcript_to_action_ms: float | None = None
    action_to_speech_ms: float | None = None
    total_ms: float | None = None
