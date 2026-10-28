# Live console

From the repository root, with Ollama running and matching UPPAAL bundles available:

```powershell
./.venv/Scripts/python.exe -m tools.live_console --config examples/smart-home/lab.yaml --logs logs/live-console --interval 3
```

Open [localhost:8766](http://localhost:8766). The default is verified profile A,
180-second AC rest, and an automatic loop. Use `--paused` to wait for Start.

- **Start / Stop after round:** resume or pause between completed rounds.
- **Human command / Queue:** enqueue one command to replace one AI round. FIFO;
  does not cancel an in-flight round. AI resumes when the queue is empty.
- **Auto-scroll:** follow the latest console records.
- **Rules:** collapsed device overview and verification summary. A stale diagram
  is hidden when its definition hash differs.

Latest raw AI output remains above the console. JSONL files retain full raw
requests/responses, decisions and observations. The page keeps recent events.
No prepared model answers or alternative guard implementation are used.

The console creates its own verified Application/session, separate from HA on
port 8765. It binds to loopback only. Closing the tab does not stop the service;
Ctrl+C in the terminal waits for the current round and closes the session.
Queued requests are receipted locally, then mapped to core request IDs between
rounds. They are not restored across service restarts.

While running or paused, check a trace with `safeflow check PATH --live-prefix`.
After service shutdown, check without that flag. A live-prefix check does not
certify a sealed run. The existing 30-property A proof is required; the demo has
no verification-bypass flag and does not invoke UPPAAL on each round.

`tests/test_live_console.py` uses labelled test fixtures for queue responsiveness,
FIFO/replay, pause, verification gate, log failure, renamed bindings, stale images
and HTTP isolation. Actual-model runs are checked separately.
