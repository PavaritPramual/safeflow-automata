# Automata policy smart-home-v1

## State and input mapping

`devices.air_conditioner` maps off/cool to AC false/true; heater off/on maps
false/true. Fan and light are observed and checked for valid modes but have no
safety restriction. `ac_off_elapsed_s` maps null or >=180 to ready, otherwise
resting. The numeric clock remains available for boundary checks. Times are
simulation seconds, not inference duration or JSONL wall timestamps.

Input is `(source, Command, state_before, simulation_time_s)`. Unknown proposals
are rejected; unknown observed modes, nonfinite/backward clocks, or unobserved
state changes halt the episode. An unknown state is not an accepting safe state.

## Transition table

| Source/event | Guard | Decision/effect |
|---|---|---|
| AI AC cool | Heater on | block; modes unchanged |
| AI heater on | AC cool | block; modes unchanged |
| AI AC off-to-cool | Rest not complete | block; modes unchanged |
| AI other valid command | Previous guards false | allow |
| Human valid command | Any known state | human_bypass; apply and observe |
| Invalid proposal | Any known state | reject_invalid; no device command |
| AC actual cool-to-off | AI or human | Clock reset to zero |
| Duplicate AC off | Already off | Clock unchanged |
| Duplicate AC cool | Already cool | No restart; conflict guard still applies |
| Round completion | Any decision | Advance 30 s; observe actual results |

Human-induced both-on is a supported state. AI hold and off requests may proceed;
opening requests that conflict remain blocked. Initial AC off is ready, even if
no off timestamp exists. Reset clears the episode and restores readiness.

## Runtime contract and failure handling

`Automata.reset(snapshot)` establishes observed state; `evaluate(command, source,
snapshot)` returns a decision without changing it; `observe(before, executed,
after, advance_s)` checks modes/time/clock against actual execution and commits
new observed state. Goals can change between rounds without advancing clocks.

Schema v2 adds policy version, decision, Automata states and check duration to
JSONL; existing proposal and execution IDs remain. Decision command means the
command to execute, while proposal command means the command requested.
`last_result` includes both `command` and `executed_command`. `/state` exposes
`automata`, `enforcement`, `policy_version`. Existing endpoints are retained.

Proposal and decision are fsynced before apply. Log failures halt, including human
queue/goal records. A post-apply failure may leave the environment changed; never
retry it automatically. Fault logging is best-effort when logging itself fails.
Replay verifies v2 decisions and actual effects, and accepts historical unshielded
v1 logs without pretending they contain policy evidence.

## Formal model and correspondence limits

`formal/smart-home.xml` separates nondeterministic Proposer, Guard and Plant,
with committed check/apply stages and a real-valued clock. Requests may occur
at arbitrary times, a superset of the runtime's 30-second rounds. The model
covers all nine valid commands and two sources; physical temperatures, malformed
input and I/O failures are outside the formal model and covered by runtime tests.

Queries cover AI conflict/cooldown, blocked-state preservation, structural
non-deadlock, reachable human conflict, blocking and post-rest AI opening.
Global `A[] !(ac && heater)` is intentionally not a requirement.
Deadlock freedom is not a fairness or no-Zeno proof.

Verification status: **pending**. UPPAAL 5.0.0 attempted verification but returned
`License does not cover verifier.` The XML has been parsed locally, but verifier
syntax/semantics and all queries still require actual UPPAAL acceptance.

Python tests cover 360 finite state/source/command combinations at selected clock
representatives and multi-step traces. This does not constitute full equivalence
between XML and Python; no such proof is claimed before verifier-based checks.
