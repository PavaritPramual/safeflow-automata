# SafeFlow AI

A formal framework for automata-based runtime control of AI proposals.

SafeFlow loads a site definition, checks it with UPPAAL, and evaluates incoming
proposal events before an environment executes them. The first case study uses
Ollama, a synthetic one-room home, and Home Assistant. Model intelligence is not
an acceptance gate for the supervisor.

## Current status — 2026-10-27

The YAML/IR engine, versioned session API, observation monitoring, Ollama and
OpenAI-compatible adapters are implemented. The production entry point requires
a complete, matching UPPAAL verification bundle.

**UPPAAL passes all 12 properties** for the current home definition. An independent
mutated-guard test fails the conflict/cooldown properties as expected. Actual
Ollama + Home Assistant runs include human intervention and autonomous resumption,
with sealed traces conforming to the pinned definition. See the
[acceptance report](experiments/implementation-2026-10-27/README.md) for exact test
results, raw outputs, observed limits and earlier unsuccessful attempts.

The successful [verification bundle](experiments/implementation-2026-10-27/verification/attempt-07/verification.json) binds to
this implementation and the local verifier binary. Other installations or changed
code/definitions must generate a matching bundle before activation.

The [pre-presentation acceptance](experiments/prepresentation-2026-10-27/README.md)
adds verified 90-second/renamed profiles and actual 1.7B/0.6B model switching,
without changing production Python source. The expanded suite passes 106 tests.

## Start here

- [Editable site definition and adapter settings](examples/smart-home/README.md)
- [Setup and Home Assistant operation](docs/guides/smart-home.md)
- [Edit a policy, switch profiles/models and rehearse](docs/guides/prepresentation.md)
- [Definition language, automata and formal assumptions](docs/guides/automata.md)
- [API request/response examples](docs/guides/api.md)
- [Architecture and SOLID boundaries](docs/development/architecture.md)

## Verify, then run

From the repository root, install the package into a virtual environment:

```powershell
./scripts/setup-local.ps1 -Python python
```

Use a verifier executable with appropriate license rights. Each output directory
must be new; do not overwrite evidence:

```powershell
./.venv/Scripts/python.exe -m safeflow verify --definition examples/smart-home/policy.yaml --output logs/verified-home-01 --verifyta /path/to/verifyta
./.venv/Scripts/python.exe -m safeflow serve --config examples/smart-home/lab.yaml --verification logs/verified-home-01
```

A failed verification keeps the control API unavailable. `/health`, `/state` and
`/v1/verification` explain readiness; no bypass flag is provided by this entry
point. For automatic rounds add `--interval 5`; each completed home round advances
30 simulated seconds. People use the Home Assistant dashboard at
[localhost:8123](http://localhost:8123). CLI administration starts and configures
the service; the API is the integration boundary for other programs.

```powershell
./.venv/Scripts/python.exe -m unittest discover -s tests -v
./.venv/Scripts/python.exe -m safeflow check logs/session-ID.jsonl
```

Set `SAFEFLOW_VERIFYTA` when running tests to include real verification and a
mutated-guard check. That integration test is explicitly skipped if the verifier
is unavailable. Unit subprocess fixtures are not formal evidence.

## Repository map

| Directory | Purpose |
|---|---|
| `src/safeflow` | Core, application service, API, verification and adapters |
| `tests` | Requirement oracles, adapter contracts, API and compatibility tests |
| `examples` | Editable definitions and site bindings |
| `docs` | Durable operator/developer documentation and research context |
| `formal` | Formal semantics and verification instructions |
| `experiments` | Curated evidence with provenance and limitations |
| `scripts` | Current setup, integration and resource tools |
| `tools` | Development-only prepared experiment utilities |
| `docker` | Home Assistant deployment and integration |
| `logs` | Ignored local runtime and build output |
| `archive` | Retired approaches and historical generators |

No presentation folder is reserved inside the package. The empty slide and module
placeholders were removed; the [migration table](docs/development/layout-migration.csv)
records moves. Earlier stage-one/stage-two results and prepared-command runs are
retained as historical evidence, not acceptance of this new architecture.

## Boundaries

Only the declared finite variables, actions, effects and timing abstraction are
verified. Thermal constants are synthetic. Trace conformance is limited to the
recorded path; interpreter replay is not an independent proof. Physical homes,
continuous RL actions, arbitrary UPPAAL syntax and 8 GB hardware acceptance are
not established. Credentials, model weights and Home Assistant storage remain
local and ignored by Git.
