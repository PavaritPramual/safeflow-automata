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
    decisions = {}
    guard = None
    enforcement = False
    for record in records:
        kind = record.get("event")
        if kind == "reset":
            if "physics" in record:
                from .environment import Physics
                home.physics = Physics(**record["physics"])
            home.reset(record["scenario"])
            pending.clear(); decisions.clear()
            if record.get("schema_version") == 2:
                from .automata import Automata, POLICY_VERSION
                if record.get("policy_version") != POLICY_VERSION:
                    raise ValueError("unsupported_policy_version")
                guard = Automata(); guard.reset(home.snapshot())
                enforcement = record["enforcement"]
            else:
                guard = None
        elif kind == "goals":
            home.set_goals(**record["goals"])
            if guard: guard.expected = home.snapshot()
        elif kind == "proposal":
            if record["before"] != home.snapshot():
                raise ValueError("proposal_state_mismatch")
            pending[record["proposal_id"]] = record
        elif kind == "decision":
            decisions[record["proposal_id"]] = record
        elif kind == "execution":
            proposal = pending.get(record["proposal_id"])
            if proposal is None:
                raise ValueError("execution_without_proposal")
            if guard:
                decision = decisions.get(record["proposal_id"])
                if decision is None or decision.get("command") != record.get("command"):
                    raise ValueError("execution_decision_mismatch")
                proposed = Command(**proposal["command"]) if proposal.get("command") else None
                expected = guard.evaluate(proposed, proposal["source"], home.snapshot())
                expected_outcome = expected.outcome if enforcement or proposed is None else "execute_unshielded"
                if decision["decision"] != expected_outcome:
                    raise ValueError("policy_decision_mismatch")
                if record["source"] != proposal["source"] or record["advance_s"] != 30:
                    raise ValueError("execution_contract_mismatch")
                allowed = decision["decision"] in ("allow", "human_bypass", "execute_unshielded")
                if record.get("command") != (proposal.get("command") if allowed else None):
                    raise ValueError("executed_command_mismatch")
            before = home.snapshot()
            if record.get("command"):
                home.apply(Command(**record["command"]))
            home.advance(record["advance_s"])
            if guard:
                guard.observe(before, Command(**record["command"]) if record.get("command") else None, home.snapshot(), record["advance_s"])
            pending.pop(record["proposal_id"])
            if home.snapshot() != record["after"]:
                raise ValueError("replay_state_mismatch")
    if pending:
        raise ValueError("incomplete_execution_trace")
    return home.snapshot()
