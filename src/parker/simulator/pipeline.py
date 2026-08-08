"""Full voice-flow simulator wiring mocks and context."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from parker.adapters.base import HermesAdapter, HomeAssistantAdapter
from parker.adapters.mock_ha import MockHomeAssistant
from parker.adapters.mock_hermes import MockHermes
from parker.context.conversation import ConversationManager
from parker.context.room import RoomResolver
from parker.context.state import StateMachine
from parker.contracts.actions import ActionCategory, ActionRequest, ActionResult
from parker.contracts.context import PARKERState
from parker.contracts.errors import (
    AmbiguousDeviceError,
    ContextExpiredError,
    DeviceNotFoundError,
    PARKERError,
)
from parker.contracts.plan import ActionPlan, Journey
from parker.contracts.voice import (
    Transcript,
    VoiceTurn,
    VoiceTurnState,
    WakeEvent,
    WakeWordSource,
)
from parker.receipts.approval import ApprovalDecision, ApprovalMiddleware
from parker.receipts.store import ReceiptStore
from parker.simulator.autonomy import GatedAutonomyEngine, ProviderBundle
from parker.simulator.latency import LatencyLogger, LatencyReport


@dataclass
class PipelineResult:
    """Outcome of a single utterance through the pipeline."""

    turn: VoiceTurn
    spoken: str
    action: ActionRequest | None = None
    action_result: ActionResult | None = None
    error_code: str | None = None
    confirmed: bool | None = None
    latency: LatencyReport | None = None
    category: ActionCategory | None = None
    plan: ActionPlan | None = None
    journey: Journey | None = None
    receipt_count: int = 0
    awaiting_confirmation: bool = False

    def summary(self) -> str:
        parts = [
            f"state={self.turn.state.value}",
            f"spoken={self.spoken!r}",
        ]
        if self.action:
            parts.append(
                f"action={self.action.domain}.{self.action.service}"
                f"({self.action.target_entity})"
            )
        if self.plan:
            parts.append(f"plan={self.plan.capability}:{len(self.plan.steps)} steps")
        if self.error_code:
            parts.append(f"error={self.error_code}")
        if self.latency:
            parts.append(f"total_ms={self.latency.total_ms:.0f}")
        return " | ".join(parts)


@dataclass
class VoicePipeline:
    """End-to-end mock voice pipeline."""

    ha_adapter: HomeAssistantAdapter
    hermes_adapter: HermesAdapter
    stt_latency_ms: float = 900.0
    tts_latency_ms: float = 350.0
    hermes_latency_ms: float = 300.0
    ha_latency_ms: float = 50.0
    receipt_store: ReceiptStore | None = None
    latency_logger: LatencyLogger | None = None
    conversations: ConversationManager = field(default_factory=ConversationManager)
    state: StateMachine = field(default_factory=StateMachine)
    providers: ProviderBundle = field(default_factory=ProviderBundle)
    _room: RoomResolver | None = field(default=None, init=False, repr=False)
    _approval: ApprovalMiddleware | None = field(default=None, init=False, repr=False)
    _autonomy: GatedAutonomyEngine | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._room = RoomResolver(self.ha_adapter)
        if isinstance(self.ha_adapter, MockHomeAssistant):
            self.ha_adapter.latency_ms = self.ha_latency_ms
        if isinstance(self.hermes_adapter, MockHermes):
            self.hermes_adapter.latency_ms = self.hermes_latency_ms
        store = self.receipt_store or ReceiptStore()
        self.receipt_store = store
        self._approval = ApprovalMiddleware(store)
        self._autonomy = GatedAutonomyEngine(self.providers, self._approval)
        if self.latency_logger is None:
            self.latency_logger = LatencyLogger()

    @property
    def room(self) -> RoomResolver:
        assert self._room is not None
        return self._room

    @property
    def approval(self) -> ApprovalMiddleware:
        assert self._approval is not None
        return self._approval

    @property
    def autonomy(self) -> GatedAutonomyEngine:
        assert self._autonomy is not None
        return self._autonomy

    def run_event(
        self,
        trigger: dict[str, Any],
        *,
        area_id: str,
        device_id: str,
        scenario_name: str = "event",
        context: dict[str, Any] | None = None,
        confirmation_response: str | None = None,
    ) -> PipelineResult:
        """Run an event-triggered capability (e.g. shower routine)."""
        t0 = time.perf_counter()
        latency = LatencyReport(scenario=scenario_name)
        wake = WakeEvent(
            source=WakeWordSource.MANUAL,
            confidence=1.0,
            device_id=device_id,
            area_id=area_id,
        )
        turn = VoiceTurn(wake_event=wake, state=VoiceTurnState.THINKING)
        self.state.goto(PARKERState.THINKING)
        self.state.set_room(area_id)
        self.state.set_device(device_id)

        ctx = context or {}
        self.providers.guest_mode = bool(ctx.get("guest_mode", False))
        self.providers.quiet_hours = bool(ctx.get("quiet_hours", False))
        if ctx.get("false_positive"):
            self.providers.presence.inject_false_positive = True
        if ctx.get("media_unavailable"):
            self.providers.media.set_unavailable("media_player.bathroom_homepod")
        if ctx.get("playlist_unavailable"):
            self.providers.media.set_playlist_unavailable("shower_morning")

        conversation = self.conversations.ensure(
            voice_device_id=device_id, area_id=area_id
        )

        event_type = trigger.get("event") or trigger.get("type")
        if event_type in {"shower_start", "presence"} or trigger.get("type") == "presence":
            event = self.providers.presence.shower_start(
                false_positive=bool(ctx.get("false_positive", False))
            )
            plan = self.autonomy.build_shower_plan(event, voice_turn_id=turn.id)
            if plan is None:
                return self._speak(
                    turn,
                    spoken="Shower sensor event suppressed as a false positive.",
                    latency=latency,
                    t0=t0,
                    device_id=device_id,
                    error_code="false_positive_suppressed",
                    category=ActionCategory.READ,
                    journey=Journey.DELEGATE_THE_ROUTINE,
                )
            return self._execute_plan_result(
                turn=turn,
                device_id=device_id,
                area_id=area_id,
                conversation_id=conversation.id,
                plan=plan,
                latency=latency,
                t0=t0,
                confirmation_response=confirmation_response,
            )

        return self._speak(
            turn,
            spoken="I don't know how to handle that event.",
            latency=latency,
            t0=t0,
            device_id=device_id,
            error_code="unknown_event",
        )

    def run_utterance(
        self,
        utterance: str,
        *,
        area_id: str,
        device_id: str,
        confirmation_response: str | None = None,
        scenario_name: str = "ad-hoc",
        reuse_conversation: bool = True,
        fail_on_expired_followup: bool = False,
    ) -> PipelineResult:
        """Run one voice turn from wake through speech."""
        t0 = time.perf_counter()
        latency = LatencyReport(scenario=scenario_name)

        wake = WakeEvent(
            source=WakeWordSource.MANUAL,
            confidence=1.0,
            device_id=device_id,
            area_id=area_id,
        )
        turn = VoiceTurn(wake_event=wake, state=VoiceTurnState.WAKE_DETECTED)

        try:
            self.state.goto(PARKERState.IDLE)
            self.state.set_room(area_id)
            self.state.set_device(device_id)

            t_listen = time.perf_counter()
            self.state.transition(PARKERState.LISTENING)
            turn.state = VoiceTurnState.LISTENING
            latency.wake_to_listening_ms = (time.perf_counter() - t_listen) * 1000

            if fail_on_expired_followup:
                try:
                    self.conversations.get_active(device_id)
                except ContextExpiredError:
                    return self._error_result(
                        turn,
                        spoken="I lost the conversation context. Please start over.",
                        error_code="context_expired",
                        latency=latency,
                        t0=t0,
                    )

            if reuse_conversation:
                conversation = self.conversations.ensure(
                    voice_device_id=device_id, area_id=area_id
                )
            else:
                conversation = self.conversations.start(
                    voice_device_id=device_id, area_id=area_id
                )

            self.state.transition(PARKERState.TRANSCRIBING)
            turn.state = VoiceTurnState.TRANSCRIBING
            t_stt = time.perf_counter()
            if self.stt_latency_ms > 0:
                time.sleep(self.stt_latency_ms / 1000.0)
            latency.stt_ms = (time.perf_counter() - t_stt) * 1000
            turn.transcript = Transcript(
                wake_event_id=wake.id,
                text=utterance,
                confidence=0.95,
                processing_time_ms=latency.stt_ms,
                engine="mock",
            )
            turn.wake_to_transcript_ms = latency.wake_to_listening_ms + latency.stt_ms
            self.state.set_transcript(utterance)

            self.state.transition(PARKERState.THINKING)
            turn.state = VoiceTurnState.THINKING
            t_hermes = time.perf_counter()
            response = self.hermes_adapter.reason(
                utterance, conversation, voice_turn_id=turn.id
            )
            latency.hermes_ms = (time.perf_counter() - t_hermes) * 1000

            # Pending confirmation replies (single action or gated plan step)
            if conversation.pending_confirmation is not None and (
                response.confirm or response.deny or response.cancel
            ):
                if conversation.pending_plan is not None:
                    return self._execute_plan_result(
                        turn=turn,
                        device_id=device_id,
                        area_id=area_id,
                        conversation_id=conversation.id,
                        plan=conversation.pending_plan,
                        latency=latency,
                        t0=t0,
                        confirmation_response=(
                            "yes"
                            if response.confirm
                            else "cancel"
                            if response.cancel
                            else "no"
                        ),
                    )
                return self._handle_confirmation_reply(
                    turn=turn,
                    device_id=device_id,
                    area_id=area_id,
                    response_confirm=response.confirm,
                    response_deny=response.deny,
                    response_cancel=response.cancel,
                    latency=latency,
                    t0=t0,
                )

            if response.plan_intent:
                plan = self.autonomy.build_from_intent(
                    response.plan_intent,
                    utterance=utterance,
                    parameters=response.plan_parameters or response.parameters,
                )
                if plan is None:
                    return self._speak(
                        turn,
                        spoken="I couldn't build a plan for that.",
                        latency=latency,
                        t0=t0,
                        device_id=device_id,
                        error_code="plan_unavailable",
                    )
                return self._execute_plan_result(
                    turn=turn,
                    device_id=device_id,
                    area_id=area_id,
                    conversation_id=conversation.id,
                    plan=plan,
                    latency=latency,
                    t0=t0,
                    confirmation_response=confirmation_response,
                )

            if response.error_code == "device_not_found":
                return self._speak(
                    turn,
                    spoken=response.spoken,
                    latency=latency,
                    t0=t0,
                    device_id=device_id,
                    error_code="device_not_found",
                )

            if response.cancel:
                return self._speak(
                    turn,
                    spoken=response.spoken,
                    latency=latency,
                    t0=t0,
                    device_id=device_id,
                )

            if response.follow_up:
                spoken = response.spoken
                if (
                    conversation.last_topic == "temperature"
                    or "tomorrow" in utterance.lower()
                ):
                    climate = self.room.resolve_climate(conversation.area_id)
                    temp = climate.attributes.get("current_temperature", 21.5)
                    spoken = (
                        "I don't have tomorrow's forecast yet, "
                        f"but today it is {temp} degrees."
                    )
                return self._speak(
                    turn,
                    spoken=spoken,
                    latency=latency,
                    t0=t0,
                    device_id=device_id,
                    category=response.category,
                )

            action = response.action_request

            if response.resolve_room_light and action is not None:
                try:
                    action = self.room.resolve_action(
                        action, area_id=area_id, resolve_room_light=True
                    )
                except (AmbiguousDeviceError, DeviceNotFoundError) as exc:
                    return self._speak(
                        turn,
                        spoken=exc.message,
                        latency=latency,
                        t0=t0,
                        device_id=device_id,
                        error_code=exc.code,
                    )

            if action is not None and action.domain == "climate":
                action = self.room.resolve_action(action, area_id=area_id)

            if action is not None and action.target_entity:
                try:
                    self.room.find_entity(action.target_entity)
                except DeviceNotFoundError as exc:
                    return self._speak(
                        turn,
                        spoken=f"I couldn't find {action.target_entity}.",
                        latency=latency,
                        t0=t0,
                        device_id=device_id,
                        error_code=exc.code,
                    )

            if response.topic == "temperature" and action is None:
                climate = self.room.resolve_climate(area_id)
                temp = climate.attributes.get("current_temperature", 21.5)
                spoken = f"The current temperature is {temp} degrees."
                self.conversations.set_topic(device_id, "temperature")
                return self._speak(
                    turn,
                    spoken=spoken,
                    latency=latency,
                    t0=t0,
                    device_id=device_id,
                    category=ActionCategory.READ,
                )

            if action is None:
                return self._speak(
                    turn,
                    spoken=response.spoken,
                    latency=latency,
                    t0=t0,
                    device_id=device_id,
                    category=response.category,
                )

            outcome = self.approval.evaluate(action)
            action = outcome.action
            turn.transcript_to_action_ms = latency.hermes_ms

            if outcome.decision == ApprovalDecision.NEEDS_CONFIRMATION:
                self.state.transition(PARKERState.CONFIRMING)
                turn.state = VoiceTurnState.CONFIRMING
                self.conversations.set_pending_confirmation(device_id, action)
                self.state.set_pending_confirmation(action)
                prompt = outcome.spoken_prompt or response.spoken

                if confirmation_response is None:
                    return self._speak(
                        turn,
                        spoken=prompt,
                        latency=latency,
                        t0=t0,
                        device_id=device_id,
                        action=action,
                        category=action.category,
                        remain_confirming=True,
                    )

                conf = confirmation_response.strip().lower()
                confirmed = conf in {"yes", "y", "confirm", "ok", "okay"}
                cancelled = conf in {"cancel", "stop"}
                denied = conf in {"no", "n", "deny"}
                return self._complete_pending(
                    turn=turn,
                    device_id=device_id,
                    area_id=area_id,
                    action=action,
                    confirmed=confirmed,
                    cancelled=cancelled,
                    denied=denied and not confirmed and not cancelled,
                    latency=latency,
                    t0=t0,
                )

            return self._execute_action(
                turn=turn,
                device_id=device_id,
                area_id=area_id,
                action=action,
                spoken_success=response.spoken,
                latency=latency,
                t0=t0,
                auto=True,
            )

        except ContextExpiredError:
            return self._error_result(
                turn,
                spoken="I lost the conversation context. Please start over.",
                error_code="context_expired",
                latency=latency,
                t0=t0,
            )
        except PARKERError as exc:
            return self._error_result(
                turn,
                spoken=exc.message,
                error_code=exc.code,
                latency=latency,
                t0=t0,
            )

    def _execute_plan_result(
        self,
        *,
        turn: VoiceTurn,
        device_id: str,
        area_id: str,
        conversation_id: UUID,
        plan: ActionPlan,
        latency: LatencyReport,
        t0: float,
        confirmation_response: str | None = None,
    ) -> PipelineResult:
        confirm: bool | None = None
        cancel = False
        deny = False
        if confirmation_response is not None:
            conf = confirmation_response.strip().lower()
            confirm = conf in {"yes", "y", "confirm", "ok", "okay"}
            cancel = conf in {"cancel", "stop"}
            deny = conf in {"no", "n", "deny"}

        if self.state.state == PARKERState.THINKING:
            self.state.transition(PARKERState.ACTING)
        elif self.state.state != PARKERState.CONFIRMING:
            self.state.goto(PARKERState.ACTING)
        turn.state = VoiceTurnState.ACTING

        outcome = self.autonomy.execute_plan(
            plan,
            voice_turn_id=turn.id,
            conversation_id=conversation_id,
            area_id=area_id,
            confirm=confirm,
            cancel=cancel,
            deny=deny,
        )

        if outcome.awaiting_confirmation:
            self.state.goto(PARKERState.CONFIRMING)
            turn.state = VoiceTurnState.CONFIRMING
            action = outcome.confirmed_action or outcome.last_action
            self.conversations.set_pending_confirmation(device_id, action)
            self.conversations.set_pending_plan(device_id, outcome.plan)
            self.state.set_pending_confirmation(action)
            return self._speak(
                turn,
                spoken=outcome.spoken,
                latency=latency,
                t0=t0,
                device_id=device_id,
                action=action,
                category=outcome.category,
                plan=outcome.plan,
                journey=outcome.plan.journey,
                receipt_count=outcome.receipts_recorded,
                awaiting_confirmation=True,
                remain_confirming=True,
            )

        self.conversations.set_pending_confirmation(device_id, None)
        self.conversations.set_pending_plan(device_id, None)
        self.state.set_pending_confirmation(None)
        if outcome.last_action is not None:
            self.conversations.set_last_action(device_id, outcome.last_action)
            self.state.set_last_action(outcome.last_action)

        confirmed: bool | None = None
        if confirmation_response is not None:
            confirmed = bool(confirm) and not cancel and not deny

        return self._speak(
            turn,
            spoken=outcome.spoken,
            latency=latency,
            t0=t0,
            device_id=device_id,
            action=outcome.last_action,
            action_result=outcome.last_result,
            error_code=outcome.error_code,
            category=outcome.category,
            plan=outcome.plan,
            journey=outcome.plan.journey,
            receipt_count=outcome.receipts_recorded,
            confirmed=confirmed,
        )

    def _complete_pending(
        self,
        *,
        turn: VoiceTurn,
        device_id: str,
        area_id: str,
        action: ActionRequest,
        confirmed: bool,
        cancelled: bool,
        denied: bool,
        latency: LatencyReport,
        t0: float,
    ) -> PipelineResult:
        if cancelled or denied:
            self.approval.confirm(
                action, confirmed=False, cancelled=cancelled, area_id=area_id
            )
            self.conversations.set_pending_confirmation(device_id, None)
            self.state.set_pending_confirmation(None)
            spoken = "Okay, cancelled." if cancelled else "Okay, I won't do that."
            return self._speak(
                turn,
                spoken=spoken,
                latency=latency,
                t0=t0,
                device_id=device_id,
                action=action,
                category=action.category,
                confirmed=False,
            )

        return self._execute_action(
            turn=turn,
            device_id=device_id,
            area_id=area_id,
            action=action,
            spoken_success=f"Done. I've completed {action.service.replace('_', ' ')}.",
            latency=latency,
            t0=t0,
            auto=False,
            confirmed=True,
        )

    def _handle_confirmation_reply(
        self,
        *,
        turn: VoiceTurn,
        device_id: str,
        area_id: str,
        response_confirm: bool,
        response_deny: bool,
        response_cancel: bool,
        latency: LatencyReport,
        t0: float,
    ) -> PipelineResult:
        conversation = self.conversations.get_active(device_id)
        action = conversation.pending_confirmation
        assert action is not None
        self.state.goto(PARKERState.CONFIRMING)
        return self._complete_pending(
            turn=turn,
            device_id=device_id,
            area_id=area_id,
            action=action,
            confirmed=response_confirm,
            cancelled=response_cancel,
            denied=response_deny,
            latency=latency,
            t0=t0,
        )

    def _execute_action(
        self,
        *,
        turn: VoiceTurn,
        device_id: str,
        area_id: str,
        action: ActionRequest,
        spoken_success: str,
        latency: LatencyReport,
        t0: float,
        auto: bool,
        confirmed: bool = True,
    ) -> PipelineResult:
        if self.state.state == PARKERState.CONFIRMING:
            self.state.transition(PARKERState.ACTING)
        elif self.state.state == PARKERState.THINKING:
            self.state.transition(PARKERState.ACTING)
        else:
            self.state.goto(PARKERState.ACTING)
        turn.state = VoiceTurnState.ACTING
        self.state.set_last_action(action)

        t_ha = time.perf_counter()
        new_state = self.ha_adapter.call_service(
            action.domain,
            action.service,
            entity_id=action.target_entity,
            data=action.parameters or None,
        )
        latency.ha_ms = (time.perf_counter() - t_ha) * 1000

        result = ActionResult(
            action_request_id=action.id,
            success=True,
            new_state=new_state.model_dump(mode="json") if new_state else None,
        )

        if auto:
            self.approval.record_auto(action, result, area_id=area_id)
        else:
            self.approval.confirm(
                action, confirmed=confirmed, result=result, area_id=area_id
            )

        self.conversations.set_pending_confirmation(device_id, None)
        self.state.set_pending_confirmation(None)
        self.conversations.set_last_action(device_id, action)

        return self._speak(
            turn,
            spoken=spoken_success,
            latency=latency,
            t0=t0,
            device_id=device_id,
            action=action,
            action_result=result,
            category=action.category,
            confirmed=confirmed,
        )

    def _speak(
        self,
        turn: VoiceTurn,
        *,
        spoken: str,
        latency: LatencyReport,
        t0: float,
        device_id: str,
        action: ActionRequest | None = None,
        action_result: ActionResult | None = None,
        error_code: str | None = None,
        category: ActionCategory | None = None,
        confirmed: bool | None = None,
        remain_confirming: bool = False,
        plan: ActionPlan | None = None,
        journey: Journey | None = None,
        receipt_count: int = 0,
        awaiting_confirmation: bool = False,
    ) -> PipelineResult:
        if remain_confirming:
            self.state.goto(PARKERState.CONFIRMING)
            turn.state = VoiceTurnState.CONFIRMING
        else:
            self.state.goto(PARKERState.SPEAKING)
            turn.state = VoiceTurnState.SPEAKING

        t_tts = time.perf_counter()
        if self.tts_latency_ms > 0:
            time.sleep(self.tts_latency_ms / 1000.0)
        latency.tts_ms = (time.perf_counter() - t_tts) * 1000
        turn.action_to_speech_ms = latency.tts_ms

        self.state.set_response(spoken)
        self.state.set_active_conversations(self.conversations.active_count())

        if not remain_confirming:
            self.state.goto(PARKERState.IDLE)
            turn.state = VoiceTurnState.COMPLETE
            turn.completed_at = datetime.now(UTC)

        latency.total_ms = (time.perf_counter() - t0) * 1000
        turn.total_ms = latency.total_ms
        latency.evaluate()
        if self.latency_logger is not None:
            self.latency_logger.append(latency)

        try:
            self.conversations.add_turn(device_id, turn)
        except ContextExpiredError:
            pass

        return PipelineResult(
            turn=turn,
            spoken=spoken,
            action=action,
            action_result=action_result,
            error_code=error_code,
            confirmed=confirmed,
            latency=latency,
            category=category,
            plan=plan,
            journey=journey,
            receipt_count=receipt_count,
            awaiting_confirmation=awaiting_confirmation,
        )

    def _error_result(
        self,
        turn: VoiceTurn,
        *,
        spoken: str,
        error_code: str,
        latency: LatencyReport,
        t0: float,
    ) -> PipelineResult:
        turn.state = VoiceTurnState.ERROR
        turn.error = spoken
        turn.completed_at = datetime.now(UTC)
        self.state.goto(PARKERState.ERROR)
        self.state.add_error(spoken)
        self.state.set_response(spoken)
        self.state.goto(PARKERState.IDLE)
        latency.total_ms = (time.perf_counter() - t0) * 1000
        if self.latency_logger is not None:
            self.latency_logger.append(latency)
        return PipelineResult(
            turn=turn,
            spoken=spoken,
            error_code=error_code,
            latency=latency,
        )

    def run(self, scenario: dict[str, Any]) -> PipelineResult | list[PipelineResult]:
        from parker.simulator.scenarios import run_scenario

        return run_scenario(self, scenario)


def main() -> None:
    """CLI: run all scenarios."""
    from parker.simulator.scenarios import load_scenarios, run_scenario

    root = Path(__file__).resolve().parents[3]
    pipeline = VoicePipeline(
        ha_adapter=MockHomeAssistant(latency_ms=0),
        hermes_adapter=MockHermes(latency_ms=0),
        stt_latency_ms=0,
        tts_latency_ms=0,
        hermes_latency_ms=0,
        ha_latency_ms=0,
    )
    scenarios = load_scenarios(root / "fixtures" / "scenarios.json")
    for scenario in scenarios:
        result = run_scenario(pipeline, scenario)
        if isinstance(result, list):
            print(f"== {scenario['name']} ==")
            for r in result:
                print(" ", r.summary())
        else:
            print(f"== {scenario['name']} == {result.summary()}")
