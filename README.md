# SafeFlow AI

SafeFlow AI: A Formal Framework for Automata-Based AI Runtime Control is a research workspace for studying automata-based runtime enforcement over actions proposed by an external AI agent.

This repository contains only SafeFlow-owned experiment scripts, curated evidence, research documentation, and future source-code boundaries. Sinergym and EnergyPlus are external simulation dependencies and are not vendored into this repository.

## Current scope

The current artifact is an unshielded baseline experiment using:

- Sinergym environment `Eplus-5zone-hot-discrete-v1`
- Stable-Baselines3 PPO with `MlpPolicy`
- A bounded discrete action space containing actions 0 through 9
- A 10-step JSON execution trace

No Automata Enforcer, safe fallback, policy parser, or environment wrapper has been implemented in this repository yet.

## Workspace structure

```text
configs/       Policy and configuration boundary (currently documentation only)
docker/        Container usage documentation
docs/          Research context, slides, and variable guides
experiments/   Curated, versioned experiment evidence
logs/          Disposable runtime logs; ignored by Git
scripts/       Executable experiment entrypoints
src/           Future SafeFlow implementation boundary
tests/         Future SafeFlow tests
```

## Run the unshielded baseline

Run the command from this repository root in PowerShell. The Docker image must
include Sinergym's optional `drl` dependencies because this experiment imports
Stable-Baselines3. Build the image from an external Sinergym checkout when it
is not already available:

```powershell
docker build -t sinergym:latest --build-arg SINERGYM_EXTRAS="drl" <path-to-sinergym>
```

Then run the experiment:

```powershell
docker run --rm -v "${PWD}:/workspace" -w /workspace sinergym:latest python scripts/experiments/real_ai_unshielded.py
```

The script writes its runtime result to:

```text
logs/execution_logs.json
```

EnergyPlus may also create `Eplus-*-res*/` and `episode-*/` directories. These generated outputs are excluded by `.gitignore`.

## Baseline evidence

The preserved trace from the initial unshielded run is stored at:

```text
experiments/unshielded-baseline/execution_logs.json
```

Runtime logs and curated experiment evidence are deliberately separated so that rerunning a script cannot overwrite the recorded baseline.

## External simulator boundary

The local Sinergym checkout used during development remains outside this repository at `../external/sinergym/`. Its upstream source layout is not part of SafeFlow and must not be reorganized as part of this project.
