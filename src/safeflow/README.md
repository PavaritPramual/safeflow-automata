# SafeFlow source modules

`environment` is deterministic RC physics; `agent` only requests raw Ollama output;
`commands` validates the proposal shape; `trace` durably records and replays;
`controller` owns state changes; `server` exposes the authenticated API;
`evaluate` runs the declared real-model feasibility gate.

There is no safety enforcer in stage one. Reserved enforcer/wrapper directories
remain explicitly unimplemented until the model acceptance gate is resolved.
