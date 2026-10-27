"""Finite automata with clocks measured in explicit environment time."""
import copy
import math


def timestamp(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('invalid_environment_time')
    return value


class Runtime:
    def __init__(self, definition, facts, time_s=0):
        definition.validate_facts(facts)
        self.definition, self.spec = definition, definition.data
        self.facts, self.time_s = copy.deepcopy(facts), timestamp(time_s)
        self.origin_s = self.time_s
        self.state = self.spec['initial']
        self.resets = {name: None for name in self.spec['clocks']}

    def context(self, event, *, outcome='block', after=None):
        ctx = {'source': event['source'], 'kind': event['kind'],
               'action': event.get('action') or 'none', 'outcome': outcome}
        for prefix, values in (('facts', self.facts), ('before', self.facts), ('after', after or self.facts), ('params', self.spec['parameters'])):
            ctx.update({prefix + '.' + k: v for k, v in values.items()})
        for name, reset in self.resets.items():
            ctx['clock.' + name] = self.time_s - (self.origin_s if reset is None else reset)
            ctx['active.' + name] = reset is not None
        return ctx

    def consider(self, event):
        if event.get('source') not in self.spec['sources'] or event.get('kind') not in self.spec['event_kinds']:
            return {'outcome': 'halt', 'reason': 'unknown_source_or_event', 'transition': None, 'next_state': self.state}
        action = event.get('action')
        if (event.get('kind') == 'proposal') != (action is not None):
            return {'outcome': 'halt', 'reason': 'event_action_contract_mismatch', 'transition': None, 'next_state': self.state}
        if action is not None and action not in self.spec['actions']:
            return {'outcome': 'halt', 'reason': 'unknown_action', 'transition': None, 'next_state': self.state}
        ctx = self.context(event)
        edges = [e for e in self.spec['transitions'] if e['from'] == self.state and event['kind'] in e['on']
                 and self.definition.guards[e['id']].evaluate(ctx)]
        if len(edges) != 1:
            return {'outcome': 'halt', 'reason': 'ambiguous_or_missing_transition', 'transition': None, 'next_state': self.state}
        e = edges[0]
        if e['outcome'] == 'allow' and action is None:
            return {'outcome': 'halt', 'reason': 'allowed_event_without_action', 'transition': e['id'], 'next_state': self.state}
        result = {'outcome': e['outcome'], 'reason': e['reason'], 'transition': e['id'], 'next_state': e['to']}
        for p in self.spec['properties']:
            if p['type'] == 'invariant' and p['at'] == 'decision' and not self.definition.assertions[p['id']].evaluate(self.context(event, outcome=e['outcome'])):
                return {**result, 'outcome': 'halt', 'reason': 'runtime_property_violation:' + p['id']}
        return result

    def observed(self, event, decision, facts, time_s, applied_at_s):
        """Return a candidate next runtime. No mutation until evidence is durable."""
        self.definition.validate_facts(facts)
        time_s, applied_at_s = timestamp(time_s), timestamp(applied_at_s)
        if applied_at_s != self.time_s or time_s < self.time_s: raise ValueError('observation_time_out_of_order')
        expected = copy.deepcopy(self.facts)
        if decision['outcome'] == 'allow': expected.update(self.spec['actions'][event['action']]['set'])
        if facts != expected: raise ValueError('observed_effect_mismatch')
        ctx = self.context(event, outcome=decision['outcome'], after=facts)
        result = copy.copy(self)
        result.facts, result.time_s, result.state = copy.deepcopy(facts), time_s, decision['next_state']
        result.resets = dict(self.resets)
        for name, expr in self.definition.clock_resets.items():
            if expr.evaluate(ctx): result.resets[name] = applied_at_s
        # Observation properties use the new clocks and explicit before/after.
        ctx = result.context(event, outcome=decision['outcome'], after=facts)
        ctx.update({'before.' + k: v for k, v in self.facts.items()})
        for p in self.spec['properties']:
            if p['type'] == 'invariant' and p['at'] == 'observation' and not self.definition.assertions[p['id']].evaluate(ctx):
                raise ValueError('runtime_property_violation:' + p['id'])
        return result

    def snapshot(self):
        return {'state': self.state, 'facts': copy.deepcopy(self.facts), 'time_s': self.time_s,
                'clocks': {k: {'active': v is not None, 'elapsed_s': self.time_s-(self.origin_s if v is None else v)}
                           for k, v in self.resets.items()}}
