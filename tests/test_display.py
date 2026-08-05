"""Tests for the PARKER display server."""

import json
import threading
import time
from http.client import HTTPConnection

from parker.context.state import StateMachine
from parker.contracts.context import PARKERState
from parker.display.server import DisplayServer


def test_status_endpoint() -> None:
    state = StateMachine()
    server = DisplayServer(state, host="127.0.0.1", port=18787)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    try:
        state.set_transcript("hello parker")
        state.goto(PARKERState.LISTENING)
        conn = HTTPConnection("127.0.0.1", 18787, timeout=2)
        conn.request("GET", "/status")
        resp = conn.getresponse()
        body = json.loads(resp.read().decode())
        assert resp.status == 200
        assert body["last_transcript"] == "hello parker"
        assert body["state"] == "listening"
        conn.close()

        conn = HTTPConnection("127.0.0.1", 18787, timeout=2)
        conn.request("GET", "/")
        resp = conn.getresponse()
        html = resp.read().decode()
        assert resp.status == 200
        assert "PARKER" in html
        conn.close()
    finally:
        if server._httpd is not None:
            server._httpd.shutdown()
