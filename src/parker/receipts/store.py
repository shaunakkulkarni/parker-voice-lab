"""JSONL receipt storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from parker.contracts.actions import ActionReceipt


class ReceiptStore:
    """Append-only JSON lines store for action receipts."""

    def __init__(self, path: Path | str | None = None) -> None:
        root = Path(__file__).resolve().parents[3]
        self.path = Path(path) if path else root / "data" / "receipts.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memory: list[ActionReceipt] = []

    def append(self, receipt: ActionReceipt, *, area_id: str | None = None) -> None:
        self._memory.append(receipt)
        record = self._to_log_record(receipt, area_id=area_id)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")

    def all(self) -> list[ActionReceipt]:
        return list(self._memory)

    def load_from_disk(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def clear(self) -> None:
        self._memory.clear()
        if self.path.exists():
            self.path.unlink()

    def find_by_conversation(self, conversation_id: UUID) -> list[ActionReceipt]:
        return [
            r
            for r in self._memory
            if r.action_request.conversation_id == conversation_id
        ]

    @staticmethod
    def _to_log_record(
        receipt: ActionReceipt, *, area_id: str | None = None
    ) -> dict[str, Any]:
        req = receipt.action_request
        result = receipt.action_result
        return {
            "id": str(receipt.id),
            "timestamp": req.requested_at.isoformat().replace("+00:00", "Z"),
            "trigger": receipt.trigger,
            "authority": receipt.authority,
            "action": {
                "domain": req.domain,
                "service": req.service,
                "target": req.target_entity,
                "parameters": req.parameters,
            },
            "result": None
            if result is None
            else {
                "success": result.success,
                "new_state": result.new_state,
                "error": result.error,
            },
            "confirmed": receipt.confirmed,
            "confirmation_method": receipt.confirmation_method,
            "conversation_id": str(req.conversation_id),
            "area_id": area_id or req.target_area,
        }
