# Tests

Run `python -m unittest discover -s tests -v` after installing the package.
Tests cover analytic RC physics, deterministic replay, strict command parsing,
real local HTTP, human FIFO/AI resumption and injected log/environment failures.
Fixture agents are labeled and are not real-model evidence. Actual Ollama/HA
evidence lives in `experiments/smart-home-stage1`.

## Home Assistant dashboard controls

With the existing lab container running, use its installed Home Assistant libraries:

```powershell
Get-Content tools/check_ha_controls.py -Raw -Encoding UTF8 | docker exec -i safeflow-homeassistant python -
```

These three isolated contract tests check duplicate-operation rejection while busy,
error recovery without automatic retries, and explicit human open/close versus AI
goal requests. They do not contact a model or mutate the live room. Actual dashboard
checks also exercised an AI round, human open/close rounds, goal editing without
execution/time advancement and native template rendering on 2026-10-28; the local
report is logs/dashboard-validation-20261028.json. That running-session check is
not a sealed formal-verification bundle or a new claim about model quality.
