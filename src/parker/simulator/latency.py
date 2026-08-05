"""Latency measurement and reporting."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LATENCY_TARGETS_MS: dict[str, float] = {
    "wake_to_listening_ms": 500,
    "stt_ms": 1500,
    "hermes_ms": 500,
    "ha_ms": 200,
    "tts_ms": 500,
    "total_ms": 3000,
}


@dataclass
class LatencyReport:
    """Per-stage latency for a pipeline run."""

    scenario: str
    wake_to_listening_ms: float = 0.0
    stt_ms: float = 0.0
    hermes_ms: float = 0.0
    ha_ms: float = 0.0
    tts_ms: float = 0.0
    total_ms: float = 0.0
    within_targets: bool = True
    violations: list[str] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )

    def evaluate(self) -> None:
        self.violations = []
        mapping = {
            "wake_to_listening_ms": self.wake_to_listening_ms,
            "stt_ms": self.stt_ms,
            "hermes_ms": self.hermes_ms,
            "ha_ms": self.ha_ms,
            "tts_ms": self.tts_ms,
            "total_ms": self.total_ms,
        }
        for key, target in LATENCY_TARGETS_MS.items():
            value = mapping[key]
            if value > target:
                self.violations.append(f"{key}: {value:.1f}ms > {target:.1f}ms")
        self.within_targets = len(self.violations) == 0

    def to_dict(self) -> dict[str, Any]:
        self.evaluate()
        return asdict(self)


class LatencyLogger:
    """Append latency reports to JSONL."""

    def __init__(self, path: Path | str | None = None) -> None:
        root = Path(__file__).resolve().parents[3]
        self.path = Path(path) if path else root / "data" / "benchmarks.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, report: LatencyReport) -> None:
        report.evaluate()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(report.to_dict()) + "\n")
