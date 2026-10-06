# Stage two evidence — 2026-10-07

## Runtime Automata

`smart-home-v1` checks two experimental AI rules before execution. Humans bypass
safety rules, but share validation, logging and observed-state updates. Blocked
requests preserve modes; time advances 30 seconds. No substitute off command.

Injected sequence: 15 rounds with the same requested commands in each mode.
Unshielded: 0 blocked. Shielded: 3 AI requests blocked, 2 human bypasses.
Both traces replay successfully. This is designed test evidence, not commands
spontaneously produced by the model or proof of physical hazards.

33 automated tests passed. The finite policy oracle covers 360 combinations of
AC/heater state, clock representatives, command and source. Multi-step tests
cover human conflict, human off/reopen, boundaries, state mismatch, log failures,
replay tampering and actual local HTTP. This is not full XML/runtime equivalence.

## Real model review

| Configuration | Valid / 40 | Expected / 40 | Gate |
|---|---:|---:|---|
| Qwen3-1.7B revised prompt + tools | 40 | 10 | Failed |
| Qwen3-1.7B revised prompt + structured JSON | 36 | 5 | Failed |

Four separate development scenarios precede the unchanged eight evaluation
scenarios, each repeated five times. No oracle enters the prompt. Configuration
is frozen before each evaluation; raw output is not repaired. Temperature zero
means repeats are not independent statistical trials. Both bounded attempts failed;
no further prompt tuning, larger model, paid API or training was introduced.

Real shielded model loop: 12 rounds, 0 blocked. This trace does not demonstrate
model-originated violations. The raw proposal evidence remains separate from the
injected test sequence. Failed action-quality gates do not invalidate Automata tests.

## Home Assistant and resources

Actual Home Assistant smoke checked 17 entities, goal update, queued human request,
one human round and AI resumption. A shared trace contains smoke and real loop
rounds. The added sensors expose decision, reason and cooldown state.

Resource samples were collected on the 32 GB host while the stack was running.
They are not guaranteed peaks and do not certify RAM 8 GB compatibility. No OOM
was observed during these runs. Full friend-machine acceptance remains pending.

## Formal verification gate

The generated UPPAAL model and eight queries are present. UPPAAL 5.0.0 was downloaded
from its official distribution and verification attempted, but exited 1 with:
`License does not cover verifier.` **No query result is claimed.** A verifier-capable
academic license and actual syntax/semantic checks are still required. See
`verification-status.json` and `../../formal/smart-home.xml`.

## Files

- `injected-*.jsonl`, `injected-results.json`: labelled designed command sequences.
- `model-*.jsonl`, `gate-*.json`: both real model configurations, including failures.
- `real-ha-and-loop.jsonl`, `real-loop-results.json`: actual HA and model rounds.
- `ha-smoke.json`, `resource-samples.json`: actual integration/resource evidence.
- `runtime-checks.json`: replay and observed check durations, excluding durable I/O.
- `verification-status.json`: failed verifier attempt, not a mathematical proof.
- `manifest.json`: evidence hashes for reproducibility.

All physics parameters remain synthetic. Claims cover command policy under the
stated assumptions, not temperature bounds, real equipment or global home safety.
