"""Shared pytest fixtures for PARKER Voice Lab tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from parker.context.state import StateMachine
from parker.display.console import ConsoleController
from parker.display.server import DisplayServer
from tests.server_helpers import running_display_server


@pytest.fixture
def api_server(tmp_path: Path) -> Iterator[tuple[DisplayServer, int]]:
    state = StateMachine()
    console = ConsoleController(
        receipt_path=tmp_path / "receipts.jsonl",
        latency_path=tmp_path / "benchmarks.jsonl",
        state_machine=state,
    )
    with running_display_server(state_machine=state, console=console) as (
        server,
        port,
        _,
    ):
        yield server, port
