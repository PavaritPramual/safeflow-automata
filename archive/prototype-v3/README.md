# Historical v3 prototype artifacts

These files predate the YAML/IR service and are preserved for provenance.
`formal/smart-home.xml` and `scripts/build-formal-model.py` duplicate home rules in
Python and XML. `scripts/run-stage2.py` belongs to historical stage-two evidence.
They are not the current build or control path. Embedded output paths retain the
historical layout: do not run these scripts blindly from the current repository.
Current builds use `python -m safeflow verify`; ordinary control requires a matching
successful verification bundle. Existing experimental logs are preserved unchanged.
