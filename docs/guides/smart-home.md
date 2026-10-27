# Run the verified one-room case study

## Setup

Use Python 3.11+, a licensed UPPAAL verifier, Ollama and Docker Desktop for the
Home Assistant lab. From the repository root:

```powershell
./scripts/setup-local.ps1 -Python python
ollama pull qwen3:1.7b
```

Setup creates a random ignored local API key and supplies it to the ignored HA
secrets file. It installs the editable Python package, including PyYAML. Never
commit `.env`, secrets, tokens, model weights or persistent HA storage.

Edit `examples/smart-home/policy.yaml` for automata and
`examples/smart-home/lab.yaml` for bindings/provider settings. Bindings map each
formal variable to a native simulator device; each allowed action maps to a
native command. The lab reads synthetic physics from `configs/home.json`.

## Verify and start

Use a new output directory and your licensed verifyta executable:

```powershell
./.venv/Scripts/python.exe -m safeflow verify --definition examples/smart-home/policy.yaml --output logs/verified-home-01 --verifyta /path/to/verifyta
./.venv/Scripts/python.exe -m safeflow serve --verification logs/verified-home-01
```

The current retained home bundle passes all 12 properties and is the default in
lab.yaml on this workstation. Early attempts with a license error and exporter
errors are retained as unsuccessful development evidence. A different executable,
implementation, definition or property needs a new matching bundle. Until a bundle
passes, the process exposes readiness but cannot call the model or execute a home
step; there is no ordinary unverified-control option.

In a separate terminal start only the configured lab:

```powershell
docker compose -f docker/compose.yaml up -d
```

Open [Home Assistant](http://localhost:8123) and select SafeFlow Lab. If this is a
fresh instance, create its local account normally. Existing accounts/storage are
preserved. The dashboard shows readiness, decisions and device state. Human
switches queue one command; Run one round uses that request before asking AI.
Adding `--interval 5` to the service enables automatic rounds with a five-second
wall-clock pause. Each completed round advances 30 simulation seconds regardless
of model latency. Ctrl+C requests stop; a response arriving after stop is logged
without a new environment operation.

Choose another model with `--model NAME`, or edit proposer settings. The
OpenAI-compatible adapter supports a compatible /v1 URL and an api_key_env field
containing only an environment-variable name. No remote provider is invoked by
the test suite and no paid call was made during implementation.

## Trace and recovery

Each session gets a new JSONL file. It contains pinned definition/verification,
raw provider request/response, normalized events, decisions, observations and
closure. Observations retain raw simulator measurements alongside the mapped
formal facts, so device, temperature and energy data can be traced back to C.
Decision writes flush/fsync before the adapter may execute. A write or
observation failure halts the session. If the operation may already have happened,
inspect the actual environment before starting a new session; do not blindly retry.

```powershell
./.venv/Scripts/python.exe -m safeflow check logs/session-ID.jsonl
```

The check is limited to X and uses the runtime interpreter; requirement-oracle and
UPPAAL tests supply separate checks. Historical v2/v3 logs remain readable through
their compatibility paths. They are not converted or relabelled as new evidence.

## Physical and resource boundaries

The environment is a synthetic one-room RC heat-balance model with analytic
constant-input evolution and power integration. Ventilation exchanges outside air
and can warm the room when outside is hotter. No humidity, air quality, physical
circuit, 3D building or validated appliance behavior is claimed.

The target friend's 8 GB host is still untested. Record the backend, model, HA,
Docker/WSL and OS footprint together; model file size is not RAM acceptance.
Existing stage-two model-quality failures remain historical results and are not
requirements for SafeFlow to correctly supervise proposals.

The lab API uses its existing bearer-key authentication. It is a single-writer
research prototype, not a public internet or concurrent physical-device gateway.
Stop the service with Ctrl+C; stop only the lab with
`docker compose -f docker/compose.yaml stop`. These preserve data and evidence.
