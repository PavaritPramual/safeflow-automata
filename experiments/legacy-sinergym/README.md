# Historical Sinergym / PPO baseline

This preserves the original unshielded experiment, not the new case study.
The agent was an untrained Stable-Baselines3 PPO MlpPolicy.

- Environment: `Eplus-5zone-hot-discrete-v1`.
- Ten actions: `6 -> 7 -> 3 -> 1 -> 4 -> 9 -> 4 -> 0 -> 4 -> 3`.
- Trace SHA-256: `082bcc4e33f20e6c1ff8f367e0518b2dc56d665f686bdee03d374931c49e6644`.

Action IDs represent setpoint combinations. The `0 -> 4` pair does not establish
compressor on/off state, cooldown violation or short-cycling. Observation indices
must be checked against the environment before treating them as indoor temperature.
The original script and trace remain unchanged, including their original labels;
do not use these as verified semantics.

There is no trained checkpoint, enforcer or UPPAAL proof in this run.
See [historical Docker instructions](docker-workflow.md). Run the retained script
from the repository root with `python experiments/legacy-sinergym/real_ai_unshielded.py`.
Reruns write ignored `logs/execution_logs.json`, not this preserved trace.
