"""Shared helpers for starting DisplayServer on ephemeral ports in tests."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPConnection

from parker.context.state import StateMachine
from parker.display.console import ConsoleController
from parker.display.server import DisplayServer

READY_TIMEOUT_S = 2.0
POLL_INTERVAL_S = 0.01
JOIN_TIMEOUT_S = 2.0


def wait_until_server_ready(
    server: DisplayServer,
    thread: threading.Thread,
    *,
    timeout: float = READY_TIMEOUT_S,
) -> int:
    """Poll until HTTP /status succeeds; return the bound port."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not thread.is_alive() and server._httpd is None:  # noqa: SLF001
            raise RuntimeError("DisplayServer thread exited before becoming ready")
        httpd = server._httpd  # noqa: SLF001
        if httpd is not None:
            host, port = httpd.server_address[:2]
            if not isinstance(port, int):
                raise TypeError(f"Unexpected server port type: {type(port)!r}")
            try:
                conn = HTTPConnection(host, port, timeout=0.2)
                conn.request("GET", "/status")
                resp = conn.getresponse()
                resp.read()
                conn.close()
                if resp.status == 200:
                    return port
            except OSError:
                pass
        time.sleep(POLL_INTERVAL_S)
    raise TimeoutError(f"DisplayServer did not become ready within {timeout:.1f}s")


@contextmanager
def running_display_server(
    *,
    state_machine: StateMachine | None = None,
    console: ConsoleController | None = None,
    demo: bool = False,
    host: str = "127.0.0.1",
) -> Iterator[tuple[DisplayServer, int, threading.Thread]]:
    """Start DisplayServer on an ephemeral port with reliable teardown.

    Binding happens in the caller thread so address conflicts raise here instead
    of as unhandled exceptions inside a daemon thread.
    """
    state = state_machine or StateMachine()
    server = DisplayServer(
        state,
        host=host,
        port=0,
        console=console,
        demo=demo,
    )
    server.bind()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = wait_until_server_ready(server, thread)
        yield server, port, thread
    finally:
        if server._httpd is not None:  # noqa: SLF001
            server._httpd.shutdown()
        thread.join(timeout=JOIN_TIMEOUT_S)
        if thread.is_alive():
            raise RuntimeError("DisplayServer thread did not stop after shutdown")
