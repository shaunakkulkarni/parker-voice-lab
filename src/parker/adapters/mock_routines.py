"""Deterministic routine store with schedule and condition evaluation."""

from __future__ import annotations

from typing import Any

from parker.contracts.domains import (
    RoutineCondition,
    RoutineDefinition,
    RoutineRunResult,
)


class MockRoutineStore:
    """User-defined routines with stale-source injection."""

    def __init__(self) -> None:
        self.routines: dict[str, RoutineDefinition] = {
            "jacket_weather": RoutineDefinition(
                id="jacket_weather",
                name="Morning jacket check",
                schedule="every morning",
                condition_source="weather",
                condition_expression="temp_c < 15",
                actions=[
                    {
                        "domain": "announce",
                        "service": "speak",
                        "parameters": {"text": "You'll want a jacket today."},
                    }
                ],
                autonomy_opt_in=True,
            ),
            "weekday_build": RoutineDefinition(
                id="weekday_build",
                name="Weekday build check",
                schedule="weekdays at 09:00",
                condition_source="ci",
                condition_expression="build_failed == true",
                actions=[
                    {
                        "domain": "announce",
                        "service": "speak",
                        "parameters": {"text": "The weekday build failed."},
                    }
                ],
                autonomy_opt_in=True,
            ),
        }
        self.source_values: dict[str, dict[str, Any]] = {
            "weather": {"temp_c": 12.0, "fresh": True},
            "ci": {"build_failed": False, "fresh": True},
        }
        self.runs: list[RoutineRunResult] = []

    def reset(self) -> None:
        self.source_values = {
            "weather": {"temp_c": 12.0, "fresh": True},
            "ci": {"build_failed": False, "fresh": True},
        }
        self.runs.clear()

    def set_condition_true(self, routine_id: str = "jacket_weather") -> None:
        routine = self.routines[routine_id]
        if routine.condition_source == "weather":
            self.source_values["weather"] = {"temp_c": 10.0, "fresh": True}
        elif routine.condition_source == "ci":
            self.source_values["ci"] = {"build_failed": True, "fresh": True}

    def set_condition_false(self, routine_id: str = "jacket_weather") -> None:
        routine = self.routines[routine_id]
        if routine.condition_source == "weather":
            self.source_values["weather"] = {"temp_c": 22.0, "fresh": True}
        elif routine.condition_source == "ci":
            self.source_values["ci"] = {"build_failed": False, "fresh": True}

    def inject_stale(self, source: str = "weather") -> None:
        values = dict(self.source_values.get(source, {}))
        values["fresh"] = False
        self.source_values[source] = values

    def evaluate(self, routine_id: str) -> RoutineRunResult:
        routine = self.routines.get(routine_id)
        if routine is None:
            result = RoutineRunResult(
                routine_id=routine_id,
                condition=RoutineCondition.AMBIGUOUS,
                source_fresh=False,
                executed=False,
                skipped_reason="unknown_routine",
                spoken=f"I don't have a routine named {routine_id}.",
            )
            self.runs.append(result)
            return result

        source = self.source_values.get(routine.condition_source, {})
        fresh = bool(source.get("fresh", False))
        if not fresh:
            result = RoutineRunResult(
                routine_id=routine_id,
                condition=RoutineCondition.STALE,
                source_fresh=False,
                executed=False,
                skipped_reason="stale_source",
                spoken=(
                    f"I skipped {routine.name} because the "
                    f"{routine.condition_source} source is stale."
                ),
            )
            self.runs.append(result)
            return result

        condition_met = self._condition_met(routine, source)
        if not condition_met:
            result = RoutineRunResult(
                routine_id=routine_id,
                condition=RoutineCondition.FALSE,
                source_fresh=True,
                executed=False,
                skipped_reason="condition_false",
                spoken=f"{routine.name}: condition is false, so I took no action.",
            )
            self.runs.append(result)
            return result

        result = RoutineRunResult(
            routine_id=routine_id,
            condition=RoutineCondition.TRUE,
            source_fresh=True,
            executed=True,
            spoken=str(routine.actions[0]["parameters"]["text"])
            if routine.actions
            else f"{routine.name} ran.",
            actions_taken=list(routine.actions),
        )
        self.runs.append(result)
        return result

    def _condition_met(self, routine: RoutineDefinition, source: dict[str, Any]) -> bool:
        expr = routine.condition_expression
        if expr == "temp_c < 15":
            return float(source.get("temp_c", 99)) < 15
        if expr == "build_failed == true":
            return bool(source.get("build_failed"))
        return False
