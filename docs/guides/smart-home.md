# Smart-home prototype with Automata

AI commands now pass two experimental guards; human commands bypass them but remain logged.
UPPAAL verification and real-home safety are not established. See [policy specification](automata.md).

## Windows setup

Prerequisites: Python 3.11+, Git, Docker Desktop (Linux containers), Ollama.
The first recorded run used Python 3.12, Ollama 0.35.1 and Home Assistant 2026.9.4.
Home Assistant's image digest is pinned in `docker/compose.yaml`. No runtime Python
dependencies are required by the backend; its networking and tests use stdlib.

From the repository root:

```powershell
./scripts/setup-local.ps1 -Python python
ollama pull qwen3:1.7b
./.venv/Scripts/python.exe -m safeflow.server --model qwen3:1.7b --output-mode json --trace logs/home.jsonl
```

Keep that terminal running. In another terminal:

```powershell
docker compose -f docker/compose.yaml up -d
./.venv/Scripts/python.exe -m safeflow.evaluate --output logs/gate-06b.json
```

Open <http://localhost:8123>, create your **local lab** account, and choose the
SafeFlow Lab sidebar dashboard. Toggles queue a request, not an immediate device
change. Run one round executes the next human request, or asks AI if the queue is
empty. Reset episode clears the queue. Goal updates do not advance simulated time.

For automatic rounds, stop the backend and restart with `--interval 5`. That is a
five-second wall-clock pause between rounds; every completed round advances the
home exactly 30 simulation seconds. Use manual mode for gate evaluation to avoid
concurrent rounds. The model gets the latest goals and state every round, with no
chat history. Human goals are structured fields; natural-language user chat is not
part of this first scope.

The setup generates a random API key in ignored `.env` and writes it to ignored
`docker/ha-config/secrets.yaml`. The server binds all host interfaces to let the
container connect, requires the key on every control/state endpoint, and exposes
only a minimal unauthenticated health endpoint. The HA UI port is bound to loopback.
Do not commit `.env`, secrets, HA storage, tokens or model weights.

## Model feasibility review

The stage-two model configurations both failed the unchanged 36-valid/32-expected
thresholds in 40 calls. See [results](../../experiments/smart-home-stage2/README.md).
`--output-mode tools` uses one tool call; `--output-mode json` parses a strict JSON
command without repair. Neither filters outputs by safety policy. Raw responses
remain in the proposal record. The selected configuration is not certified for
successful autonomous control.

Safety enforcement is on by default. `--unshielded` is an explicit baseline mode.
Model-quality evaluation and Automata evaluation have independent acceptance gates.

## API and trace

All endpoints except `GET /health` require `Authorization: Bearer <local-key>`.

| Endpoint | Behavior |
|---|---|
| `GET /state` | Authoritative state, model metadata, queue count and stage |
| `POST /human` | Queue `{device, mode}`; reply 202 with request ID |
| `POST /goals` | Update `target_c` (10â€“40 Â°C) and/or boolean `light_required` |
| `POST /step` | One round, optional integer seed; direct human command wins |
| `POST /reset` | Reset scenario, trace a new episode, clear pending requests |

Unknown human commands enter the same logged validation path as AI. An invalid
goal never changes state. Reset is a lab operation, not an AI tool. The server is
a single-writer prototype: while a model call is pending, state/request operations
wait for that round's lock. It is not a concurrent real-time device controller.

JSONL records `reset`, `goals`, `human_request`, `proposal`, `decision` and
`execution`, with run/episode/proposal IDs. Proposal and decision are flushed and
fsynced before execution. If either write fails, the episode halts without applying
the command. If the simulator or execution-result write fails, the episode halts;
the preceding proposal/decision remains as evidence of the pending operation.
Do not retry such an episode without an explicit reset. No crash-transaction or
physical-device acknowledgement guarantee is claimed.

## Physics and provenance

The one-room energy balance is

`C dT/dt = UA (T_out - T) + Q_heater - Q_cooling + Q_light`.

Fan operation adds outdoor-air exchange conductance; it can warm the room when
outside air is hotter. Constant inputs use the analytic exponential solution; zero
conductance uses the linear solution. Power is summed in watts and integrated in
watt-hours. RC model structure is informed by the
[Modelica Buildings reduced-order documentation](https://simulationresearch.lbl.gov/modelica/releases/latest/help/Buildings_ThermalZones_ReducedOrder_RC_UsersGuide.html).
**Every numerical value in `configs/home.json` is synthetic**. None is fitted to a
real building or validated as an appliance specification. Weather is a fixed
scenario input. No humidity, air-quality, electrical-circuit or 3D model is claimed.

## Testing and actual integration

```powershell
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

The tests include analytic physics, replay, strict decoding, a real local HTTP
fixture, FIFO human requests and log/simulator failure injection. Fixture-agent
tests are not real-model evidence.

`scripts/ha-smoke.py --bootstrap-lab` is optional automation for **a fresh lab
container only**. It creates a random local lab account, saves credentials in
ignored `logs/ha-credentials.json`, checks real HA entities/services and proves
queued requests, goal changes, one human round and AI resumption. Later runs reuse
the saved refresh token. Do not use bootstrap against an existing personal instance.
The ordinary setup above lets you create your own account in the browser instead.

## RAM 8 GB constraint

The friend's 8 GB machine is an acceptance target, not this run's hardware. CPU
inference is forced (`num_gpu=0`), context is capped, one model should be loaded at
a time, and HA has a 1.5 GiB container cap. The backend is small and has no training
or replay buffer. These choices do **not** certify 8 GB compatibility.

Measure the backend, Ollama runner, HA, Docker/WSL overhead and host OS together.
The recorded host had 32 GB; WSL's resident footprint was already large and included
shared runtime/cache overhead. Do not infer RAM suitability by adding only model
file size and HA container usage. Required remaining check: run this setup on the
friend's 8 GB machine with other large models stopped and record peak memory/OOM.

## Stop

Stop the backend with Ctrl+C. Keep all traces, then stop only this lab:

```powershell
docker compose -f docker/compose.yaml stop
ollama stop qwen3:0.6b
ollama stop qwen3:1.7b
```

These commands retain images, configuration, accounts and evidence.
