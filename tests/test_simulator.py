"""Simulator scenario tests."""

from pathlib import Path

import pytest

from parker.adapters.mock_ha import MockHomeAssistant
from parker.adapters.mock_hermes import MockHermes
from parker.receipts.store import ReceiptStore
from parker.simulator.latency import LatencyLogger
from parker.simulator.pipeline import VoicePipeline
from parker.simulator.scenarios import (
    assert_scenario_expectations,
    load_scenarios,
    run_scenario,
)


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


def test_all_scenarios(pipeline: VoicePipeline) -> None:
    scenarios = load_scenarios()
    assert len(scenarios) >= 8
    for scenario in scenarios:
        result = run_scenario(pipeline, scenario)
        assert_scenario_expectations(scenario, result)


def test_simple_light_on(pipeline: VoicePipeline) -> None:
    result = pipeline.run_utterance(
        "Turn on the living room light",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert result.action is not None
    assert result.action.target_entity == "light.living_room"
    assert result.action_result is not None
    assert result.action_result.success is True
    assert pipeline.ha_adapter.get_state("light.living_room").state == "on"  # type: ignore[attr-defined]


def test_ambiguous_resolves_to_room(pipeline: VoicePipeline) -> None:
    result = pipeline.run_utterance(
        "Turn on the light",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert result.action is not None
    assert result.action.target_entity == "light.living_room"


def test_confirmation_required_for_lock(pipeline: VoicePipeline) -> None:
    result = pipeline.run_utterance(
        "Lock the front door",
        area_id="hallway",
        device_id="voice_pe_living_room",
        confirmation_response="yes",
    )
    assert result.action is not None
    assert result.action.requires_confirmation is True
    assert result.action_result is not None
    assert result.confirmed is True


def test_cancel_pending_confirmation(pipeline: VoicePipeline) -> None:
    pending = pipeline.run_utterance(
        "Lock the front door",
        area_id="hallway",
        device_id="voice_pe_living_room",
    )
    assert pending.action is not None
    assert pending.turn.state.value == "confirming"

    cancelled = pipeline.run_utterance(
        "Cancel that",
        area_id="hallway",
        device_id="voice_pe_living_room",
    )
    assert cancelled.confirmed is False
    assert "cancel" in cancelled.spoken.lower()


def test_context_followup(pipeline: VoicePipeline) -> None:
    pipeline.run_utterance(
        "What's the temperature?",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    follow = pipeline.run_utterance(
        "And tomorrow?",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert follow.error_code is None
    assert "tomorrow" in follow.spoken.lower() or "degrees" in follow.spoken.lower()


def test_context_expiry(pipeline: VoicePipeline) -> None:
    pipeline.run_utterance(
        "Turn on the light",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    pipeline.conversations.advance_time("voice_pe_living_room", 130)
    result = pipeline.run_utterance(
        "And the kitchen?",
        area_id="living_room",
        device_id="voice_pe_living_room",
        fail_on_expired_followup=True,
    )
    assert result.error_code == "context_expired"


def test_device_not_found_spoken_error(pipeline: VoicePipeline) -> None:
    result = pipeline.run_utterance(
        "Turn on the garage light",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert result.error_code == "device_not_found"
    assert result.spoken


def test_action_receipt_logged(pipeline: VoicePipeline) -> None:
    pipeline.run_utterance(
        "Turn on the living room light",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert pipeline.receipt_store is not None
    assert len(pipeline.receipt_store.all()) == 1


def test_latency_reported(pipeline: VoicePipeline) -> None:
    result = pipeline.run_utterance(
        "What time is it?",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert result.latency is not None
    assert result.latency.total_ms >= 0
    assert result.turn.total_ms is not None
