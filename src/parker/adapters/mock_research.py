"""Deterministic web search/extract mock (no network)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from parker.contracts.domains import ResearchReport, ResearchSource


class MockWebSearch:
    """Cited research results with freshness and conflict injection."""

    def __init__(self) -> None:
        self.inject_conflicts = False
        self.calls: list[str] = []

    def reset(self) -> None:
        self.inject_conflicts = False
        self.calls.clear()

    def research(self, topic: str) -> ResearchReport:
        self.calls.append(topic)
        now = datetime.now(UTC)
        sources = [
            ResearchSource(
                title="Aqara FP2 mmWave review",
                url="https://example.test/aqara-fp2",
                freshness="fresh",
                retrieved_at=now - timedelta(hours=2),
                claim="Aqara FP2 offers reliable shower-zone presence detection.",
            ),
            ResearchSource(
                title="Everything Presence Lite comparison",
                url="https://example.test/ep-lite",
                freshness="fresh",
                retrieved_at=now - timedelta(hours=6),
                claim="Everything Presence Lite is a strong open alternative.",
            ),
            ResearchSource(
                title="Older PIR survey",
                url="https://example.test/pir-survey",
                freshness="stale",
                retrieved_at=now - timedelta(days=400),
                claim="PIR sensors are sufficient for most bathrooms.",
            ),
        ]
        conflicting: list[str] = []
        if self.inject_conflicts or "conflict" in topic.lower():
            sources[0] = sources[0].model_copy(
                update={
                    "claim": "mmWave is required for shower-zone accuracy.",
                    "conflicts_with": ["Older PIR survey"],
                }
            )
            sources[2] = sources[2].model_copy(
                update={
                    "claim": "PIR alone is enough; mmWave is unnecessary.",
                    "conflicts_with": ["Aqara FP2 mmWave review"],
                }
            )
            conflicting = [
                "mmWave is required for shower-zone accuracy.",
                "PIR alone is enough; mmWave is unnecessary.",
            ]
        stale = [s.title for s in sources if s.freshness == "stale"]
        summary = (
            f"Rundown on {topic}: leading options are Aqara FP2 and "
            "Everything Presence Lite. Prefer mmWave for shower zones."
        )
        if conflicting:
            summary += " Sources disagree on whether PIR is sufficient."
        if stale:
            summary += f" Stale source disclosed: {stale[0]}."
        return ResearchReport(
            topic=topic,
            summary=summary,
            sources=sources,
            conflicting_claims=conflicting,
            stale_sources=stale,
        )
