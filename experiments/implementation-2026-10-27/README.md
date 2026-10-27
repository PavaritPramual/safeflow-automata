# Implementation acceptance — 2026-10-27

Branch: `feature/declarative-automata-evidence`. This bundle contains actual
verification and actual-provider integration evidence, with test doubles labelled
separately. No paid provider call, physical device, new account, or model training
was used.

## Results

| Criterion | Observed result |
|---|---|
| Current automated suite | **99 passed, 0 failures/errors/skips**, including real local HTTP and real UPPAAL |
| Current normative home model A | **12/12 properties passed** with UPPAAL 5.0.0 |
| Deliberately wrong conflict guard | Real UPPAAL rejects conflict and early-restart properties; bundle remains not_ready |
| Independent requirement oracle | 360 state/source/action/clock combinations in the new engine tests |
| Exporter/runtime agreement samples | 375 concrete generated-XML transitions including declared halt; not a symbolic proof |
| Actual Home Assistant API | 18 entities, goals, queue-before-execution, one human round, AI resumption |
| Full-observation autonomous run (313fa74) | **11 rounds: 10 actual Ollama proposals + 1 human request**, 330 simulated seconds |
| Raw C observations in that autonomous run | 11/11 include native devices, temperature, power and energy alongside formal facts |
| Final checkpoint HA run (95df7b4) | 2 rounds: actual human command then actual AI, with full observations |
| All retained real runs | 30 executed rounds: 26 actual AI proposals + 4 human requests; all sealed X paths conform |
| Deterministic replay of current C | 11 native snapshots and 10 AI input snapshots match exactly |
| Independent live-rule oracle | 30 decisions/effects/clock updates match independently computed home requirements |
| Actual AI blocks in these runs | **0**; all model responses selected light_on. No real-model rule violation is claimed |
| 8 GB target machine | Not tested; no compatibility/resource acceptance claim |

## Evidence links

- [Current suite summary](tests-summary.json) and [complete output](tests.txt).
- [Current activation bundle](verification/attempt-07/verification.json),
  [generated model](verification/attempt-07/model.xml), and individual raw verifier outputs beside it.
- [Independent actual UPPAAL integration](formal-integration-final/original/verification.json)
  and [mutated-guard results](formal-integration-final/mutated/verification.json).
- [Final actual HA service test](ha-smoke-final.json), [current autonomous run](live-current.json),
  [all X/A reports](live-conformance.json), [independent live oracle](home-oracle-final.json), [environment replay](environment-replay.json),
  and [service preflight](service-preflight.json).
- [Current full raw trace](current-traces/session-c5529bd7-fbba-4a0c-9ead-b7b938e4177d.jsonl).

The earlier live-traces and autonomous-traces runs predate the additive native
observation-evidence field. They are retained as historical valid runs for that
implementation, not relabelled as current raw-observation coverage. The empty
startup session is also sealed and has zero executed rounds.

Every current AI receipt retains its actual provider request, seed/options,
messages, and raw response before normalization. Actual-provider identity is
qwen3:1.7b; the local tag/digest was recorded in service-preflight.json. No prepared
agent is used in these real traces. The human heater request was sent through the
actual HA switch service; it replaced one automatic AI round, then AI resumed.
Repeated light_on proposals are allowed by the rules and are not evidence of
useful temperature control; AI quality is outside this supervisor acceptance.

The saved scripts/check-home-trace.py oracle reads recorded raw JSON action IDs, compares decisions
with the two home rules independently of Runtime, checks literal effects, verifies
30-second progression and actual-off clock resets, and compares native device
snapshots to formal facts wherever that evidence is present. It is specific to
this case study, not a general proof of all domains.

## Reproduce on the owned lab

Run from the repository root with the existing lab account/storage:

```powershell
./.venv/Scripts/python.exe -m safeflow serve --interval 5 --logs logs/new-live-run
```

In another terminal start only the lab container if needed, then use the existing
refresh-token file (or supply its path; no bootstrap is performed):

```powershell
docker compose -f docker/compose.yaml up -d homeassistant
./.venv/Scripts/python.exe scripts/check-live-loop.py --rounds 8 --output logs/new-live-report.json
```

Stop between completed rounds to obtain a sealed trace, then run
`python -m safeflow check TRACE`. An in-flight shutdown can intentionally produce
a terminal fault/incomplete path rather than falsely claiming a completed episode.
Use a new output path each time. Actual model proposals may differ between runs.
On another installation regenerate a matching verification bundle with the local
licensed executable instead of assuming the retained absolute executable path exists.

For actual verifier tests set SAFEFLOW_VERIFYTA. Optionally set
SAFEFLOW_FORMAL_TEST_OUTPUT to a new directory to retain original/mutated artifacts.
A syntax or engine error fails that integration test; only the explicit known
license-unavailable condition is skipped. Unit subprocess fixtures stay temporary
and cannot be presented as real verification.

## Development provenance and limits

Verification attempts 01/02 recorded the initial license-unavailable execution
context. Actual verification in a permitted process context exposed exporter
syntax/schema/clock-guard errors, retained in attempts 03/04 and the failed first
suite attempt. Those errors were fixed rather than treating them as proof skips.
Attempt 05 passes for source checkpoint 82cc137; attempt 06 also binds the added
raw-observation logging in 313fa74. Old bundles cannot activate a changed source
fingerprint. Paths were grouped without modifying original output contents; raw
verifier diagnostics therefore retain their original execution paths.

Attempt 07 binds the final terminal-halt correction at source commit 95df7b4.
The declared stop now seals normally without an observation or time advance in
both the generated model and runtime; an absent halt seal is inconclusive.
The final HA test was repeated against this exact code and successful bundle.

Trace context.config preserves the originally loaded settings; CLI verification
overrides are represented by the effective session_start.verification identity.
The final example default now points to attempt-07. The HA container and temporary
backend were stopped after acceptance, preserving the existing account/storage
and restoring the container state observed before testing. Ollama was left alone.

The final full-suite files supersede the earlier before-observation-evidence
suite for current-code acceptance. Earlier reports remain historical evidence.
The source checkpoint before this work is 27ee31d; subsequent Git commits retain
structure, engine/verification, API/adapters, semantic fixes, and observation work.
No push or merge was performed.

UPPAAL establishes only the listed model properties under the declared finite,
atomic-effect and timing abstraction. Sampled XML stepping, runtime assertion
monitoring and trace replay do not prove total compiler/runtime equivalence or
all possible AI behavior. Replay shares the runtime interpreter; independent
oracles and actual verifier mutation evidence supplement it. Continuous actions,
asynchronous physical acknowledgements, arbitrary domains and 8 GB acceptance
remain outside this delivery. The existing Graphify pilot was not rebuilt and
its source hashes must be checked before reuse.
