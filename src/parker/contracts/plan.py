"""Multi-step action plans and gated-autonomy policy contracts."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from parker.contracts._time import utc_now
from parker.contracts.actions import ActionCategory, ActionRequest, ActionResult


class GatePolicy(StrEnum):
    """How a plan step may execute under gated autonomy."""

    AUTO = "auto"
    CONFIRM = "confirm"
    DRAFT_FIRST = "draft_first"


class PlanStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    DRAFTED = "drafted"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class Journey(StrEnum):
    ORIENT_ME = "orient_me"
    KEEP_ME_AHEAD = "keep_me_ahead"
    RUN_THE_ROOM = "run_the_room"
    PUT_ME_INTO_A_MODE = "put_me_into_a_mode"
    COORDINATE_MY_DAY = "coordinate_my_day"
    ACT_ON_MY_BEHALF = "act_on_my_behalf"
    NOTICE_AND_RECOVER = "notice_and_recover"
    RUN_MY_SYSTEMS = "run_my_systems"
    DELEGATE_THE_ROUTINE = "delegate_the_routine"
    WATCH_THE_HOME = "watch_the_home"


def default_gate_policy(category: ActionCategory) -> GatePolicy:
    """Map action class to gate policy. No capability is autonomous by default."""
    if category == ActionCategory.READ:
        return GatePolicy.AUTO
    if category == ActionCategory.ROUTINE:
        return GatePolicy.AUTO
    if category == ActionCategory.CONSEQUENTIAL:
        return GatePolicy.CONFIRM
    return GatePolicy.DRAFT_FIRST


class PlanStep(BaseModel):
    """One itemised step in an action plan."""

    id: UUID = Field(default_factory=uuid4)
    domain: str
    service: str
    target_entity: str | None = None
    target_area: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    category: ActionCategory
    gate_policy: GatePolicy
    status: PlanStepStatus = PlanStepStatus.PENDING
    label: str = ""
    spoken_preview: str | None = None
    result: ActionResult | None = None
    error_code: str | None = None
    draft: dict[str, Any] | None = None

    def to_action_request(
        self,
        *,
        voice_turn_id: UUID,
        conversation_id: UUID,
    ) -> ActionRequest:
        return ActionRequest(
            voice_turn_id=voice_turn_id,
            domain=self.domain,
            service=self.service,
            target_entity=self.target_entity,
            target_area=self.target_area,
            parameters=dict(self.parameters),
            category=self.category,
            requires_confirmation=self.gate_policy
            in (GatePolicy.CONFIRM, GatePolicy.DRAFT_FIRST),
            conversation_id=conversation_id,
        )


class ActionPlan(BaseModel):
    """Itemised multi-step plan with mixed-risk gating."""

    id: UUID = Field(default_factory=uuid4)
    capability: str
    journey: Journey | None = None
    autonomy_opt_in: bool = False
    steps: list[PlanStep] = Field(default_factory=list)
    current_index: int = 0
    risk_class: ActionCategory = ActionCategory.READ
    created_at: datetime = Field(default_factory=utc_now)
    completed: bool = False
    spoken_summary: str | None = None

    def recompute_risk(self) -> ActionCategory:
        order = [
            ActionCategory.READ,
            ActionCategory.ROUTINE,
            ActionCategory.CONSEQUENTIAL,
            ActionCategory.IRREVERSIBLE,
        ]
        highest = ActionCategory.READ
        for step in self.steps:
            if order.index(step.category) > order.index(highest):
                highest = step.category
        self.risk_class = highest
        return highest

    @property
    def pending_step(self) -> PlanStep | None:
        for step in self.steps:
            if step.status in (
                PlanStepStatus.AWAITING_CONFIRMATION,
                PlanStepStatus.DRAFTED,
            ):
                return step
        if 0 <= self.current_index < len(self.steps):
            step = self.steps[self.current_index]
            if step.status == PlanStepStatus.PENDING:
                return step
        return None

    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.steps if s.status == PlanStepStatus.COMPLETED)

    @property
    def receipt_eligible_count(self) -> int:
        return sum(
            1
            for s in self.steps
            if s.status
            in (
                PlanStepStatus.COMPLETED,
                PlanStepStatus.FAILED,
                PlanStepStatus.CANCELLED,
            )
        )
