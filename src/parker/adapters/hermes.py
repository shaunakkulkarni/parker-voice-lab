"""Real Hermes adapter stub (not used until Hermes gateway is ready)."""

from uuid import UUID

from parker.adapters.base import HermesAdapter, HermesResponse
from parker.contracts.context import ConversationContext


class Hermes(HermesAdapter):
    """Stub for the real Hermes gateway adapter."""

    def __init__(self, gateway_url: str) -> None:
        self.gateway_url = gateway_url

    def reason(
        self,
        utterance: str,
        conversation: ConversationContext,
        *,
        voice_turn_id: UUID,
    ) -> HermesResponse:
        raise NotImplementedError("Real Hermes adapter is not enabled yet.")
