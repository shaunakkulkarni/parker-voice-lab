"""Action request, result, and receipt contracts."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from parker.contracts._time import utc_now


class ActionCategory(StrEnum):
    READ = "read"
    ROUTINE = "routine"
    CONSEQUENTIAL = "consequential"
    IRREVERSIBLE = "irreversible"


class ActionRequest(BaseModel):
    """A request to execute a Home Assistant action."""

    id: UUID = Field(default_factory=uuid4)
    voice_turn_id: UUID
    domain: str
    service: str
    target_entity: str | None = None
    target_area: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    category: ActionCategory
    requires_confirmation: bool = False
    conversation_id: UUID
    requested_at: datetime = Field(default_factory=utc_now)


class ActionResult(BaseModel):
    """The result of executing an action."""

    id: UUID = Field(default_factory=uuid4)
    action_request_id: UUID
    success: bool
    new_state: dict[str, Any] | None = None
    error: str | None = None
    error_code: str | None = None
    executed_at: datetime = Field(default_factory=utc_now)


class ActionReceipt(BaseModel):
    """A complete audit trail for an action."""

    id: UUID = Field(default_factory=uuid4)
    trigger: str
    authority: str
    action_request: ActionRequest
    action_result: ActionResult | None = None
    confirmed: bool = False
    confirmation_method: str | None = None
    rollback_info: str | None = None
