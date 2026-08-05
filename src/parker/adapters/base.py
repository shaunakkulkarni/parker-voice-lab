"""Abstract adapter interfaces for Home Assistant and Hermes."""

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from parker.contracts.actions import ActionCategory, ActionRequest
from parker.contracts.context import ConversationContext, DeviceState


class HermesResponse(BaseModel):
    """Structured response from the Hermes reasoning layer."""

    intent: str
    spoken: str
    action_request: ActionRequest | None = None
    category: ActionCategory = ActionCategory.READ
    requires_confirmation: bool = False
    error_code: str | None = None
    cancel: bool = False
    confirm: bool = False
    deny: bool = False
    follow_up: bool = False
    topic: str | None = None
    resolve_room_light: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)


class HomeAssistantAdapter(ABC):
    """Interface for Home Assistant entity and service operations."""

    @abstractmethod
    def get_state(self, entity_id: str) -> DeviceState:
        """GET /api/states/<entity_id>."""

    @abstractmethod
    def list_states(self) -> list[DeviceState]:
        """GET /api/states."""

    @abstractmethod
    def call_service(
        self,
        domain: str,
        service: str,
        *,
        entity_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> DeviceState | None:
        """POST /api/services/<domain>/<service>."""


class HermesAdapter(ABC):
    """Interface for Hermes reasoning."""

    @abstractmethod
    def reason(
        self,
        utterance: str,
        conversation: ConversationContext,
        *,
        voice_turn_id: UUID,
    ) -> HermesResponse:
        """Interpret an utterance in conversation context."""
