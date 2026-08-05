"""Real Home Assistant adapter stub (not used until hardware is ready)."""

from typing import Any

from parker.adapters.base import HomeAssistantAdapter
from parker.contracts.context import DeviceState


class HomeAssistant(HomeAssistantAdapter):
    """Stub for the real HA REST adapter.

    Will connect to http://192.168.1.171:8123 with HASS_TOKEN when ready.
    """

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url
        self.token = token

    def get_state(self, entity_id: str) -> DeviceState:
        raise NotImplementedError("Real Home Assistant adapter is not enabled yet.")

    def list_states(self) -> list[DeviceState]:
        raise NotImplementedError("Real Home Assistant adapter is not enabled yet.")

    def entities_in_area(self, area_id: str) -> list[DeviceState]:
        raise NotImplementedError("Real Home Assistant adapter is not enabled yet.")

    def call_service(
        self,
        domain: str,
        service: str,
        *,
        entity_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> DeviceState | None:
        raise NotImplementedError("Real Home Assistant adapter is not enabled yet.")
