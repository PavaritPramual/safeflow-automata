# Recorded stage-one feasibility run — 2026-10-06

These are **real Ollama and Home Assistant runs**, separate from fixture tests.
The prototype logs proposals before simulated execution. There is no Automata
Enforcer and no UPPAAL verification in this stage.

## Model gate

| Candidate | Valid commands | Expected actions | Gate |
|---|---:|---:|---|
| Qwen3-0.6B | 0/40 | 0/40 | Failed |
| Qwen3-1.7B | 40/40 | 20/40 | Failed |

Required: at least 36 valid and 32 expected commands in 40 requests. Eight declared
normal scenarios were reset before each call and run with seeds 0–4. Temperature
was 0; repeated outputs are not independent statistical trials. The same fixed
prompt/tool schema was used for both models. This is a feasibility gate, not a
comparison benchmark or a general model-capability claim.

0.6B returned empty assistant messages without usable tool calls. Those responses
did not change any device. 1.7B returned structurally valid commands, but half
failed the declared task oracle; for example, hot/cold idle-room scenarios produced
light commands rather than the expected thermal command. Raw outputs are retained.
This establishes a failure of this model/configuration/prompt stack, not that the
model can never work with a different stack. No output was repaired into a command.

**Decision:** both candidates failed. Stop before the Enforcer/UPPAAL stage and
review model/prompt selection with the user. Do not silently change the gate or
claim readiness for autonomous home control.

## Integration and validation

- 21 automated tests passed: analytic physics, strict decoding, replay, FIFO human
  commands, real HTTP fixture, log failures and simulator failures.
- Actual Home Assistant 2026.9.4 loaded all 14 SafeFlow entities.
- Actual HA service calls changed the target and lighting goal, queued a direct
  light request without immediately changing the device, executed that request
  as one human round, then resumed AI on the next round.
- The real 1.7B trace, including those HA rounds, replays deterministically.
- The automatic-round backend ran four rounds (120 simulation seconds) without
  manual step calls. This demonstrates scheduling/logging, not good control.
- Baseline Sinergym evidence is preserved with its original SHA-256.

## Resources and limits

Host RAM: 34,085,847,040 bytes (approximately 32 GiB), Python 3.12.14,
Ollama 0.35.1, CPU-only inference, context 2,048 tokens, no training.
The friend's **8 GB constraint remains unverified**.

At one sample HA reported 276.8 MiB of its 1.5 GiB cap, Ollama reported loaded
allocation sizes of about 1.53 GiB (1.7B) and 0.73 GiB (0.6B). Both candidates were
still cached at that sample; 0.6B was subsequently unloaded. This is not peak RAM
or whole-machine demand. WSL's resident sample was approximately 6.3 GiB, including
shared Docker/WSL overhead and cache. Adding only model and HA memory would hide
this overhead and cannot certify that the friend's machine will fit.

Synthetic physics has no real-home calibration. No safety, equipment-hazard,
latency guarantee, model/runtime formal agreement or 8 GB success is claimed.

## Evidence

- `gate-06b.json`, `gate-17b.json`: all 40 decisions against declared oracles.
- `trace-06b.jsonl`, `trace-17b.jsonl`: raw proposals and execution events.
- `ha-smoke.json`: real service/state checks.
- `resources.json`: point-in-time resource sample, not a peak measurement.
- `resource-samples.json`: six resource samples during automatic rounds, with
  0.6B unloaded. Sampled maxima are not guaranteed peak memory.
- `trace-autonomous17.jsonl`: actual automatic-round events.
- `manifest.json`: exact evidence SHA-256 values and software identifiers.

Credentials, model weights and local HA storage are excluded.
