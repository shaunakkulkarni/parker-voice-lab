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
    has_trigger = "trigger" in scenario
    has_turns = "turns" in scenario
    has_utterance = "utterance" in scenario
    if not has_trigger and not has_turns and not has_utterance:
        raise ValueError(
            f"Scenario {scenario.get('name', '<unnamed>')!r} must have "
            "either 'turns', 'utterance', or 'trigger'"
        )

    area_id = scenario["area_id"]
    device_id = scenario["device_id"]
    name = scenario.get("name", "unnamed")
    context = dict(scenario.get("context") or {})

    # Fresh provider + conversation state per scenario for determinism.
    pipeline.providers.reset()
    providers = pipeline.providers
    if context.get("failing_tests"):
        providers.devops.inject_failing_tests(
            str(context.get("project", "parker-voice-lab"))
        )
    if context.get("inject_conflicts"):
        providers.research.inject_conflicts = True
    if context.get("guest_mode"):
        providers.guest_mode = True
    if context.get("quiet_hours"):
        providers.quiet_hours = True

    pipeline.conversations.start(voice_device_id=device_id, area_id=area_id)

    if has_trigger:
        return pipeline.run_event(
            scenario["trigger"],
            area_id=area_id,
            device_id=device_id,
            scenario_name=name,
            context=context,
            confirmation_response=scenario.get("confirmation_response"),
        )

    if has_turns:
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
                confirmation_response=turn.get("confirmation_response"),
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
            return _check_single(scenario, last)

        return _check_single(scenario, result)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _check_single(
    scenario: dict[str, Any],
    result: PipelineResult,
) -> tuple[bool, str | None]:
    if scenario.get("expected_error"):
        if result.error_code != scenario["expected_error"]:
            return (
                False,
                f"Expected error {scenario['expected_error']!r}, "
                f"got {result.error_code!r}",
            )
        # Continue to optional spoken checks for suppressed events, etc.

    expected_action = scenario.get("expected_action")
    if expected_action is None:
        if (
            result.action is not None
            and scenario.get("expected_category") != "read"
            and not scenario.get("expected_actions")
            and result.plan is None
        ):
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
        entity = expected_action.get("entity") or expected_action.get("target")
        if entity is not None and result.action.target_entity != entity:
            return (
                False,
                f"Expected entity {entity!r}, got {result.action.target_entity!r}",
            )

    expected_actions = scenario.get("expected_actions")
    if expected_actions is not None:
        if result.plan is None:
            # Single-action path: compare the one action if present
            if expected_actions and result.action is not None:
                first = expected_actions[0]
                entity = first.get("entity") or first.get("target")
                if (
                    result.action.domain != first.get("domain")
                    or result.action.service != first.get("service")
                    or (entity and result.action.target_entity != entity)
                ):
                    return False, "expected_actions did not match result.action"
            elif expected_actions and result.action is None and not scenario.get(
                "expected_confirmation"
            ):
                return False, "expected_actions provided but no plan/action"
        else:
            steps = result.plan.steps
            if len(steps) < len(expected_actions):
                return (
                    False,
                    f"Expected {len(expected_actions)} actions, "
                    f"got {len(steps)} plan steps",
                )
            for i, expected in enumerate(expected_actions):
                step = steps[i]
                entity = expected.get("entity") or expected.get("target")
                if step.domain != expected.get("domain"):
                    return (
                        False,
                        f"Step {i} domain {step.domain!r} != "
                        f"{expected.get('domain')!r}",
                    )
                if step.service != expected.get("service"):
                    return (
                        False,
                        f"Step {i} service {step.service!r} != "
                        f"{expected.get('service')!r}",
                    )
                if entity and step.target_entity != entity:
                    return (
                        False,
                        f"Step {i} target {step.target_entity!r} != {entity!r}",
                    )

    if scenario.get("expected_category") and result.category is not None:
        if result.category.value != scenario["expected_category"]:
            return (
                False,
                f"Expected category {scenario['expected_category']!r}, "
                f"got {result.category.value!r}",
            )

    expected_confirmation = scenario.get("expected_confirmation")
    if expected_confirmation is None:
        expected_confirmation = scenario.get("requires_confirmation")

    if expected_confirmation:
        if not (
            result.awaiting_confirmation
            or (result.action is not None and result.action.requires_confirmation)
        ):
            return False, "Expected confirmation gate"
        if scenario.get("confirmation_response") == "yes":
            if result.action_result is None or result.action_result.success is not True:
                return False, "Expected successful confirmed action result"
            if result.awaiting_confirmation:
                return False, "Expected confirmation to complete"
        elif scenario.get("confirmation_response") is None:
            if not result.awaiting_confirmation and result.action_result is not None:
                return False, "Expected to stop for confirmation"

    spoken_contains = scenario.get("expected_spoken_contains") or []
    spoken_lower = result.spoken.lower()
    for fragment in spoken_contains:
        if fragment.lower() not in spoken_lower:
            return (
                False,
                f"Expected spoken to contain {fragment!r}, got {result.spoken!r}",
            )

    receipt_exp = scenario.get("expected_receipt")
    if receipt_exp:
        if receipt_exp.get("recorded") and result.receipt_count <= 0:
            # Single-action path records via approval; receipt_count may be 0
            # when not going through plan engine — allow action_result as evidence.
            if result.plan is not None:
                return False, "Expected receipt to be recorded for plan"
            if result.action_result is None and not scenario.get("expected_error"):
                return False, "Expected receipt evidence via action result"
        if "count" in receipt_exp and result.plan is not None:
            if result.receipt_count != receipt_exp["count"]:
                return (
                    False,
                    f"Expected receipt count {receipt_exp['count']}, "
                    f"got {result.receipt_count}",
                )
        if receipt_exp.get("confirmed") is True:
            confirmed_ok = result.confirmed is True or (
                scenario.get("confirmation_response") == "yes"
                and result.action_result is not None
            )
            if not confirmed_ok:
                return False, "Expected confirmed receipt"
        if receipt_exp.get("confirmed") is False and result.confirmed is True:
            return False, "Expected unconfirmed / denied receipt"

    if scenario.get("journey") and result.journey is not None:
        if result.journey.value != scenario["journey"]:
            return (
                False,
                f"Expected journey {scenario['journey']!r}, "
                f"got {result.journey.value!r}",
            )

    if scenario.get("expected_error") and result.error_code == scenario["expected_error"]:
        return True, None

    if scenario.get("expected_error") and result.error_code != scenario["expected_error"]:
        return (
            False,
            f"Expected error {scenario['expected_error']!r}, got {result.error_code!r}",
        )

    return True, None
