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
    if isinstance(result, list):
        if scenario.get("expected_error"):
            assert any(r.error_code == scenario["expected_error"] for r in result), (
                f"Expected error {scenario['expected_error']} in {[r.error_code for r in result]}"
            )
            return
        last = result[-1]
        if scenario.get("expected_category"):
            assert last.category is not None
            assert last.category.value == scenario["expected_category"]
        return

    if scenario.get("expected_error"):
        assert result.error_code == scenario["expected_error"]
        return

    expected_action = scenario.get("expected_action")
    if expected_action is None:
        assert result.action is None or scenario.get("expected_category") == "read"
    else:
        assert result.action is not None
        assert result.action.domain == expected_action["domain"]
        assert result.action.service == expected_action["service"]
        assert result.action.target_entity == expected_action["entity"]

    if scenario.get("expected_category") and result.category is not None:
        assert result.category.value == scenario["expected_category"]

    if scenario.get("requires_confirmation"):
        assert result.action is not None
        assert result.action.requires_confirmation is True
        if scenario.get("confirmation_response") == "yes":
            assert result.action_result is not None
            assert result.action_result.success is True
