"""Static UI coverage for PARKER Test Console v1."""

from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path

from parker.context.state import StateMachine
from parker.display.console import ConsoleController
from tests.server_helpers import running_display_server

DISPLAY_HTML = Path(__file__).resolve().parents[1] / "display" / "index.html"


def test_html_contains_console_controls() -> None:
    html = DISPLAY_HTML.read_text(encoding="utf-8")
    assert "TEST CONSOLE" in html.upper() or "Test Console" in html
    assert "MOCK MODE" in html.upper()
    assert "NO LIVE DEVICE ACTIONS" in html.upper()
    assert 'id="command-form"' in html
    assert 'id="utterance"' in html
    assert 'for="utterance"' in html
    assert 'id="area_id"' in html
    assert 'id="device_id"' in html
    assert 'id="run-all"' in html
    assert 'id="reset-session"' in html
    assert 'id="confirm-btn"' in html
    assert 'id="deny-btn"' in html
    assert 'id="cancel-btn"' in html
    assert 'id="health-panel"' in html
    assert 'id="pipeline-trace"' in html
    assert 'id="action-receipt"' in html
    assert 'id="event-log"' in html
    assert 'id="scenario-runner"' in html
    assert "Turn on the living room light" in html
    assert "What's the temperature?" in html
    assert "Lock the front door" in html
    assert "Turn on the garage light" in html


def test_js_can_parse_session_payload_shape(tmp_path: Path) -> None:
    """Ensure session JSON shape matches what the UI expects."""
    controller = ConsoleController(receipt_path=tmp_path / "receipts.jsonl")
    run = controller.run_command(
        "Turn on the living room light",
        area_id="living_room",
        device_id="voice_pe_living_room",
    )
    session = controller.session().model_dump(mode="json")
    raw = json.dumps(session)
    parsed = json.loads(raw)
    assert parsed["last_run"]["run_id"] == str(run.run_id)
    assert parsed["last_run"]["passed"] is None
    assert parsed["health"]["mode"] == "mock"
    assert "stages" in parsed["last_run"]["latency_trace"]
    assert isinstance(parsed["recent_events"], list)


def test_served_html_includes_console_markup() -> None:
    state = StateMachine()
    console = ConsoleController(state_machine=state)
    with running_display_server(state_machine=state, console=console) as (_, port, _):
        conn = HTTPConnection("127.0.0.1", port, timeout=3)
        conn.request("GET", "/")
        resp = conn.getresponse()
        html = resp.read().decode()
        conn.close()
        assert resp.status == 200
        assert 'id="command-form"' in html
        assert 'id="run-all"' in html
        assert "No action receipt in this session." in html
