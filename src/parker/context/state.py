"""PARKER system state machine and status tracking."""

from __future__ import annotations

import time
from collections.abc import Callable

from parker.contracts.actions import ActionRequest
from parker.contracts.context import PARKERState, SystemStatus
from parker.contracts.errors import PARKERError

# Allowed transitions: from -> set of to
_TRANSITIONS: dict[PARKERState, set[PARKERState]] = {
    PARKERState.IDLE: {PARKERState.LISTENING, PARKERState.ERROR},
    PARKERState.LISTENING: {
        PARKERState.TRANSCRIBING,
        PARKERState.ERROR,
        PARKERState.IDLE,
    },
    PARKERState.TRANSCRIBING: {
        PARKERState.THINKING,
        PARKERState.ERROR,
        PARKERState.IDLE,
    },
    PARKERState.THINKING: {
        PARKERState.CONFIRMING,
        PARKERState.ACTING,
        PARKERState.SPEAKING,
        PARKERState.ERROR,
        PARKERState.IDLE,
    },
    PARKERState.CONFIRMING: {
        PARKERState.ACTING,
        PARKERState.SPEAKING,
        PARKERState.IDLE,
        PARKERState.ERROR,
    },
    PARKERState.ACTING: {
        PARKERState.SPEAKING,
        PARKERState.ERROR,
        PARKERState.IDLE,
    },
    PARKERState.SPEAKING: {PARKERState.IDLE, PARKERState.ERROR},
    PARKERState.ERROR: {PARKERState.IDLE},
}


class StateMachine:
    """Tracks PARKER operational state and SystemStatus for the display."""

    def __init__(self) -> None:
        self._state = PARKERState.IDLE
        self._started = time.monotonic()
        self._current_room: str | None = None
        self._current_device: str | None = None
        self._last_transcript: str | None = None
        self._last_response: str | None = None
        self._last_action: ActionRequest | None = None
        self._pending_confirmation: ActionRequest | None = None
        self._active_conversations = 0
        self._errors: list[str] = []
        self._listeners: list[Callable[[SystemStatus], None]] = []

    @property
    def state(self) -> PARKERState:
        return self._state

    def on_change(self, listener: Callable[[SystemStatus], None]) -> None:
        self._listeners.append(listener)

    def transition(self, new_state: PARKERState) -> None:
        if new_state == self._state:
            return
        allowed = _TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            raise PARKERError(
                f"Invalid transition {self._state.value} -> {new_state.value}",
                code="invalid_transition",
                recoverable=True,
            )
        self._state = new_state
        self._notify()

    def force_idle(self) -> None:
        self._state = PARKERState.IDLE
        self._pending_confirmation = None
        self._notify()

    def reset_session(self) -> None:
        """Clear session view fields and return to IDLE (keeps uptime/listeners)."""
        self._state = PARKERState.IDLE
        self._current_room = None
        self._current_device = None
        self._last_transcript = None
        self._last_response = None
        self._last_action = None
        self._pending_confirmation = None
        self._active_conversations = 0
        self._errors.clear()
        self._notify()

    def goto(self, new_state: PARKERState) -> None:
        """Set state without transition validation (simulator recovery)."""
        self._state = new_state
        self._notify()

    def set_room(self, room: str | None) -> None:
        self._current_room = room
        self._notify()

    def set_device(self, device: str | None) -> None:
        self._current_device = device
        self._notify()

    def set_transcript(self, text: str | None) -> None:
        self._last_transcript = text
        self._notify()

    def set_response(self, text: str | None) -> None:
        self._last_response = text
        self._notify()

    def set_last_action(self, action: ActionRequest | None) -> None:
        self._last_action = action
        self._notify()

    def set_pending_confirmation(self, action: ActionRequest | None) -> None:
        self._pending_confirmation = action
        self._notify()

    def set_active_conversations(self, count: int) -> None:
        self._active_conversations = count
        self._notify()

    def add_error(self, message: str) -> None:
        self._errors.append(message)
        self._notify()

    def status(self) -> SystemStatus:
        return SystemStatus(
            state=self._state,
            current_room=self._current_room,
            current_device=self._current_device,
            last_transcript=self._last_transcript,
            last_response=self._last_response,
            last_action=self._last_action,
            pending_confirmation=self._pending_confirmation,
            active_conversations=self._active_conversations,
            uptime_seconds=time.monotonic() - self._started,
            errors=list(self._errors),
        )

    def _notify(self) -> None:
        status = self.status()
        for listener in self._listeners:
            listener(status)
