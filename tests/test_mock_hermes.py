"""Tests for the mock Hermes adapter."""

from uuid import uuid4

import pytest

from parker.adapters.mock_hermes import MockHermes
from parker.contracts.actions import ActionCategory
from parker.contracts.context import ConversationContext


@pytest.fixture
def hermes() -> MockHermes:
    return MockHermes(latency_ms=0)


@pytest.fixture
def conversation() -> ConversationContext:
    return ConversationContext(
        area_id="living_room",
        voice_device_id="voice_pe_living_room",
    )


def test_turn_on_living_room_light(hermes: MockHermes, conversation: ConversationContext) -> None:
    turn_id = uuid4()
    resp = hermes.reason(
        "Turn on the living room light",
        conversation,
        voice_turn_id=turn_id,
    )
    assert resp.action_request is not None
    assert resp.action_request.domain == "light"
    assert resp.action_request.service == "turn_on"
    assert resp.action_request.target_entity == "light.living_room"
    assert resp.category == ActionCategory.ROUTINE
    assert resp.requires_confirmation is False


def test_lock_requires_confirmation(hermes: MockHermes, conversation: ConversationContext) -> None:
    resp = hermes.reason(
        "Lock the front door",
        conversation,
        voice_turn_id=uuid4(),
    )
    assert resp.requires_confirmation is True
    assert resp.category == ActionCategory.CONSEQUENTIAL
    assert resp.action_request is not None
    assert resp.action_request.target_entity == "lock.front_door"


def test_temperature_query(hermes: MockHermes, conversation: ConversationContext) -> None:
    resp = hermes.reason(
        "What's the temperature?",
        conversation,
        voice_turn_id=uuid4(),
    )
    assert resp.category == ActionCategory.READ
    assert resp.action_request is None
    assert resp.topic == "temperature"
    assert "temperature" in resp.spoken.lower() or "degrees" in resp.spoken.lower()


def test_set_thermostat(hermes: MockHermes, conversation: ConversationContext) -> None:
    resp = hermes.reason(
        "Set the thermostat to 24 degrees",
        conversation,
        voice_turn_id=uuid4(),
    )
    assert resp.action_request is not None
    assert resp.action_request.domain == "climate"
    assert resp.action_request.service == "set_temperature"
    assert resp.action_request.parameters["temperature"] == 24.0


def test_ambiguous_light_resolve_flag(
    hermes: MockHermes, conversation: ConversationContext
) -> None:
    resp = hermes.reason("Turn on the light", conversation, voice_turn_id=uuid4())
    assert resp.resolve_room_light is True
    assert resp.action_request is not None
    assert resp.action_request.target_entity is None


def test_device_not_found(hermes: MockHermes, conversation: ConversationContext) -> None:
    resp = hermes.reason(
        "Turn on the garage light",
        conversation,
        voice_turn_id=uuid4(),
    )
    assert resp.error_code == "device_not_found"
    assert resp.action_request is None


def test_cancel_and_confirm(hermes: MockHermes, conversation: ConversationContext) -> None:
    cancel = hermes.reason("Cancel that", conversation, voice_turn_id=uuid4())
    assert cancel.cancel is True
    yes = hermes.reason("yes", conversation, voice_turn_id=uuid4())
    assert yes.confirm is True
    no = hermes.reason("no", conversation, voice_turn_id=uuid4())
    assert no.deny is True


def test_play_music(hermes: MockHermes, conversation: ConversationContext) -> None:
    resp = hermes.reason("Play some music", conversation, voice_turn_id=uuid4())
    assert resp.action_request is not None
    assert resp.action_request.domain == "media_player"
    assert resp.action_request.service == "play_media"


def test_error_injection(conversation: ConversationContext) -> None:
    hermes = MockHermes(latency_ms=0, fail_next=True)
    resp = hermes.reason("Turn on the light", conversation, voice_turn_id=uuid4())
    assert resp.error_code == "hermes_unavailable"
