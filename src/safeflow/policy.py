"""Small declarative automata interpreter. No device names or executable expressions."""
import copy
import hashlib
import json
import math
import re
from pathlib import Path

DEFAULT_POLICY = Path(__file__).with_name("policies") / "smart-home.json"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def policy_hash(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate_policy_key:" + key)
        obj[key] = value
    return obj


def lookup(context, path):
    value = context
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise ValueError("unknown_reference:" + path)
        value = value[part]
    return value


def expression(node, context):
    if not isinstance(node, dict):
        return node
    op, args = next(iter(node.items()))
    if op == "ref":
        return lookup(context, args)
    if op == "not":
        return not expression(args, context)
    if op in ("and", "or"):
        values = [expression(x, context) for x in args]
        if any(type(x) is not bool for x in values):
            raise ValueError("boolean_expression_required")
        return all(values) if op == "and" else any(values)
    left, right = [expression(x, context) for x in args]
    if op == "eq": return left == right
    if op == "ne": return left != right
    if left is None or right is None: return False
    if op == "lt": return left < right
    if op == "ge": return left >= right
    raise ValueError("unknown_operator:" + op)


def condition(node, context):
    value = expression(node, context)
    if type(value) is not bool: raise ValueError("boolean_condition_required")
    return value


def validate_expression(node, references):
    if not isinstance(node, dict):
        if node is None or type(node) in (bool, str): return
        if type(node) in (int, float) and math.isfinite(node): return
        raise ValueError("invalid_expression_literal")
    if len(node) != 1: raise ValueError("one_operator_required")
    op, args = next(iter(node.items()))
    if op == "ref":
        if args not in references: raise ValueError("unknown_reference:" + str(args))
    elif op == "not": validate_expression(args, references)
    elif op in ("and", "or", "eq", "ne", "lt", "ge"):
        if not isinstance(args, list) or (len(args) < 1 if op in ("and", "or") else len(args) != 2):
            raise ValueError("invalid_operator_arguments")
        for item in args: validate_expression(item, references)
    else: raise ValueError("unsupported_operator:" + op)


class Policy:
    def __init__(self, definition):
        self._definition = copy.deepcopy(definition)
        try:
            self._validate()
        except (TypeError, KeyError, AttributeError, IndexError) as exc:
            raise ValueError("malformed_policy_definition") from exc

    def _validate(self):
        d = self._definition
        if set(d) != {"format_version", "policy_version", "parameters", "facts", "event_fields", "sources", "clocks", "machines"}:
            raise ValueError("invalid_policy_fields")
        if d["format_version"] != 1 or not isinstance(d["policy_version"], str) or not d["policy_version"]:
            raise ValueError("unsupported_policy_format")
        if not isinstance(d["machines"], list) or not d["machines"] or not d["facts"] or d["sources"] != ["ai", "human"]:
            raise ValueError("invalid_policy_domain")
        if d["event_fields"] != ["name", "device", "mode"]:
            raise ValueError("unsupported_event_schema")
        if any(not name.isidentifier() for name in d["parameters"]): raise ValueError("invalid_parameter_name")
        for name, kind in d["facts"].items():
            if not name.isidentifier() or kind not in ("bool", "number", "nullable_number"):
                raise ValueError("invalid_fact_definition")
        for value in d["parameters"].values():
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("invalid_policy_parameter")
        refs = {f"{prefix}.{name}" for prefix in ("facts", "before", "after") for name in d["facts"]}
        refs |= {"event." + name for name in d["event_fields"]} | {"source"}
        refs |= {"parameters." + name for name in d["parameters"]}
        for name, clock in d["clocks"].items():
            if set(clock) != {"fact", "reset_when"} or d["facts"].get(clock["fact"]) != "nullable_number":
                raise ValueError("invalid_clock_definition")
            validate_expression(clock["reset_when"], refs)
        ids = set()
        for machine in d["machines"]:
            if set(machine) != {"id", "initial", "states", "transitions"} or machine["id"] in ids:
                raise ValueError("invalid_machine")
            ids.add(machine["id"])
            states = machine["states"]
            if not machine["id"].isidentifier() or any(not name.isidentifier() for name in states):
                raise ValueError("invalid_machine_or_state_name")
            if machine["initial"] not in states: raise ValueError("invalid_initial_state")
            for condition in states.values(): validate_expression(condition, refs)
            edge_ids = set()
            for edge in machine["transitions"]:
                if set(edge) != {"id", "phase", "from", "to", "when", "outcome", "reason"}:
                    raise ValueError("invalid_transition_fields")
                if not re.fullmatch(r"[A-Za-z0-9_.-]+", edge["id"]): raise ValueError("invalid_transition_id")
                if edge["id"] in edge_ids or edge["from"] not in states or edge["to"] not in states:
                    raise ValueError("invalid_transition_state_or_id")
                edge_ids.add(edge["id"])
                if edge["phase"] not in ("proposal", "observed"): raise ValueError("invalid_phase")
                if edge["outcome"] not in ("allow", "block", "human_bypass", "observe"):
                    raise ValueError("invalid_outcome")
                if edge["phase"] == "proposal" and (edge["to"] != edge["from"] or edge["outcome"] == "observe"):
                    raise ValueError("proposal_must_not_change_state")
                if edge["phase"] == "observed" and edge["outcome"] != "observe": raise ValueError("invalid_observed_edge")
                if edge["outcome"] == "block" and not isinstance(edge["reason"], str): raise ValueError("block_reason_required")
                validate_expression(edge["when"], refs)
            for state in states:
                for phase in ("proposal", "observed"):
                    if not any(e["from"] == state and e["phase"] == phase for e in machine["transitions"]):
                        raise ValueError("missing_transition_phase")
        self.version = d["policy_version"]
        self.sha256 = policy_hash(d)

    @property
    def definition(self):
        return copy.deepcopy(self._definition)

    @classmethod
    def load(cls, path=DEFAULT_POLICY):
        return cls(json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object))

    def facts_valid(self, facts):
        if set(facts) != set(self._definition["facts"]): raise ValueError("unknown_observed_facts")
        for name, kind in self._definition["facts"].items():
            value = facts[name]
            if kind == "bool":
                if type(value) is not bool: raise ValueError("boolean_fact_required")
            elif not (value is None and kind == "nullable_number"):
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError("invalid_numeric_fact")

    def context(self, facts, event=None, source="ai", before=None, after=None):
        self.facts_valid(facts)
        return {"facts": facts, "before": before or facts, "after": after or facts,
                "event": event or {k: None for k in self._definition["event_fields"]},
                "source": source, "parameters": self._definition["parameters"]}

    def classify(self, facts):
        context = self.context(facts)
        result = {}
        for m in self._definition["machines"]:
            matches = [name for name, predicate in m["states"].items() if condition(predicate, context)]
            if len(matches) != 1: raise ValueError("ambiguous_or_unknown_state:" + m["id"])
            result[m["id"]] = matches[0]
        return result

    def edges(self, states, phase, context):
        result = []
        for m in self._definition["machines"]:
            matches = [e for e in m["transitions"] if e["from"] == states[m["id"]]
                       and e["phase"] == phase and condition(e["when"], context)]
            if len(matches) != 1: raise ValueError("ambiguous_or_missing_transition:" + m["id"])
            result.append({"machine": m["id"], **matches[0]})
        return result


class Engine:
    def __init__(self, policy):
        self.policy = policy

    def reset(self, facts):
        self.facts = copy.deepcopy(facts)
        self.states = self.policy.classify(facts)

    def consider(self, event, source, facts):
        if facts != self.facts: raise ValueError("automata_state_mismatch")
        if source not in self.policy._definition["sources"]: raise ValueError("unknown_command_source")
        if set(event) != set(self.policy._definition["event_fields"]): raise ValueError("unknown_event_fields")
        edges = self.policy.edges(self.states, "proposal", self.policy.context(facts, event, source))
        blocked = [e for e in edges if e["outcome"] == "block"]
        bypass = [e for e in edges if e["outcome"] == "human_bypass"]
        if bypass and len(bypass) != len(edges): raise ValueError("inconsistent_source_exception")
        return ("block" if blocked else "human_bypass" if bypass else "allow",
                tuple(e["reason"] for e in blocked), tuple(e["id"] for e in edges))

    def observe(self, facts, event, source, advance_s):
        self.policy.facts_valid(facts)
        if type(advance_s) not in (float, int) or not math.isfinite(advance_s) or advance_s < 0:
            raise ValueError("invalid_time_advance")
        context = self.policy.context(facts, event, source, self.facts, facts)
        for clock in self.policy._definition["clocks"].values():
            old = self.facts[clock["fact"]]
            base = 0 if condition(clock["reset_when"], context) else old
            expected = None if base is None else base + advance_s
            if facts[clock["fact"]] != expected: raise ValueError("unexpected_clock_transition")
        edges = self.policy.edges(self.states, "observed", context)
        target = {e["machine"]: e["to"] for e in edges}
        if target != self.policy.classify(facts): raise ValueError("observed_target_mismatch")
        self.facts, self.states = copy.deepcopy(facts), target
        return tuple(e["id"] for e in edges)
