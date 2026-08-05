"""Tiny stdlib HTTP server with SSE for PARKER system status."""

from __future__ import annotations

import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from parker.context.state import StateMachine
from parker.contracts.context import SystemStatus

DISPLAY_DIR = Path(__file__).resolve().parents[3] / "display"


class DisplayServer:
    """Serve display/index.html and stream SystemStatus over SSE."""

    def __init__(
        self,
        state_machine: StateMachine | None = None,
        *,
        host: str = "127.0.0.1",
        port: int = 8787,
    ) -> None:
        self.state_machine = state_machine or StateMachine()
        self.host = host
        self.port = port
        self._clients: list[queue.Queue[str]] = []
        self._lock = threading.Lock()
        self._httpd: ThreadingHTTPServer | None = None
        self.state_machine.on_change(self._broadcast)

    def status(self) -> SystemStatus:
        return self.state_machine.status()

    def _broadcast(self, status: SystemStatus) -> None:
        payload = json.dumps(status.model_dump(mode="json"))
        with self._lock:
            for client_queue in list(self._clients):
                client_queue.put(payload)

    def _register(self) -> queue.Queue[str]:
        client_queue: queue.Queue[str] = queue.Queue()
        with self._lock:
            self._clients.append(client_queue)
        # Immediate snapshot
        client_queue.put(json.dumps(self.status().model_dump(mode="json")))
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
                    self._serve_status()
                else:
                    self.send_error(404)

            def _serve_index(self) -> None:
                html_path = DISPLAY_DIR / "index.html"
                data = html_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _serve_status(self) -> None:
                body = json.dumps(server.status().model_dump(mode="json")).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

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

        return Handler

    def serve_forever(self) -> None:
        handler = self.make_handler()
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        print(f"PARKER display at http://{self.host}:{self.port}")
        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self._httpd.server_close()

    def start_background(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.05)
        return thread


def main() -> None:
    """CLI entry: serve the PARKER state display."""
    from parker.adapters.mock_ha import MockHomeAssistant
    from parker.adapters.mock_hermes import MockHermes
    from parker.simulator.pipeline import VoicePipeline
    from parker.simulator.scenarios import load_scenarios, run_scenario

    state = StateMachine()
    server = DisplayServer(state, port=8787)

    def demo() -> None:
        time.sleep(0.5)
        pipeline = VoicePipeline(
            ha_adapter=MockHomeAssistant(latency_ms=0),
            hermes_adapter=MockHermes(latency_ms=0),
            stt_latency_ms=0,
            tts_latency_ms=0,
            hermes_latency_ms=0,
            ha_latency_ms=0,
            state=state,
        )
        for scenario in load_scenarios():
            run_scenario(pipeline, scenario)
            time.sleep(1.0)

    threading.Thread(target=demo, daemon=True).start()
    server.serve_forever()
