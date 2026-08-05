"""Benchmark CLI flag consistency."""

from __future__ import annotations

import subprocess
import sys


def test_benchmark_help_lists_both_flags() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "parker.benchmark.runner", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--realistic" in result.stdout
    assert "--zero-latency" in result.stdout


def test_benchmark_flags_mutually_exclusive() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "parker.benchmark.runner",
            "--realistic",
            "--zero-latency",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "not allowed with" in (result.stderr + result.stdout).lower() or result.returncode == 2


def test_benchmark_rejects_unknown_flag() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "parker.benchmark.runner", "--not-a-flag"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
