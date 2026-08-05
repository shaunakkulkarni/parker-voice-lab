"""End-to-end mock integration tests."""

from pathlib import Path

import pytest

from parker.adapters.mock_ha import MockHomeAssistant
from parker.adapters.mock_hermes import MockHermes
from parker.contracts.actions import ActionCategory
from parker.contracts.errors import ContextExpiredError
from parker.receipts.store import ReceiptStore
from parker.simulator.latency import LatencyLogger
from parker.simulator.pipeline import VoicePipeline


@pytest.fixture
def pipeline(tmp_path: Path) -> VoicePipeline:
    return VoicePipeline(
        ha_adapter=MockHomeAssistant(),
        hermes_adapter=MockHermes(),
        stt_latency_ms=0,
        tts_latency_ms=0,
        hermes_latency_ms=0,
        ha_latency_ms=0,
        receipt_store=ReceiptStore(tmp_path / "receipts.jsonl"),
        latency_logger=LatencyLogger(tmp_path / "benchmarks.jsonl"),
    )


def test_cross_room_requires_explicit_room(pipeline: VoicePipeline) -> None:
    result = pipeline.run_utterance(
        "Turn on the kitchen light",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert result.action is not None
    assert result.action.target_entity == "light.kitchen"
    assert pipeline.ha_adapter.get_state("light.kitchen").state == "on"  # type: ignore[attr-defined]


def test_thermostat_change(pipeline: VoicePipeline) -> None:
    result = pipeline.run_utterance(
        "Set the thermostat to 24 degrees",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert result.action is not None
    assert result.action.domain == "climate"
    assert result.action.parameters["temperature"] == 24.0
    state = pipeline.ha_adapter.get_state("climate.living_room")  # type: ignore[attr-defined]
    assert state.attributes["temperature"] == 24.0


def test_deny_lock(pipeline: VoicePipeline) -> None:
    pipeline.run_utterance(
        "Unlock the front door",
        area_id="hallway",
        device_id="voice_pe_living_room",
    )
    denied = pipeline.run_utterance(
        "no",
        area_id="hallway",
        device_id="voice_pe_living_room",
    )
    assert denied.confirmed is False
    assert pipeline.ha_adapter.get_state("lock.front_door").state == "locked"  # type: ignore[attr-defined]


def test_play_music(pipeline: VoicePipeline) -> None:
    result = pipeline.run_utterance(
        "Play some music",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert result.action is not None
    assert result.category == ActionCategory.ROUTINE
    assert (
        pipeline.ha_adapter.get_state(  # type: ignore[attr-defined]
            "media_player.living_room_homepod"
        ).state
        == "playing"
    )


def test_pipeline_status_updates(pipeline: VoicePipeline) -> None:
    pipeline.run_utterance(
        "Turn on the living room light",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    status = pipeline.state.status()
    assert status.last_transcript == "Turn on the living room light"
    assert status.last_response is not None
    assert status.current_room == "living_room"


def test_context_expiry(pipeline: VoicePipeline) -> None:
    pipeline.run_utterance(
        "Turn on the light",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    pipeline.conversations.advance_time("voice_pe_living_room", 130)
    with pytest.raises(ContextExpiredError):
        pipeline.conversations.get_active("voice_pe_living_room")
    result = pipeline.run_utterance(
        "And the kitchen?",
        area_id="living_room",
        device_id="voice_pe_living_room",
        fail_on_expired_followup=True,
    )
    assert result.error_code == "context_expired"
    assert result.spoken


def test_two_turn_conversation(pipeline: VoicePipeline) -> None:
    first = pipeline.run_utterance(
        "What's the temperature?",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert first.category == ActionCategory.READ
    assert "degrees" in first.spoken.lower()

    second = pipeline.run_utterance(
        "And tomorrow?",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert second.error_code is None
    assert "tomorrow" in second.spoken.lower() or "degrees" in second.spoken.lower()
    ctx = pipeline.conversations.get_active("voice_pe_living_room")
    assert ctx.last_topic == "temperature"


def test_confirmation_then_confirm(pipeline: VoicePipeline) -> None:
    pending = pipeline.run_utterance(
        "Lock the front door",
        area_id="hallway",
        device_id="voice_pe_living_room",
    )
    assert pending.action is not None
    assert pending.action.requires_confirmation is True
    assert pending.turn.state.value == "confirming"
    assert pending.action_result is None

    confirmed = pipeline.run_utterance(
        "yes",
        area_id="hallway",
        device_id="voice_pe_living_room",
    )
    assert confirmed.confirmed is True
    assert confirmed.action_result is not None
    assert confirmed.action_result.success is True
    assert pipeline.ha_adapter.get_state("lock.front_door").state == "locked"
    assert pipeline.receipt_store is not None
    assert len(pipeline.receipt_store.all()) == 1
    assert pipeline.receipt_store.all()[0].confirmed is True


def test_device_not_found_spoken_error(pipeline: VoicePipeline) -> None:
    result = pipeline.run_utterance(
        "Turn on the garage light",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert result.error_code == "device_not_found"
    assert result.spoken
    assert result.action_result is None
    assert result.turn.state.value in {"complete", "error"}


def test_ha_offline_error_injection(tmp_path: Path) -> None:
    ha = MockHomeAssistant(offline_entities={"light.living_room"})
    pipeline = VoicePipeline(
        ha_adapter=ha,
        hermes_adapter=MockHermes(),
        stt_latency_ms=0,
        tts_latency_ms=0,
        hermes_latency_ms=0,
        ha_latency_ms=0,
        receipt_store=ReceiptStore(tmp_path / "receipts.jsonl"),
        latency_logger=LatencyLogger(tmp_path / "benchmarks.jsonl"),
    )
    result = pipeline.run_utterance(
        "Turn on the living room light",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert result.error_code == "service_unavailable"
    assert "offline" in result.spoken.lower()
    assert result.action_result is None
