# Site definition and timed-automata semantics

Start from [the commented home policy](../../examples/smart-home/policy.yaml).
The source format is YAML version 1; `on`/`off` remain strings (YAML 1.2 boolean
rules). Duplicate keys, aliases and executable YAML tags are rejected.

## Supported definition

- `parameters`: nonnegative bounded integers; the example rest time is 180 seconds.
- `variables`: boolean, finite enum, or bounded integer, each with an initial value.
  Device modes are enum variables; measurements such as temperature may be passed
  to the model and logged without entering the formal state.
- `clocks`: clocks with a not-yet-reset flag and `reset_when` predicates over `before`,
  `after`, and parameters. `clock.NAME` advances from session start until reset, then measures elapsed
  environment seconds since reset. `active.NAME` distinguishes first use from cooldown.
- `sources` and `event_kinds`: finite input domains. `proposal` carries a declared
  action ID. Other kinds carry no action; the example declares invalid output,
  timeout and adapter error.
- `actions`: opaque IDs with literal assignments to declared variables. Empty
  assignments represent hold. The home adapter requires at most one device per
  action; the core does not know native device names.
- `states`, `initial`, `transitions`: explicit control locations. The home example
  uses Monitoring plus device-mode data variables, an extended timed automaton.
  Each transition declares from/to, event kinds, a guard, outcome and reason.
- `properties`: named `invariant` or `reachable` assertions at `decision` or
  `observation`; independent from the transition guards.

Expressions allow True/False, integer and enum literals, declared references,
`and`, `or`, `not`, and ==, !=, <, <=, >, >=. Calls, indexing, arithmetic, floats,
custom Python, arbitrary TCTL and unsupported constructs are rejected. Guards
cannot read future observations or their own outcome. No eval/exec is used.

A declared halt is terminal: no command, observation, clock advance or state
change follows it, so its to location must equal from. A sealed session_halt
record distinguishes this normal policy stop from an undefined transition or
runtime fault. Queued requests are abandoned by a terminal stop.

Exactly one outgoing transition must match an event. Missing/ambiguous matches
halt rather than choosing an order-dependent fallback. In the example, malformed
and timeout events block and advance time; editing that transition to halt changes
the behavior without editing the engine (and requires re-verification).

## Observation and clock contract

Sessions start from the initial facts covered by their bundle. An allowed action
has an atomic declared effect at the decision timestamp. The caller reports the
actual resulting facts, `applied_at_s` equal to that timestamp, and `time_s` after
an explicit nonnegative delay. The example adapter advances exactly 30 seconds.
Only then do state and elapsed clocks commit. Wrong references, backwards time,
unexpected effects and invariant violations cannot advance the session.

AC-off reset uses an actual cool-to-off change. Repeated off does not reset it;
first use has no artificial rest period. Human commands use the same observation
path and reset clocks identically, but their permit exception is in the policy.
Both-on is reachable by a human, so a global invariant banning both-on would be
incorrect for this case study. The properties constrain AI admissions instead.

## UPPAAL and readiness

Run `python -m safeflow verify --definition FILE --output NEW_DIRECTORY --verifyta EXECUTABLE`.
The same typed IR feeds the exporter and runtime. Each new bundle stores a
canonical definition, IR, XML, individual query files, manifest, raw verifier
outputs and the per-property report. No existing bundle is overwritten.

The generated model explores finite proposals and arbitrary nonnegative delays;
thermal physics and arbitrary physical failures are not part of it. Committed
locations make decision and declared application instantaneous. Each decision
must be unique; explicit fault branches expose missing/ambiguous transitions.
Boolean expressions are lowered to committed decision graphs so clock guards
remain in the conjunction form required by UPPAAL; clocks cannot advance inside
those graphs.
Properties are checked at the selected phase, not at unrelated intermediate
committed locations.

Activation checks every property result, hashes, converter version, exact output
files and the verifier executable. An unavailable tool, timeout, false property,
modified source/query/model or missing result keeps the service not ready.
The current home definition passes all 12 properties; see the
[actual results](../../experiments/implementation-2026-10-27/verification/attempt-07/verification.json). Earlier license and generated-model errors
remain in preceding attempts, and cannot activate the service.

During operation SafeFlow monitors each event/effect against A; it does not call
UPPAAL per request. `python -m safeflow check TRACE` checks the ordered recorded X.
A sealed complete path can conform, a mismatch reports the first line with
expected/found, and an unfinished tail is inconclusive. `--live-prefix` explicitly
checks only an observed prefix. None of these proves all future AI behavior.
