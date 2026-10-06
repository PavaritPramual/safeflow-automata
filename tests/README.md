# Tests

Run `python -m unittest discover -s tests -v` after installing the package.
Tests cover analytic RC physics, deterministic replay, strict command parsing,
real local HTTP, human FIFO/AI resumption and injected log/environment failures.
Fixture agents are labeled and are not real-model evidence. Actual Ollama/HA
evidence lives in `experiments/smart-home-stage1`.
