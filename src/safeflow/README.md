# Source boundaries

Current service: core/ (typed definitions and runtime), service.py (sessions),
verification.py (UPPAAL), monitoring.py (X/A), adapters/ (providers and simulation),
runner.py (loop), application.py (composition), api.py and cli.py (interfaces).
See ../../docs/development/architecture.md for contracts and SOLID decisions.

agent.py, automata.py, commands.py, controller.py, policy.py, behavior.py and the
packaged policies retain the historical v3 regression/experiment path. The v2
interpreter is under compat/. environment.py is the retained case-study physics
implementation, used only through the new environment adapter by the service.
The old server module entry point redirects to the new gated CLI.
