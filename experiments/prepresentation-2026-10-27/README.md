# Pre-presentation acceptance — 2026-10-27

This is evidence of configurable supervisor reuse, not an AI-quality evaluation.
Production Python source under src/safeflow is unchanged from d46a821. The original
180-second example and its accepted bundle remain the baseline.

## Requirement and verification results

| Profile | Rest requirement | Definition identifiers | Decision at elapsed 120 s | UPPAAL |
|---|---:|---|---|---|
| A | 180 s | original | block | 12/12 pass |
| B | 90 s | original | allow | 12/12 pass |
| C | 90 s | cooling_unit, cooling_on, cooling_off | allow | 12/12 pass |

[Fresh actual verifier outputs](verification-summary.json),
[controlled real-HTTP results](controlled/summary.json), and
[rejected activations](controlled/rejections/report.json) support this table.
The controlled tests use exact times 0, 89, 90, 91, 120, 179, 180 and 181 seconds,
plus first use, repeated off, human exception/resumption, invalid output and timeout.
They send prepared, explicitly labelled test inputs and call no LLM. The native
simulator supplies actual effects at controlled delays; ordinary live rounds still
advance 30 simulated seconds. Seven wrong/stale bundle activations return 503 and
create no session traces. Production bindings are also exercised against native C.

## Actual model and Home Assistant results

| Case | Actual model | Native replies after test baseline | Total completed rounds | Blocked | Closed trace / replay |
|---|---|---:|---:|---:|---|
| B-17 | qwen3:1.7b | 4 | 9 | 0 | conforms / replay matches |
| C-17 | qwen3:1.7b | 4 | 10 | 0 | conforms / replay matches |
| C-06 | qwen3:0.6b | 4 | 5 | 0 | conforms / replay matches |

[Closed-run checks](live-checks/summary.json) validate X/A, the independently
specified oracle and deterministic simulator replay. Each case also has an actual
HA goal update and at least one native air-conditioner request from a human, then
AI resumption. In C the HA request becomes cooling_on through the configured
bindings. Initial automatic rounds before the test baseline and any final completed
round are retained and counted in the full trace, not confused with the minimum
four responses checked during the live phase.

This acceptance covers model selection within the existing Ollama provider.
C-17 and C-06 have the same policy hash, bindings, prompt configuration and actual
request options (including seed). The selected model name and digest differ.
All chosen model tags were read from the actual local Ollama service before and
after acceptance. Raw requests/responses remain in each trace before normalization.
No model was downloaded, trained, replaced by prepared responses, or prompted to
produce a preselected violation. The controls and rule decision are the acceptance
criteria; usefulness of model actions is outside this check.

The first C-06 run met response criteria but shutdown overlapped a subsequent model
request, producing shutdown_requested instead of a sealed complete run. It is not
accepted. [The retry ledger](shutdown-retry.json) records this and the local ignored
raw-log location. Accepted C-06 was rerun with a 20-second wall pause to allow clean
shutdown, versus 5 seconds for B-17/C-17. Every run still advances 30 simulation
seconds per completed round. This is not a speed or paired model-quality benchmark.
No production code was changed to make the retry pass.

## Validation and provenance

- [106/106 tests, no skips](tests-summary.json), including original real UPPAAL
  integration/mutation and new profile/API/oracle/native-response tests.
- [Baseline production source hashes](baseline.json) and the closed-run source
  comparison show that every production Python file is unchanged.
- [Verification/A](verification/A/verification.json), [B](verification/B/verification.json),
  [C](verification/C/verification.json) each bind their own definition and model.
- Each live case has report.json for the successful live prefix. It is not by itself
  a sealed-trace certificate: live-checks performs the required post-shutdown checks.
- All tests and raw controlled traces are marked not_real_ai; actual runs are under
  live/. No unverified-control path or normal API contract was added.

Re-run controlled HTTP acceptance with
`python -m tools.profile_acceptance --output NEW_DIRECTORY` after verification.
Re-run independent closed-run checks with
`python -m tools.check_profile_runs --output NEW_DIRECTORY`.
The home trace oracle accepts --contract pointing to the independent requirements
file; legacy usage without that option still uses the 180-second original names.

See [the operator rehearsal guide](../../docs/guides/prepresentation.md).

These results establish only the tested home-case configurations and observed
paths. They do not establish arbitrary physical devices, all domains, compiler
correctness for every future definition, or an 8 GB hardware acceptance. No slides,
signed proposal, Canva design or main-branch merge was changed in this work.
The temporary backend and the owned HA container were stopped after acceptance;
existing HA account/storage were preserved and Ollama was left running as before.
