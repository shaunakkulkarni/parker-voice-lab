"""Deterministic baseline/anomaly store (no network)."""

from __future__ import annotations

from typing import Any

from parker.contracts.domains import AnomalyFinding, AnomalyReport


class MockAnomalyStore:
    """Sensor history and baseline comparison with insufficient-history case."""

    def __init__(self) -> None:
        self.baselines: dict[str, dict[str, Any]] = {
            "lock.front_door": {
                "typical_state": "locked",
                "history_points": 48,
                "freshness": "fresh",
            },
            "climate.bedroom": {
                "typical_state": "21.0",
                "history_points": 72,
                "freshness": "fresh",
            },
        }
        self.current: dict[str, str] = {
            "lock.front_door": "unlocked",
            "climate.bedroom": "21.2",
        }
        self.insufficient_history_entities: set[str] = set()
        self.calls: list[str] = []

    def reset(self) -> None:
        self.current = {
            "lock.front_door": "unlocked",
            "climate.bedroom": "21.2",
        }
        self.insufficient_history_entities.clear()
        for entity in self.baselines.values():
            entity["history_points"] = max(int(entity.get("history_points", 0)), 24)
            entity["freshness"] = "fresh"
        self.calls.clear()

    def set_door_open(self) -> None:
        self.current["lock.front_door"] = "unlocked"

    def set_door_locked(self) -> None:
        self.current["lock.front_door"] = "locked"

    def inject_insufficient_history(self, entity_id: str = "lock.front_door") -> None:
        self.insufficient_history_entities.add(entity_id)
        if entity_id in self.baselines:
            self.baselines[entity_id]["history_points"] = 2

    def scan(self, focus: str | None = None) -> AnomalyReport:
        self.calls.append(focus or "all")
        findings: list[AnomalyFinding] = []
        entities = [focus] if focus and focus in self.baselines else list(self.baselines)

        for entity_id in entities:
            baseline = self.baselines[entity_id]
            history_points = int(baseline.get("history_points", 0))
            if entity_id in self.insufficient_history_entities or history_points < 12:
                return AnomalyReport(
                    findings=[],
                    evidence_sufficient=False,
                    spoken=(
                        f"I don't have enough history for {entity_id} "
                        "to claim an anomaly."
                    ),
                    proposed_actions=[],
                )
            current = self.current.get(entity_id, "unknown")
            typical = str(baseline["typical_state"])
            if current != typical:
                findings.append(
                    AnomalyFinding(
                        entity_id=entity_id,
                        description=f"{entity_id} is {current}; baseline is {typical}.",
                        baseline=typical,
                        current=current,
                        freshness=str(baseline.get("freshness", "unknown")),
                        evidence_sufficient=True,
                    )
                )

        if not findings:
            return AnomalyReport(
                findings=[],
                evidence_sufficient=True,
                spoken="Nothing looks unusual based on current baselines.",
            )

        spoken_parts = [f.description for f in findings]
        proposed: list[dict[str, str]] = []
        if any(f.entity_id == "lock.front_door" for f in findings):
            proposed.append(
                {
                    "domain": "lock",
                    "service": "lock",
                    "target": "lock.front_door",
                }
            )
        return AnomalyReport(
            findings=findings,
            evidence_sufficient=True,
            spoken="I found something odd: " + " ".join(spoken_parts),
            proposed_actions=proposed,
        )
