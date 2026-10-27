# Architecture and implementation decisions — 2026-10-27

The maintainer writes a YAML definition. The loader builds a typed finite IR;
the runtime interpreter and UPPAAL exporter consume that IR. The normative model
(A), real proposer (B), environment (C), scenario (F), and observed path (X) have
distinct responsibilities. X contains ordered observations, not invented paths
formed by merging graph edges.

## Dependency boundaries and SOLID

- `core`: definition validation, restricted expressions, state, event guards and clocks.
- `service`: pinned sessions, durable decisions, one pending observation, idempotence.
- `verification`: UPPAAL export, subprocess results, immutable identity checks.
- `monitoring`: ordered X/A checks and first-mismatch reporting.
- `adapters`: native provider output and one-room simulator APIs.
- `application`: the composition root that selects concrete implementations.
- `api` / `cli`: transport and administration; no policy decisions.

The core and session service import no Ollama, Home Assistant, native command
schema or simulator implementation. Protocols in `ports` describe small contracts.
Implementations need no common superclass. A new provider implements metadata,
propose and normalize, then is registered at the composition root. A new
environment implements sample, execute, goals and reset; external systems may
instead call the versioned API directly.

SRP separates the reasons for change. OCP is demonstrated by changing site IDs,
parameters or provider adapters without editing the engine. Contract tests check
substitutability (LSP). Separate proposer/environment/log/verifier ports implement
ISP. Constructor injection and the composition root implement DIP. Domain-specific
bindings and the Home Assistant display mapping remain in the case-study layer.

## Runtime flow

1. Sample authoritative environment facts and time; compare with the session.
2. A human request replaces one AI proposal, otherwise call the real provider.
3. Persist the raw response and actual request metadata before normalization.
4. Normalize to an event and optional opaque action ID. Invalid output and timeout
   are event kinds; their handling is declared by the policy.
5. Resolve exactly one transition, evaluate runtime assertions, persist the decision.
6. Execute only an allowed action. A blocked round still advances environment time.
7. Read the actual effect; validate it against the declared action effect, update
   clocks from actual changes, persist the observation, then commit session state.

No received proposal implicitly changes device state. No wall-clock inference
latency advances simulation time. Application effects are atomic at decision time
in v1; an observation reports the resulting facts after an explicit nonnegative
environment delay. Delayed/asynchronous physical acknowledgements need a future
contract and are not silently accepted.

An unknown or ambiguous transition halts. A missing or changed verification
receipt prevents activation. Log failures halt before executing an undecided
proposal. A result-write failure after execution leaves a pending/fault trace;
it is not safe to retry execution as if it had never happened.

## Formal checking and independent evidence

The exporter emits clock constraints as transition guards, with committed
locations for instantaneous decision/application phases. State variables have
finite domains. A declared action applies literal variable effects. Clock resets
are predicates over before/after observations. Environment delay is arbitrary
nonnegative time, over-approximating the case study's 30-second steps.

Properties are independent invariant/reachability assertions at decision or
observation boundaries, plus deadlock and transition-completeness queries.
Hashes bind the definition, IR, generated model, queries, converter version and
verifier binary/results. Receipts are trusted local administrator artifacts;
hashes detect stale changes, not a malicious administrator forging files.
HTTP clients cannot upload verification receipts or executable paths.

Runtime assertion/trace replay shares expression semantics with the engine.
Independent requirement oracles and real UPPAAL integration/mutation tests are
therefore also required. A successful unit suite does not prove equivalence of
all generated models and programs. Actual verification passes 12 properties for the current home model; a mutated
guard is rejected. Concrete generated-XML stepping and independent home-rule
oracles supplement real-loop traces. These checks do not establish general
compiler correctness for every future definition. The early license/parser/type
errors are retained separately from the successful current results.

## Compatibility and Git

The supported entry points are `safeflow` and `python -m safeflow`. The old
`python -m safeflow.server` redirects to the verified service. Earlier root modules
remain solely for v2/v3 historical replay, regression and prepared experiments;
new code uses `core`, `service`, `runner` and the new adapters. The legacy v2
interpreter is explicitly under `compat`.

Checkpoint 27ee31d retains the inherited uncommitted work. Subsequent commits
separate structure, the YAML/IR + verification engine, API/adapters, and validation
evidence. No push, merge, credential replacement, account bootstrap or persistent storage
reset is part of this implementation. The owned HA container was started for
acceptance and uses its existing account and storage. Historical generators retain their original embedded paths and
must not be run as current build tools.
