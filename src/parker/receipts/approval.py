"""Approval middleware for consequential / irreversible actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from parker.contracts.actions import ActionCategory, ActionReceipt, ActionRequest, ActionResult
from parker.receipts.store import ReceiptStore

# Domains/services that always require confirmation
_CONSEQUENTIAL_RULES: set[tuple[str, str]] = {
    ("lock", "lock"),
    ("lock", "unlock"),
    ("devops", "deploy"),
    ("devops", "restart"),
    ("devops", "publish"),
    ("travel", "check_in"),
    ("security", "arm"),
}

_IRREVERSIBLE_RULES: set[tuple[str, str]] = {
    ("automation", "delete"),
    ("notify", "send"),
    ("messaging", "send"),
}


class ApprovalDecision(StrEnum):
    AUTO_APPROVE = "auto_approve"
    NEEDS_CONFIRMATION = "needs_confirmation"
    CONFIRMED = "confirmed"
    DENIED = "denied"
    CANCELLED = "cancelled"


@dataclass
class ApprovalOutcome:
    decision: ApprovalDecision
    action: ActionRequest
    receipt: ActionReceipt | None = None
    spoken_prompt: str | None = None


class ApprovalMiddleware:
    """Gates actions by category and records receipts."""

    def __init__(self, store: ReceiptStore) -> None:
        self.store = store

    def categorize(self, action: ActionRequest) -> ActionCategory:
        key = (action.domain, action.service)
        if key in _IRREVERSIBLE_RULES:
            return ActionCategory.IRREVERSIBLE
        if key in _CONSEQUENTIAL_RULES or action.requires_confirmation:
            return ActionCategory.CONSEQUENTIAL
        if action.category == ActionCategory.READ:
            return ActionCategory.READ
        # Extreme thermostat changes
        if action.domain == "climate" and action.service == "set_temperature":
            temp = action.parameters.get("temperature")
            if isinstance(temp, (int, float)) and (temp < 10 or temp > 30):
                return ActionCategory.CONSEQUENTIAL
        return action.category

    def evaluate(self, action: ActionRequest) -> ApprovalOutcome:
        category = self.categorize(action)
        updated = action.model_copy(
            update={
                "category": category,
                "requires_confirmation": category
                in (ActionCategory.CONSEQUENTIAL, ActionCategory.IRREVERSIBLE),
            }
        )
        if updated.requires_confirmation:
            prompt = (
                f"Should I {updated.service.replace('_', ' ')} "
                f"the {self._friendly_target(updated)}?"
            )
            return ApprovalOutcome(
                decision=ApprovalDecision.NEEDS_CONFIRMATION,
                action=updated,
                spoken_prompt=prompt,
            )
        return ApprovalOutcome(
            decision=ApprovalDecision.AUTO_APPROVE,
            action=updated,
        )

    def confirm(
        self,
        action: ActionRequest,
        *,
        confirmed: bool,
        cancelled: bool = False,
        result: ActionResult | None = None,
        area_id: str | None = None,
    ) -> ApprovalOutcome:
        if cancelled:
            decision = ApprovalDecision.CANCELLED
            authority = "user_voice_cancel"
            confirmed_flag = False
        elif confirmed:
            decision = ApprovalDecision.CONFIRMED
            authority = "user_voice_confirmation"
            confirmed_flag = True
        else:
            decision = ApprovalDecision.DENIED
            authority = "user_voice_denial"
            confirmed_flag = False

        receipt = ActionReceipt(
            trigger="voice_command",
            authority=authority,
            action_request=action,
            action_result=result,
            confirmed=confirmed_flag,
            confirmation_method="voice" if action.requires_confirmation else "auto",
        )
        self.store.append(receipt, area_id=area_id)
        return ApprovalOutcome(decision=decision, action=action, receipt=receipt)

    def record_auto(
        self,
        action: ActionRequest,
        result: ActionResult | None,
        *,
        area_id: str | None = None,
    ) -> ActionReceipt:
        receipt = ActionReceipt(
            trigger="voice_command",
            authority="auto",
            action_request=action,
            action_result=result,
            confirmed=True,
            confirmation_method="auto",
        )
        self.store.append(receipt, area_id=area_id)
        return receipt

    @staticmethod
    def _friendly_target(action: ActionRequest) -> str:
        if action.target_entity:
            return action.target_entity.replace(".", " ").replace("_", " ")
        return action.domain
