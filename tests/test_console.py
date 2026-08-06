"""Tests for the transport-independent Test Console controller."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from parker.adapters.base import HermesAdapter, HermesResponse, HomeAssistantAdapter
from parker.adapters.mock_ha import MockHomeAssistant
from parker.adapters.mock_hermes import MockHermes
from parker.contracts.context import ConversationContext, DeviceState
from parker.display.console import (
    ConsoleAdapterError,
    ConsoleBusyError,
    ConsoleConfirmationError,
    ConsoleController,
)
from parker.simulator.scenarios import load_scenarios


class _LiveHomeAssistant(HomeAssistantAdapter):
    """Stand-in for a non-mock HA adapter; must be rejected by the console."""

    def get_state(self, entity_id: str) -> DeviceState:
        raise NotImplementedError

    def list_states(self) -> list[DeviceState]:
        return []

    def entities_in_area(self, area_id: str) -> list[DeviceState]:
        return []

    def call_service(
        self,
        domain: str,
        service: str,
        *,
        entity_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> DeviceState | None:
        return None


class _LiveHermes(HermesAdapter):
    """Stand-in for a non-mock Hermes adapter; must be rejected by the console."""

    def reason(
        self,
        utterance: str,
        conversation: ConversationContext,
        *,
        voice_turn_id: UUID,
    ) -> HermesResponse:
        raise NotImplementedError


@pytest.fixture
def console(tmp_path: Path) -> ConsoleController:
    return ConsoleController(receipt_path=tmp_path / "receipts.jsonl")


def test_manual_safe_light_command(console: ConsoleController) -> None:
    run = console.run_command(
        "Turn on the living room light",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert run.run_type == "manual"
    assert run.passed is None
    assert run.spoken_response
    assert run.action is not None
    assert run.action.target_entity == "light.living_room"
    assert run.action_result is not None
    assert run.action_result.success is True
    assert run.error_code is None
    assert console.ha.get_state("light.living_room").state == "on"


def test_manual_temperature_query(console: ConsoleController) -> None:
    run = console.run_command(
        "What's the temperature?",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert run.passed is None
    assert "degrees" in run.spoken_response.lower()
    assert run.error_code is None


def test_unknown_device_structured_error(console: ConsoleController) -> None:
    run = console.run_command(
        "Turn on the garage light",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert run.error_code == "device_not_found"
    assert run.spoken_response
    assert run.action_result is None


def test_ha_offline_structured_error(tmp_path: Path) -> None:
    ha = MockHomeAssistant(offline_entities={"light.living_room"})
    console = ConsoleController(
        receipt_path=tmp_path / "receipts.jsonl",
        ha_adapter=ha,
    )
    run = console.run_command(
        "Turn on the living room light",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert run.error_code == "service_unavailable"
    assert "offline" in run.spoken_response.lower()


def test_confirmation_creates_pending_without_service_call(
    console: ConsoleController,
) -> None:
    run = console.run_command(
        "Unlock the front door",
        area_id="hallway",
        device_id="voice_pe_living_room",
    )
    assert run.action is not None
    assert run.action.requires_confirmation is True
    assert run.action_result is None
    assert console.pending_confirmation is not None
    assert console.ha.service_calls == []
    assert console.ha.get_state("lock.front_door").state == "locked"


def test_confirm_executes_and_receipt(console: ConsoleController) -> None:
    console.run_command(
        "Unlock the front door",
        area_id="hallway",
        device_id="voice_pe_living_room",
    )
    run = console.resolve_confirmation("confirm")
    assert run.action_result is not None
    assert run.action_result.success is True
    assert console.ha.get_state("lock.front_door").state == "unlocked"
    assert console.pending_confirmation is None
    assert run.receipt is not None
    assert run.receipt.confirmed is True
    session = console.session()
    assert session.pending_confirmation is None
    assert len(session.recent_receipts) >= 1


def test_deny_does_not_execute(console: ConsoleController) -> None:
    console.run_command(
        "Unlock the front door",
        area_id="hallway",
        device_id="voice_pe_living_room",
    )
    run = console.resolve_confirmation("deny")
    assert run.confirmed is False or run.action_result is None
    assert console.ha.get_state("lock.front_door").state == "locked"
    assert console.pending_confirmation is None
    assert any(c.service == "unlock" for c in console.ha.service_calls) is False


def test_cancel_does_not_execute(console: ConsoleController) -> None:
    console.run_command(
        "Unlock the front door",
        area_id="hallway",
        device_id="voice_pe_living_room",
    )
    run = console.resolve_confirmation("cancel")
    assert console.ha.get_state("lock.front_door").state == "locked"
    assert console.pending_confirmation is None
    assert "cancel" in run.spoken_response.lower()


def test_reset_clears_session_keeps_persistent_receipts(
    console: ConsoleController, tmp_path: Path
) -> None:
    console.run_command(
        "Turn on the living room light",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    console.run_command(
        "Unlock the front door",
        area_id="hallway",
        device_id="voice_pe_living_room",
    )
    assert console.pending_confirmation is not None
    receipt_path = tmp_path / "receipts.jsonl"
    # Confirm to create a persistent receipt
    console.resolve_confirmation("confirm")
    assert receipt_path.exists()
    before_disk = receipt_path.read_text(encoding="utf-8")
    assert before_disk.strip()

    snapshot = console.reset()
    assert snapshot.pending_confirmation is None
    assert snapshot.recent_runs == []
    assert snapshot.recent_receipts == []
    assert all(e.kind == "session_reset" for e in snapshot.recent_events)
    assert len(snapshot.recent_events) <= 1
    assert snapshot.status.state.value == "idle"
    assert snapshot.status.last_transcript is None
    assert snapshot.status.last_response is None
    assert console.ha.get_state("light.living_room").state == "off"
    assert console.ha.get_state("lock.front_door").state == "locked"
    assert receipt_path.read_text(encoding="utf-8") == before_disk


def test_run_and_event_history_capped_at_20(console: ConsoleController) -> None:
    for i in range(25):
        console.run_command(
            "What's the temperature?",
            area_id="living_room",
            device_id="voice_pe_living_room",
            scenario_name=f"manual-{i}",
        )
    session = console.session()
    assert len(session.recent_runs) == 20
    assert len(session.recent_events) == 20


def test_scenario_pass_fail_uses_fixture_expectations(console: ConsoleController) -> None:
    passed = console.run_scenario("Simple light on")
    assert passed.passed is True
    assert passed.run_type == "scenario"
    assert passed.scenario_name == "Simple light on"

    # Force a failure by using a scenario after poisoning HA offline for its entity
    console.ha.inject_offline("light.living_room")
    failed = console.run_scenario("Simple light on")
    assert failed.passed is False
    assert failed.error_code == "service_unavailable"


def test_run_all_executes_every_fixture_scenario(console: ConsoleController) -> None:
    scenarios = load_scenarios()
    result = console.run_all_scenarios()
    assert result.summary.total == len(scenarios)
    assert len(result.runs) == len(scenarios)
    assert result.summary.passed + result.summary.failed == result.summary.total
    assert result.summary.passed == result.summary.total


def test_concurrent_execution_rejected(console: ConsoleController) -> None:
    started = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []

    def slow_hold() -> None:
        with console._lock:  # noqa: SLF001
            started.set()
            release.wait(timeout=2.0)

    holder = threading.Thread(target=slow_hold)
    holder.start()
    assert started.wait(timeout=1.0)

    def try_run() -> None:
        try:
            console.run_command(
                "What's the temperature?",
                area_id="living_room",
                device_id="voice_pe_living_room",
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    runner = threading.Thread(target=try_run)
    runner.start()
    # Give the runner a moment to hit the busy path
    time.sleep(0.05)
    release.set()
    holder.join(timeout=2.0)
    runner.join(timeout=2.0)
    assert errors
    assert isinstance(errors[0], ConsoleBusyError)


def test_health_snapshot_is_mock_only(console: ConsoleController) -> None:
    health = console.health()
    assert health.mode == "mock"
    assert health.home_assistant == "ready"
    assert health.hermes == "ready"
    assert health.stt == "simulated"
    assert health.tts == "simulated"
    assert health.voice_preview_edition == "not_connected"
    assert health.live_device_actions is False
    assert isinstance(console.pipeline.ha_adapter, MockHomeAssistant)
    assert isinstance(console.pipeline.hermes_adapter, MockHermes)


def test_rejects_non_mock_home_assistant(tmp_path: Path) -> None:
    with pytest.raises(ConsoleAdapterError, match="MockHomeAssistant"):
        ConsoleController(
            receipt_path=tmp_path / "receipts.jsonl",
            ha_adapter=_LiveHomeAssistant(),  # type: ignore[arg-type]
        )


def test_rejects_non_mock_hermes(tmp_path: Path) -> None:
    with pytest.raises(ConsoleAdapterError, match="MockHermes"):
        ConsoleController(
            receipt_path=tmp_path / "receipts.jsonl",
            hermes_adapter=_LiveHermes(),  # type: ignore[arg-type]
        )


def test_mock_home_assistant_injection_supports_offline(tmp_path: Path) -> None:
    """Regression: MockHomeAssistant injection remains valid for offline tests."""
    ha = MockHomeAssistant(offline_entities={"light.living_room"})
    console = ConsoleController(
        receipt_path=tmp_path / "receipts.jsonl",
        ha_adapter=ha,
    )
    run = console.run_command(
        "Turn on the living room light",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    assert run.error_code == "service_unavailable"
    health = console.health()
    assert health.mode == "mock"
    assert health.live_device_actions is False


def test_resolve_confirmation_without_pending_raises(console: ConsoleController) -> None:
    with pytest.raises(ConsoleConfirmationError):
        console.resolve_confirmation("confirm")
