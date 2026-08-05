# PARKER Voice Lab — Build Context for Cursor

This document defines what to build, what to avoid, and the technical constraints for the PARKER Voice Lab project. Read this in full before generating any code.

---

## What is PARKER

PARKER is a local-first apartment voice assistant. Think JARVIS, but for a real apartment with real constraints:

- **Mac Mini** runs the infrastructure (Docker, Homebridge, Home Assistant, Hermes/PARKER AI).
- **Home Assistant Voice Preview Edition** is a dedicated physical voice satellite arriving soon.
- **Hermes** is the reasoning/orchestration AI backend (like ChatGPT but self-hosted, with tools, memory, and multi-agent delegation).
- **Whisper** handles local speech-to-text.
- **Piper** handles local text-to-speech.
- **HomePods** provide room audio output via AirPlay.

The physical hardware has not arrived yet. This project builds the software layer that will connect to it.

## What this project IS

A **local-only, hardware-independent software project** that:

1. Defines typed contracts for the voice pipeline.
2. Simulates the entire voice flow with mocks.
3. Builds the Hermes ↔ Home Assistant adapter.
4. Implements conversation context and room awareness.
5. Adds action receipts and approval middleware.
6. Benchmarks STT/TTS latency.
7. Prototypes a PARKER state display.

The project runs entirely on a laptop (M5 Pro MacBook Pro) with no external dependencies, no cloud services, no real hardware, and no secrets.

## What this project is NOT

- NOT a Home Assistant integration or plugin.
- NOT a modification to Hermes internals.
- NOT a smart home controller (Home Assistant handles devices).
- NOT a wake-word trainer.
- NOT a mobile app.
- NOT a cloud-connected service.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  PARKER Voice Lab                    │
│                  (this project)                      │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────────┐   │
│  │ Voice    │──▶│ Hermes   │──▶│ Action       │   │
│  │ Input    │   │ Bridge   │   │ Executor     │   │
│  └──────────┘   └──────────┘   └──────────────┘   │
│       │              │                │             │
│       ▼              ▼                ▼             │
│  ┌──────────┐   ┌──────────┐   ┌──────────────┐   │
│  │ STT      │   │ Context  │   │ Receipts &   │   │
│  │ Engine   │   │ Engine   │   │ Approvals    │   │
│  └──────────┘   └──────────┘   └──────────────┘   │
│       │                                             │
│       ▼                                             │
│  ┌──────────┐                                       │
│  │ TTS      │                                       │
│  │ Engine   │                                       │
│  └──────────┘                                       │
│                                                     │
├─────────────────────────────────────────────────────┤
│  Adapters:                                          │
│  ┌──────────────┐  ┌──────────────────────────┐    │
│  │ Mock HA      │  │ Real HA (later)           │    │
│  │ (tests/sim)  │  │ http://192.168.1.171:8123 │    │
│  └──────────────┘  └──────────────────────────┘    │
│  ┌──────────────┐  ┌──────────────────────────┐    │
│  │ Mock Hermes  │  │ Real Hermes (later)       │    │
│  │ (tests/sim)  │  │ via Hermes gateway        │    │
│  └──────────────┘  └──────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

### Component responsibilities

| Component | Responsibility | Real-world counterpart |
|-----------|---------------|----------------------|
| Voice Input | Receive audio/text, detect wake word | Home Assistant Voice Preview Edition |
| STT Engine | Transcribe speech to text | Whisper (rhasspy/wyoming-whisper) |
| Hermes Bridge | Route user intent to Hermes for reasoning | Hermes gateway + REST adapter |
| Context Engine | Track room, conversation, device context | Custom logic in PARKER |
| Action Executor | Call Home Assistant services | Home Assistant REST API |
| Receipts & Approvals | Log actions, require confirmation for dangerous ones | Custom middleware |
| TTS Engine | Synthesize speech from text | Piper (rhasspy/wyoming-piper) |
| Mock HA | Fake Home Assistant for testing | In-memory entity store |
| Mock Hermes | Fake Hermes for testing | Deterministic response generator |

---

## File Structure

```
parker-voice-lab/
├── CURSOR_CONTEXT.md           # This file
├── README.md                   # Project overview
├── pyproject.toml              # Python project config (use uv or poetry)
├── src/
│   ├── parker/
│   │   ├── __init__.py
│   │   ├── contracts/          # Typed schemas (the most important module)
│   │   │   ├── __init__.py
│   │   │   ├── voice.py        # VoiceTurn, Transcript, WakeEvent
│   │   │   ├── actions.py      # ActionRequest, ActionResult, ActionReceipt
│   │   │   ├── context.py      # ConversationContext, RoomContext, DeviceState
│   │   │   └── errors.py       # Typed error hierarchy
│   │   ├── adapters/
│   │   │   ├── __init__.py
│   │   │   ├── base.py         # Abstract adapter interfaces
│   │   │   ├── mock_ha.py      # Mock Home Assistant adapter
│   │   │   ├── mock_hermes.py  # Mock Hermes adapter
│   │   │   ├── home_assistant.py  # Real HA adapter (stub until HA is ready)
│   │   │   └── hermes.py       # Real Hermes adapter (stub until ready)
│   │   ├── context/
│   │   │   ├── __init__.py
│   │   │   ├── conversation.py # Conversation history and follow-ups
│   │   │   ├── room.py         # Room/device resolution
│   │   │   └── state.py        # PARKER state machine
│   │   ├── receipts/
│   │   │   ├── __init__.py
│   │   │   ├── store.py        # Receipt storage (SQLite or JSON)
│   │   │   └── approval.py     # Approval middleware
│   │   ├── simulator/
│   │   │   ├── __init__.py
│   │   │   ├── pipeline.py     # Full voice-flow simulator
│   │   │   ├── scenarios.py    # Predefined test scenarios
│   │   │   └── latency.py      # Latency measurement
│   │   ├── benchmark/
│   │   │   ├── __init__.py
│   │   │   └── runner.py       # Whisper/Piper benchmark harness
│   │   └── display/
│   │       ├── __init__.py
│   │       └── server.py       # Local web UI for PARKER state
├── tests/
│   ├── __init__.py
│   ├── test_contracts.py       # Schema validation tests
│   ├── test_mock_ha.py         # Mock HA adapter tests
│   ├── test_mock_hermes.py     # Mock Hermes adapter tests
│   ├── test_context.py         # Context engine tests
│   ├── test_receipts.py        # Receipt and approval tests
│   ├── test_simulator.py       # Full pipeline simulation tests
│   └── test_integration.py     # End-to-end mock integration tests
├── fixtures/
│   ├── scenarios.json          # Predefined conversation scenarios
│   ├── devices.json            # Mock device/room definitions
│   └── responses.json          # Mock Hermes responses
└── display/
    └── index.html              # PARKER state display prototype
```

---

## Contracts (the most important module)

Everything flows through typed contracts. No dictionaries, no raw JSON strings, no `Any` types. Use Pydantic v2 for all schemas.

### Voice contracts (`contracts/voice.py`)

```python
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
from uuid import UUID, uuid4

class WakeWordSource(str, Enum):
    NABU = "nabu"           # Built-in "Okay Nabu"
    CUSTOM = "custom"       # Future "Hey PARKER"
    MANUAL = "manual"       # Text input (no wake word)

class WakeEvent(BaseModel):
    """A wake-word detection event."""
    id: UUID = Field(default_factory=uuid4)
    source: WakeWordSource
    confidence: float = Field(ge=0.0, le=1.0)
    device_id: str
    area_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class Transcript(BaseModel):
    """The result of speech-to-text processing."""
    id: UUID = Field(default_factory=uuid4)
    wake_event_id: UUID
    text: str
    language: str = "en"
    confidence: float = Field(ge=0.0, le=1.0)
    processing_time_ms: float
    engine: str  # e.g. "whisper-base", "whisper-small", "mock"

class VoiceTurnState(str, Enum):
    WAKE_DETECTED = "wake_detected"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    CONFIRMING = "confirming"
    ACTING = "acting"
    SPEAKING = "speaking"
    COMPLETE = "complete"
    ERROR = "error"

class VoiceTurn(BaseModel):
    """A complete voice interaction from wake to response."""
    id: UUID = Field(default_factory=uuid4)
    wake_event: WakeEvent
    transcript: Transcript | None = None
    state: VoiceTurnState = VoiceTurnState.WAKE_DETECTED
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    error: str | None = None

    # Timing breakdown (milliseconds)
    wake_to_transcript_ms: float | None = None
    transcript_to_action_ms: float | None = None
    action_to_speech_ms: float | None = None
    total_ms: float | None = None
```

### Action contracts (`contracts/actions.py`)

```python
class ActionCategory(str, Enum):
    READ = "read"               # Safe: read temperature, check time
    ROUTINE = "routine"         # Normal: turn on light, play music
    CONSEQUENTIAL = "consequential"  # Needs confirmation: unlock door, change thermostat significantly
    IRREVERSIBLE = "irreversible"    # Dangerous: delete, purchase, send, publish

class ActionRequest(BaseModel):
    """A request to execute a Home Assistant action."""
    id: UUID = Field(default_factory=uuid4)
    voice_turn_id: UUID
    domain: str                 # e.g. "light", "climate", "media_player"
    service: str                # e.g. "turn_on", "turn_off", "set_temperature"
    target_entity: str | None = None  # e.g. "light.living_room"
    target_area: str | None = None    # e.g. "living_room"
    parameters: dict = {}
    category: ActionCategory
    requires_confirmation: bool = False
    conversation_id: UUID
    requested_at: datetime = Field(default_factory=datetime.utcnow)

class ActionResult(BaseModel):
    """The result of executing an action."""
    id: UUID = Field(default_factory=uuid4)
    action_request_id: UUID
    success: bool
    new_state: dict | None = None  # Entity state after action
    error: str | None = None
    error_code: str | None = None
    executed_at: datetime = Field(default_factory=datetime.utcnow)

class ActionReceipt(BaseModel):
    """A complete audit trail for an action."""
    id: UUID = Field(default_factory=uuid4)
    trigger: str                # What caused this action
    authority: str              # Who/what authorized it
    action_request: ActionRequest
    action_result: ActionResult | None = None
    confirmed: bool = False
    confirmation_method: str | None = None  # "voice", "auto", "display"
    rollback_info: str | None = None
```

### Context contracts (`contracts/context.py`)

```python
class DeviceState(BaseModel):
    """Current state of a Home Assistant entity."""
    entity_id: str              # e.g. "light.living_room"
    domain: str                 # e.g. "light"
    friendly_name: str          # e.g. "Living Room Light"
    state: str                  # e.g. "on", "off", "22.5"
    attributes: dict = {}
    area_id: str | None = None
    last_changed: datetime | None = None

class RoomContext(BaseModel):
    """Context for a specific room/area."""
    area_id: str
    area_name: str
    devices: list[DeviceState] = []
    voice_device_id: str | None = None  # The Voice PE in this room
    last_activity: datetime | None = None

class ConversationContext(BaseModel):
    """Tracks the state of an ongoing conversation."""
    id: UUID = Field(default_factory=uuid4)
    area_id: str
    voice_device_id: str
    turns: list[VoiceTurn] = []
    last_action: ActionRequest | None = None
    pending_confirmation: ActionRequest | None = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    expires_after_seconds: int = 120  # Context expires after 2 minutes of silence

    @property
    def is_expired(self) -> bool:
        return (datetime.utcnow() - self.last_active).total_seconds() > self.expires_after_seconds

class PARKERState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    CONFIRMING = "confirming"
    ACTING = "acting"
    SPEAKING = "speaking"
    ERROR = "error"

class SystemStatus(BaseModel):
    """Overall PARKER system status for the display."""
    state: PARKERState = PARKERState.IDLE
    current_room: str | None = None
    current_device: str | None = None
    last_transcript: str | None = None
    last_response: str | None = None
    last_action: ActionRequest | None = None
    pending_confirmation: ActionRequest | None = None
    active_conversations: int = 0
    uptime_seconds: float = 0
    errors: list[str] = []
```

### Error contracts (`contracts/errors.py`)

```python
class PARKERError(Exception):
    """Base error for PARKER."""
    code: str
    message: str
    recoverable: bool = True

class DeviceNotFoundError(PARKERError):
    code = "device_not_found"
    message = "The requested device could not be found."

class AmbiguousDeviceError(PARKERError):
    code = "ambiguous_device"
    message = "Multiple devices match the request. Please specify."

class ConfirmationRequiredError(PARKERError):
    code = "confirmation_required"
    message = "This action requires explicit confirmation."
    recoverable = True

class ActionExecutionError(PARKERError):
    code = "action_failed"
    message = "The action failed to execute."

class TranscriptionError(PARKERError):
    code = "transcription_failed"
    message = "Speech transcription failed."

class ContextExpiredError(PARKERError):
    code = "context_expired"
    message = "The conversation context has expired."
```

---

## Mock Home Assistant Adapter

The mock adapter simulates Home Assistant's REST API. It should:

1. Store entities in memory with predefined states.
2. Support `GET /api/states/<entity_id>`.
3. Support `POST /api/services/<domain>/<service>`.
4. Support `GET /api/states` (list all).
5. Track service calls for test assertions.
6. Return realistic state changes (light turns on → state becomes "on").
7. Simulate latency (configurable, default 50ms).
8. Support error injection (device offline, service unavailable).

Pre-populate with these mock devices:

```json
{
  "devices": [
    {
      "entity_id": "light.living_room",
      "friendly_name": "Living Room Light",
      "area_id": "living_room",
      "state": "off",
      "attributes": {"brightness": 0, "color_temp": 4000}
    },
    {
      "entity_id": "light.bedroom",
      "friendly_name": "Bedroom Light",
      "area_id": "bedroom",
      "state": "off",
      "attributes": {"brightness": 0, "color_temp": 4000}
    },
    {
      "entity_id": "light.kitchen",
      "friendly_name": "Kitchen Light",
      "area_id": "kitchen",
      "state": "on",
      "attributes": {"brightness": 200, "color_temp": 3500}
    },
    {
      "entity_id": "climate.living_room",
      "friendly_name": "Living Room Thermostat",
      "area_id": "living_room",
      "state": "heating",
      "attributes": {"temperature": 22.0, "current_temperature": 21.5, "hvac_mode": "heat"}
    },
    {
      "entity_id": "media_player.living_room_homepod",
      "friendly_name": "Living Room HomePod",
      "area_id": "living_room",
      "state": "idle",
      "attributes": {"volume_level": 0.4, "media_title": null}
    },
    {
      "entity_id": "lock.front_door",
      "friendly_name": "Front Door Lock",
      "area_id": "hallway",
      "state": "locked",
      "attributes": {}
    },
    {
      "entity_id": "switch.coffee_maker",
      "friendly_name": "Coffee Maker",
      "area_id": "kitchen",
      "state": "off",
      "attributes": {}
    }
  ],
  "areas": [
    {"area_id": "living_room", "name": "Living Room"},
    {"area_id": "bedroom", "name": "Bedroom"},
    {"area_id": "kitchen", "name": "Kitchen"},
    {"area_id": "hallway", "name": "Hallway"}
  ],
  "voice_devices": [
    {
      "device_id": "voice_pe_living_room",
      "name": "Living Room Voice PE",
      "area_id": "living_room",
      "wake_word": "okay_nabu"
    }
  ]
}
```

---

## Mock Hermes Adapter

The mock Hermes simulates the reasoning layer. It should:

1. Accept a user utterance and conversation context.
2. Return a structured response with:
   - What the user wants
   - The action to take (if any)
   - The spoken response
   - Whether confirmation is needed
3. Support configurable latency (default 300ms).
4. Support error injection.
5. Handle these patterns:

| User says | Expected action |
|-----------|----------------|
| "Turn on the living room light" | `light.turn_on` on `light.living_room` |
| "Turn off the kitchen light" | `light.turn_off` on `light.kitchen` |
| "What's the temperature?" | `climate.living_room` read (context-dependent) |
| "Set the thermostat to 24" | `climate.set_temperature` with `{temperature: 24}` |
| "Lock the front door" | `lock.lock` on `lock.front_door` — **confirmation required** |
| "What time is it?" | No action, spoken response only |
| "Play some music" | `media_player.play_media` on HomePod |
| "Cancel that" | Cancel pending action |
| "And tomorrow?" | Follow-up using conversation context |
| "Turn on the light" | Ambiguous — ask which room |

The mock should use simple pattern matching, not an LLM. Real Hermes integration comes later.

---

## Context Engine

### Conversation context

- Track the current conversation per voice device.
- A conversation starts on wake-word detection.
- A conversation expires after 120 seconds of silence.
- Follow-up questions ("and tomorrow?") reuse the current conversation.
- Different voice devices have independent conversations.

### Room context

- Each voice device belongs to a room (area).
- "Turn on the light" resolves to the light in the current room.
- "What's the temperature?" reads the thermostat in the current room.
- Cross-room commands require explicit room names.

### State machine

```
IDLE
  ↓ (wake word detected)
LISTENING
  ↓ (audio captured / text input received)
TRANSCRIBING
  ↓ (text available)
THINKING
  ↓ (action determined)
  ├── (safe/routine) → ACTING
  └── (consequential/irreversible) → CONFIRMING
                                    ↓ (confirmed)
                                    ACTING
                                    ↓ (action complete)
                                    SPEAKING
                                    ↓ (speech complete)
                                    COMPLETE → IDLE

  ↓ (error at any stage)
ERROR → IDLE
```

---

## Action Receipts and Approval Middleware

### Action categorization rules

| Category | Examples | Behavior |
|----------|---------|----------|
| READ | Get temperature, check time, list devices | Auto-execute, no confirmation |
| ROUTINE | Turn on/off light, play music, set brightness | Auto-execute, no confirmation |
| CONSEQUENTIAL | Set thermostat to extreme value, unlock door | Require voice confirmation |
| IRREVERSIBLE | Delete automation, send message, purchase | Require voice confirmation, log prominently |

### Confirmation flow

1. Hermes determines an action requires confirmation.
2. PARKER state moves to CONFIRMING.
3. TTS speaks: "Should I unlock the front door?"
4. User says "yes" / "no" / "cancel".
5. If confirmed: execute and log receipt.
6. If denied: cancel and log receipt.

### Receipt storage

Store receipts as JSON lines in `data/receipts.jsonl`:

```json
{
  "id": "...",
  "timestamp": "2026-08-04T20:00:00Z",
  "trigger": "voice_command",
  "authority": "user_voice_confirmation",
  "action": {"domain": "lock", "service": "lock", "target": "lock.front_door"},
  "result": {"success": true, "new_state": "locked"},
  "confirmed": true,
  "confirmation_method": "voice",
  "conversation_id": "...",
  "area_id": "hallway"
}
```

---

## Simulator

The simulator runs the full voice pipeline end-to-end with all mocks.

### Usage

```python
from parker.simulator.pipeline import VoicePipeline
from parker.simulator.scenarios import load_scenarios

pipeline = VoicePipeline(
    ha_adapter=MockHomeAssistant(),
    hermes_adapter=MockHermes(),
    stt_latency_ms=900,
    tts_latency_ms=350,
    hermes_latency_ms=300,
)

for scenario in load_scenarios("fixtures/scenarios.json"):
    result = pipeline.run(scenario)
    print(result.summary())
```

### Predefined scenarios (`fixtures/scenarios.json`)

```json
[
  {
    "name": "Simple light on",
    "area_id": "living_room",
    "device_id": "voice_pe_living_room",
    "utterance": "Turn on the living room light",
    "expected_action": {"domain": "light", "service": "turn_on", "entity": "light.living_room"},
    "expected_category": "routine",
    "requires_confirmation": false
  },
  {
    "name": "Ambiguous light",
    "area_id": "living_room",
    "device_id": "voice_pe_living_room",
    "utterance": "Turn on the light",
    "expected_action": {"domain": "light", "service": "turn_on", "entity": "light.living_room"},
    "expected_category": "routine",
    "requires_confirmation": false,
    "notes": "Should resolve to living room light based on voice device area"
  },
  {
    "name": "Temperature query",
    "area_id": "living_room",
    "device_id": "voice_pe_living_room",
    "utterance": "What's the temperature?",
    "expected_action": null,
    "expected_category": "read",
    "requires_confirmation": false
  },
  {
    "name": "Thermostat change",
    "area_id": "living_room",
    "device_id": "voice_pe_living_room",
    "utterance": "Set the thermostat to 24 degrees",
    "expected_action": {"domain": "climate", "service": "set_temperature", "entity": "climate.living_room"},
    "expected_category": "routine",
    "requires_confirmation": false
  },
  {
    "name": "Lock door - requires confirmation",
    "area_id": "hallway",
    "device_id": "voice_pe_living_room",
    "utterance": "Lock the front door",
    "expected_action": {"domain": "lock", "service": "lock", "entity": "lock.front_door"},
    "expected_category": "consequential",
    "requires_confirmation": true,
    "confirmation_response": "yes"
  },
  {
    "name": "Two-turn conversation",
    "area_id": "living_room",
    "device_id": "voice_pe_living_room",
    "turns": [
      {"utterance": "What's the temperature?"},
      {"utterance": "And tomorrow?"}
    ],
    "expected_category": "read",
    "notes": "Second turn should use conversation context to understand 'tomorrow' refers to weather/temperature"
  },
  {
    "name": "Context expiry",
    "area_id": "living_room",
    "device_id": "voice_pe_living_room",
    "turns": [
      {"utterance": "Turn on the light"},
      {"wait_seconds": 130},
      {"utterance": "And the kitchen?"}
    ],
    "expected_error": "context_expired",
    "notes": "Context should expire after 120 seconds, second turn should fail gracefully"
  },
  {
    "name": "Device not found",
    "area_id": "living_room",
    "device_id": "voice_pe_living_room",
    "utterance": "Turn on the garage light",
    "expected_error": "device_not_found",
    "notes": "Should produce a spoken error, not crash"
  }
]
```

---

## Latency Targets

| Stage | Target | Measurement |
|-------|--------|-------------|
| Wake word detection | < 500ms | Wake event to listening state |
| Whisper transcription | < 1500ms | Audio to transcript |
| Hermes reasoning | < 500ms | Transcript to action request |
| Home Assistant action | < 200ms | Request to result |
| Piper synthesis | < 500ms | Response text to audio |
| **Total end-to-end** | **< 3000ms** | Wake to speech complete |

The simulator should measure and report all of these. Store results in `data/benchmarks.jsonl`.

---

## Testing Requirements

### Every test must pass before any new feature

Use `pytest` with `pytest-asyncio`. Test categories:

1. **Contract tests** — Every schema validates correctly, rejects bad input.
2. **Mock HA tests** — CRUD entities, call services, error injection.
3. **Mock Hermes tests** — Pattern matching, category assignment, confirmation logic.
4. **Context tests** — Room resolution, conversation tracking, expiry.
5. **Receipt tests** — Logging, categorization, approval flow.
6. **Simulator tests** — Full pipeline with all scenarios.
7. **Integration tests** — End-to-end mock flow with timing assertions.

### Critical test cases

```python
def test_simple_light_on():
    """Turn on a light in the current room."""
    # Wake → transcript → action → result → receipt

def test_ambiguous_device_asks_clarification():
    """'Turn on the light' with no room context should ask which room."""

def test_confirmation_required_for_lock():
    """Locking a door should trigger confirmation flow."""

def test_context_followup():
    """'What's the temperature?' then 'And tomorrow?' should use context."""

def test_context_expiry():
    """Context should expire after 120 seconds of silence."""

def test_device_not_found_spoken_error():
    """Missing device should produce a spoken error, not crash."""

def test_action_receipt_logged():
    """Every executed action should produce a receipt."""

def test_latency_reported():
    """Every pipeline run should report per-stage latency."""

def test_cross_room_requires_explicit_room():
    """'Turn on the kitchen light' from living room should work."""

def test_cancel_pending_confirmation():
    """'Cancel' during confirmation should abort the action."""
```

---

## Technology Choices

- **Language:** Python 3.12+
- **Schema/validation:** Pydantic v2
- **Testing:** pytest + pytest-asyncio
- **HTTP client:** httpx (for real HA adapter later)
- **Storage:** JSON lines files (no database dependency)
- **Display:** Simple HTML + vanilla JS + SSE (Server-Sent Events) for live state
- **Package manager:** uv (preferred) or poetry
- **Linting:** ruff
- **Type checking:** mypy (strict mode)
- **No frameworks:** No Flask, no FastAPI, no Django. Plain Python with a tiny HTTP server for the display.

---

## What NOT to build

1. **Do not connect to real Home Assistant.** Use the mock adapter.
2. **Do not connect to real Hermes.** Use the mock adapter.
3. **Do not use API keys, tokens, or secrets.** The mock adapter is sufficient.
4. **Do not build a wake-word detector.** That is a hardware/firmware concern.
5. **Do not build a real STT/TTS engine.** Mock latency is sufficient.
6. **Do not add cloud dependencies.** No external APIs, no cloud services.
7. **Do not build a mobile app.** The display is a local web page.
8. **Do not modify Hermes internals.** Build an adapter around it.
9. **Do not use an LLM in the mock Hermes.** Use pattern matching.
10. **Do not over-engineer.** Start simple, add complexity when tests demand it.

---

## Integration Points (for later)

When the physical hardware arrives and services are running, these adapters connect to reality:

### Real Home Assistant adapter

```python
# Will connect to: http://192.168.1.171:8123
# Auth: Bearer token from HASS_TOKEN environment variable
# API: Home Assistant REST API
# Endpoints:
#   GET  /api/states/<entity_id>
#   GET  /api/states
#   POST /api/services/<domain>/<service>
```

### Real Hermes adapter

```python
# Will connect to Hermes gateway
# Auth: Configured in Hermes environment
# Protocol: REST or websocket (TBD based on Hermes gateway config)
# The adapter sends: user utterance + conversation context
# The adapter receives: structured response with action request + spoken text
```

### Real STT (Whisper)

```python
# Wyoming protocol over TCP
# Host: localhost (on Mac Mini)
# Port: 10300
# The simulator will swap mock STT for Wyoming client
```

### Real TTS (Piper)

```python
# Wyoming protocol over TCP
# Host: localhost (on Mac Mini)
# Port: 10200
# The simulator will swap mock TTS for Wyoming client
```

---

## Development Workflow

1. **Contracts first.** Write schemas, write contract tests, make them pass.
2. **Mock adapters second.** Implement mock HA and mock Hermes with tests.
3. **Context engine third.** Room resolution, conversation tracking, with tests.
4. **Simulator fourth.** Wire everything together, run all scenarios.
5. **Receipts fifth.** Add approval middleware and receipt logging.
6. **Display sixth.** Simple HTML page showing PARKER state via SSE.
7. **Benchmarks seventh.** Add latency measurement and reporting.

Each step must have passing tests before moving to the next.

---

## Current State

- Home Assistant is running on the Mac Mini at `http://192.168.1.171:8123` (version 2026.7.4).
- HA onboarding is not yet complete (no admin account created).
- Whisper and Piper are not yet deployed.
- The Voice Preview Edition hardware has not arrived.
- This project is being built on the M5 Pro laptop, not the Mac Mini.
- No real Home Assistant or Hermes connections are needed yet.

Build everything with mocks. The real connections come later.
