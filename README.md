# PARKER Voice Lab

Local-first apartment voice assistant software lab. Simulates the full voice pipeline with typed contracts and mock adapters — no real hardware or cloud required.

## Test Console v1

The browser **Test Console** is an active, mock-only development instrument. It can:

- Submit manual mock voice commands
- Run individual fixture scenarios or the full suite
- Show PASS / FAIL / MANUAL results
- Display latency traces and action receipts
- Resolve confirm / deny / cancel for consequential actions
- Reset the active session without deleting persistent JSONL receipt history
- Report mock adapter health

The console **cannot** control real apartment devices. All actions target `MockHomeAssistant` only.

### What is mocked

- Home Assistant (`MockHomeAssistant`)
- Hermes reasoning (`MockHermes`)
- Speech-to-text and text-to-speech (simulated latencies)
- Voice Preview Edition hardware (`not_connected`)

### What is deliberately not connected

- Live Home Assistant
- Real Hermes
- Whisper / Piper network clients
- Voice Preview Edition hardware
- HomePods / AirPlay
- Cloud APIs, secrets, MQTT, or external exposure by default

## Install

```bash
uv sync --extra dev
```

## Run tests

```bash
uv run --extra dev pytest
```

## Start the Test Console

Idle-by-default (safe; no automatic scenario cycling):

```bash
uv run parker-display
```

Open [http://127.0.0.1:8787](http://127.0.0.1:8787).

Expose on the LAN (still mock-only — do not treat this as a production service):

```bash
uv run parker-display --host 0.0.0.0 --port 9090
```

Opt-in demo mode (cycles fixture scenarios and resets between cycles):

```bash
uv run parker-display --demo
```

### Using the console

1. **Manual commands** — enter an utterance, choose room/device, submit. Quick-command buttons fill common phrases. Manual runs show result label `MANUAL` (no fixture expectation).
2. **Scenarios** — run one fixture scenario from the table, or **Run all scenarios**. Results show `PASS` / `FAIL`.
3. **Confirmation** — consequential actions (for example locking/unlocking the door) pause with Confirm / Deny / Cancel. The mock service is not called until Confirm.
4. **Reset session** — clears pending confirmation, run/event history, conversation state, and mock device state back to fixture defaults. Persistent JSONL receipts under `data/` are **not** deleted.

## Benchmarks

Default is zero-latency for deterministic speed:

```bash
uv run parker-bench
uv run parker-bench --zero-latency
```

Target-like mock latencies:

```bash
uv run parker-bench --realistic
```

`--realistic` and `--zero-latency` are mutually exclusive.

## Other commands

| Command | Purpose |
|---------|---------|
| `uv run parker-sim` | Run predefined voice scenarios in the terminal |
| `uv run parker-display` | Serve the Test Console (SSE + JSON API) |
| `uv run parker-bench` | Run latency benchmarks |

## Project contents

- Typed Pydantic contracts for the voice pipeline
- Mock Home Assistant and Hermes adapters
- Conversation context and room awareness
- Action receipts and approval middleware
- End-to-end voice flow simulator
- Browser Test Console (vanilla HTML/CSS/JS)

See [CURSOR_CONTEXT.md](CURSOR_CONTEXT.md) for architecture and constraints.
