"""Tests for conversation, room resolution, and state machine."""

from uuid import uuid4

import pytest

from parker.adapters.mock_ha import MockHomeAssistant
from parker.context.conversation import ConversationManager
from parker.context.room import RoomResolver
from parker.context.state import StateMachine
from parker.contracts.actions import ActionCategory, ActionRequest
from parker.contracts.context import PARKERState
from parker.contracts.errors import AmbiguousDeviceError, ContextExpiredError, DeviceNotFoundError
from parker.contracts.voice import VoiceTurn, WakeEvent, WakeWordSource


def test_conversation_start_and_independent_devices() -> None:
    mgr = ConversationManager()
    a = mgr.start(voice_device_id="voice_a", area_id="living_room")
    b = mgr.start(voice_device_id="voice_b", area_id="bedroom")
    assert a.id != b.id
    assert mgr.get("voice_a") is not None
    assert mgr.get("voice_b") is not None


def test_conversation_follow_up_reuses_context() -> None:
    mgr = ConversationManager()
    ctx = mgr.start(voice_device_id="voice_pe_living_room", area_id="living_room")
    wake = WakeEvent(
        source=WakeWordSource.MANUAL,
        confidence=1.0,
        device_id="voice_pe_living_room",
        area_id="living_room",
    )
    mgr.add_turn("voice_pe_living_room", VoiceTurn(wake_event=wake))
    again = mgr.touch("voice_pe_living_room")
    assert again.id == ctx.id
    assert len(again.turns) == 1


def test_conversation_expiry() -> None:
    mgr = ConversationManager(expires_after_seconds=120)
    mgr.start(voice_device_id="voice_pe_living_room", area_id="living_room")
    mgr.advance_time("voice_pe_living_room", 130)
    with pytest.raises(ContextExpiredError):
        mgr.get_active("voice_pe_living_room")


def test_ensure_restarts_after_expiry() -> None:
    mgr = ConversationManager()
    first = mgr.start(voice_device_id="d1", area_id="living_room")
    mgr.expire_now("d1")
    second = mgr.ensure(voice_device_id="d1", area_id="living_room")
    assert second.id != first.id


def test_room_resolve_light() -> None:
    ha = MockHomeAssistant(latency_ms=0)
    resolver = RoomResolver(ha)
    light = resolver.resolve_light("living_room")
    assert light.entity_id == "light.living_room"


def test_room_resolve_light_no_area() -> None:
    ha = MockHomeAssistant(latency_ms=0)
    resolver = RoomResolver(ha)
    with pytest.raises(AmbiguousDeviceError):
        resolver.resolve_light(None)


def test_room_resolve_missing_light() -> None:
    ha = MockHomeAssistant(latency_ms=0)
    resolver = RoomResolver(ha)
    with pytest.raises(DeviceNotFoundError):
        resolver.resolve_light("hallway")


def test_resolve_action_fills_room_light() -> None:
    ha = MockHomeAssistant(latency_ms=0)
    resolver = RoomResolver(ha)
    action = ActionRequest(
        voice_turn_id=uuid4(),
        domain="light",
        service="turn_on",
        category=ActionCategory.ROUTINE,
        conversation_id=uuid4(),
    )
    resolved = resolver.resolve_action(
        action, area_id="living_room", resolve_room_light=True
    )
    assert resolved.target_entity == "light.living_room"


def test_cross_room_explicit_entity() -> None:
    ha = MockHomeAssistant(latency_ms=0)
    resolver = RoomResolver(ha)
    action = ActionRequest(
        voice_turn_id=uuid4(),
        domain="light",
        service="turn_on",
        target_entity="light.kitchen",
        category=ActionCategory.ROUTINE,
        conversation_id=uuid4(),
    )
    resolved = resolver.resolve_action(action, area_id="living_room")
    assert resolved.target_entity == "light.kitchen"


def test_state_machine_happy_path() -> None:
    sm = StateMachine()
    assert sm.state == PARKERState.IDLE
    sm.transition(PARKERState.LISTENING)
    sm.transition(PARKERState.TRANSCRIBING)
    sm.transition(PARKERState.THINKING)
    sm.transition(PARKERState.ACTING)
    sm.transition(PARKERState.SPEAKING)
    sm.transition(PARKERState.IDLE)
    assert sm.state == PARKERState.IDLE


def test_state_machine_confirmation_path() -> None:
    sm = StateMachine()
    sm.transition(PARKERState.LISTENING)
    sm.transition(PARKERState.TRANSCRIBING)
    sm.transition(PARKERState.THINKING)
    sm.transition(PARKERState.CONFIRMING)
    sm.transition(PARKERState.ACTING)
    sm.transition(PARKERState.SPEAKING)
    sm.transition(PARKERState.IDLE)


def test_state_machine_invalid_transition() -> None:
    sm = StateMachine()
    with pytest.raises(Exception):
        sm.transition(PARKERState.ACTING)


def test_system_status_updates() -> None:
    sm = StateMachine()
    updates: list[str] = []
    sm.on_change(lambda s: updates.append(s.state.value))
    sm.set_transcript("hello")
    sm.set_response("hi")
    status = sm.status()
    assert status.last_transcript == "hello"
    assert status.last_response == "hi"
    assert len(updates) >= 2
