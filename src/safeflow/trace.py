"""Append + flush + fsync before the controller may execute a proposal."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path


class Trace:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event):
        record = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), **event}
        line = json.dumps(record, ensure_ascii=False, allow_nan=False)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line + "\n")
            stream.flush()
            os.fsync(stream.fileno())


def replay(records, home):
    """Reproduce executed commands and goal changes; never call a model."""
    from .commands import Command
    pending = {}
    for record in records:
        kind = record.get("event")
        if kind == "reset":
            if "physics" in record:
                from .environment import Physics
                home.physics = Physics(**record["physics"])
            home.reset(record["scenario"])
        elif kind == "goals":
            home.set_goals(**record["goals"])
        elif kind == "proposal":
            if record["before"] != home.snapshot():
                raise ValueError("proposal_state_mismatch")
            pending[record["proposal_id"]] = record
        elif kind == "execution":
            proposal = pending.get(record["proposal_id"])
            if proposal is None:
                raise ValueError("execution_without_proposal")
            if record.get("command"):
                home.apply(Command(**record["command"]))
            home.advance(record["advance_s"])
            if home.snapshot() != record["after"]:
                raise ValueError("replay_state_mismatch")
    return home.snapshot()
