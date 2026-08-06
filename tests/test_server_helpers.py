"""Regression coverage for ephemeral DisplayServer test helpers."""

from __future__ import annotations

from http.client import HTTPConnection

from tests.server_helpers import running_display_server


def test_ephemeral_port_server_becomes_ready_and_tears_down() -> None:
    with running_display_server() as (server, port, thread):
        assert port > 0
        assert server.port == port
        conn = HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", "/status")
        resp = conn.getresponse()
        assert resp.status == 200
        conn.close()
    assert not thread.is_alive()
