# SafeFlow API v1

All endpoints except GET /health require `Authorization: Bearer <local-key>`.
The site definition and verification directory are trusted startup settings;
remote callers cannot select paths or upload verification results.

| Endpoint | Purpose |
|---|---|
| GET /health | Process status and current readiness; ok does not mean ready |
| GET /v1/verification | Readiness, reason and per-property verifier report |
| POST /v1/sessions | Start with verified initial facts; optional facts/time_s |
| GET /v1/sessions/ID | Pinned definition, state, clocks, pending event and issue |
| POST /v1/sessions/ID/events | Receive raw evidence and decide a normalized event |
| POST /v1/sessions/ID/observations | Acknowledge an actual effect and advance time |
| POST /v1/sessions/ID/close | Seal a session without pending work |

## Minimal external client flow

Start a session with `{}` and retain the returned session_id. The example starts
all four devices off. Send this body to its events endpoint:

```json
{"event_id":"request-001","source":"ai","kind":"proposal","action":"heater_on","raw":{"native_output":3}}
```

The supervisor returns outcome, reason, transition, next_state, event_id,
definition_sha256, replayed and observation_recorded. On allow, the client sends
the corresponding command to its environment. On block, it preserves device
modes. On halt, it stops the session without an observation or time advance. A declared
policy halt seals the session normally; runtime faults remain distinguishable. After an allowed heater change and one lab
step, send this to observations:

```json
{"event_id":"request-001","facts":{"ac":"off","heater":"on","fan":"off","light":"off"},"applied_at_s":0,"time_s":30}
```

Observations may include an optional `evidence` object containing the native
environment snapshot. The lab records device modes, temperature, power and energy
there before updating formal state; these measurements are not extra formal
variables unless declared in the definition.

The next AI `ac_cool` proposal is blocked by the conflict guard. A blocked proposal
still needs an observation with unchanged facts and the advanced time. Invalid
provider output is represented as kind `invalid_output`, action null, with the
original response in raw; the declared automaton decides its handling.

Only one event can await a decision/result per session. A repeated event ID with
the same body returns the same decision without another log/execution. Changed
content is rejected. Repeated matching observations return the stored result.
Use replayed/observation_recorded to avoid reissuing an actuator command. This is
not a distributed exactly-once guarantee: a crash between an external physical
operation and its acknowledgement needs application-specific recovery. Sessions
are in memory and are not silently resumed after a process restart.

The embedded provider path persists raw input before normalization. For external
clients, raw and normalized data arrive together and are recorded before the
service decides; the service cannot attest when the external client decoded them.

JSON bodies are limited to 64 KiB. Malformed transport returns 400; unauthenticated
requests return 401, unknown sessions 404, halted sessions 409, and unverified
activation/control 503. Semantic observation errors can return 400 and halt the
session; inspect its issue before any recovery. No request may ignore a halt.

## Home Assistant facade

The lab still provides GET /state and POST /human, /goals, /step, /reset. Those
routes compose the same new session service with the case-study adapters.
`/step` accepts an optional integer seed and request_id; repeated matching IDs do
not run the model or environment twice. Human requests queue for one round.
Goals change model input without advancing formal state/time. Reset closes the
old session when possible, records queued cancellations, and starts a new trace
from verified initial device states; it can change temperature/goals, not silently
change verified device initial modes.

When verification is unavailable, /state exposes readiness not_ready and halted
true, while control calls return 503. Home Assistant shows readiness and disables
controls. Updating the integration adds a readiness sensor; reload/restart the lab
Home Assistant instance to load it. Actual HA/live acceptance is recorded in the implementation evidence; fixture
HTTP tests are separate from those real-provider runs.
