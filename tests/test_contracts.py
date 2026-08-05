"""Schema validation tests for PARKER contracts."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from parker.contracts.actions import ActionCategory, ActionReceipt, ActionRequest, ActionResult
from parker.contracts.context import ConversationContext, DeviceState, PARKERState, SystemStatus
from parker.contracts.errors import (
    AmbiguousDeviceError,
    ConfirmationRequiredError,
    ContextExpiredError,
    DeviceNotFoundError,
    PARKERError,
)
from parker.contracts.voice import (
    Transcript,
    VoiceTurn,
    VoiceTurnState,
    WakeEvent,
    WakeWordSource,
)


def test_wake_event_valid() -> None:
    event = WakeEvent(
        source=WakeWordSource.NABU,
        confidence=0.95,
        device_id="voice_pe_living_room",
        area_id="living_room",
    )
    assert event.confidence == 0.95
    assert event.source == WakeWordSource.NABU


def test_wake_event_rejects_bad_confidence() -> None:
    with pytest.raises(ValidationError):
        WakeEvent(
            source=WakeWordSource.MANUAL,
            confidence=1.5,
            device_id="d",
            area_id="a",
        )


def test_transcript_valid() -> None:
    wake_id = uuid4()
    transcript = Transcript(
        wake_event_id=wake_id,
        text="Turn on the light",
        confidence=0.9,
        processing_time_ms=900.0,
        engine="mock",
    )
    assert transcript.language == "en"
    assert transcript.wake_event_id == wake_id


def test_voice_turn_defaults() -> None:
    wake = WakeEvent(
        source=WakeWordSource.MANUAL,
        confidence=1.0,
        device_id="voice_pe_living_room",
        area_id="living_room",
    )
    turn = VoiceTurn(wake_event=wake)
    assert turn.state == VoiceTurnState.WAKE_DETECTED
    assert turn.transcript is None


def test_action_request_mutable_defaults_isolated() -> None:
    turn_id = uuid4()
    conv_id = uuid4()
    a = ActionRequest(
        voice_turn_id=turn_id,
        domain="light",
        service="turn_on",
        category=ActionCategory.ROUTINE,
        conversation_id=conv_id,
    )
    b = ActionRequest(
        voice_turn_id=turn_id,
        domain="light",
        service="turn_off",
        category=ActionCategory.ROUTINE,
        conversation_id=conv_id,
    )
    a.parameters["brightness"] = 100
    assert "brightness" not in b.parameters


def test_action_result_and_receipt() -> None:
    turn_id = uuid4()
    conv_id = uuid4()
    request = ActionRequest(
        voice_turn_id=turn_id,
        domain="lock",
        service="lock",
        target_entity="lock.front_door",
        category=ActionCategory.CONSEQUENTIAL,
        requires_confirmation=True,
        conversation_id=conv_id,
    )
    result = ActionResult(
        action_request_id=request.id,
        success=True,
        new_state={"state": "locked"},
    )
    receipt = ActionReceipt(
        trigger="voice_command",
        authority="user_voice_confirmation",
        action_request=request,
        action_result=result,
        confirmed=True,
        confirmation_method="voice",
    )
    assert receipt.confirmed is True
    assert receipt.action_result is not None
    assert receipt.action_result.success is True


def test_device_state() -> None:
    device = DeviceState(
        entity_id="light.living_room",
        domain="light",
        friendly_name="Living Room Light",
        state="off",
        area_id="living_room",
    )
    assert device.attributes == {}


def test_conversation_context_not_expired() -> None:
    ctx = ConversationContext(
        area_id="living_room",
        voice_device_id="voice_pe_living_room",
        last_active=datetime.now(UTC),
    )
    assert ctx.is_expired is False


def test_conversation_context_expired() -> None:
    ctx = ConversationContext(
        area_id="living_room",
        voice_device_id="voice_pe_living_room",
        last_active=datetime.now(UTC) - timedelta(seconds=130),
        expires_after_seconds=120,
    )
    assert ctx.is_expired is True


def test_system_status_defaults() -> None:
    status = SystemStatus()
    assert status.state == PARKERState.IDLE
    assert status.active_conversations == 0
    assert status.errors == []


def test_error_hierarchy() -> None:
    err = DeviceNotFoundError()
    assert err.code == "device_not_found"
    assert err.recoverable is True

    amb = AmbiguousDeviceError("Which light?")
    assert amb.message == "Which light?"
    assert amb.code == "ambiguous_device"

    conf = ConfirmationRequiredError()
    assert conf.recoverable is True

    expired = ContextExpiredError()
    assert expired.code == "context_expired"

    base = PARKERError("custom", code="custom_code", recoverable=False)
    assert base.code == "custom_code"
    assert base.recoverable is False
