"""Room and device resolution helpers."""

from __future__ import annotations

from parker.adapters.base import HomeAssistantAdapter
from parker.contracts.actions import ActionRequest
from parker.contracts.context import DeviceState
from parker.contracts.errors import AmbiguousDeviceError, DeviceNotFoundError


class RoomResolver:
    """Resolve vague device references using room context."""

    def __init__(self, ha: HomeAssistantAdapter) -> None:
        self._ha = ha

    def devices_in_area(self, area_id: str) -> list[DeviceState]:
        return self._ha.entities_in_area(area_id)

    def resolve_light(self, area_id: str | None) -> DeviceState:
        """Resolve 'the light' to the light in the given area."""
        if not area_id:
            raise AmbiguousDeviceError(
                "Which light? Please specify a room."
            )
        lights = [
            d for d in self.devices_in_area(area_id) if d.domain == "light"
        ]
        if not lights:
            raise DeviceNotFoundError(f"No light found in {area_id}.")
        if len(lights) > 1:
            raise AmbiguousDeviceError(
                f"Multiple lights in {area_id}. Please specify which one."
            )
        return lights[0]

    def resolve_climate(self, area_id: str | None) -> DeviceState:
        if not area_id:
            raise AmbiguousDeviceError(
                "Which thermostat? Please specify a room."
            )
        climates = [
            d for d in self.devices_in_area(area_id) if d.domain == "climate"
        ]
        if not climates:
            raise DeviceNotFoundError(f"No thermostat found in {area_id}.")
        return climates[0]

    def resolve_action(
        self,
        action: ActionRequest,
        *,
        area_id: str | None,
        resolve_room_light: bool = False,
    ) -> ActionRequest:
        """Fill in target_entity from room context when needed."""
        if resolve_room_light and action.domain == "light" and not action.target_entity:
            light = self.resolve_light(area_id)
            return action.model_copy(
                update={
                    "target_entity": light.entity_id,
                    "target_area": light.area_id,
                }
            )

        if (
            action.domain == "climate"
            and action.service == "set_temperature"
            and not action.target_entity
        ):
            climate = self.resolve_climate(area_id)
            return action.model_copy(
                update={
                    "target_entity": climate.entity_id,
                    "target_area": climate.area_id,
                }
            )

        if action.target_entity:
            try:
                self._ha.get_state(action.target_entity)
            except DeviceNotFoundError:
                raise
            return action

        return action

    def find_entity(self, entity_id: str) -> DeviceState:
        return self._ha.get_state(entity_id)
