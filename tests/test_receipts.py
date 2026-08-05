"""Tests for receipt store and approval middleware."""

from pathlib import Path
from uuid import uuid4

from parker.contracts.actions import ActionCategory, ActionReceipt, ActionRequest, ActionResult
from parker.receipts.approval import ApprovalDecision, ApprovalMiddleware
from parker.receipts.store import ReceiptStore


def _action(
    *,
    domain: str = "light",
    service: str = "turn_on",
    entity: str | None = "light.living_room",
    category: ActionCategory = ActionCategory.ROUTINE,
    requires_confirmation: bool = False,
    parameters: dict[str, float] | None = None,
) -> ActionRequest:
    return ActionRequest(
        voice_turn_id=uuid4(),
        domain=domain,
        service=service,
        target_entity=entity,
        category=category,
        requires_confirmation=requires_confirmation,
        conversation_id=uuid4(),
        parameters=parameters or {},
    )


def test_receipt_store_jsonl(tmp_path: Path) -> None:
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    action = _action()
    result = ActionResult(
        action_request_id=action.id, success=True, new_state={"state": "on"}
    )
    receipt = ActionReceipt(
        trigger="voice_command",
        authority="auto",
        action_request=action,
        action_result=result,
        confirmed=True,
        confirmation_method="auto",
    )
    store.append(receipt, area_id="living_room")
    rows = store.load_from_disk()
    assert len(rows) == 1
    assert rows[0]["action"]["target"] == "light.living_room"
    assert rows[0]["confirmed"] is True


def test_routine_auto_approved(tmp_path: Path) -> None:
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    middleware = ApprovalMiddleware(store)
    outcome = middleware.evaluate(_action())
    assert outcome.decision == ApprovalDecision.AUTO_APPROVE
    receipt = middleware.record_auto(
        outcome.action,
        ActionResult(action_request_id=outcome.action.id, success=True),
    )
    assert receipt.confirmation_method == "auto"
    assert len(store.all()) == 1


def test_lock_requires_confirmation(tmp_path: Path) -> None:
    store = ReceiptStore(tmp_path / "r.jsonl")
    mw = ApprovalMiddleware(store)
    action = _action(
        domain="lock",
        service="lock",
        entity="lock.front_door",
        category=ActionCategory.CONSEQUENTIAL,
        requires_confirmation=True,
    )
    outcome = mw.evaluate(action)
    assert outcome.decision == ApprovalDecision.NEEDS_CONFIRMATION
    assert outcome.spoken_prompt is not None


def test_confirm_and_cancel(tmp_path: Path) -> None:
    store = ReceiptStore(tmp_path / "r.jsonl")
    mw = ApprovalMiddleware(store)
    action = _action(
        domain="lock",
        service="unlock",
        entity="lock.front_door",
        category=ActionCategory.CONSEQUENTIAL,
        requires_confirmation=True,
    )
    confirmed = mw.confirm(
        action,
        confirmed=True,
        result=ActionResult(
            action_request_id=action.id,
            success=True,
            new_state={"state": "unlocked"},
        ),
        area_id="hallway",
    )
    assert confirmed.decision == ApprovalDecision.CONFIRMED
    assert confirmed.receipt is not None
    assert confirmed.receipt.confirmed is True

    cancelled = mw.confirm(action, confirmed=False, cancelled=True, area_id="hallway")
    assert cancelled.decision == ApprovalDecision.CANCELLED
    assert len(store.all()) == 2


def test_extreme_thermostat_consequential(tmp_path: Path) -> None:
    mw = ApprovalMiddleware(ReceiptStore(tmp_path / "r.jsonl"))
    action = _action(
        domain="climate",
        service="set_temperature",
        entity="climate.living_room",
        category=ActionCategory.ROUTINE,
        parameters={"temperature": 5},
    )
    outcome = mw.evaluate(action)
    assert outcome.decision == ApprovalDecision.NEEDS_CONFIRMATION
