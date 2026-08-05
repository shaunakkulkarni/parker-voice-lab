"""Tests for the mock Home Assistant adapter."""

from uuid import uuid4

import pytest

from parker.adapters.mock_ha import MockHomeAssistant
from parker.contracts.errors import ActionExecutionError, DeviceNotFoundError


@pytest.fixture
def ha() -> MockHomeAssistant:
    return MockHomeAssistant(latency_ms=0)


def test_list_states(ha: MockHomeAssistant) -> None:
    states = ha.list_states()
    entity_ids = {s.entity_id for s in states}
    assert "light.living_room" in entity_ids
    assert "lock.front_door" in entity_ids


def test_get_state(ha: MockHomeAssistant) -> None:
    light = ha.get_state("light.living_room")
    assert light.state == "off"
    assert light.area_id == "living_room"


def test_get_state_missing(ha: MockHomeAssistant) -> None:
    with pytest.raises(DeviceNotFoundError):
        ha.get_state("light.garage")


def test_turn_on_light(ha: MockHomeAssistant) -> None:
    result = ha.call_service("light", "turn_on", entity_id="light.living_room")
    assert result is not None
    assert result.state == "on"
    assert result.attributes["brightness"] == 255
    assert ha.service_calls[-1]["service"] == "turn_on"


def test_turn_off_light(ha: MockHomeAssistant) -> None:
    ha.call_service("light", "turn_off", entity_id="light.kitchen")
    assert ha.get_state("light.kitchen").state == "off"


def test_set_temperature(ha: MockHomeAssistant) -> None:
    result = ha.call_service(
        "climate",
        "set_temperature",
        entity_id="climate.living_room",
        data={"temperature": 24.0},
    )
    assert result is not None
    assert result.attributes["temperature"] == 24.0


def test_lock_and_unlock(ha: MockHomeAssistant) -> None:
    ha.call_service("lock", "unlock", entity_id="lock.front_door")
    assert ha.get_state("lock.front_door").state == "unlocked"
    ha.call_service("lock", "lock", entity_id="lock.front_door")
    assert ha.get_state("lock.front_door").state == "locked"


def test_play_media(ha: MockHomeAssistant) -> None:
    result = ha.call_service(
        "media_player",
        "play_media",
        entity_id="media_player.living_room_homepod",
        data={"media_content_id": "Jazz"},
    )
    assert result is not None
    assert result.state == "playing"
    assert result.attributes["media_title"] == "Jazz"


def test_offline_injection(ha: MockHomeAssistant) -> None:
    ha.inject_offline("light.bedroom")
    with pytest.raises(ActionExecutionError) as exc:
        ha.call_service("light", "turn_on", entity_id="light.bedroom")
    assert exc.value.code == "service_unavailable"


def test_entities_in_area(ha: MockHomeAssistant) -> None:
    devices = ha.entities_in_area("kitchen")
    ids = {d.entity_id for d in devices}
    assert "light.kitchen" in ids
    assert "switch.coffee_maker" in ids


def test_service_call_tracking(ha: MockHomeAssistant) -> None:
    assert ha.service_calls == []
    ha.call_service("switch", "turn_on", entity_id="switch.coffee_maker")
    assert len(ha.service_calls) == 1
    assert ha.service_calls[0]["domain"] == "switch"
    _ = uuid4()  # keep import used for future turn-id wiring


def test_invalid_service_for_domain(ha: MockHomeAssistant) -> None:
    with pytest.raises(ActionExecutionError) as exc:
        ha.call_service("light", "set_temperature", entity_id="light.living_room")
    assert "not valid" in exc.value.message

    with pytest.raises(ActionExecutionError) as exc:
        ha.call_service("media_player", "media_stop", entity_id="media_player.living_room_homepod")
    assert "not valid" in exc.value.message
