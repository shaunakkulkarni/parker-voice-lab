"""Domain contracts for gated-autonomy capabilities."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from parker.contracts._time import utc_now


class PresenceZone(StrEnum):
    BATHROOM_SHOWER = "bathroom_shower"
    BATHROOM = "bathroom"
    LIVING_ROOM = "living_room"


class PresenceEvent(BaseModel):
    """Deterministic presence/motion event from a mock sensor."""

    id: UUID = Field(default_factory=uuid4)
    zone: PresenceZone
    event_type: str
    confidence: float = Field(ge=0.0, le=1.0)
    false_positive: bool = False
    timestamp: datetime = Field(default_factory=utc_now)
    attributes: dict[str, Any] = Field(default_factory=dict)


class MediaPlayResult(BaseModel):
    """Result of starting media on a mock player."""

    entity_id: str
    playlist_id: str
    success: bool
    state: str
    error_code: str | None = None
    media_title: str | None = None


class CLIResult(BaseModel):
    """Hermes CLI / shell command result."""

    command: str
    project: str
    exit_code: int
    stdout: str
    stderr: str = ""
    duration_ms: float = 0.0

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class ResearchSource(BaseModel):
    title: str
    url: str
    freshness: str
    retrieved_at: datetime = Field(default_factory=utc_now)
    claim: str
    conflicts_with: list[str] = Field(default_factory=list)


class ResearchReport(BaseModel):
    topic: str
    summary: str
    sources: list[ResearchSource] = Field(default_factory=list)
    conflicting_claims: list[str] = Field(default_factory=list)
    stale_sources: list[str] = Field(default_factory=list)


class RoutineCondition(StrEnum):
    TRUE = "true"
    FALSE = "false"
    AMBIGUOUS = "ambiguous"
    STALE = "stale"


class RoutineDefinition(BaseModel):
    id: str
    name: str
    schedule: str
    condition_source: str
    condition_expression: str
    actions: list[dict[str, Any]] = Field(default_factory=list)
    autonomy_opt_in: bool = False


class RoutineRunResult(BaseModel):
    routine_id: str
    condition: RoutineCondition
    source_fresh: bool
    executed: bool
    skipped_reason: str | None = None
    spoken: str
    actions_taken: list[dict[str, Any]] = Field(default_factory=list)


class AnomalyFinding(BaseModel):
    entity_id: str
    description: str
    baseline: str
    current: str
    freshness: str
    evidence_sufficient: bool = True


class AnomalyReport(BaseModel):
    findings: list[AnomalyFinding] = Field(default_factory=list)
    evidence_sufficient: bool = True
    spoken: str
    proposed_actions: list[dict[str, Any]] = Field(default_factory=list)


class FlightInfo(BaseModel):
    flight_number: str
    destination: str
    departure_time: str
    check_in_open: bool = True
    stale: bool = False


class TravelPlan(BaseModel):
    destination: str
    packing_list: list[str] = Field(default_factory=list)
    departure_time: str | None = None
    weather_summary: str | None = None
    flight: FlightInfo | None = None
    home_readiness: list[str] = Field(default_factory=list)
    spoken: str
    check_in_pending: bool = False
