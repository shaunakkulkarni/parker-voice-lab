"""Run scenarios and report latency against targets."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from parker.adapters.mock_ha import MockHomeAssistant
from parker.adapters.mock_hermes import MockHermes
from parker.receipts.store import ReceiptStore
from parker.simulator.latency import LATENCY_TARGETS_MS, LatencyLogger, LatencyReport
from parker.simulator.pipeline import VoicePipeline
from parker.simulator.scenarios import load_scenarios, run_scenario


@dataclass
class BenchmarkSummary:
    reports: list[LatencyReport]

    @property
    def count(self) -> int:
        return len(self.reports)

    @property
    def within_targets(self) -> int:
        return sum(1 for r in self.reports if r.within_targets)

    def print(self) -> None:
        print("PARKER latency benchmark")
        print("Targets (ms):", LATENCY_TARGETS_MS)
        print("-" * 60)
        for report in self.reports:
            report.evaluate()
            flag = "OK" if report.within_targets else "MISS"
            print(
                f"[{flag}] {report.scenario}: "
                f"stt={report.stt_ms:.0f} hermes={report.hermes_ms:.0f} "
                f"ha={report.ha_ms:.0f} tts={report.tts_ms:.0f} "
                f"total={report.total_ms:.0f}"
            )
            for violation in report.violations:
                print(f"       ! {violation}")
        print("-" * 60)
        print(f"{self.within_targets}/{self.count} runs within targets")


class BenchmarkRunner:
    """Execute all scenarios and collect latency reports."""

    def __init__(
        self,
        *,
        stt_latency_ms: float = 900.0,
        tts_latency_ms: float = 350.0,
        hermes_latency_ms: float = 300.0,
        ha_latency_ms: float = 50.0,
        output_path: Path | str | None = None,
        zero_latency: bool = False,
    ) -> None:
        if zero_latency:
            stt_latency_ms = 0.0
            tts_latency_ms = 0.0
            hermes_latency_ms = 0.0
            ha_latency_ms = 0.0
        root = Path(__file__).resolve().parents[3]
        out = Path(output_path) if output_path else root / "data" / "benchmarks.jsonl"
        self.logger = LatencyLogger(out)
        self.pipeline = VoicePipeline(
            ha_adapter=MockHomeAssistant(latency_ms=ha_latency_ms),
            hermes_adapter=MockHermes(latency_ms=hermes_latency_ms),
            stt_latency_ms=stt_latency_ms,
            tts_latency_ms=tts_latency_ms,
            hermes_latency_ms=hermes_latency_ms,
            ha_latency_ms=ha_latency_ms,
            receipt_store=ReceiptStore(root / "data" / "bench-receipts.jsonl"),
            latency_logger=self.logger,
        )

    def run(self) -> BenchmarkSummary:
        reports: list[LatencyReport] = []
        for scenario in load_scenarios():
            result = run_scenario(self.pipeline, scenario)
            if isinstance(result, list):
                for item in result:
                    if item.latency is not None:
                        reports.append(item.latency)
            elif result.latency is not None:
                reports.append(result.latency)
        return BenchmarkSummary(reports=reports)


def main() -> None:
    parser = argparse.ArgumentParser(description="PARKER latency benchmark")
    parser.add_argument(
        "--realistic",
        action="store_true",
        help="Use target-like mock latencies (default is zero for speed)",
    )
    args = parser.parse_args()
    runner = BenchmarkRunner(zero_latency=not args.realistic)
    summary = runner.run()
    summary.print()


if __name__ == "__main__":
    main()
