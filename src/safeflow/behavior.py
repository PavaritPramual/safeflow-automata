"""Build observed episode paths X and check them against A; never infer unseen paths."""
import argparse
import copy
import json
from pathlib import Path
from .automata import Automata, home_facts
from .commands import Command, decode_response
from .environment import Home, Physics
from .policy import Policy


class Incomplete(ValueError):
    pass


def check_records(records, home=None, require_seal=True):
    records = list(records)
    home = home or Home()
    report = {"status": "conforms", "integrity": "complete", "issue": None,
              "replay_error": None, "episodes": [], "steps": 0,
              "scope": "Only the recorded paths; not exhaustive model verification."}
    first_mismatch = None
    stage, active, episode, guard = "idle", None, None, None
    requests = []
    previous_seq = 0
    run_id = None
    sealed = False

    def require(condition, message):
        if not condition: raise ValueError(message)

    def mismatch(line, field, expected, found):
        nonlocal first_mismatch
        if expected != found and first_mismatch is None:
            first_mismatch = {"line": line, "field": field, "expected": expected, "found": found}

    try:
        if not records: raise Incomplete("empty_trace")
        for line, row in enumerate(records, 1):
            # Files are one run, with any number of complete episodes.
            if type(row.get("event_seq")) is not int or row["event_seq"] != previous_seq + 1:
                raise Incomplete("missing_or_reordered_event")
            previous_seq = row["event_seq"]
            if run_id is None: run_id = row["run_id"]
            require(row["run_id"] == run_id, "mixed_run_ids")
            require(bool(row.get("timestamp_utc")), "missing_wall_clock_timestamp")
            kind = row["event"]
            if kind == "reset":
                if stage != "idle": raise Incomplete("reset_during_unfinished_round")
                require(row["schema_version"] == 3, "schema_3_required")
                policy = Policy(row["policy"])
                require(policy.sha256 == row["policy_sha256"] and policy.version == row["policy_version"], "policy_identity_mismatch")
                home.physics = Physics(**row["physics"])
                home.reset(row["scenario"])
                guard = Automata(policy); guard.reset(home.snapshot())
                episode = {"episode_id": row["episode_id"], "reset_line": line,
                           "policy_sha256": policy.sha256, "enforcement": row["enforcement"],
                           "model": row["model"], "path": []}
                report["episodes"].append(episode)
                requests = []
                sealed = False
                seen = set()
                continue
            if guard is None: raise Incomplete("reset_missing")
            require(row["episode_id"] == episode["episode_id"], "episode_identity_mismatch")
            require(not sealed, "event_after_episode_end")
            if kind == "episode_end":
                if stage != "idle" or requests: raise Incomplete("unfinished_round_at_end")
                require(row["steps"] == len(episode["path"]) and row["after"] == home.snapshot(), "episode_end_mismatch")
                require(row["policy_sha256"] == policy.sha256 and row["automata_after"] == guard.state, "episode_end_policy_mismatch")
                episode["end_line"] = line
                sealed = True
                continue
            if kind == "human_request":
                requests.append((row["request_id"], row["raw"]))
                continue
            if kind == "goals":
                require(stage == "idle", "goals_inside_round")
                home.set_goals(**row["goals"]); guard._sync(home.snapshot())
                continue
            if kind == "fault": raise Incomplete("episode_fault:" + row.get("reason", "unknown"))
            if kind == "received":
                require(stage == "idle", "unexpected_received_event")
                require(row["proposal_id"] not in seen, "duplicate_proposal_id")
                seen.add(row["proposal_id"])
                require(row["source"] in ("ai", "human"), "unknown_source")
                if row["source"] == "human":
                    if not requests: raise Incomplete("human_request_missing")
                    req, raw = requests.pop(0)
                    require(row["request_id"] == req, "human_queue_order_mismatch")
                    require(row["raw"] == {"message": {"tool_calls": [raw]}}, "human_raw_mismatch")
                else:
                    require(not requests and row["request_id"] is None, "human_queue_not_served")
                require(row["before"] == home.snapshot(), "received_state_mismatch")
                active = {"received": row, "lines": {"received": line}}
                stage = "received"
                continue
            require(kind in ("proposal", "decision", "execution"), "unknown_event_kind")
            expected_stage = {"proposal": "received", "decision": "proposal", "execution": "decision"}[kind]
            if stage != expected_stage: raise Incomplete("missing_or_out_of_order_round_event:" + kind)
            require(row["proposal_id"] == active["received"]["proposal_id"], "proposal_identity_mismatch")
            require(row["source"] == active["received"]["source"], "source_mismatch")
            active["lines"][kind] = line
            if kind == "proposal":
                received = active["received"]
                for field in ("raw", "prompt", "model", "before", "request_id", "seed"):
                    require(row.get(field) == received.get(field), "received_proposal_mismatch:" + field)
                error = received.get("error")
                command = None
                if not error:
                    try: command = decode_response(received["raw"], received.get("output_mode", "tools"))
                    except ValueError as exc: error = str(exc)
                require(row["command"] == (command.to_dict() if command else None), "decoded_command_mismatch")
                require(row["validation"] == ("valid" if command else "invalid") and row.get("reason") == error, "proposal_validation_mismatch")
                active.update(proposal=row, command=command, error=error)
                stage = "proposal"
            elif kind == "decision":
                command = active["command"]
                checked = guard.evaluate(command, row["source"], home.snapshot())
                actual_mode_outcome = checked.outcome if episode["enforcement"] or command is None else "execute_unshielded"
                reason = active["error"] or (checked.reason if episode["enforcement"] else None)
                require(row["decision"] == actual_mode_outcome and row.get("reason") == reason, "logged_decision_mismatch")
                require(row["reasons"] == list(checked.reasons) and row["transitions"] == list(checked.transitions), "decision_transition_mismatch")
                require(row["policy_sha256"] == policy.sha256 and row["policy_version"] == policy.version, "decision_policy_mismatch")
                require(row["automata_before"] == guard.state, "logged_automata_before_mismatch")
                allowed = actual_mode_outcome in ("allow", "human_bypass", "execute_unshielded")
                executed = command if allowed else None
                require(row["command"] == (executed.to_dict() if executed else None), "decision_command_mismatch")
                # Check A even when execution intentionally runs without enforcement.
                if command is not None and checked.outcome == "block" and allowed:
                    mismatch(line, "command_permitted_by_A", "block", actual_mode_outcome)
                active.update(decision=row, executed=executed, checked=checked)
                stage = "decision"
            else:
                require(row["advance_s"] == 30, "unexpected_time_step")
                command = active["executed"]
                require(row["command"] == (command.to_dict() if command else None), "execution_command_mismatch")
                before = home.snapshot()
                if command: home.apply(command)
                after = home.advance(row["advance_s"])
                require(after == row["after"], "replayed_environment_mismatch")
                transitions = guard.observe(before, command, after, 30, row["source"])
                require(row["automata_after"] == guard.state and row["transitions"] == list(transitions), "logged_automata_after_mismatch")
                episode["path"].append({"index": len(episode["path"]) + 1,
                    "proposal_id": row["proposal_id"], "lines": active["lines"],
                    "source": row["source"], "before": home_facts(before),
                    "command_origin": active["received"]["command_origin"],
                    "event": active["proposal"]["command"], "decision": active["decision"]["decision"],
                    "reason": active["decision"].get("reason"), "reasons": active["decision"]["reasons"],
                    "executed": row["command"], "after": home_facts(after),
                    "states_before": active["decision"]["automata_before"]["machines"],
                    "states_after": copy.deepcopy(guard.engine.states),
                    "proposal_transitions": active["decision"]["transitions"],
                    "observed_transitions": list(transitions)})
                report["steps"] += 1
                stage, active = "idle", None
        if stage != "idle" or requests: raise Incomplete("unfinished_round_or_pending_human_request")
        if require_seal and not sealed: raise Incomplete("episode_end_missing_live_or_truncated_log")
        if first_mismatch:
            report.update(status="nonconforming", issue=first_mismatch)
    except Incomplete as exc:
        report.update(status="inconclusive", integrity="incomplete", issue={"line": locals().get("line", 0), "message": str(exc)})
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        report.update(status="nonconforming", integrity="invalid", replay_error=str(exc),
                      issue={"line": locals().get("line", 0), "message": str(exc)})
    return report


def check_file(path):
    try:
        rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines()]
    except (ValueError, OSError) as exc:
        return {"status": "inconclusive", "integrity": "incomplete", "issue": {"message": str(exc)}, "episodes": [], "steps": 0}
    return check_records(rows)


def path_plantuml(episode):
    lines = ["@startuml", "skinparam monochrome true", "skinparam backgroundColor white",
             "skinparam defaultFontName Arial", "skinparam defaultFontSize 18", "hide empty description",
             "skinparam stateBackgroundColor white", "skinparam stateBorderColor black", "skinparam stateBorderThickness 1",
             'title X: recorded path (not all possible behavior)', 'state "Observed episode" as Scope {',
             'state "Initial" as S0', '[*] --> S0']
    for step in episode["path"]:
        n = step["index"]
        states = " / ".join(step["states_after"].values())
        event = step["event"] or {"name": "invalid"}
        detail = event['name'] if event['name'] != 'set_device' else event['device'] + '.' + event['mode']
        label = f'{n}. {step["source"]}: {detail}\\n{step["decision"]}; t={step["after"]["time_s"]:g}s'
        lines += [f'state "{states}" as S{n}', f'S{n-1} --> S{n} : {label}']
    return "\n".join(lines + ["}", "@enduml", ""])


def main():
    parser = argparse.ArgumentParser(description="Check observed paths X against their recorded A")
    parser.add_argument("trace")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    report = check_file(args.trace)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for index, episode in enumerate(report["episodes"], 1):
        (out / f"episode-{index}.puml").write_text(path_plantuml(episode), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "integrity", "steps", "issue")}, ensure_ascii=False))
    return 0 if report["status"] == "conforms" else 2 if report["status"] == "nonconforming" else 3


if __name__ == "__main__":
    raise SystemExit(main())
