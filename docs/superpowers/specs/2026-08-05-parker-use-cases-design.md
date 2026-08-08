# PARKER Combined JARVIS Use Cases

**Date:** 2026-08-05 (expanded 2026-08-07)
**Status:** Approved design (expanded)
**Project:** PARKER Voice Lab

## 1. Purpose

PARKER is a local-first assistant spanning two domains:

1. the apartment: room-aware control, climate, media, security, scenes, and home status;
2. the user's personal and work life: briefings, calendar, reminders, files, research, preparation, and carefully gated delegation.

The use-case set must describe the eventual product while remaining executable as deterministic simulator scenarios. Product cards explain the human value. Simulator fixtures verify the pipeline contract. Future adapters connect the same contracts to real services without introducing a second safety model.

The central product rule is:

> **Understand -> classify risk -> explain -> confirm when necessary -> act -> report the result.**

The expanded set adds gated autonomy: multi-step agentic work — event-triggered routines, dev operations, research, self-running routines, anomaly hunting, and travel preparation — executes within the same trust model. Routine steps run without per-step confirmation; consequential and irreversible steps keep their gates.

## 2. Scope and non-goals

### In scope

- Product-level use cases for apartment and personal/work orchestration.
- Room, time, device, and conversation context.
- Read, routine, consequential, and irreversible action classes.
- Explicit confirmations, cancellation, receipts, recovery, and latency evidence.
- Deterministic mock providers for future calendar, weather, task, file, messaging, presence, media, web, flight, and Hermes CLI integrations.
- Controlled proactive event ingestion for high-signal email, message, and shipment updates.
- A designated-speaker announcement queue with quiet hours, deduplication, and acknowledgement state.
- A privacy policy layer with explicit Guest Mode and privacy-safe automatic inference.
- A three-level presence model: voice-source room, home/away presence, and optional room occupancy.
- Traceability from each product use case to simulator scenarios and later adapters.
- A local test console showing plans, state, confirmations, receipts, adapter health, and latency.
- **Gated autonomy:** multi-step plans whose routine steps execute without per-step confirmation while consequential and irreversible steps retain explicit gates.
- **Event-triggered routines:** sensor- or presence-driven behaviour such as the shower routine.
- **Dev operations by voice:** bounded test runs, status checks, and gated deploys through the Hermes gateway.
- **Research and synthesis:** multi-source gathering with cited, freshness-labelled summaries.
- **Self-running routines:** user-defined scheduled work with condition evaluation per run.
- **Home anomaly hunting:** baseline comparison with evidence-based explanations.
- **Travel and day preparation:** calendar- and flight-driven plans with gated check-in.

### Out of scope for the first slice

- Real Home Assistant, Hermes, calendar, messaging, file, weather, flight, or web credentials.
- A mobile application.
- A new wake-word detector.
- Autonomous open-ended agent behaviour.
- Silent background actions based on unbounded inference.
- Proactive intervention before the trust loop is proven.
- Camera-based identity or guest recognition.

## 3. Journey map and priority

PARKER's use cases are grouped into ten journeys.

| Journey | User goal | Typical risk | First capabilities |
|---|---|---|---|
| **Orient me** | Understand the day and the state of the home | Read | Calendar, weather, reminders, home/device status, concise briefings |
| **Keep me ahead** | Hear about important inbound events before asking | Read-only | Event ingestion, priority triage, shipment tracking, speaker announcements |
| **Run the room** | Control the apartment naturally from the current room | Read / routine | Room-aware lights, climate, media, scenes, follow-up conversation |
| **Put me into a mode** | Start focus, sleep, hosting, or away mode | Routine / consequential | Multi-device plans, meaningful-change preview, expiry and reversal |
| **Coordinate my day** | Turn intentions into reminders, notes, files, and preparation | Read / routine | Calendar lookup, task capture, meeting preparation, research/file retrieval |
| **Act on my behalf** | Send, publish, purchase, unlock, delete, or change something externally | Consequential / irreversible | Draft-first behaviour, explicit confirmation, prominent receipt, rollback where possible |
| **Notice and recover** | Handle ambiguity, stale data, unavailable devices, failed actions, and expired context | No silent action | Clarification, truthful failure, bounded retry, recovery prompt |
| **Run my systems** | Operate the development environment by voice | Read / routine / consequential | Test runs, status checks, gated deploys |
| **Delegate the routine** | Turn recurring or event-triggered work into routines | Routine / consequential | Shower routine, self-running routines |
| **Watch the home** | Understand what is odd and why | Read | Anomaly scans, evidence-based explanations |

### Delivery priority

- **P0 — Trust loop:** room-aware control, risk classification, confirmation, cancellation, receipts, errors, state display, and latency traces.
- **P1 — Daily utility:** morning briefing, controlled proactive alerts, focus mode, leave-home review, arrival/hosting routine, apartment status, shower routine, and dev-ops read/routine.
- **P2 — Personal/work delegation:** calendar, reminders, files, research, meeting preparation, draft creation, research and synthesis, and travel preparation.
- **P3 — Proactivity:** anomaly detection, suggestions, time-based routines, narrowly configured interventions, self-running routines, and anomaly hunting.

The current voice lab can exercise most of **Run the room** and **Notice and recover** immediately. The remaining journeys should be specified now and represented initially by deterministic mock providers. Controlled proactive alerts are in scope; autonomous intervention remains deferred.

### Room and presence model

PARKER must not conflate three different signals:

1. **Voice-source room:** the Home Assistant Area assigned to the satellite that heard the request. This is available without an occupancy sensor and is sufficient to resolve "the light" or "here."
2. **Home/away presence:** whether the user's phone or another device tracker places the user at home or in a broad zone. This is not room-level location.
3. **Room occupancy:** whether a room appears occupied, using PIR, mmWave, door events, Bluetooth/Wi-Fi proxies, or a fused sensor. This does not, by itself, identify the person present.

The designated proactive speaker remains a fixed output target until room-level personal presence is proven. A room-origin signal may route an interactive response; it must not be treated as proof that the user is still in that room later.

## 4. Product use-case cards

Every card has the following fields:

- **User goal:** the job PARKER is helping with.
- **Trigger and context:** utterance, room, time, conversation, devices, and relevant external sources.
- **Behaviour:** what PARKER retrieves, plans, says, and executes.
- **Risk:** action category and confirmation rule.
- **Failure path:** ambiguity, stale data, unavailable provider, partial failure, or expired context.
- **Evidence:** state, sources, receipts, authority, and latency.
- **Simulator mapping:** deterministic fixture name and mock capability.
- **Later integration:** real adapter or service boundary.

### UC-01 — Morning orientation

- **User goal:** understand the day and the state of the home.
- **Example:** "Good morning, PARKER. What matters today?"
- **Context:** time, calendar, reminders, weather, current room, and overnight home state.
- **Behaviour:** gather available sources, rank the result, give a concise briefing, and offer one next step such as starting focus mode.
- **Risk:** read-only; no confirmation.
- **Failure path:** identify unavailable or stale sources instead of silently omitting important information.
- **Evidence:** source timestamps, response latency, and a briefing record.
- **Simulator mapping:** `morning_briefing_aggregates_sources` with deterministic calendar, weather, task, and HA read mocks.
- **Later integration:** calendar, weather, task, and Home Assistant adapters.

### UC-02 — Room-aware apartment control

- **User goal:** control the nearby environment without naming every entity.
- **Examples:** "Turn on the light." "Make it warmer." "Play music here."
- **Context:** voice satellite area, conversation, device inventory, and current state.
- **Behaviour:** resolve "the light" or "here" from room context, execute an ordinary routine action, and report the verified resulting state.
- **Risk:** routine for ordinary light, media, and bounded climate changes; no confirmation by default.
- **Failure path:** ask when multiple devices match; report the device as unavailable when execution cannot be verified.
- **Evidence:** action receipt, resulting entity state, and per-stage latency.
- **Simulator mapping:** existing `Simple light on`, `Temperature query`, and `Ambiguous light` scenarios.
- **Later integration:** real voice satellite, Whisper, Piper, Hermes, and Home Assistant adapters.

### UC-03 — Start a mode

- **User goal:** change several aspects of the environment with one intention.
- **Examples:** "Start focus mode until three." "Set the apartment up for guests at seven."
- **Context:** time window, user-defined mode, current device states, and conflicts with existing routines.
- **Behaviour:** construct an explicit plan, identify meaningful changes, execute safe steps, and announce expiry or reversal.
- **Risk:** routine by default; notification suppression, security changes, and unusual climate changes require preview and confirmation.
- **Failure path:** report partial completion item by item; do not narrate a failed plan as complete.
- **Evidence:** mode record, per-action receipts, reversibility/expiry metadata, and latency.
- **Simulator mapping:** `focus_mode_multi_action` using a multi-action mock Home Assistant provider and mode store.
- **Later integration:** Home Assistant scenes and a configured work-status or notification provider.

### UC-04 — Leave-home review

- **User goal:** leave without wondering whether the apartment is still running itself.
- **Example:** "I'm leaving."
- **Context:** lights, media, climate, locks, windows, occupancy, and departure policy.
- **Behaviour:** inspect first. If correct, report that the home is ready. If not, present an itemised plan such as: "The kitchen light is on and the front door is unlocked. Shall I turn off the light and lock the door?"
- **Risk:** mixed. Lights and media may be routine; locking, arming, and material climate changes require explicit confirmation.
- **Failure path:** report exactly which step failed and preserve each step's receipt.
- **Evidence:** departure checklist, confirmation authority, per-action results, and final home state.
- **Simulator mapping:** `leave_home_mixed_risk_plan` using light, media, and lock entities with injected partial failure.
- **Later integration:** occupancy, security, window, and real Home Assistant adapters.

### UC-05 — Meeting preparation

- **User goal:** move from "I have a meeting" to "I am prepared."
- **Example:** "Prepare me for my two o'clock client meeting and set the office up."
- **Context:** calendar event, related notes/files, prior reminders, current room, and focus settings.
- **Behaviour:** retrieve the event, collect relevant material, summarise what matters, identify missing preparation, and apply the office routine.
- **Risk:** read operations plus bounded routine actions; no external write.
- **Failure path:** distinguish no matching meeting, meeting found but no notes, and unavailable office devices.
- **Evidence:** sources consulted, referenced files/notes, device actions, and elapsed time.
- **Simulator mapping:** `meeting_prep_with_missing_notes` with deterministic calendar, file, and HA mocks.
- **Later integration:** Google/Microsoft workspace or local file adapters plus Home Assistant.

### UC-06 — Draft, then send

- **User goal:** delegate a small communication without surrendering control.
- **Example:** "Tell Alex I'll be ten minutes late."
- **Context:** recipient identity, channel, current time, meeting context, and message content.
- **Behaviour:** resolve the recipient, draft the exact message, display or speak it, and wait. "Send it" is a separate confirmation turn.
- **Risk:** irreversible; never send on the initial request without an explicitly configured, narrowly bounded exception.
- **Failure path:** ambiguous recipient, unavailable channel, or changed context causes a new confirmation rather than a guess.
- **Evidence:** draft, confirmation authority, sent-message receipt, timestamp, channel, and final content.
- **Simulator mapping:** `draft_message_requires_confirmation`, followed by a separate confirmed-send scenario, using a deterministic mock messaging provider.
- **Later integration:** iMessage, email, or another explicitly configured messaging adapter.

### UC-07 — Notice and recover

- **User goal:** get an honest answer when something goes wrong.
- **Examples:** "Turn on the garage light" when no entity exists; "Turn on the kitchen light" when it is offline.
- **Behaviour:** name the actual problem, preserve the user's intent, and offer a bounded recovery such as clarification, retry, or a known alternative.
- **Risk:** no action until ambiguity or availability is resolved.
- **Failure path:** distinguish not found, offline, stale state, permission failure, timeout, and expired conversation context.
- **Evidence:** error code, attempted operation, adapter status, and recovery choice. An unsuccessful operation must not produce a success receipt.
- **Simulator mapping:** existing `Device not found` and `Context expiry`, plus `device_offline` and `partial_plan_failure`.
- **Later integration:** real adapter health/status and retry policies.

### UC-08 — Explain before intervening

- **User goal:** understand a condition and decide what to do.
- **Examples:** "Why is the bedroom cold?" "The apartment feels dark."
- **Context:** relevant sensors, recent actions, room, device history, and data freshness.
- **Behaviour:** inspect first, explain observed evidence, propose bounded actions, and wait when the remedy has meaningful consequences.
- **Risk:** read first; proposed remedies are classified separately.
- **Failure path:** state when evidence is insufficient rather than converting a hunch into a thermostat or security command.
- **Evidence:** sensor values, freshness, reasoning inputs, proposed action, and eventual receipt.
- **Simulator mapping:** `cold_room_explains_before_action` with deterministic sensor history and climate state.
- **Later integration:** event-driven sensor streams and a proactive detection layer.

### UC-09 — Keep me ahead

- **User goal:** hear about high-signal inbound events without having to ask PARKER first.
- **Examples:** "You have a new message from Alex." "Your package has shipped; here is the latest tracking information."
- **Context:** new email or iMessage/SMS event, sender or source priority, shipment status, current time, quiet-hours policy, and the designated speaker.
- **Behaviour:** detect a new item, deduplicate it, classify it with deterministic rules first, optionally summarise a shortlisted message or resolve a shipment status, and speak a concise metadata-first announcement through the designated speaker.
- **Risk:** read-only. PARKER may inspect, classify, summarise, and announce, but it must not reply, send, archive, delete, or alter a message as part of this use case.
- **Failure path:** suppress duplicate events; keep low-confidence or routine items silent; disclose stale tracking data; report mailbox or watcher health without fabricating an alert; queue speech during quiet hours.
- **Evidence:** source and message identifiers, classification, announcement timestamp, acknowledgement state, source freshness, tracking status, and delivery latency.
- **Simulator mapping:** `priority_message_announced_once`, `package_shipped_with_tracking_summary`, `duplicate_event_suppressed`, `quiet_hours_queue_and_release`, `ordinary_newsletter_not_announced`, and `read_full_message_only_after_request`.
- **Later integration:** Gmail API or IMAP, macOS Messages access, carrier tracking sources, and Home Assistant/Piper speaker delivery.

### UC-10 — Host privately with Guest Mode

- **User goal:** allow guests to use the apartment without PARKER broadcasting private information.
- **Examples:** "PARKER, guests are here for four hours." "Turn on Guest Mode."
- **Context:** explicit mode command or display control, expiry time, optional owner device presence, recent entry event, room occupancy, announcement queue, and safety-alert policy.
- **Behaviour:** set `guest_mode`, suppress private email, message, calendar, shipment, financial, and work announcements from the designated speaker, hold them for private delivery, mask private details on public displays, and continue safety-critical announcements. Home-control responses remain available but must not expose private context.
- **Risk:** explicit mode activation is a routine policy change; automatic inference is advisory and privacy-preserving rather than identity proof.
- **Failure path:** if occupancy evidence is stale or ambiguous, do not announce private content; keep private events queued and notify the user through a private channel when possible. Never discard an alert because Guest Mode was active.
- **Evidence:** mode state, activation authority, expiry, reason, events held, events released, output target, and privacy decision.
- **Simulator mapping:** `guest_mode_manual_suppresses_private_announcement`, `guest_likely_auto_mutes_private_alerts`, `guest_mode_expiry_restores_queue`, and `safety_alert_bypasses_guest_mode`.
- **Later integration:** Home Assistant helper/state machine, optional room occupancy sensors, owner device tracking, event watchers, designated speaker, and private phone delivery.

### UC-11 — Shower routine

- **User goal:** start the shower and have PARKER handle the soundtrack and the morning readout.
- **Trigger:** event-triggered, no utterance. A bathroom presence sensor detects the shower start.
- **Context:** bathroom sensor (Aqara FP2 mmWave with shower-zone detection, or a vibration sensor on the pipe as the low-cost fallback), time, quiet hours, Guest Mode, designated speaker, configured playlist.
- **Behaviour:** on the shower-start event, speak a concise metadata-first readout (time, weather, first calendar item, high-signal messages per UC-09 rules) and start the configured playlist on the designated speaker. Respect quiet hours (queue or skip the readout) and Guest Mode (suppress private content; the playlist may continue).
- **Risk:** routine (media + TTS). No confirmation for the routine itself; announcement content is governed by the privacy rules.
- **Failure path:** sensor false positive (plumbing noise, steam), speaker unavailable, playlist unavailable -> suppress or fall back; never announce private content in Guest Mode.
- **Evidence:** trigger source and sensor state, announcement receipt, media receipt, and latency.
- **Simulator mapping:** `shower_routine_readout_and_playlist`, `shower_routine_quiet_hours_queued`, `shower_routine_guest_mode_private_suppressed`, and `shower_sensor_false_positive_suppressed`.
- **Later integration:** Aqara FP2 mmWave or vibration sensor via Home Assistant, media player, and Piper TTS.

### UC-12 — Dev operations by voice

- **User goal:** operate the development environment without opening a terminal.
- **Examples:** "Run the tests." "What's the deploy status?" "Deploy the dashboard."
- **Context:** project identity, repository state, CI status, current session, and the Hermes gateway on the Mac Mini.
- **Behaviour:** resolve the project, run the bounded command, and report a concise result with exit status and key output. Deploys, restarts, and publishes are consequential and require confirmation of the exact target.
- **Risk:** read for status; routine for test runs within configured projects; consequential for deploy, restart, and publish.
- **Failure path:** unknown project, long-running or hanging command, failing tests, deploy failure -> honest report; no success receipt without a verified result.
- **Evidence:** command, exit code, output summary, duration, and receipt for gated actions.
- **Simulator mapping:** `dev_ops_test_run_reports_result`, `dev_ops_deploy_requires_confirmation`, and `dev_ops_failing_tests_honest_report`.
- **Later integration:** Hermes gateway on the Mac Mini, git, CI status, and shell.

### UC-13 — Research and synthesis

- **User goal:** get a multi-source rundown on a topic without doing the legwork.
- **Example:** "Research the best mmWave presence sensors and give me the rundown."
- **Context:** topic, time budget, source freshness, and prior conversation.
- **Behaviour:** gather from multiple sources, deduplicate, rank by relevance and freshness, produce a concise cited summary, and offer one follow-up.
- **Risk:** read; no confirmation.
- **Failure path:** unavailable sources, conflicting claims, stale results -> disclose rather than silently omit.
- **Evidence:** sources consulted, freshness, citations, and latency.
- **Simulator mapping:** `research_rundown_cited_sources` and `research_conflicting_claims_disclosed`.
- **Later integration:** Hermes web search and extract, SearXNG, and Firecrawl.

### UC-14 — Self-running routines

- **User goal:** delegate recurring agentic work.
- **Examples:** "Every morning, check the weather and tell me if I need a jacket." "Every weekday at nine, check the build and report failures."
- **Context:** schedule, condition, sources, action policy, and quiet hours.
- **Behaviour:** store the routine with schedule and condition; on each run, evaluate the condition against fresh sources; execute only actions permitted by the routine's gate policy; report results; never act on stale or ambiguous state.
- **Risk:** defining a routine is routine; each run's actions are classified individually, and consequential steps still gate.
- **Failure path:** condition ambiguous, source stale, action fails -> no silent action; report the failure.
- **Evidence:** routine record, schedule, per-run condition evaluation, and per-run receipts.
- **Simulator mapping:** `routine_condition_true_executes`, `routine_condition_false_skips`, and `routine_stale_source_no_action`.
- **Later integration:** Hermes cron and Home Assistant automations.

### UC-15 — Home anomaly hunting

- **User goal:** understand what is odd about the home and why.
- **Examples:** "Anything weird going on?" "Why is the bedroom cold?"
- **Context:** device states, baselines (time-of-day, day-of-week), sensor history, and freshness.
- **Behaviour:** compare current state to baselines, flag anomalies with evidence, explain, and propose bounded remedies; remedies are classified separately.
- **Risk:** read; no confirmation for the scan; remedies gate per class.
- **Failure path:** insufficient history or stale data -> state that evidence is insufficient; never convert a hunch into a command.
- **Evidence:** baseline, current values, freshness, anomaly list, and proposed actions.
- **Simulator mapping:** `anomaly_door_open_flagged` and `anomaly_insufficient_history_no_claim`.
- **Later integration:** Home Assistant history and event-driven sensor streams.

### UC-16 — Travel and day preparation

- **User goal:** be prepared for a trip or a demanding day.
- **Examples:** "Prepare me for my trip to New York." "Prepare me for tomorrow."
- **Context:** calendar, flights, weather at destination, home state, and departure policy.
- **Behaviour:** gather the event, build a plan (packing list, departure time, home readiness), and present it; check-in and other irreversible steps gate.
- **Risk:** read / routine; consequential gate for check-in.
- **Failure path:** no matching event, stale flight data, unavailable sources -> distinguish and disclose.
- **Evidence:** sources, plan, and receipts for gated steps.
- **Simulator mapping:** `travel_prep_plan_generated` and `travel_checkin_requires_confirmation`.
- **Later integration:** calendar, flight APIs, weather, and Home Assistant.

## 5. Trust and safety model

### Action classes

| Class | Examples | Allowed behaviour |
|---|---|---|
| **Read** | Temperature, calendar, reminders, file lookup, home status | Execute immediately; state freshness and source when relevant |
| **Routine** | Lights, media, bounded climate changes, focus scene | Execute within configured scope; report the resulting state |
| **Consequential** | Lock/unlock, arm security, large climate change, mixed-risk departure plan | Explain the exact action and require confirmation immediately before execution |
| **Irreversible** | Send, publish, purchase, delete, important file modification | Draft/preview first; require explicit confirmation; record a prominent receipt |

### Gated autonomy

The trust model extends to multi-step agentic work without weakening it:

1. **Routine steps execute without per-step confirmation.** Once a plan is formed, ordinary steps (reads, media, bounded climate, test runs) run end-to-end.
2. **Consequential gates stop the plan.** Send, lock, purchase, delete, deploy, restart, publish, and check-in each require explicit confirmation of the exact pending action before execution.
3. **Irreversible actions draft first.** The UC-06 rule applies unchanged.
4. **Every step produces a receipt.** Autonomy is not opacity; the user can review the full plan and per-step results after the fact.
5. **Autonomy is per-capability and opt-in.** Each card declares its gate policy; no capability is autonomous by default.
6. **Proactivity still suggests before it acts.** Gated autonomy applies to user-requested or explicitly configured routines, not to silent background intervention.

### Non-negotiable rules

1. No silent side effects. A read may be combined with a suggestion; a side effect must be named.
2. Confirmation is specific to the pending plan. "Yes" confirms only the action whose target and parameters were just spoken or shown. A changed recipient, amount, device, or payload requires fresh confirmation.
3. Voice confirmation proves intent, not identity. Security-sensitive actions must support a stronger configurable policy such as presence, display confirmation, PIN, or another factor.
4. Ambiguity stops execution. PARKER asks which device, recipient, or file is intended.
5. Stale information is labelled when it could change the decision.
6. Plans are itemised. Mixed-risk plans separate safe actions from gated actions, and each step reports success or failure.
7. "Done" is reserved for a verified result from the adapter.
8. **Proactivity suggests before it acts.** Autonomous intervention is opt-in and narrowly bounded.
9. **Receipts are the system of record.** Executed, failed, denied, and cancelled consequential attempts are recorded.
10. **Room origin is not current personal location.** A satellite identifies where a request began, not where the user remains afterward.
11. **Guest inference fails closed for privacy.** Uncertain occupancy may mute private TTS, but it must never expose private content or claim to identify a guest.
12. **Recovery is part of every use case, not an afterthought.**

## 6. Simulator and integration traceability

The product card and simulator fixture must remain linked by stable identifiers.

| Product card | Initial fixture | Mock capability | Later integration |
|---|---|---|---|
| UC-01 | `morning_briefing_aggregates_sources` | Calendar, weather, tasks, HA reads | Calendar/task/weather providers |
| UC-02 | Existing light, temperature, and room scenarios | Existing mock HA/Hermes | Real voice and HA adapters |
| UC-03 | `focus_mode_multi_action` | Multi-action HA and mode store | HA scenes and work-status provider |
| UC-04 | `leave_home_mixed_risk_plan` | Light, media, lock, occupancy, failure injection | Security and occupancy integrations |
| UC-05 | `meeting_prep_with_missing_notes` | Calendar, file search, HA | Workspace or local-file adapters |
| UC-06 | `draft_message_requires_confirmation` plus confirmed send | Messaging provider | iMessage/email/messaging adapter |
| UC-07 | Existing not-found/context-expiry plus offline/partial-failure fixtures | Error injection and retry state | Real adapter health/status |
| UC-08 | `cold_room_explains_before_action` | Sensor history and climate state | Event-driven sensor/proactive layer |
| UC-09 | `priority_message_announced_once` plus shipment and quiet-hours fixtures | Mail/message watchers, event deduplication, announcement queue, tracking mock | Gmail/IMAP, Messages.app, carrier sources, Home Assistant/Piper |
| UC-10 | `guest_mode_manual_suppresses_private_announcement` plus expiry and safety-bypass fixtures | Privacy policy, mode timer, private queue, optional occupancy inference | Home Assistant helper/state, device trackers, room sensors, private delivery |
| UC-11 | `shower_routine_readout_and_playlist` plus quiet-hours, guest-mode, and false-positive fixtures | Presence/motion mock, media player, announcement queue | Aqara FP2 mmWave or vibration sensor via HA, media player, Piper |
| UC-12 | `dev_ops_test_run_reports_result` plus gated-deploy and failing-tests fixtures | Mock Hermes CLI provider with exit codes and output | Hermes gateway, git, CI, shell |
| UC-13 | `research_rundown_cited_sources` plus conflicting-claims fixture | Mock web search/extract with freshness metadata | Hermes web tools, SearXNG, Firecrawl |
| UC-14 | `routine_condition_true_executes` plus skip and stale-source fixtures | Routine store, schedule, condition evaluator | Hermes cron, HA automations |
| UC-15 | `anomaly_door_open_flagged` plus insufficient-history fixture | Baseline store, sensor history, anomaly detector | HA history, event-driven sensor streams |
| UC-16 | `travel_prep_plan_generated` plus gated check-in fixture | Calendar, flight, weather, home-state mocks | Calendar, flight APIs, weather, HA |

### Fixture expectation shape

The existing single-action expectation model should be extended for cross-domain and multi-action cases:

```json
{
  "name": "draft_message_requires_confirmation",
  "journey": "act_on_my_behalf",
  "utterance": "Tell Alex I'll be ten minutes late",
  "expected_category": "irreversible",
  "expected_actions": [],
  "expected_confirmation": true,
  "expected_spoken_contains": ["Alex", "ten minutes late"],
  "expected_receipt": {
    "recorded": true,
    "confirmed": false
  }
}
```

A later confirmation turn should verify the exact pending action:

```json
{
  "expected_actions": [
    {
      "domain": "messaging",
      "service": "send",
      "target": "alex"
    }
  ],
  "expected_confirmation": false,
  "expected_receipt": {
    "confirmed": true
  }
}
```

Multi-action scenarios must assert order, gating, partial failure, final state, spoken result, receipt count, and per-stage latency.

## 7. First implementation boundary

The initial implementation should establish the general contract with a representative slice rather than attempt all cards simultaneously:

1. one room-aware read and routine action;
2. one ambiguous request;
3. one consequential confirmation and cancellation;
4. one mixed-risk multi-action plan;
5. one read-only personal/work briefing;
6. one draft-then-send irreversible action;
7. one offline or partial-failure path;
8. one high-signal proactive message or shipment announcement with deduplication and quiet-hours handling;
9. one manual Guest Mode run with private-alert suppression, expiry, and a safety-alert bypass;
10. one event-triggered routine (shower) with readout, playlist, quiet-hours, and Guest Mode behaviour;
11. one dev-ops read/routine scenario and one gated deploy;
12. one research rundown with cited sources and disclosed conflicts;
13. one self-running routine with condition-true and condition-false runs;
14. one anomaly scan with a flagged anomaly and an insufficient-evidence case;
15. one travel-prep plan with a gated check-in.

The local test console should expose, for each run:

- scenario and journey;
- input utterance and resolved context;
- proposed plan and risk class;
- pending confirmation and authority;
- adapter calls and results;
- action receipts;
- final spoken response;
- adapter health and per-stage latency;
- resettable session state.

## 8. Acceptance criteria

The design is implemented successfully when:

- every executed side effect has a receipt;
- no ambiguous request executes;
- no confirmation response executes without a matching pending action;
- a changed target or payload requires fresh confirmation;
- no failed adapter call produces a success response;
- mixed-risk plans show safe and gated steps separately;
- stale source data is disclosed when relevant;
- high-signal proactive events are announced once through the designated speaker;
- routine or low-confidence inbound items remain silent;
- quiet-hours alerts are queued and released without duplication;
- full message content is not spoken until explicitly requested;
- proactive scanning never sends or modifies an external message;
- voice-source room is used for immediate room-aware commands without requiring occupancy sensors;
- Guest Mode can be activated explicitly with an expiry time;
- private alerts are held or routed privately while Guest Mode is active;
- safety-critical alerts bypass Guest Mode;
- automatic guest inference never speaks private content and never claims to identify a guest;
- the state display exposes current state, pending confirmation, latest receipt, adapter health, and latency;
- ordinary local interactions meet the existing `< 3 s` end-to-end target under the configured benchmark profile;
- a user can tell, without reading logs, what PARKER did and why;
- every product card has at least one deterministic simulator scenario and a named future integration boundary;
- event-triggered routines fire once per event and respect quiet hours and Guest Mode;
- dev-ops deploys, restarts, and publishes require confirmation of the exact target;
- research summaries cite sources and disclose conflicts and freshness;
- self-running routines evaluate conditions against fresh state before acting and never act on stale or ambiguous state;
- anomaly reports distinguish evidence from inference and never convert a hunch into a command;
- travel prep gates check-in and other irreversible steps;
- no capability is autonomous by default; autonomy is per-capability and opt-in.

## 9. Deferred expansion

After the first slice is stable, add:

- energy and weather-aware reactions (usage tracking, waste flags, weather-triggered home adjustments);
- cooking assistant (multi-timers, recipe readout, unit conversions);
- intercom and multi-room announcements;
- conversation rewind ("say that again", rephrase, continue a thread);
- media and entertainment queue management;
- shopping and inventory with gated purchase;
- richer work and personal providers;
- stronger identity and display/PIN policies for security-sensitive actions;
- real hardware and network adapters.

The deferred work must reuse the same action categories, confirmation rules, receipts, and recovery semantics. New integrations do not receive a private definition of "done."
