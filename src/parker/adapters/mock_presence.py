"""Deterministic presence/motion mock (no network)."""

from __future__ import annotations

from parker.contracts.domains import PresenceEvent, PresenceZone


class MockPresence:
    """Presence sensor stand-in with false-positive injection."""

    def __init__(self) -> None:
        self.events: list[PresenceEvent] = []
        self.inject_false_positive = False
        self.shower_zone_active = False

    def reset(self) -> None:
        self.events.clear()
        self.inject_false_positive = False
        self.shower_zone_active = False

    def shower_start(
        self,
        *,
        zone: PresenceZone = PresenceZone.BATHROOM_SHOWER,
        false_positive: bool | None = None,
    ) -> PresenceEvent:
        is_fp = self.inject_false_positive if false_positive is None else false_positive
        confidence = 0.35 if is_fp else 0.96
        event = PresenceEvent(
            zone=zone,
            event_type="shower_start",
            confidence=confidence,
            false_positive=is_fp,
            attributes={"sensor": "aqara_fp2_mock"},
        )
        self.events.append(event)
        if not is_fp:
            self.shower_zone_active = True
        return event

    def is_valid_shower_trigger(self, event: PresenceEvent) -> bool:
        """False positives and low-confidence events are suppressed."""
        if event.false_positive:
            return False
        if event.event_type != "shower_start":
            return False
        return event.confidence >= 0.8
