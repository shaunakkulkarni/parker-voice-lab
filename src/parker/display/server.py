"""Tiny stdlib HTTP server with SSE and Test Console JSON API."""

from __future__ import annotations

import argparse
import json
import queue
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from parker.context.state import StateMachine
from parker.contracts.context import SystemStatus
from parker.display.console import (
    ConsoleBusyError,
    ConsoleConfirmationError,
    ConsoleController,
    ConsoleNotFoundError,
)

DISPLAY_DIR = Path(__file__).resolve().parents[3] / "display"
MAX_BODY_BYTES = 64_000
MAX_SSE_QUEUE = 32


class DisplayServer:
    """Serve display/index.html, stream SystemStatus over SSE, and expose console APIs."""

    def __init__(
        self,
        state_machine: StateMachine | None = None,
        *,
        host: str = "127.0.0.1",
        port: int = 8787,
        console: ConsoleController | None = None,
        demo: bool = False,
    ) -> None:
        self.state_machine = state_machine or StateMachine()
        self.host = host
        self.port = port
        self.demo = demo
        self.console = console or ConsoleController(state_machine=self.state_machine)
        # Ensure console and server share the same state machine
        self.state_machine = self.console.state
        self._clients: list[queue.Queue[str]] = []
        self._lock = threading.Lock()
        self._httpd: ThreadingHTTPServer | None = None
        self._demo_stop = threading.Event()
        self.state_machine.on_change(self._broadcast)

    def status(self) -> SystemStatus:
        return self.state_machine.status()

    def _broadcast(self, status: SystemStatus) -> None:
        payload = json.dumps(status.model_dump(mode="json"))
        with self._lock:
            for client_queue in list(self._clients):
                try:
                    client_queue.put_nowait(payload)
                except queue.Full:
                    try:
                        client_queue.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        client_queue.put_nowait(payload)
                    except queue.Full:
                        pass

    def _register(self) -> queue.Queue[str]:
        client_queue: queue.Queue[str] = queue.Queue(maxsize=MAX_SSE_QUEUE)
        with self._lock:
            self._clients.append(client_queue)
        try:
            client_queue.put_nowait(json.dumps(self.status().model_dump(mode="json")))
        except queue.Full:
            pass
        return client_queue

    def _unregister(self, client_queue: queue.Queue[str]) -> None:
        with self._lock:
            if client_queue in self._clients:
                self._clients.remove(client_queue)

    def make_handler(self) -> type[BaseHTTPRequestHandler]:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                return

            def do_GET(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if path in {"/", "/index.html"}:
                    self._serve_index()
                elif path == "/events":
                    self._serve_sse()
                elif path == "/status":
                    self._json_response(200, server.status().model_dump(mode="json"))
                elif path == "/api/health":
                    self._json_response(200, server.console.health().model_dump(mode="json"))
                elif path == "/api/session":
                    self._json_response(200, server.console.session().model_dump(mode="json"))
                elif path == "/api/scenarios":
                    scenarios = [
                        s.model_dump(mode="json") for s in server.console.list_scenarios()
                    ]
                    self._json_response(200, scenarios)
                elif path == "/api/journeys":
                    self._json_response(200, {"journeys": server.console.list_journeys()})
                elif path.startswith("/api/"):
                    self._api_error(404, "not_found", "Unknown route")
                else:
                    self._api_error(404, "not_found", "Unknown route")

            def do_POST(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                try:
                    if path == "/api/run":
                        self._handle_run()
                    elif path == "/api/scenarios/run":
                        self._handle_scenario_run()
                    elif path == "/api/scenarios/run-all":
                        self._handle_run_all()
                    elif path == "/api/confirmation":
                        self._handle_confirmation()
                    elif path == "/api/reset":
                        snapshot = server.console.reset()
                        self._json_response(200, snapshot.model_dump(mode="json"))
                    elif path.startswith("/api/"):
                        self._api_error(405, "method_not_allowed", "Unsupported method")
                    else:
                        self._api_error(404, "not_found", "Unknown route")
                except ConsoleBusyError as exc:
                    self._api_error(409, "busy", str(exc))
                except ConsoleConfirmationError as exc:
                    self._api_error(409, "no_pending_confirmation", str(exc))
                except ConsoleNotFoundError as exc:
                    self._api_error(404, "not_found", str(exc))
                except ValueError as exc:
                    self._api_error(400, "invalid_request", str(exc))
                except Exception:  # noqa: BLE001
                    self._api_error(500, "internal_error", "Unexpected internal error")

            def do_PUT(self) -> None:  # noqa: N802
                self._method_not_allowed()

            def do_DELETE(self) -> None:  # noqa: N802
                self._method_not_allowed()

            def _method_not_allowed(self) -> None:
                path = urlparse(self.path).path
                if path.startswith("/api/") or path in {"/status", "/events"}:
                    self._api_error(405, "method_not_allowed", "Unsupported method")
                else:
                    self._api_error(404, "not_found", "Unknown route")

            def _serve_index(self) -> None:
                html_path = DISPLAY_DIR / "index.html"
                data = html_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _serve_sse(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                client_queue = server._register()
                try:
                    while True:
                        try:
                            payload = client_queue.get(timeout=15.0)
                            self.wfile.write(f"data: {payload}\n\n".encode())
                            self.wfile.flush()
                        except queue.Empty:
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    server._unregister(client_queue)

            def _read_json(self) -> dict[str, Any]:
                length_header = self.headers.get("Content-Length", "0")
                try:
                    length = int(length_header)
                except ValueError as exc:
                    raise ValueError("Invalid Content-Length") from exc
                if length < 0 or length > MAX_BODY_BYTES:
                    raise ValueError("Request body too large or invalid")
                raw = self.rfile.read(length) if length else b"{}"
                if not raw.strip():
                    return {}
                try:
                    data = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValueError("Malformed JSON") from exc
                if not isinstance(data, dict):
                    raise ValueError("JSON body must be an object")
                return data

            def _handle_run(self) -> None:
                data = self._read_json()
                utterance = data.get("utterance")
                area_id = data.get("area_id")
                device_id = data.get("device_id")
                if not isinstance(utterance, str) or not utterance.strip():
                    raise ValueError("utterance is required")
                if not isinstance(area_id, str) or not area_id.strip():
                    raise ValueError("area_id is required")
                if not isinstance(device_id, str) or not device_id.strip():
                    raise ValueError("device_id is required")
                confirmation = data.get("confirmation_response")
                if confirmation is not None and not isinstance(confirmation, str):
                    raise ValueError("confirmation_response must be a string")
                scenario_name = data.get("scenario_name")
                if scenario_name is not None and not isinstance(scenario_name, str):
                    raise ValueError("scenario_name must be a string")
                run = server.console.run_command(
                    utterance.strip(),
                    area_id=area_id.strip(),
                    device_id=device_id.strip(),
                    scenario_name=scenario_name,
                    confirmation_response=confirmation,
                )
                self._json_response(
                    200,
                    {
                        "run": run.model_dump(mode="json"),
                        "session": server.console.session().model_dump(mode="json"),
                    },
                )

            def _handle_scenario_run(self) -> None:
                data = self._read_json()
                name = data.get("scenario_name")
                if not isinstance(name, str) or not name.strip():
                    raise ValueError("scenario_name is required")
                run = server.console.run_scenario(name.strip())
                self._json_response(
                    200,
                    {
                        "run": run.model_dump(mode="json"),
                        "session": server.console.session().model_dump(mode="json"),
                    },
                )

            def _handle_run_all(self) -> None:
                _ = self._read_json()
                result = server.console.run_all_scenarios()
                self._json_response(200, result.model_dump(mode="json"))

            def _handle_confirmation(self) -> None:
                data = self._read_json()
                decision = data.get("decision")
                if not isinstance(decision, str) or not decision.strip():
                    raise ValueError("decision is required")
                run = server.console.resolve_confirmation(decision.strip())
                self._json_response(
                    200,
                    {
                        "run": run.model_dump(mode="json"),
                        "session": server.console.session().model_dump(mode="json"),
                    },
                )

            def _json_response(self, status: int, payload: Any) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _api_error(self, status: int, code: str, message: str) -> None:
                self._json_response(
                    status,
                    {"error": {"code": code, "message": message}},
                )

        return Handler

    def _demo_loop(self) -> None:
        while not self._demo_stop.is_set():
            try:
                self.console.reset()
                self.console.run_all_scenarios()
            except ConsoleBusyError:
                pass
            except Exception:  # noqa: BLE001
                pass
            # Reset between cycles to avoid stale confirmations / unbounded growth
            try:
                self.console.reset()
            except ConsoleBusyError:
                pass
            self._demo_stop.wait(2.0)

    def bind(self) -> int:
        """Bind the listening socket and return the actual port.

        Safe to call before ``serve_forever`` so callers (especially tests) can
        catch bind failures in the foreground thread. When ``port`` is 0, the
        OS assigns an ephemeral port and ``self.port`` is updated.
        """
        if self._httpd is not None:
            return self.port
        handler = self.make_handler()
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self.port = int(self._httpd.server_address[1])
        return self.port

    def serve_forever(self) -> None:
        self.bind()
        assert self._httpd is not None
        mode = "DEMO" if self.demo else "IDLE"
        print(
            f"PARKER Test Console at http://{self.host}:{self.port} "
            f"[{mode}] MOCK MODE — no live device actions"
        )
        demo_thread: threading.Thread | None = None
        if self.demo:
            demo_thread = threading.Thread(target=self._demo_loop, daemon=True)
            demo_thread.start()
        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self._demo_stop.set()
            self._httpd.server_close()

    def start_background(self) -> threading.Thread:
        """Bind, then serve in a daemon thread; wait until /status responds."""
        self.bind()
        thread = threading.Thread(target=self.serve_forever, daemon=True)
        thread.start()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if not thread.is_alive():
                raise RuntimeError("DisplayServer failed to start")
            try:
                with socket.create_connection((self.host, self.port), timeout=0.2) as sock:
                    sock.sendall(
                        b"GET /status HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
                    )
                    data = sock.recv(64)
                    if data.startswith(b"HTTP/1.0 200") or data.startswith(b"HTTP/1.1 200"):
                        return thread
            except OSError:
                pass
            time.sleep(0.01)
        raise TimeoutError("DisplayServer did not become ready before timeout")


def main() -> None:
    """CLI entry: serve the PARKER Test Console."""
    parser = argparse.ArgumentParser(description="PARKER Test Console (mock-only)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8787, help="Bind port (default 8787)")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Opt-in: cycle fixture scenarios with reset between cycles",
    )
    args = parser.parse_args()

    state = StateMachine()
    console = ConsoleController(state_machine=state)
    server = DisplayServer(
        state,
        host=args.host,
        port=args.port,
        console=console,
        demo=args.demo,
    )
    server.serve_forever()
