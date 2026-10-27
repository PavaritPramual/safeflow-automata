# Formal verification

Current models are generated from the typed YAML/IR definition by
`safeflow.verification.compile_model`; do not maintain a second hand-coded rule set.
Run `python -m safeflow verify` to create a new immutable bundle, including XML,
queries, identities, raw verifier output and per-property results.

See [semantics and supported constructs](../docs/guides/automata.md).
The hand-written predecessor and generator are retained under
[archive/prototype-v3](../archive/prototype-v3/README.md) for provenance only.
The [current bundle](../experiments/device-rules-2026-10-28/verification/A/verification.json)
passes all 30 properties for the declared abstraction. Raw verifier outputs and
a mutated-guard failure are retained with the acceptance evidence. This does not
prove the Python implementation or physical homes correct for all behaviors.
