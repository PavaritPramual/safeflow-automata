# Research context

SafeFlow AI: A Formal Framework for Automata-Based AI Runtime Control studies
external interception of AI commands. Its case study may change without equating
the model or environment with the framework itself.

The new first stage uses a small pretrained local LLM and one simulated room with
air conditioning, heating, ventilation and lighting. Home Assistant displays
state and accepts human requests; it is not the physics simulator. RC physics
and electrical power give observable consequences, not real-world safety proof.

Stage one demonstrates model proposals and durable pre-execution traces. Stage
two adds conflict and minimum-off-time automata, offline UPPAAL safety/deadlock
checks, and model/runtime agreement. The proposed 180-second off time is an
experimental policy parameter, not a manufacturer's requirement.

Observed behavioral graphs and normative safety automata are separate. Unobserved
transitions are not automatically impossible or unsafe. Model checking concerns
the model and its assumptions, not all AI, runtime code or physical homes.
No graph-subset proof or constant-time runtime claim is assumed.

The preserved Sinergym run demonstrates historical logging only. New simulation,
model, latency and safety results must be measured before being claimed.
