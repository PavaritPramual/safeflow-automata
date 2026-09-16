# Unshielded baseline

This directory preserves the JSON trace produced by the original `real_ai_unshielded.py` experiment before a runtime safety enforcer was introduced.

## Experiment boundary

- Environment: `Eplus-5zone-hot-discrete-v1`
- Agent: Stable-Baselines3 PPO with `MlpPolicy`
- Recorded steps: 10
- Recorded action trace: `6 -> 7 -> 3 -> 1 -> 4 -> 9 -> 4 -> 0 -> 4 -> 3`

The transition from action 0 at step 8 to action 4 at step 9 is retained as an observed short-cycling hazard candidate for later policy evaluation. The baseline trace is empirical evidence only; it is not itself a formal proof or a completed safety mechanism.

Rerunning the experiment writes to `logs/execution_logs.json` and does not overwrite this curated trace.
