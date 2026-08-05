"""Load and run predefined voice scenarios."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from parker.simulator.pipeline import PipelineResult, VoicePipeline

DEFAULT_SCENARIOS_PATH = Path(__file__).resolve().parents[3] / "fixtures" / "scenarios.json"


def load_scenarios(path: Path | str | None = None) -> list[dict[str, Any]]:
    p = Path(path) if path else DEFAULT_SCENARIOS_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("scenarios.json must be a list")
    return data


def run_scenario(
    pipeline: VoicePipeline, scenario: dict[str, Any]
) -> PipelineResult | list[PipelineResult]:
    """Execute a scenario; multi-turn scenarios return a list of results."""
    if "turns" not in scenario and "utterance" not in scenario:
        raise ValueError(
            f"Scenario {scenario.get('name', '<unnamed>')!r} must have "
            "either 'turns' or 'utterance'"
        )

    area_id = scenario["area_id"]
    device_id = scenario["device_id"]
    name = scenario.get("name", "unnamed")

    # Fresh conversation per scenario unless multi-turn
    pipeline.conversations.start(voice_device_id=device_id, area_id=area_id)

    if "turns" in scenario:
        results: list[PipelineResult] = []
        for i, turn in enumerate(scenario["turns"]):
            if "wait_seconds" in turn:
                pipeline.conversations.advance_time(device_id, float(turn["wait_seconds"]))
                continue
            utterance = turn["utterance"]
            # After a wait that expires context, follow-ups should fail
            fail_on_expired = scenario.get("expected_error") == "context_expired" and i > 0
            result = pipeline.run_utterance(
                utterance,
                area_id=area_id,
                device_id=device_id,
                scenario_name=name,
                reuse_conversation=True,
                fail_on_expired_followup=fail_on_expired,
            )
            results.append(result)
        return results

    return pipeline.run_utterance(
        scenario["utterance"],
        area_id=area_id,
        device_id=device_id,
        confirmation_response=scenario.get("confirmation_response"),
        scenario_name=name,
        reuse_conversation=True,
    )


def assert_scenario_expectations(
    scenario: dict[str, Any],
    result: PipelineResult | list[PipelineResult],
) -> None:
    """Validate result(s) against scenario expectations (for tests)."""
    ok, message = check_scenario_expectations(scenario, result)
    assert ok, message


def check_scenario_expectations(
    scenario: dict[str, Any],
    result: PipelineResult | list[PipelineResult],
) -> tuple[bool, str | None]:
    """Return (passed, failure_message) for fixture expectations without raising."""
    try:
        if isinstance(result, list):
            if scenario.get("expected_error"):
                if not any(r.error_code == scenario["expected_error"] for r in result):
                    return (
                        False,
                        f"Expected error {scenario['expected_error']} in "
                        f"{[r.error_code for r in result]}",
                    )
                return True, None
            last = result[-1]
            if scenario.get("expected_category"):
                if last.category is None:
                    return False, "Expected category but result.category is None"
                if last.category.value != scenario["expected_category"]:
                    return (
                        False,
                        f"Expected category {scenario['expected_category']!r}, "
                        f"got {last.category.value!r}",
                    )
            return True, None

        if scenario.get("expected_error"):
            if result.error_code != scenario["expected_error"]:
                return (
                    False,
                    f"Expected error {scenario['expected_error']!r}, "
                    f"got {result.error_code!r}",
                )
            return True, None

        expected_action = scenario.get("expected_action")
        if expected_action is None:
            if result.action is not None and scenario.get("expected_category") != "read":
                return False, f"Expected no action, got {result.action}"
        else:
            if result.action is None:
                return False, "Expected action but result.action is None"
            if result.action.domain != expected_action["domain"]:
                return (
                    False,
                    f"Expected domain {expected_action['domain']!r}, "
                    f"got {result.action.domain!r}",
                )
            if result.action.service != expected_action["service"]:
                return (
                    False,
                    f"Expected service {expected_action['service']!r}, "
                    f"got {result.action.service!r}",
                )
            if result.action.target_entity != expected_action["entity"]:
                return (
                    False,
                    f"Expected entity {expected_action['entity']!r}, "
                    f"got {result.action.target_entity!r}",
                )

        if scenario.get("expected_category") and result.category is not None:
            if result.category.value != scenario["expected_category"]:
                return (
                    False,
                    f"Expected category {scenario['expected_category']!r}, "
                    f"got {result.category.value!r}",
                )

        if scenario.get("requires_confirmation"):
            if result.action is None:
                return False, "Expected confirmation action but action is None"
            if result.action.requires_confirmation is not True:
                return False, "Expected requires_confirmation=True"
            if scenario.get("confirmation_response") == "yes":
                if result.action_result is None or result.action_result.success is not True:
                    return False, "Expected successful confirmed action result"
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
