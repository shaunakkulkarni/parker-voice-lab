"""Mock Hermes adapter using pattern matching (no LLM)."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from parker.adapters.base import HermesAdapter, HermesResponse
from parker.contracts.actions import ActionCategory, ActionRequest
from parker.contracts.context import ConversationContext

DEFAULT_RESPONSES_PATH = Path(__file__).resolve().parents[3] / "fixtures" / "responses.json"


class MockHermes(HermesAdapter):
    """Deterministic Hermes stand-in for tests and simulation."""

    def __init__(
        self,
        responses_path: Path | str | None = None,
        *,
        latency_ms: float = 0.0,
        fail_next: bool = False,
    ) -> None:
        self.latency_ms = latency_ms
        self.fail_next = fail_next
        path = Path(responses_path) if responses_path else DEFAULT_RESPONSES_PATH
        data = json.loads(path.read_text(encoding="utf-8"))
        self._patterns: list[dict[str, Any]] = list(data.get("patterns", []))
        # Longer matches first for specificity
        self._patterns.sort(key=lambda p: len(p.get("match", "")), reverse=True)

    def _sleep(self) -> None:
        if self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000.0)

    def reason(
        self,
        utterance: str,
        conversation: ConversationContext,
        *,
        voice_turn_id: UUID,
    ) -> HermesResponse:
        self._sleep()
        if self.fail_next:
            self.fail_next = False
            return HermesResponse(
                intent="error",
                spoken="Sorry, I had trouble understanding that.",
                error_code="hermes_unavailable",
            )

        text = utterance.strip().lower()
        text = text.rstrip("?.!")

        for pattern in self._patterns:
            match = pattern.get("match", "")
            if match and match in text:
                return self._build_response(pattern, text, conversation, voice_turn_id)

        # "And the kitchen?" style follow-up for lights
        if text.startswith("and the ") and conversation.last_action is not None:
            room = text.removeprefix("and the ").strip().rstrip("?")
            return HermesResponse(
                intent="follow_up_room",
                spoken=f"Turning on the {room} light.",
                category=ActionCategory.ROUTINE,
                follow_up=True,
                action_request=ActionRequest(
                    voice_turn_id=voice_turn_id,
                    domain="light",
                    service="turn_on",
                    target_entity=f"light.{room.replace(' ', '_')}",
                    target_area=room.replace(" ", "_"),
                    category=ActionCategory.ROUTINE,
                    conversation_id=conversation.id,
                ),
            )

        return HermesResponse(
            intent="unknown",
            spoken="Sorry, I didn't understand that.",
            error_code="unknown_intent",
        )

    def _build_response(
        self,
        pattern: dict[str, Any],
        text: str,
        conversation: ConversationContext,
        voice_turn_id: UUID,
    ) -> HermesResponse:
        if pattern.get("error"):
            return HermesResponse(
                intent=pattern.get("intent", "error"),
                spoken=pattern.get("spoken", "Something went wrong."),
                error_code=pattern["error"],
            )

        if pattern.get("cancel"):
            return HermesResponse(
                intent="cancel",
                spoken=pattern.get("spoken", "Okay, cancelled."),
                cancel=True,
            )
        if pattern.get("confirm"):
            return HermesResponse(
                intent="confirm",
                spoken=pattern.get("spoken", "Confirmed."),
                confirm=True,
            )
        if pattern.get("deny"):
            return HermesResponse(
                intent="deny",
                spoken=pattern.get("spoken", "Okay, I won't do that."),
                deny=True,
            )

        category = ActionCategory(pattern.get("category", "read"))
        params: dict[str, Any] = {}
        spoken = pattern.get("spoken", "")

        # Extract thermostat temperature
        temp_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:degrees?)?", text)
        if pattern.get("intent") == "set_temperature" and temp_match:
            params["temperature"] = float(temp_match.group(1))
            spoken = spoken.format(temperature=params["temperature"])

        if pattern.get("intent") == "tell_time":
            spoken = spoken.format(time=datetime.now().strftime("%I:%M %p").lstrip("0"))

        if pattern.get("follow_up"):
            # Follow-ups need prior topic; pipeline may still reject if expired.
            spoken = spoken.replace("{temperature}", "21.5")

        action: ActionRequest | None = None
        domain = pattern.get("domain")
        service = pattern.get("service")
        entity = pattern.get("entity")
        resolve_room_light = bool(pattern.get("resolve_room_light"))

        if domain and service and not pattern.get("follow_up"):
            if resolve_room_light:
                # Leave entity unset; room resolver fills it when area is known.
                entity = None
            if pattern.get("intent") == "set_temperature":
                entity = entity or f"climate.{conversation.area_id}"
            if pattern.get("intent") == "read_temperature":
                # Read-only: no service call required by HA adapter
                action = None
            elif domain == "climate" and service == "get_temperature":
                action = None
            else:
                action = ActionRequest(
                    voice_turn_id=voice_turn_id,
                    domain=domain,
                    service=service,
                    target_entity=entity,
                    target_area=pattern.get("area_id"),
                    parameters=params,
                    category=category,
                    requires_confirmation=bool(pattern.get("requires_confirmation")),
                    conversation_id=conversation.id,
                )

        # Temperature read uses placeholder; pipeline fills real value.
        if "{temperature}" in spoken:
            spoken = spoken.replace("{temperature}", "21.5")

        plan_intent = pattern.get("plan_intent")
        plan_parameters = dict(pattern.get("plan_parameters") or {})
        # Fill topic from utterance for research patterns
        if plan_intent == "research" and "topic" not in plan_parameters:
            plan_parameters["topic"] = text
        if plan_intent == "travel_prep" and "destination" not in plan_parameters:
            for marker in ("trip to ", "for my trip to ", "prepare me for "):
                if marker in text:
                    plan_parameters["destination"] = text.split(marker, 1)[1].strip()
                    break
            plan_parameters.setdefault("destination", text)

        return HermesResponse(
            intent=pattern.get("intent", "unknown"),
            spoken=spoken,
            action_request=action,
            category=category,
            requires_confirmation=bool(pattern.get("requires_confirmation")),
            follow_up=bool(pattern.get("follow_up")),
            topic=pattern.get("topic"),
            resolve_room_light=resolve_room_light,
            parameters=params,
            plan_intent=plan_intent,
            plan_parameters=plan_parameters,
        )
