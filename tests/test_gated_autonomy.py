"""Tests for gated autonomy scenarios and failure paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from parker.adapters.mock_ha import MockHomeAssistant
from parker.adapters.mock_hermes import MockHermes
from parker.contracts.plan import GatePolicy, Journey
from parker.display.console import ConsoleController
from parker.receipts.store import ReceiptStore
from parker.simulator.latency import LatencyLogger
from parker.simulator.pipeline import VoicePipeline
from parker.simulator.scenarios import (
    assert_scenario_expectations,
    load_scenarios,
    run_scenario,
)

GATED_SCENARIOS = [
    "shower_routine_readout_and_playlist",
    "shower_routine_quiet_hours_queued",
    "shower_routine_guest_mode_private_suppressed",
    "shower_sensor_false_positive_suppressed",
    "dev_ops_test_run_reports_result",
    "dev_ops_deploy_requires_confirmation",
    "dev_ops_failing_tests_honest_report",
    "research_rundown_cited_sources",
    "research_conflicting_claims_disclosed",
    "routine_condition_true_executes",
    "routine_condition_false_skips",
    "routine_stale_source_no_action",
    "anomaly_door_open_flagged",
    "anomaly_insufficient_history_no_claim",
    "travel_prep_plan_generated",
    "travel_checkin_requires_confirmation",
]


@pytest.fixture
def pipeline(tmp_path: Path) -> VoicePipeline:
    return VoicePipeline(
        ha_adapter=MockHomeAssistant(latency_ms=0),
        hermes_adapter=MockHermes(latency_ms=0),
        stt_latency_ms=0,
        tts_latency_ms=0,
        hermes_latency_ms=0,
        ha_latency_ms=0,
        receipt_store=ReceiptStore(tmp_path / "receipts.jsonl"),
        latency_logger=LatencyLogger(tmp_path / "benchmarks.jsonl"),
    )


def _by_name() -> dict[str, dict[str, Any]]:
    return {s["name"]: s for s in load_scenarios()}


@pytest.mark.parametrize("name", GATED_SCENARIOS)
def test_gated_scenario(pipeline: VoicePipeline, name: str) -> None:
    scenario = _by_name()[name]
    result = run_scenario(pipeline, scenario)
    assert_scenario_expectations(scenario, result)


def test_all_sixteen_gated_scenarios_present() -> None:
    names = {s["name"] for s in load_scenarios()}
    missing = set(GATED_SCENARIOS) - names
    assert not missing, f"Missing scenarios: {missing}"


def test_shower_false_positive_no_media(pipeline: VoicePipeline) -> None:
    scenario = _by_name()["shower_sensor_false_positive_suppressed"]
    result = run_scenario(pipeline, scenario)
    assert result.error_code == "false_positive_suppressed"
    assert pipeline.providers.media.calls == []


def test_deploy_stops_without_confirmation(pipeline: VoicePipeline) -> None:
    result = pipeline.run_utterance(
        "Deploy the dashboard",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert result.awaiting_confirmation is True
    assert result.action is not None
    assert result.action.domain == "devops"
    assert result.action.service == "deploy"
    assert "dashboard" not in pipeline.providers.devops.deployed


def test_deploy_requires_exact_confirmation(pipeline: VoicePipeline) -> None:
    pending = pipeline.run_utterance(
        "Deploy the dashboard",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert pending.awaiting_confirmation
    confirmed = pipeline.run_utterance(
        "yes",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert "dashboard" in pipeline.providers.devops.deployed
    assert confirmed.action_result is not None
    assert confirmed.action_result.success is True
    assert confirmed.receipt_count >= 1


def test_travel_checkin_gates(pipeline: VoicePipeline) -> None:
    pending = pipeline.run_utterance(
        "Check in for flight UA412",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert pending.awaiting_confirmation
    assert pipeline.providers.travel.checked_in == []
    done = pipeline.run_utterance(
        "yes",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert "UA412" in pipeline.providers.travel.checked_in
    assert "Checked in" in done.spoken


def test_routine_steps_auto_execute_without_per_step_confirm(
    pipeline: VoicePipeline,
) -> None:
    scenario = _by_name()["shower_routine_readout_and_playlist"]
    result = run_scenario(pipeline, scenario)
    assert result.plan is not None
    assert result.awaiting_confirmation is False
    assert all(s.gate_policy == GatePolicy.AUTO for s in result.plan.steps)
    assert result.receipt_count == 2
    assert result.latency is not None
    assert result.latency.total_ms >= 0


def test_console_exposes_new_journeys(tmp_path: Path) -> None:
    console = ConsoleController(receipt_path=tmp_path / "receipts.jsonl")
    journeys = console.list_journeys()
    assert "run_my_systems" in journeys
    assert "delegate_the_routine" in journeys
    assert "watch_the_home" in journeys
    run = console.run_scenario("dev_ops_deploy_requires_confirmation")
    assert run.journey == Journey.RUN_MY_SYSTEMS.value
    assert run.risk_class == "consequential"
    assert run.plan is not None
    assert run.authority in {"user_voice_confirmation", "auto", None} or run.receipt


def test_failing_tests_do_not_claim_success(pipeline: VoicePipeline) -> None:
    scenario = _by_name()["dev_ops_failing_tests_honest_report"]
    result = run_scenario(pipeline, scenario)
    assert "failed" in result.spoken.lower()
    assert "not reporting success" in result.spoken.lower()
    assert result.action_result is not None
    assert result.action_result.success is True  # verified CLI result
    assert result.action_result.new_state is not None
    assert result.action_result.new_state.get("tests_passed") is False


def test_research_discloses_conflicts(pipeline: VoicePipeline) -> None:
    scenario = _by_name()["research_conflicting_claims_disclosed"]
    result = run_scenario(pipeline, scenario)
    assert "conflicting" in result.spoken.lower()
    assert result.action_result is not None
    assert result.action_result.new_state is not None
    assert result.action_result.new_state.get("conflicting_claims")


def test_stale_routine_source_no_side_effect(pipeline: VoicePipeline) -> None:
    scenario = _by_name()["routine_stale_source_no_action"]
    result = run_scenario(pipeline, scenario)
    assert "stale" in result.spoken.lower()
    assert result.action_result is not None
    assert result.action_result.new_state is not None
    assert result.action_result.new_state.get("executed") is False
