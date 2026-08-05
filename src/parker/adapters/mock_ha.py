"""Mock Home Assistant adapter with in-memory entity store."""

from __future__ import annotations

import json
import time
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from parker.adapters.base import HomeAssistantAdapter
from parker.contracts.context import DeviceState
from parker.contracts.errors import ActionExecutionError, DeviceNotFoundError

DEFAULT_DEVICES_PATH = Path(__file__).resolve().parents[3] / "fixtures" / "devices.json"

VALID_SERVICES: dict[str, frozenset[str]] = {
    "light": frozenset({"turn_on", "turn_off"}),
    "climate": frozenset({"set_temperature"}),
    "lock": frozenset({"lock", "unlock"}),
    "media_player": frozenset({"play_media"}),
    "switch": frozenset({"turn_on", "turn_off"}),
}


class MockHomeAssistant(HomeAssistantAdapter):
    """In-memory Home Assistant for tests and simulation."""

    def __init__(
        self,
        devices_path: Path | str | None = None,
        *,
        latency_ms: float = 0.0,
        offline_entities: set[str] | None = None,
    ) -> None:
        self.latency_ms = latency_ms
        self.offline_entities = offline_entities or set()
        self.service_calls: list[dict[str, Any]] = []
        self.areas: dict[str, str] = {}
        self.voice_devices: list[dict[str, Any]] = []
        self._entities: dict[str, DeviceState] = {}
        path = Path(devices_path) if devices_path else DEFAULT_DEVICES_PATH
        self._load(path)

    def _load(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        for area in data.get("areas", []):
            self.areas[area["area_id"]] = area["name"]
        self.voice_devices = list(data.get("voice_devices", []))
        for device in data.get("devices", []):
            entity_id = device["entity_id"]
            domain = entity_id.split(".", 1)[0]
            self._entities[entity_id] = DeviceState(
                entity_id=entity_id,
                domain=domain,
                friendly_name=device["friendly_name"],
                state=device["state"],
                attributes=deepcopy(device.get("attributes", {})),
                area_id=device.get("area_id"),
                last_changed=datetime.now(UTC),
            )

    def _sleep(self) -> None:
        if self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000.0)

    def get_state(self, entity_id: str) -> DeviceState:
        self._sleep()
        if entity_id in self.offline_entities:
            raise ActionExecutionError(
                f"Entity {entity_id} is offline.",
                code="service_unavailable",
            )
        entity = self._entities.get(entity_id)
        if entity is None:
            raise DeviceNotFoundError(f"Entity {entity_id} not found.")
        return entity.model_copy(deep=True)

    def list_states(self) -> list[DeviceState]:
        self._sleep()
        return [e.model_copy(deep=True) for e in self._entities.values()]

    def entities_in_area(self, area_id: str) -> list[DeviceState]:
        return [
            e.model_copy(deep=True)
            for e in self._entities.values()
            if e.area_id == area_id
        ]

    def call_service(
        self,
        domain: str,
        service: str,
        *,
        entity_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> DeviceState | None:
        self._sleep()
        payload = data or {}
        self.service_calls.append(
            {
                "domain": domain,
                "service": service,
                "entity_id": entity_id,
                "data": deepcopy(payload),
            }
        )

        if entity_id and entity_id in self.offline_entities:
            raise ActionExecutionError(
                f"Entity {entity_id} is offline.",
                code="service_unavailable",
            )

        if entity_id is None:
            return None

        entity = self._entities.get(entity_id)
        if entity is None:
            raise DeviceNotFoundError(f"Entity {entity_id} not found.")
        if entity.domain != domain:
            raise ActionExecutionError(
                f"Domain mismatch for {entity_id}: expected {entity.domain}, got {domain}."
            )

        allowed = VALID_SERVICES.get(domain)
        if allowed is None:
            raise ActionExecutionError(f"Unsupported domain: {domain}")
        if service not in allowed:
            raise ActionExecutionError(
                f"Service '{service}' is not valid for domain '{domain}'. "
                f"Allowed: {sorted(allowed)}"
            )

        now = datetime.now(UTC)
        attrs = deepcopy(entity.attributes)

        if domain == "light":
            if service == "turn_on":
                entity.state = "on"
                attrs["brightness"] = payload.get("brightness", attrs.get("brightness") or 255)
            else:  # turn_off
                entity.state = "off"
                attrs["brightness"] = 0
        elif domain == "climate":
            temp = payload.get("temperature")
            if temp is None:
                raise ActionExecutionError("temperature parameter required")
            attrs["temperature"] = float(temp)
            entity.state = attrs.get("hvac_mode", entity.state)
        elif domain == "lock":
            entity.state = "locked" if service == "lock" else "unlocked"
        elif domain == "media_player":
            entity.state = "playing"
            attrs["media_title"] = payload.get("media_content_id", "Music")
        elif domain == "switch":
            entity.state = "on" if service == "turn_on" else "off"

        entity.attributes = attrs
        entity.last_changed = now
        self._entities[entity_id] = entity
        return entity.model_copy(deep=True)

    def inject_offline(self, entity_id: str) -> None:
        self.offline_entities.add(entity_id)

    def clear_offline(self, entity_id: str | None = None) -> None:
        if entity_id is None:
            self.offline_entities.clear()
        else:
            self.offline_entities.discard(entity_id)
