# Editable site variants

A is the primary [180-second case](../policy.yaml).
All current profiles include the complete four-device rule catalogue; retained
2026-10-27 bundles are historical and must not activate changed definitions.
B is [cooldown-90](cooldown-90/policy.yaml); only parameters.rest_s changes.
C is [renamed-90](renamed-90/policy.yaml); its AC fact/action IDs also change.
Native devices and the proposer prompt are unchanged. Each variant has its own
verified bundle and independent requirements contract. No production Python
source change is needed to load these profiles.

Use each folder's lab.yaml through --config. Do not reuse another profile's bundle.
The contracts map canonical home test roles/actions to declared aliases; they do
not contain executable guards and are not consumed by the runtime engine.

[Operator walkthrough](../../../docs/guides/prepresentation.md) ·
[Acceptance evidence](../../../experiments/prepresentation-2026-10-27/README.md)
