"""Conversation history and follow-up tracking per voice device."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from parker.contracts.actions import ActionRequest
from parker.contracts.context import ConversationContext
from parker.contracts.errors import ContextExpiredError
from parker.contracts.plan import ActionPlan
from parker.contracts.voice import VoiceTurn


class ConversationManager:
    """Tracks independent conversations per voice device."""

    def __init__(self, expires_after_seconds: int = 120) -> None:
        self.expires_after_seconds = expires_after_seconds
        self._conversations: dict[str, ConversationContext] = {}

    def start(
        self,
        *,
        voice_device_id: str,
        area_id: str,
    ) -> ConversationContext:
        """Start a new conversation for a voice device."""
        ctx = ConversationContext(
            area_id=area_id,
            voice_device_id=voice_device_id,
            expires_after_seconds=self.expires_after_seconds,
        )
        self._conversations[voice_device_id] = ctx
        return ctx

    def get(self, voice_device_id: str) -> ConversationContext | None:
        return self._conversations.get(voice_device_id)

    def get_active(self, voice_device_id: str) -> ConversationContext:
        """Return an active (non-expired) conversation or raise."""
        ctx = self._conversations.get(voice_device_id)
        if ctx is None or ctx.is_expired:
            raise ContextExpiredError()
        return ctx

    def touch(self, voice_device_id: str) -> ConversationContext:
        """Update last_active; raises if expired or missing."""
        ctx = self.get_active(voice_device_id)
        ctx.last_active = datetime.now(UTC)
        return ctx

    def add_turn(self, voice_device_id: str, turn: VoiceTurn) -> ConversationContext:
        ctx = self.touch(voice_device_id)
        ctx.turns.append(turn)
        return ctx

    def set_last_action(
        self, voice_device_id: str, action: ActionRequest | None
    ) -> ConversationContext:
        ctx = self.touch(voice_device_id)
        ctx.last_action = action
        return ctx

    def set_pending_confirmation(
        self, voice_device_id: str, action: ActionRequest | None
    ) -> ConversationContext:
        ctx = self.touch(voice_device_id)
        ctx.pending_confirmation = action
        return ctx

    def set_pending_plan(
        self, voice_device_id: str, plan: ActionPlan | None
    ) -> ConversationContext:
        ctx = self.touch(voice_device_id)
        ctx.pending_plan = plan
        return ctx

    def set_guest_mode(self, voice_device_id: str, enabled: bool) -> ConversationContext:
        ctx = self.touch(voice_device_id)
        ctx.guest_mode = enabled
        return ctx

    def set_quiet_hours(self, voice_device_id: str, enabled: bool) -> ConversationContext:
        ctx = self.touch(voice_device_id)
        ctx.quiet_hours = enabled
        return ctx

    def set_topic(self, voice_device_id: str, topic: str | None) -> ConversationContext:
        ctx = self.touch(voice_device_id)
        ctx.last_topic = topic
        return ctx

    def expire_now(self, voice_device_id: str) -> None:
        """Force-expire a conversation (for tests / simulator waits)."""
        ctx = self._conversations.get(voice_device_id)
        if ctx is None:
            return
        ctx.last_active = datetime.now(UTC) - timedelta(
            seconds=ctx.expires_after_seconds + 1
        )

    def advance_time(self, voice_device_id: str, seconds: float) -> None:
        """Simulate silence by rewinding last_active."""
        ctx = self._conversations.get(voice_device_id)
        if ctx is None:
            return
        ctx.last_active = ctx.last_active - timedelta(seconds=seconds)

    def active_count(self) -> int:
        return sum(1 for ctx in self._conversations.values() if not ctx.is_expired)

    def clear(self) -> None:
        """Drop all active conversations."""
        self._conversations.clear()

    def ensure(
        self,
        *,
        voice_device_id: str,
        area_id: str,
        allow_expired_restart: bool = True,
    ) -> ConversationContext:
        """Get active conversation or start a new one if missing/expired."""
        ctx = self._conversations.get(voice_device_id)
        if ctx is not None and not ctx.is_expired:
            ctx.last_active = datetime.now(UTC)
            return ctx
        if ctx is not None and ctx.is_expired and not allow_expired_restart:
            raise ContextExpiredError()
        return self.start(voice_device_id=voice_device_id, area_id=area_id)
