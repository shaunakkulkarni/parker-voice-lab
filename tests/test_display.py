"""Tests for the PARKER display server."""

import json
from http.client import HTTPConnection

from parker.context.state import StateMachine
from parker.contracts.context import PARKERState
from tests.server_helpers import running_display_server


def test_status_endpoint() -> None:
    state = StateMachine()
    with running_display_server(state_machine=state) as (server, port, _):
        state.set_transcript("hello parker")
        state.goto(PARKERState.LISTENING)
        conn = HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", "/status")
        resp = conn.getresponse()
        body = json.loads(resp.read().decode())
        assert resp.status == 200
        assert body["last_transcript"] == "hello parker"
        assert body["state"] == "listening"
        conn.close()

        conn = HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", "/")
        resp = conn.getresponse()
        html = resp.read().decode()
        assert resp.status == 200
        assert "PARKER" in html
        conn.close()
        assert server.port == port
