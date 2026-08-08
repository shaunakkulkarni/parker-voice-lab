"""Gated autonomy: plan construction and multi-step execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from parker.adapters.mock_anomaly import MockAnomalyStore
from parker.adapters.mock_devops import MockHermesCLI
from parker.adapters.mock_media import MockMediaPlayer
from parker.adapters.mock_presence import MockPresence
from parker.adapters.mock_research import MockWebSearch
from parker.adapters.mock_routines import MockRoutineStore
from parker.adapters.mock_travel import MockTravel
from parker.contracts.actions import ActionCategory, ActionRequest, ActionResult
from parker.contracts.domains import PresenceEvent
from parker.contracts.plan import (
    ActionPlan,
    GatePolicy,
    Journey,
    PlanStep,
    PlanStepStatus,
    default_gate_policy,
)
from parker.receipts.approval import ApprovalMiddleware


def _step(
    *,
    domain: str,
    service: str,
    category: ActionCategory,
    target_entity: str | None = None,
    target_area: str | None = None,
    parameters: dict[str, Any] | None = None,
    label: str = "",
    spoken_preview: str | None = None,
    draft: dict[str, Any] | None = None,
) -> PlanStep:
    gate = default_gate_policy(category)
    return PlanStep(
        domain=domain,
        service=service,
        target_entity=target_entity,
        target_area=target_area,
        parameters=parameters or {},
        category=category,
        gate_policy=gate,
        label=label or f"{domain}.{service}",
        spoken_preview=spoken_preview,
        draft=draft,
        status=PlanStepStatus.DRAFTED if gate == GatePolicy.DRAFT_FIRST else PlanStepStatus.PENDING,
    )


@dataclass
class ProviderBundle:
    """Deterministic mock providers for gated-autonomy capabilities."""

    presence: MockPresence = field(default_factory=MockPresence)
    media: MockMediaPlayer = field(default_factory=MockMediaPlayer)
    devops: MockHermesCLI = field(default_factory=MockHermesCLI)
    research: MockWebSearch = field(default_factory=MockWebSearch)
    routines: MockRoutineStore = field(default_factory=MockRoutineStore)
    anomaly: MockAnomalyStore = field(default_factory=MockAnomalyStore)
    travel: MockTravel = field(default_factory=MockTravel)
    guest_mode: bool = False
    quiet_hours: bool = False
    queued_announcements: list[str] = field(default_factory=list)

    def reset(self) -> None:
        self.presence.reset()
        self.media.reset()
        self.devops.reset()
        self.research.reset()
        self.routines.reset()
        self.anomaly.reset()
        self.travel.reset()
        self.guest_mode = False
        self.quiet_hours = False
        self.queued_announcements.clear()


@dataclass
class PlanExecutionResult:
    plan: ActionPlan
    spoken: str
    awaiting_confirmation: bool = False
    confirmed_action: ActionRequest | None = None
    last_action: ActionRequest | None = None
    last_result: ActionResult | None = None
    error_code: str | None = None
    category: ActionCategory | None = None
    receipts_recorded: int = 0


class GatedAutonomyEngine:
    """Build and execute multi-step plans under the trust model."""

    def __init__(
        self,
        providers: ProviderBundle,
        approval: ApprovalMiddleware,
    ) -> None:
        self.providers = providers
        self.approval = approval

    def build_shower_plan(
        self,
        event: PresenceEvent,
        *,
        voice_turn_id: UUID,
    ) -> ActionPlan | None:
        del voice_turn_id  # plan steps carry their own ids
        if not self.providers.presence.is_valid_shower_trigger(event):
            return None

        private_bits = ["calendar: standup at 10", "message from Alex"]
        public_bits = ["It's 7:15.", "Weather: 18C and cloudy."]
        if self.providers.guest_mode:
            readout = " ".join(public_bits) + " Private items are held for you."
        else:
            readout = " ".join(public_bits + private_bits)

        steps: list[PlanStep] = []
        if self.providers.quiet_hours:
            self.providers.queued_announcements.append(readout)
            steps.append(
                _step(
                    domain="announce",
                    service="queue_readout",
                    category=ActionCategory.ROUTINE,
                    parameters={"text": readout, "queued": True},
                    label="queue shower readout (quiet hours)",
                    spoken_preview="Quiet hours: I queued the shower readout.",
                )
            )
        else:
            steps.append(
                _step(
                    domain="announce",
                    service="speak_readout",
                    category=ActionCategory.ROUTINE,
                    parameters={
                        "text": readout,
                        "private_suppressed": self.providers.guest_mode,
                    },
                    label="shower morning readout",
                    spoken_preview=readout,
                )
            )

        steps.append(
            _step(
                domain="media_player",
                service="play_media",
                category=ActionCategory.ROUTINE,
                target_entity="media_player.bathroom_homepod",
                parameters={"playlist_id": "shower_morning"},
                label="start shower playlist",
            )
        )
        plan = ActionPlan(
            capability="shower_routine",
            journey=Journey.DELEGATE_THE_ROUTINE,
            autonomy_opt_in=True,
            steps=steps,
            spoken_summary=steps[0].spoken_preview,
        )
        plan.recompute_risk()
        return plan

    def build_from_intent(
        self,
        intent: str,
        *,
        utterance: str,
        parameters: dict[str, Any],
    ) -> ActionPlan | None:
        builders = {
            "dev_ops_test": self._plan_dev_ops_test,
            "dev_ops_deploy": self._plan_dev_ops_deploy,
            "research": self._plan_research,
            "routine_run": self._plan_routine,
            "anomaly_scan": self._plan_anomaly,
            "travel_prep": self._plan_travel_prep,
            "travel_checkin": self._plan_travel_checkin,
        }
        builder = builders.get(intent)
        if builder is None:
            return None
        return builder(utterance=utterance, parameters=parameters)

    def _plan_dev_ops_test(
        self, *, utterance: str, parameters: dict[str, Any]
    ) -> ActionPlan:
        del utterance
        project = str(parameters.get("project", "parker-voice-lab"))
        plan = ActionPlan(
            capability="dev_ops",
            journey=Journey.RUN_MY_SYSTEMS,
            autonomy_opt_in=True,
            steps=[
                _step(
                    domain="devops",
                    service="run_tests",
                    category=ActionCategory.ROUTINE,
                    parameters={"project": project},
                    label=f"run tests for {project}",
                )
            ],
        )
        plan.recompute_risk()
        return plan

    def _plan_dev_ops_deploy(
        self, *, utterance: str, parameters: dict[str, Any]
    ) -> ActionPlan:
        del utterance
        target = str(parameters.get("target", "dashboard"))
        plan = ActionPlan(
            capability="dev_ops",
            journey=Journey.RUN_MY_SYSTEMS,
            autonomy_opt_in=True,
            steps=[
                _step(
                    domain="devops",
                    service="deploy",
                    category=ActionCategory.CONSEQUENTIAL,
                    parameters={"target": target},
                    label=f"deploy {target}",
                    spoken_preview=f"Should I deploy {target}?",
                )
            ],
        )
        plan.recompute_risk()
        return plan

    def _plan_research(self, *, utterance: str, parameters: dict[str, Any]) -> ActionPlan:
        topic = str(parameters.get("topic") or utterance)
        inject = bool(parameters.get("inject_conflicts"))
        if inject:
            self.providers.research.inject_conflicts = True
        plan = ActionPlan(
            capability="research",
            journey=Journey.COORDINATE_MY_DAY,
            autonomy_opt_in=True,
            steps=[
                _step(
                    domain="research",
                    service="rundown",
                    category=ActionCategory.READ,
                    parameters={"topic": topic},
                    label=f"research {topic}",
                )
            ],
        )
        plan.recompute_risk()
        return plan

    def _plan_routine(self, *, utterance: str, parameters: dict[str, Any]) -> ActionPlan:
        del utterance
        routine_id = str(parameters.get("routine_id", "jacket_weather"))
        mode = str(parameters.get("mode", "true"))
        if mode == "true":
            self.providers.routines.set_condition_true(routine_id)
        elif mode == "false":
            self.providers.routines.set_condition_false(routine_id)
        elif mode == "stale":
            self.providers.routines.set_condition_true(routine_id)
            self.providers.routines.inject_stale()
        plan = ActionPlan(
            capability="self_running_routine",
            journey=Journey.DELEGATE_THE_ROUTINE,
            autonomy_opt_in=True,
            steps=[
                _step(
                    domain="routine",
                    service="evaluate",
                    category=ActionCategory.ROUTINE,
                    parameters={"routine_id": routine_id},
                    label=f"evaluate routine {routine_id}",
                )
            ],
        )
        plan.recompute_risk()
        return plan

    def _plan_anomaly(self, *, utterance: str, parameters: dict[str, Any]) -> ActionPlan:
        del utterance
        if parameters.get("insufficient_history"):
            self.providers.anomaly.inject_insufficient_history()
        else:
            self.providers.anomaly.set_door_open()
        plan = ActionPlan(
            capability="anomaly_hunt",
            journey=Journey.WATCH_THE_HOME,
            autonomy_opt_in=True,
            steps=[
                _step(
                    domain="anomaly",
                    service="scan",
                    category=ActionCategory.READ,
                    parameters={"focus": parameters.get("focus")},
                    label="home anomaly scan",
                )
            ],
        )
        plan.recompute_risk()
        return plan

    def _plan_travel_prep(
        self, *, utterance: str, parameters: dict[str, Any]
    ) -> ActionPlan:
        destination = str(parameters.get("destination") or utterance)
        plan = ActionPlan(
            capability="travel_prep",
            journey=Journey.COORDINATE_MY_DAY,
            autonomy_opt_in=True,
            steps=[
                _step(
                    domain="travel",
                    service="prepare",
                    category=ActionCategory.READ,
                    parameters={"destination": destination},
                    label=f"prepare trip to {destination}",
                )
            ],
        )
        plan.recompute_risk()
        return plan

    def _plan_travel_checkin(
        self, *, utterance: str, parameters: dict[str, Any]
    ) -> ActionPlan:
        del utterance
        flight = str(parameters.get("flight", "UA412"))
        plan = ActionPlan(
            capability="travel_prep",
            journey=Journey.COORDINATE_MY_DAY,
            autonomy_opt_in=True,
            steps=[
                _step(
                    domain="travel",
                    service="check_in",
                    category=ActionCategory.CONSEQUENTIAL,
                    parameters={"flight_number": flight},
                    label=f"check in for {flight}",
                    spoken_preview=f"Should I check in for flight {flight}?",
                )
            ],
        )
        plan.recompute_risk()
        return plan

    def execute_plan(
        self,
        plan: ActionPlan,
        *,
        voice_turn_id: UUID,
        conversation_id: UUID,
        area_id: str | None = None,
        confirm: bool | None = None,
        cancel: bool = False,
        deny: bool = False,
    ) -> PlanExecutionResult:
        if not plan.autonomy_opt_in:
            return PlanExecutionResult(
                plan=plan,
                spoken="This capability is not opted into autonomy.",
                error_code="autonomy_not_enabled",
                category=plan.risk_class,
            )

        receipts = 0
        spoken_parts: list[str] = []
        last_action: ActionRequest | None = None
        last_result: ActionResult | None = None

        # Resolve a previously gated step first.
        pending = next(
            (
                s
                for s in plan.steps
                if s.status
                in (PlanStepStatus.AWAITING_CONFIRMATION, PlanStepStatus.DRAFTED)
            ),
            None,
        )
        if pending is not None:
            action = pending.to_action_request(
                voice_turn_id=voice_turn_id, conversation_id=conversation_id
            )
            if cancel or deny or confirm is False:
                pending.status = PlanStepStatus.CANCELLED
                self.approval.confirm(
                    action, confirmed=False, cancelled=cancel, area_id=area_id
                )
                receipts += 1
                plan.completed = True
                return PlanExecutionResult(
                    plan=plan,
                    spoken="Okay, cancelled." if cancel else "Okay, I won't do that.",
                    last_action=action,
                    receipts_recorded=receipts,
                    category=pending.category,
                    confirmed_action=action,
                )
            if confirm is True:
                result = self._run_step(pending, action_id=action.id)
                last_action = action
                last_result = result
                self.approval.confirm(
                    action,
                    confirmed=True,
                    result=result,
                    area_id=area_id,
                )
                receipts += 1
                if result.success:
                    pending.status = PlanStepStatus.COMPLETED
                    spoken_parts.append(self._success_spoken(pending, result))
                else:
                    pending.status = PlanStepStatus.FAILED
                    spoken_parts.append(result.error or "That step failed.")
                    plan.completed = True
                    return PlanExecutionResult(
                        plan=plan,
                        spoken=" ".join(spoken_parts),
                        last_action=last_action,
                        last_result=last_result,
                        error_code=result.error_code,
                        receipts_recorded=receipts,
                        category=pending.category,
                    )
            else:
                return PlanExecutionResult(
                    plan=plan,
                    spoken=pending.spoken_preview
                    or f"Should I {pending.service.replace('_', ' ')}?",
                    awaiting_confirmation=True,
                    confirmed_action=action,
                    last_action=action,
                    category=pending.category,
                )

        for index, step in enumerate(plan.steps):
            if step.status in (
                PlanStepStatus.COMPLETED,
                PlanStepStatus.FAILED,
                PlanStepStatus.CANCELLED,
                PlanStepStatus.SKIPPED,
            ):
                continue

            plan.current_index = index
            action = step.to_action_request(
                voice_turn_id=voice_turn_id, conversation_id=conversation_id
            )

            if step.gate_policy == GatePolicy.DRAFT_FIRST and step.status != PlanStepStatus.DRAFTED:
                step.status = PlanStepStatus.DRAFTED
                step.draft = {
                    "domain": step.domain,
                    "service": step.service,
                    "target": step.target_entity,
                    "parameters": step.parameters,
                }
                if confirm is not True:
                    return PlanExecutionResult(
                        plan=plan,
                        spoken=step.spoken_preview
                        or f"Draft ready for {step.label}. Confirm to proceed.",
                        awaiting_confirmation=True,
                        confirmed_action=action,
                        last_action=action,
                        category=step.category,
                    )
                # Inline confirmation provided with the scenario/request.

            if step.gate_policy == GatePolicy.CONFIRM and confirm is not True:
                step.status = PlanStepStatus.AWAITING_CONFIRMATION
                return PlanExecutionResult(
                    plan=plan,
                    spoken=step.spoken_preview
                    or f"Should I {step.service.replace('_', ' ')}?",
                    awaiting_confirmation=True,
                    confirmed_action=action,
                    last_action=action,
                    category=step.category,
                )

            if cancel or deny or confirm is False:
                step.status = PlanStepStatus.CANCELLED
                self.approval.confirm(
                    action, confirmed=False, cancelled=cancel, area_id=area_id
                )
                receipts += 1
                plan.completed = True
                return PlanExecutionResult(
                    plan=plan,
                    spoken="Okay, cancelled." if cancel else "Okay, I won't do that.",
                    last_action=action,
                    receipts_recorded=receipts,
                    category=step.category,
                    confirmed_action=action,
                )

            # AUTO (read/routine) or confirmed gated step
            step.status = PlanStepStatus.RUNNING
            result = self._run_step(step, action_id=action.id)
            last_action = action
            last_result = result
            if step.gate_policy in (GatePolicy.CONFIRM, GatePolicy.DRAFT_FIRST):
                self.approval.confirm(
                    action, confirmed=True, result=result, area_id=area_id
                )
            else:
                self.approval.record_auto(action, result, area_id=area_id)
            receipts += 1
            if result.success:
                step.status = PlanStepStatus.COMPLETED
                spoken_parts.append(self._success_spoken(step, result))
            else:
                step.status = PlanStepStatus.FAILED
                spoken_parts.append(result.error or f"{step.label} failed.")
                plan.completed = True
                return PlanExecutionResult(
                    plan=plan,
                    spoken=" ".join(spoken_parts),
                    last_action=last_action,
                    last_result=last_result,
                    error_code=result.error_code,
                    receipts_recorded=receipts,
                    category=step.category,
                )

        plan.completed = True
        spoken = " ".join(p for p in spoken_parts if p).strip()
        if not spoken and plan.spoken_summary:
            spoken = plan.spoken_summary
        if not spoken:
            spoken = "Done."
        return PlanExecutionResult(
            plan=plan,
            spoken=spoken,
            last_action=last_action,
            last_result=last_result,
            receipts_recorded=receipts,
            category=plan.risk_class,
        )

    def _run_step(self, step: PlanStep, *, action_id: UUID) -> ActionResult:
        try:
            new_state = self._dispatch(step)
            return ActionResult(
                action_request_id=action_id,
                success=True,
                new_state=new_state,
            )
        except _StepError as exc:
            return ActionResult(
                action_request_id=action_id,
                success=False,
                error=exc.message,
                error_code=exc.code,
            )

    def _dispatch(self, step: PlanStep) -> dict[str, Any] | None:
        domain = step.domain
        service = step.service
        params = step.parameters

        if domain == "announce":
            text = str(params.get("text", ""))
            if service == "queue_readout":
                return {"queued": True, "text": text}
            return {"spoken": text, "private_suppressed": params.get("private_suppressed")}

        if domain == "media_player" and service == "play_media":
            entity = step.target_entity or "media_player.bathroom_homepod"
            playlist = str(params.get("playlist_id", "shower_morning"))
            result = self.providers.media.start_playlist(entity, playlist)
            if not result.success:
                raise _StepError(
                    result.error_code or "media_failed",
                    f"Could not start playlist on {entity}.",
                )
            return result.model_dump(mode="json")

        if domain == "devops" and service == "run_tests":
            # Verified CLI result is a successful adapter call even when tests fail.
            cli = self.providers.devops.run_tests(str(params.get("project", "parker-voice-lab")))
            return {
                "exit_code": cli.exit_code,
                "stdout": cli.stdout,
                "stderr": cli.stderr,
                "command": cli.command,
                "tests_passed": cli.success,
            }

        if domain == "devops" and service == "deploy":
            cli = self.providers.devops.deploy(str(params.get("target", "dashboard")))
            if not cli.success:
                raise _StepError("deploy_failed", cli.stderr or "Deploy failed.")
            return {"exit_code": cli.exit_code, "stdout": cli.stdout, "target": cli.project}

        if domain == "research" and service == "rundown":
            research_report = self.providers.research.research(
                str(params.get("topic", "topic"))
            )
            return research_report.model_dump(mode="json")

        if domain == "routine" and service == "evaluate":
            routine_run = self.providers.routines.evaluate(str(params.get("routine_id")))
            return routine_run.model_dump(mode="json")

        if domain == "anomaly" and service == "scan":
            focus = params.get("focus")
            anomaly_report = self.providers.anomaly.scan(
                str(focus) if focus else None
            )
            return anomaly_report.model_dump(mode="json")

        if domain == "travel" and service == "prepare":
            travel_plan = self.providers.travel.prepare(str(params.get("destination", "")))
            if travel_plan is None:
                raise _StepError("not_found", "I couldn't find a matching trip.")
            return travel_plan.model_dump(mode="json")

        if domain == "travel" and service == "check_in":
            flight = str(params.get("flight_number", ""))
            return self.providers.travel.check_in(flight)

        raise _StepError("unsupported_step", f"Unsupported step {domain}.{service}")

    def _success_spoken(self, step: PlanStep, result: ActionResult) -> str:
        state = result.new_state or {}
        if step.domain == "announce":
            if step.service == "queue_readout":
                return "Quiet hours: I queued the shower readout."
            return str(state.get("spoken") or step.spoken_preview or "")
        if step.domain == "media_player":
            title = state.get("media_title") or "your playlist"
            return f"Playing {title}."
        if step.domain == "devops" and step.service == "run_tests":
            if state.get("tests_passed"):
                return (
                    f"Tests passed for the project. "
                    f"Exit code {state.get('exit_code')}: {state.get('stdout')}"
                )
            return (
                f"Tests failed. Exit code {state.get('exit_code')}: "
                f"{state.get('stdout')}. I am not reporting success."
            )
        if step.domain == "devops" and step.service == "deploy":
            return str(state.get("stdout") or "Deploy complete.")
        if step.domain == "research":
            summary = str(state.get("summary", "Research complete."))
            conflicts = state.get("conflicting_claims") or []
            if conflicts:
                summary += " Conflicting claims disclosed."
            sources = state.get("sources") or []
            if sources:
                titles = ", ".join(s.get("title", "source") for s in sources[:3])
                summary += f" Sources: {titles}."
            return summary
        if step.domain == "routine":
            return str(state.get("spoken") or "Routine evaluated.")
        if step.domain == "anomaly":
            return str(state.get("spoken") or "Anomaly scan complete.")
        if step.domain == "travel" and step.service == "prepare":
            return str(state.get("spoken") or "Travel plan ready.")
        if step.domain == "travel" and step.service == "check_in":
            return f"Checked in for {state.get('flight_number')}."
        return f"Done. {step.label}."


class _StepError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
