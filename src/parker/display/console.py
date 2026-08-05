"""Transport-independent Test Console controller and session models."""

from __future__ import annotations

import threading
from collections import deque
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from parker.adapters.base import HermesAdapter, HomeAssistantAdapter
from parker.adapters.mock_ha import MockHomeAssistant
from parker.adapters.mock_hermes import MockHermes
from parker.context.conversation import ConversationManager
from parker.context.state import StateMachine
from parker.contracts._time import utc_now
from parker.contracts.actions import ActionReceipt, ActionRequest, ActionResult
from parker.contracts.context import SystemStatus
from parker.receipts.store import ReceiptStore
from parker.simulator.latency import LATENCY_TARGETS_MS, LatencyLogger, LatencyReport
from parker.simulator.pipeline import PipelineResult, VoicePipeline
from parker.simulator.scenarios import (
    check_scenario_expectations,
    load_scenarios,
    run_scenario,
)

HISTORY_LIMIT = 20

STAGE_LABELS: list[tuple[str, str]] = [
    ("wake_to_listening_ms", "Wake"),
    ("stt_ms", "Speech-to-text"),
    ("hermes_ms", "Hermes reasoning"),
    ("ha_ms", "Home Assistant action"),
    ("tts_ms", "Text-to-speech"),
    ("total_ms", "Total"),
]


class ConsoleBusyError(RuntimeError):
    """Raised when a pipeline mutation is already in progress."""

    code = "busy"


class ConsoleConfirmationError(RuntimeError):
    """Raised when confirmation is requested without a pending action."""

    code = "no_pending_confirmation"


class ConsoleNotFoundError(LookupError):
    """Raised when a named scenario does not exist."""

    code = "not_found"


class RunType(StrEnum):
    MANUAL = "manual"
    SCENARIO = "scenario"
    SUITE_MEMBER = "suite_member"


class LatencyStage(BaseModel):
    stage: str
    actual_ms: float
    target_ms: float
    status: Literal["pass", "miss", "skipped"]


class LatencyTrace(BaseModel):
    wake_to_listening_ms: float = 0.0
    stt_ms: float = 0.0
    hermes_ms: float = 0.0
    ha_ms: float = 0.0
    tts_ms: float = 0.0
    total_ms: float = 0.0
    stages: list[LatencyStage] = Field(default_factory=list)
    within_targets: bool = True


class HealthSnapshot(BaseModel):
    mode: Literal["mock"] = "mock"
    home_assistant: str = "ready"
    hermes: str = "ready"
    stt: str = "simulated"
    tts: str = "simulated"
    voice_preview_edition: str = "not_connected"
    live_device_actions: bool = False


class ConsoleEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=utc_now)
    kind: str
    message: str
    run_id: UUID | None = None


class PendingConfirmationView(BaseModel):
    action: ActionRequest
    spoken_prompt: str | None = None
    area_id: str
    device_id: str
    category: str | None = None


class ConsoleRun(BaseModel):
    run_id: UUID = Field(default_factory=uuid4)
    started_at: datetime
    completed_at: datetime
    run_type: RunType
    scenario_name: str | None = None
    utterance: str | None = None
    area_id: str
    voice_device_id: str
    passed: bool | None = None
    expected: dict[str, Any] | None = None
    actual: dict[str, Any] | None = None
    spoken_response: str
    error_code: str | None = None
    action: ActionRequest | None = None
    action_result: ActionResult | None = None
    receipt: ActionReceipt | None = None
    latency_trace: LatencyTrace
    final_state: str
    confirmed: bool | None = None


class SuiteSummary(BaseModel):
    total: int
    passed: int
    failed: int
    manual: int = 0


class SuiteResult(BaseModel):
    summary: SuiteSummary
    runs: list[ConsoleRun]
    session: SessionSnapshot


class SessionSnapshot(BaseModel):
    status: SystemStatus
    health: HealthSnapshot
    pending_confirmation: PendingConfirmationView | None = None
    last_run: ConsoleRun | None = None
    recent_runs: list[ConsoleRun] = Field(default_factory=list)
    recent_events: list[ConsoleEvent] = Field(default_factory=list)
    recent_receipts: list[ActionReceipt] = Field(default_factory=list)
    is_busy: bool = False


class ScenarioInfo(BaseModel):
    name: str
    utterance: str | None = None
    turns: list[dict[str, Any]] | None = None
    expected_action: dict[str, Any] | None = None
    expected_category: str | None = None
    expected_error: str | None = None
    requires_confirmation: bool = False
    confirmation_response: str | None = None
    area_id: str
    device_id: str
    notes: str | None = None


def build_latency_trace(
    report: LatencyReport | None,
    *,
    ha_ran: bool,
) -> LatencyTrace:
    if report is None:
        empty_stages = [
            LatencyStage(
                stage=label,
                actual_ms=0.0,
                target_ms=LATENCY_TARGETS_MS[key],
                status="skipped",
            )
            for key, label in STAGE_LABELS
        ]
        return LatencyTrace(stages=empty_stages, within_targets=True)

    values = {
        "wake_to_listening_ms": report.wake_to_listening_ms,
        "stt_ms": report.stt_ms,
        "hermes_ms": report.hermes_ms,
        "ha_ms": report.ha_ms,
        "tts_ms": report.tts_ms,
        "total_ms": report.total_ms,
    }
    stages: list[LatencyStage] = []
    within = True
    for key, label in STAGE_LABELS:
        actual = float(values[key])
        target = float(LATENCY_TARGETS_MS[key])
        status: Literal["pass", "miss", "skipped"]
        if key == "ha_ms" and not ha_ran:
            status = "skipped"
        elif actual > target:
            status = "miss"
            within = False
        else:
            status = "pass"
        stages.append(
            LatencyStage(stage=label, actual_ms=actual, target_ms=target, status=status)
        )
    return LatencyTrace(
        wake_to_listening_ms=report.wake_to_listening_ms,
        stt_ms=report.stt_ms,
        hermes_ms=report.hermes_ms,
        ha_ms=report.ha_ms,
        tts_ms=report.tts_ms,
        total_ms=report.total_ms,
        stages=stages,
        within_targets=within,
    )


def _actual_from_result(result: PipelineResult) -> dict[str, Any]:
    action_payload = None
    if result.action is not None:
        action_payload = {
            "domain": result.action.domain,
            "service": result.action.service,
            "entity": result.action.target_entity,
        }
    return {
        "spoken": result.spoken,
        "error_code": result.error_code,
        "action": action_payload,
        "category": result.category.value if result.category else None,
        "confirmed": result.confirmed,
        "turn_state": result.turn.state.value,
    }


def _expected_from_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        "expected_action": scenario.get("expected_action"),
        "expected_category": scenario.get("expected_category"),
        "expected_error": scenario.get("expected_error"),
        "requires_confirmation": scenario.get("requires_confirmation"),
        "confirmation_response": scenario.get("confirmation_response"),
    }


class ConsoleController:
    """Owns mock pipeline construction and console session state."""

    def __init__(
        self,
        *,
        receipt_path: Path | str | None = None,
        latency_path: Path | str | None = None,
        state_machine: StateMachine | None = None,
        ha_adapter: HomeAssistantAdapter | None = None,
        hermes_adapter: HermesAdapter | None = None,
        devices_path: Path | str | None = None,
    ) -> None:
        root = Path(__file__).resolve().parents[3]
        self._receipt_path = (
            Path(receipt_path) if receipt_path else root / "data" / "receipts.jsonl"
        )
        self._latency_path = (
            Path(latency_path) if latency_path else root / "data" / "benchmarks.jsonl"
        )
        self._devices_path = Path(devices_path) if devices_path else None
        self.state = state_machine or StateMachine()
        self._external_ha = ha_adapter
        self._external_hermes = hermes_adapter
        self._lock = threading.Lock()
        self._busy = False
        self._runs: deque[ConsoleRun] = deque(maxlen=HISTORY_LIMIT)
        self._events: deque[ConsoleEvent] = deque(maxlen=HISTORY_LIMIT)
        self._session_receipts: deque[ActionReceipt] = deque(maxlen=HISTORY_LIMIT)
        self._pending_meta: PendingConfirmationView | None = None
        self._build_pipeline()

    @property
    def ha(self) -> MockHomeAssistant:
        adapter = self.pipeline.ha_adapter
        if not isinstance(adapter, MockHomeAssistant):
            raise TypeError("ConsoleController requires MockHomeAssistant")
        return adapter

    @property
    def pending_confirmation(self) -> PendingConfirmationView | None:
        return self._pending_meta

    def _build_pipeline(self, *, reset_ha: bool = False) -> None:
        if self._external_ha is not None:
            ha: HomeAssistantAdapter = self._external_ha
            if reset_ha and isinstance(ha, MockHomeAssistant):
                ha.reset()
        else:
            ha = MockHomeAssistant(
                self._devices_path,
                latency_ms=0.0,
            )
        hermes: HermesAdapter = self._external_hermes or MockHermes(latency_ms=0.0)
        store = ReceiptStore(self._receipt_path)
        self.pipeline = VoicePipeline(
            ha_adapter=ha,
            hermes_adapter=hermes,
            stt_latency_ms=0.0,
            tts_latency_ms=0.0,
            hermes_latency_ms=0.0,
            ha_latency_ms=0.0,
            receipt_store=store,
            latency_logger=LatencyLogger(self._latency_path),
            conversations=ConversationManager(),
            state=self.state,
        )
        self._external_ha = ha
        self._external_hermes = hermes

    def _acquire(self) -> None:
        if not self._lock.acquire(blocking=False):
            raise ConsoleBusyError("Another console operation is already in progress")
        self._busy = True

    def _release(self) -> None:
        self._busy = False
        self._lock.release()

    def health(self) -> HealthSnapshot:
        return HealthSnapshot()

    def list_scenarios(self) -> list[ScenarioInfo]:
        infos: list[ScenarioInfo] = []
        for scenario in load_scenarios():
            infos.append(
                ScenarioInfo(
                    name=scenario["name"],
                    utterance=scenario.get("utterance"),
                    turns=scenario.get("turns"),
                    expected_action=scenario.get("expected_action"),
                    expected_category=scenario.get("expected_category"),
                    expected_error=scenario.get("expected_error"),
                    requires_confirmation=bool(scenario.get("requires_confirmation")),
                    confirmation_response=scenario.get("confirmation_response"),
                    area_id=scenario["area_id"],
                    device_id=scenario["device_id"],
                    notes=scenario.get("notes"),
                )
            )
        return infos

    def session(self) -> SessionSnapshot:
        return SessionSnapshot(
            status=self.state.status(),
            health=self.health(),
            pending_confirmation=self._pending_meta,
            last_run=self._runs[-1] if self._runs else None,
            recent_runs=list(self._runs),
            recent_events=list(self._events),
            recent_receipts=list(self._session_receipts),
            is_busy=self._busy,
        )

    def _emit(self, kind: str, message: str, *, run_id: UUID | None = None) -> None:
        self._events.append(ConsoleEvent(kind=kind, message=message, run_id=run_id))

    def _sync_session_receipts(self) -> ActionReceipt | None:
        assert self.pipeline.receipt_store is not None
        all_receipts = self.pipeline.receipt_store.all()
        if not all_receipts:
            return None
        known = {r.id for r in self._session_receipts}
        newest: ActionReceipt | None = None
        for receipt in all_receipts:
            if receipt.id not in known:
                self._session_receipts.append(receipt)
                newest = receipt
        return newest

    def _refresh_pending(
        self,
        *,
        result: PipelineResult,
        area_id: str,
        device_id: str,
    ) -> None:
        pending = self.state.status().pending_confirmation
        if pending is None:
            self._pending_meta = None
            return
        prompt = result.spoken if result.action_result is None else None
        self._pending_meta = PendingConfirmationView(
            action=pending,
            spoken_prompt=prompt or result.spoken,
            area_id=area_id,
            device_id=device_id,
            category=pending.category.value if pending.category else None,
        )

    def _record_run(
        self,
        *,
        result: PipelineResult,
        run_type: RunType,
        area_id: str,
        device_id: str,
        utterance: str | None,
        scenario_name: str | None,
        started_at: datetime,
        passed: bool | None,
        expected: dict[str, Any] | None,
        actual: dict[str, Any] | None,
    ) -> ConsoleRun:
        ha_ran = result.action_result is not None or result.error_code == "service_unavailable"
        receipt = self._sync_session_receipts()
        run = ConsoleRun(
            started_at=started_at,
            completed_at=datetime.now(UTC),
            run_type=run_type,
            scenario_name=scenario_name,
            utterance=utterance,
            area_id=area_id,
            voice_device_id=device_id,
            passed=passed,
            expected=expected,
            actual=actual,
            spoken_response=result.spoken,
            error_code=result.error_code,
            action=result.action,
            action_result=result.action_result,
            receipt=receipt,
            latency_trace=build_latency_trace(result.latency, ha_ran=ha_ran),
            final_state=self.state.state.value,
            confirmed=result.confirmed,
        )
        self._runs.append(run)
        self._refresh_pending(result=result, area_id=area_id, device_id=device_id)
        return run

    def run_command(
        self,
        utterance: str,
        *,
        area_id: str,
        device_id: str,
        scenario_name: str | None = None,
        confirmation_response: str | None = None,
        run_type: RunType = RunType.MANUAL,
    ) -> ConsoleRun:
        self._acquire()
        try:
            started = datetime.now(UTC)
            self._emit("run_started", f"Manual command: {utterance}")
            result = self.pipeline.run_utterance(
                utterance,
                area_id=area_id,
                device_id=device_id,
                confirmation_response=confirmation_response,
                scenario_name=scenario_name or "manual",
            )
            run = self._record_run(
                result=result,
                run_type=run_type,
                area_id=area_id,
                device_id=device_id,
                utterance=utterance,
                scenario_name=scenario_name,
                started_at=started,
                passed=None,
                expected=None,
                actual=_actual_from_result(result),
            )
            if self._pending_meta is not None:
                self._emit(
                    "confirmation_requested",
                    "PARKER is waiting for confirmation",
                    run_id=run.run_id,
                )
            elif result.action_result is not None:
                self._emit("action_executed", run.spoken_response, run_id=run.run_id)
            if result.error_code:
                self._emit("error", result.error_code, run_id=run.run_id)
            self._emit("state_changed", self.state.state.value, run_id=run.run_id)
            return run
        finally:
            self._release()

    def _find_scenario(self, scenario_name: str) -> dict[str, Any]:
        for scenario in load_scenarios():
            if scenario["name"] == scenario_name:
                return scenario
        raise ConsoleNotFoundError(f"Unknown scenario: {scenario_name}")

    def run_scenario(
        self,
        scenario_name: str,
        *,
        run_type: RunType = RunType.SCENARIO,
    ) -> ConsoleRun:
        scenario = self._find_scenario(scenario_name)
        self._acquire()
        try:
            started = datetime.now(UTC)
            self._emit("run_started", f"Scenario: {scenario_name}")
            result = run_scenario(self.pipeline, scenario)
            primary = result[-1] if isinstance(result, list) else result
            passed, message = check_scenario_expectations(scenario, result)
            if not passed and message:
                self._emit("run_failed", message)
            else:
                self._emit("run_passed", f"{scenario_name} passed")

            utterance = scenario.get("utterance")
            if utterance is None and scenario.get("turns"):
                turns = [
                    t.get("utterance")
                    for t in scenario["turns"]
                    if isinstance(t, dict) and t.get("utterance")
                ]
                utterance = " → ".join(str(t) for t in turns)

            run = self._record_run(
                result=primary,
                run_type=run_type,
                area_id=scenario["area_id"],
                device_id=scenario["device_id"],
                utterance=utterance,
                scenario_name=scenario_name,
                started_at=started,
                passed=passed,
                expected=_expected_from_scenario(scenario),
                actual=_actual_from_result(primary),
            )
            if not passed and run.error_code is None and message:
                # Keep structured failure visible even when pipeline succeeded
                # but expectations did not match.
                run = run.model_copy(update={"error_code": "expectation_failed"})
                self._runs[-1] = run
            self._emit("state_changed", self.state.state.value, run_id=run.run_id)
            return run
        finally:
            self._release()

    def run_all_scenarios(self) -> SuiteResult:
        scenarios = load_scenarios()
        self._acquire()
        try:
            runs: list[ConsoleRun] = []
            passed = 0
            failed = 0
            for scenario in scenarios:
                # Fresh conversation/device context between suite members
                if isinstance(self.pipeline.ha_adapter, MockHomeAssistant):
                    offline = set(self.pipeline.ha_adapter.offline_entities)
                    self.pipeline.ha_adapter.reset()
                    self.pipeline.ha_adapter.offline_entities = offline
                self.pipeline.conversations.clear()
                self.state.set_pending_confirmation(None)
                self._pending_meta = None

                started = datetime.now(UTC)
                name = scenario["name"]
                self._emit("run_started", f"Suite member: {name}")
                result = run_scenario(self.pipeline, scenario)
                primary = result[-1] if isinstance(result, list) else result
                ok, message = check_scenario_expectations(scenario, result)
                if ok:
                    passed += 1
                    self._emit("run_passed", f"{name} passed")
                else:
                    failed += 1
                    self._emit("run_failed", message or f"{name} failed")

                utterance = scenario.get("utterance")
                if utterance is None and scenario.get("turns"):
                    turns = [
                        t.get("utterance")
                        for t in scenario["turns"]
                        if isinstance(t, dict) and t.get("utterance")
                    ]
                    utterance = " → ".join(str(t) for t in turns)

                run = self._record_run(
                    result=primary,
                    run_type=RunType.SUITE_MEMBER,
                    area_id=scenario["area_id"],
                    device_id=scenario["device_id"],
                    utterance=utterance,
                    scenario_name=name,
                    started_at=started,
                    passed=ok,
                    expected=_expected_from_scenario(scenario),
                    actual=_actual_from_result(primary),
                )
                if not ok and run.error_code is None and message:
                    run = run.model_copy(update={"error_code": "expectation_failed"})
                    self._runs[-1] = run
                runs.append(run)

            summary = SuiteSummary(
                total=len(scenarios),
                passed=passed,
                failed=failed,
            )
            return SuiteResult(summary=summary, runs=runs, session=self.session())
        finally:
            self._release()

    def resolve_confirmation(self, decision: str) -> ConsoleRun:
        decision_norm = decision.strip().lower()
        if decision_norm not in {"confirm", "deny", "cancel"}:
            raise ValueError(f"Invalid confirmation decision: {decision}")
        meta = self._pending_meta
        if meta is None:
            raise ConsoleConfirmationError("No pending confirmation")

        mapping = {
            "confirm": "yes",
            "deny": "no",
            "cancel": "cancel",
        }
        return self.run_command(
            mapping[decision_norm],
            area_id=meta.area_id,
            device_id=meta.device_id,
            scenario_name="confirmation",
        )

    def reset(self) -> SessionSnapshot:
        self._acquire()
        try:
            # Preserve persistent JSONL; rebuild in-memory session only.
            if isinstance(self.pipeline.ha_adapter, MockHomeAssistant):
                self.pipeline.ha_adapter.reset()
            self.pipeline.conversations.clear()
            # Keep the same receipt store path/object; clear only session view.
            assert self.pipeline.receipt_store is not None
            # Drop in-memory receipt cache so session receipts reset, but do not
            # unlink the JSONL file.
            self.pipeline.receipt_store._memory.clear()  # noqa: SLF001
            self.state.reset_session()
            self._runs.clear()
            self._events.clear()
            self._session_receipts.clear()
            self._pending_meta = None
            self._emit("session_reset", "Console session reset")
            return self.session()
        finally:
            self._release()
