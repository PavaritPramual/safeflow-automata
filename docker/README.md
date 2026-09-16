# Docker workflow

SafeFlow uses the external `sinergym:latest` image. This repository is mounted at `/workspace`; the Sinergym source repository is not copied or vendored here.

The unshielded experiment imports Stable-Baselines3, so the image must include
Sinergym's optional `drl` dependencies. Build it from an external Sinergym
checkout if necessary:

```powershell
docker build -t sinergym:latest --build-arg SINERGYM_EXTRAS="drl" <path-to-sinergym>
```

Run from the SafeFlow repository root:

```powershell
docker run --rm -v "${PWD}:/workspace" -w /workspace sinergym:latest python scripts/experiments/real_ai_unshielded.py
```

The container writes runtime JSON to `/workspace/logs/execution_logs.json`, which maps to `logs/execution_logs.json` on the host.
