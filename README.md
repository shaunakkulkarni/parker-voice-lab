# PARKER Voice Lab

Local-first apartment voice assistant software lab. Simulates the full voice pipeline with typed contracts and mock adapters — no real hardware or cloud required.

## Quick start

```bash
uv sync --extra dev
uv run pytest
```

## Commands

| Command | Purpose |
|---------|---------|
| `uv run parker-sim` | Run predefined voice scenarios |
| `uv run parker-display` | Serve the PARKER state display (SSE) |
| `uv run parker-bench` | Run latency benchmarks |

## What this is

- Typed Pydantic contracts for the voice pipeline
- Mock Home Assistant and Hermes adapters
- Conversation context and room awareness
- Action receipts and approval middleware
- End-to-end voice flow simulator
- Local state display prototype

See [CURSOR_CONTEXT.md](CURSOR_CONTEXT.md) for architecture and constraints.
