"""HTTP/API tests for PARKER Test Console v1."""

from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

import pytest

from parker.context.state import StateMachine
from parker.display.console import ConsoleController
from parker.display.server import DisplayServer
from parker.simulator.scenarios import load_scenarios


@pytest.fixture
def api_server(tmp_path: Path) -> tuple[DisplayServer, int]:
    port = 18790
    state = StateMachine()
    console = ConsoleController(
        receipt_path=tmp_path / "receipts.jsonl",
        latency_path=tmp_path / "benchmarks.jsonl",
        state_machine=state,
    )
    server = DisplayServer(
        state,
        host="127.0.0.1",
        port=port,
        console=console,
        demo=False,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    yield server, port
    if server._httpd is not None:  # noqa: SLF001
        server._httpd.shutdown()


def _request(
    port: int,
    method: str,
    path: str,
    body: dict | None = None,
) -> tuple[int, dict | str]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    payload = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if method == "POST" and body is None:
        payload = b"{}"
        headers = {"Content-Type": "application/json"}
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode()
    conn.close()
    try:
        return resp.status, json.loads(raw)
    except json.JSONDecodeError:
        return resp.status, raw


def test_status_endpoint_compatible(api_server: tuple[DisplayServer, int]) -> None:
    _, port = api_server
    status_code, body = _request(port, "GET", "/status")
    assert status_code == 200
    assert isinstance(body, dict)
    assert "state" in body
    assert "last_transcript" in body
    assert "uptime_seconds" in body


def test_api_health(api_server: tuple[DisplayServer, int]) -> None:
    _, port = api_server
    status_code, body = _request(port, "GET", "/api/health")
    assert status_code == 200
    assert isinstance(body, dict)
    assert body["mode"] == "mock"
    assert body["live_device_actions"] is False
    assert body["voice_preview_edition"] == "not_connected"


def test_api_session(api_server: tuple[DisplayServer, int]) -> None:
    _, port = api_server
    status_code, body = _request(port, "GET", "/api/session")
    assert status_code == 200
    assert isinstance(body, dict)
    assert "status" in body
    assert "health" in body
    assert "recent_runs" in body
    assert body["is_busy"] is False


def test_api_scenarios(api_server: tuple[DisplayServer, int]) -> None:
    _, port = api_server
    status_code, body = _request(port, "GET", "/api/scenarios")
    assert status_code == 200
    assert isinstance(body, list)
    assert len(body) == len(load_scenarios())
    assert body[0]["name"]


def test_api_run_valid(api_server: tuple[DisplayServer, int]) -> None:
    _, port = api_server
    status_code, body = _request(
        port,
        "POST",
        "/api/run",
        {
            "utterance": "Turn on the living room light",
            "area_id": "living_room",
            "device_id": "voice_pe_living_room",
        },
    )
    assert status_code == 200
    assert isinstance(body, dict)
    assert body["run"]["passed"] is None
    assert body["run"]["run_type"] == "manual"
    assert body["session"]["last_run"]["utterance"] == "Turn on the living room light"


def test_api_malformed_json(api_server: tuple[DisplayServer, int]) -> None:
    _, port = api_server
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(
        "POST",
        "/api/run",
        body=b"{not-json",
        headers={"Content-Type": "application/json"},
    )
    resp = conn.getresponse()
    raw = resp.read().decode()
    conn.close()
    assert resp.status == 400
    body = json.loads(raw)
    assert body["error"]["code"] == "invalid_request"
    assert "Traceback" not in raw


def test_api_missing_utterance(api_server: tuple[DisplayServer, int]) -> None:
    _, port = api_server
    status_code, body = _request(
        port,
        "POST",
        "/api/run",
        {"area_id": "living_room", "device_id": "voice_pe_living_room"},
    )
    assert status_code == 400
    assert isinstance(body, dict)
    assert body["error"]["code"] == "invalid_request"
    assert "utterance" in body["error"]["message"].lower()


def test_api_unknown_scenario(api_server: tuple[DisplayServer, int]) -> None:
    _, port = api_server
    status_code, body = _request(
        port,
        "POST",
        "/api/scenarios/run",
        {"scenario_name": "Does not exist"},
    )
    assert status_code == 404
    assert isinstance(body, dict)
    assert body["error"]["code"] == "not_found"


def test_api_confirmation_confirm_deny_cancel(
    api_server: tuple[DisplayServer, int],
) -> None:
    _, port = api_server

    def unlock() -> None:
        _request(
            port,
            "POST",
            "/api/run",
            {
                "utterance": "Unlock the front door",
                "area_id": "hallway",
                "device_id": "voice_pe_living_room",
            },
        )

    unlock()
    status_code, body = _request(
        port, "POST", "/api/confirmation", {"decision": "confirm"}
    )
    assert status_code == 200
    assert isinstance(body, dict)
    assert body["session"]["pending_confirmation"] is None

    unlock()
    status_code, body = _request(
        port, "POST", "/api/confirmation", {"decision": "deny"}
    )
    assert status_code == 200

    unlock()
    status_code, body = _request(
        port, "POST", "/api/confirmation", {"decision": "cancel"}
    )
    assert status_code == 200

    status_code, body = _request(
        port, "POST", "/api/confirmation", {"decision": "confirm"}
    )
    assert status_code == 409
    assert isinstance(body, dict)
    assert body["error"]["code"] == "no_pending_confirmation"


def test_api_reset(api_server: tuple[DisplayServer, int]) -> None:
    _, port = api_server
    _request(
        port,
        "POST",
        "/api/run",
        {
            "utterance": "What's the temperature?",
            "area_id": "living_room",
            "device_id": "voice_pe_living_room",
        },
    )
    status_code, body = _request(port, "POST", "/api/reset")
    assert status_code == 200
    assert isinstance(body, dict)
    assert body["recent_runs"] == []
    assert body["status"]["state"] == "idle"


def test_api_run_all(api_server: tuple[DisplayServer, int]) -> None:
    _, port = api_server
    status_code, body = _request(port, "POST", "/api/scenarios/run-all", {})
    assert status_code == 200
    assert isinstance(body, dict)
    assert body["summary"]["total"] == len(load_scenarios())
    assert body["summary"]["passed"] == body["summary"]["total"]
    assert len(body["runs"]) == body["summary"]["total"]


def test_unsupported_method(api_server: tuple[DisplayServer, int]) -> None:
    _, port = api_server
    status_code, body = _request(port, "POST", "/api/health", {})
    assert status_code == 405
    assert isinstance(body, dict)
    assert body["error"]["code"] == "method_not_allowed"


def test_unknown_route(api_server: tuple[DisplayServer, int]) -> None:
    _, port = api_server
    status_code, body = _request(port, "GET", "/api/nope")
    assert status_code == 404
    assert isinstance(body, dict)
    assert body["error"]["code"] == "not_found"


def test_no_traceback_in_errors(api_server: tuple[DisplayServer, int]) -> None:
    _, port = api_server
    status_code, body = _request(port, "POST", "/api/run", {"utterance": "x"})
    assert status_code == 400
    assert isinstance(body, dict)
    assert "traceback" not in json.dumps(body).lower()
    assert "Traceback" not in json.dumps(body)


def test_browser_smoke_sequence(api_server: tuple[DisplayServer, int]) -> None:
    """Smoke the console flow the browser UI exercises."""
    _, port = api_server

    status_code, html = _request(port, "GET", "/")
    assert status_code == 200
    assert isinstance(html, str)
    assert 'id="command-form"' in html

    status_code, body = _request(
        port,
        "POST",
        "/api/run",
        {
            "utterance": "Turn on the living room light",
            "area_id": "living_room",
            "device_id": "voice_pe_living_room",
        },
    )
    assert status_code == 200
    assert isinstance(body, dict)
    assert body["run"]["passed"] is None

    status_code, body = _request(
        port,
        "POST",
        "/api/run",
        {
            "utterance": "Lock the front door",
            "area_id": "hallway",
            "device_id": "voice_pe_living_room",
        },
    )
    assert status_code == 200
    assert isinstance(body, dict)
    assert body["session"]["pending_confirmation"] is not None

    status_code, body = _request(
        port, "POST", "/api/confirmation", {"decision": "confirm"}
    )
    assert status_code == 200
    assert isinstance(body, dict)
    assert body["session"]["pending_confirmation"] is None
    assert body["run"]["action_result"]["success"] is True

    status_code, body = _request(port, "POST", "/api/reset")
    assert status_code == 200
    assert isinstance(body, dict)
    assert body["recent_runs"] == []

    status_code, body = _request(port, "POST", "/api/scenarios/run-all", {})
    assert status_code == 200
    assert isinstance(body, dict)
    assert body["summary"]["total"] == len(load_scenarios())
    assert body["summary"]["failed"] == 0
