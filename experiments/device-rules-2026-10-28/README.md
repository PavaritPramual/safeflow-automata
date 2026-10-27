# Four-device rules acceptance — 2026-10-28

**A is the primary demo: 180-second AC rest.** B/C are optional configuration
examples, not three competing primary systems. Definitions now explicitly name
AC start/stop, heater start/stop, fan control, light control and hold transitions.
The allowed/blocked outcomes are preserved from the previous case study; this
change completes and independently checks the specification rather than inventing
new safety thresholds for fans or lights.

## Scope and decisions

| Device / command | Requirement |
|---|---|
| AC start | AI blocked if heater on, or AC off with active rest clock below 180 s |
| AC stop | Permitted; resets rest only on actual cool-to-off transition |
| Heater start | AI blocked if AC on |
| Heater stop | Permitted |
| Fan on/off | Permitted, changes fan only |
| Light on/off | Permitted, changes light only |
| Hold | Permitted, no device change; simulation time continues |
| Human proposals | Explicit exception to conflict/rest, still require declared command and exact effects |
| Invalid/timeout/adapter_error | Block, preserve devices, advance observed time |

Goals are inputs to the proposer, not safety requirements. There is no invented
fan timer, lighting restriction, global energy cap or temperature safety bound.
This is a synthetic home case, not complete physical-appliance safety coverage.
See the [Thai rule catalogue](../../docs/guides/home-rules.md).

## Evidence

- [Definitions and actual UPPAAL reports](verification/) have 30 properties each:
  28 declared assertions plus deadlock and decision completeness. Each profile
  has its own bundle; definition, IR, model, queries, converter and verifier are bound.
- [Independent controlled cases](device-cases.json): 1,728 per A/B/C, 5,184 total.
  They cover all 16 device combinations, both sources, nine actions and six clock
  cases. Expected effects and thresholds are specified separately from YAML.
  They are controlled tests, not actual AI responses.
- [Complete suite](tests-summary.json): 109 tests, no errors/failures/skips;
  [raw test output](tests.txt) includes actual UPPAAL original/conflict-mutation
  integration and XML-path comparison. The [seven profile tests rerun](followup-tests.json)
  after the utility fix are already in this count, not seven extra unique tests.
- [Controlled HTTP acceptance](controlled-current/summary.json): A blocks at 120 s;
  B/C allow. Tests include boundaries and seven wrong/stale activation rejections.
- [Actual verifier mutation checks](verification-summary.json): intentionally block
  otherwise-permitted fan commands, or declare light_on to change the fan too.
  The relevant independent properties must fail. Mutated models are never activated.
- [Actual A smoke](main-A-live-prefix.json) covers goal editing and real HA button
  requests. [Post-closure checks](live-checks.json) validate the sealed three-round
  trace with one native Ollama response and two human rounds against the monitor
  and independent home oracle. The prefix report alone is not the closure certificate.
- [Actual A resumption](live-resumption-checks.json) has a sealed two-round trace:
  a human command followed by an actual native AI response. These are two actual
  AI replies across two runs, not the four-reply provider-swap acceptance from 27 October.
- All raw accepted A traces are in [live/](live/). They identify the current definition
  and native request/response. No model choice or violation was staged.
- [Baseline source hashes](baseline.json) support that production src/safeflow
  Python is unchanged. YAML, configuration, tests, documentation and an acceptance
  utility changed. Historical evidence directories remain unchanged locally.

## Attempts and delivery

[The attempt ledger](attempts.json) distinguishes the initially rejected stale-bundle
utility call and an empty unsealed old B demo session from accepted evidence.
The utility now reads each current lab.yaml, with an optional --verification-root;
it no longer silently chooses the 27 October proof for a changed definition.

The normal demo was switched from old B to a new verified A session. After checking,
HA's reset button sealed each test run and returned the demo to an empty A session
with default goals/time/energy. The backend and HA are left running for the user.
Later user interaction can naturally change that initial state.

Reproduce from the repo root with a licensed native verifier:

```powershell
./.venv/Scripts/python.exe -m safeflow verify --definition examples/smart-home/policy.yaml --output logs/new-A-proof --verifyta /path/to/verifyta.exe
./.venv/Scripts/python.exe -m safeflow serve --config examples/smart-home/lab.yaml --verification logs/new-A-proof
./.venv/Scripts/python.exe -m tools.profile_acceptance --output NEW_DIRECTORY
```

The last command uses the three current lab configs' matching bundles. On another
installation, regenerate each of them first or supply --verification-root containing
fresh A/B/C directories. Unit subprocess fixtures are not native formal evidence.

No slides, signed proposal, physical devices, additional provider, continuous RL
interface or 8 GB host acceptance were added. Proof remains conditional on the
finite declared effects/timing abstraction; runtime observation checks remain required.
