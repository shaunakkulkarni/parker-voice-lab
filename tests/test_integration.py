"""End-to-end mock integration tests."""

from pathlib import Path

import pytest

from parker.adapters.mock_ha import MockHomeAssistant
from parker.adapters.mock_hermes import MockHermes
from parker.contracts.actions import ActionCategory
from parker.receipts.store import ReceiptStore
from parker.simulator.latency import LatencyLogger
from parker.simulator.pipeline import VoicePipeline


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
