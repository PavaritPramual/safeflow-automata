"""Safe YAML -> validated finite intermediate representation (IR)."""
import copy
import hashlib
import json
import re
from pathlib import Path
import yaml
from .expressions import Expression

FORMAT = 1
IR_VERSION = 'safeflow-ir-1'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class StrictLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent): raise ValueError('yaml_aliases_not_supported')
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if type(key) is not str or key in result: raise ValueError('duplicate_or_nonstring_yaml_key')
            result[key] = self.construct_object(value_node, deep=deep)
        return result


# YAML 1.2-style booleans: unquoted keys such as `on` are ordinary strings.
StrictLoader.yaml_implicit_resolvers = {
    k: [(tag, pattern) for tag, pattern in values if tag != 'tag:yaml.org,2002:bool']
    for k, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
StrictLoader.add_implicit_resolver('tag:yaml.org,2002:bool', re.compile(r'^(?:true|false)$', re.I), list('tTfF'))


def identifier(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', value):
        raise ValueError('invalid_identifier:' + str(value))


def exact(value, required, optional=()):
    if type(value) is not dict or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise ValueError('invalid_fields_expected:' + ','.join(required))


class Definition:
    def __init__(self, data):
        self._data = copy.deepcopy(data)
        try:
            self._validate()
        except (TypeError, KeyError, AttributeError, OverflowError) as exc:
            raise ValueError('malformed_definition') from exc
        self.sha256 = digest(self._data)
        self.ir_sha256 = digest({'ir_version': IR_VERSION, 'definition': self._data})

    @classmethod
    def load(cls, path):
        text = Path(path).read_text(encoding='utf-8-sig')
        if len(text.encode()) > 262144: raise ValueError('definition_too_large')
        try: return cls(yaml.load(text, Loader=StrictLoader))
        except yaml.YAMLError as exc: raise ValueError('invalid_yaml') from exc

    @property
    def data(self): return copy.deepcopy(self._data)

    def _validate(self):
        d = self._data
        exact(d, ['format_version', 'id', 'parameters', 'variables', 'clocks', 'sources',
                  'event_kinds', 'actions', 'states', 'initial', 'transitions', 'properties'])
        if type(d['format_version']) is not int or d['format_version'] != FORMAT: raise ValueError('unsupported_definition_version')
        identifier(d['id'])
        for key in ('parameters', 'variables', 'clocks', 'actions'):
            if type(d[key]) is not dict: raise ValueError('mapping_required:' + key)
            for name in d[key]: identifier(name)
        for key in ('sources', 'event_kinds', 'states'):
            if type(d[key]) is not list or not d[key] or any(type(x) is not str for x in d[key]) or len(set(d[key])) != len(d[key]):
                raise ValueError('unique_nonempty_list_required:' + key)
            for name in d[key]: identifier(name)
        if 'proposal' not in d['event_kinds']: raise ValueError('proposal_event_required')
        if d['initial'] not in d['states'] or not d['variables'] or not d['actions']:
            raise ValueError('initial_state_and_domain_required')
        if len(d['variables']) > 32 or len(d['actions']) > 128 or len(d['states']) > 64 or len(d['clocks']) > 8:
            raise ValueError('definition_exceeds_v1_limits')
        self.symbols = {'source': ('enum', tuple(d['sources'])), 'kind': ('enum', tuple(d['event_kinds'])),
                        'action': ('enum', tuple(d['actions']) + ('none',)),
                        'outcome': ('enum', ('allow', 'block', 'halt'))}
        if 'none' in d['actions']: raise ValueError('reserved_action_none')
        for name, p in d['parameters'].items():
            if type(p) is not int or not 0 <= p <= 2147483647: raise ValueError('bounded_integer_parameter_required')
            self.symbols['params.' + name] = 'number'
        for name, spec in d['variables'].items():
            exact(spec, ['type', 'initial'], ['values', 'min', 'max'])
            kind = spec['type']
            if kind == 'bool':
                if set(spec) != {'type', 'initial'}: raise ValueError('invalid_bool_definition')
                t = 'bool'
            elif kind == 'enum':
                if set(spec) != {'type', 'initial', 'values'} or type(spec['values']) is not list or not spec['values'] or any(type(x) is not str for x in spec['values']) or len(set(spec['values'])) != len(spec['values']):
                    raise ValueError('invalid_enum_definition')
                t = ('enum', tuple(spec['values']))
            elif kind == 'int':
                if set(spec) != {'type', 'initial', 'min', 'max'} or any(type(spec[k]) is not int for k in ('min', 'max')) or not -2147483647 <= spec['min'] <= spec['max'] <= 2147483647:
                    raise ValueError('invalid_integer_bounds')
                t = 'number'
            else: raise ValueError('unsupported_variable_type:' + str(kind))
            self.validate_value(name, spec['initial'])
            for prefix in ('facts', 'before', 'after'): self.symbols[prefix + '.' + name] = t
        self.clock_resets = {}
        for name, spec in d['clocks'].items():
            exact(spec, ['reset_when'])
            self.symbols['clock.' + name] = 'number'
            self.symbols['active.' + name] = 'bool'
        for name, spec in d['clocks'].items():
            expr = Expression(spec['reset_when'], self.symbols)
            # Resets may depend on observed state only, never circular clock state.
            import ast
            for node in ast.walk(expr.tree):
                if isinstance(node, ast.Name) and node.id not in ('before', 'after', 'params'):
                    raise ValueError('clock_reset_requires_observation_only')
            self.clock_resets[name] = expr
        for name, spec in d['actions'].items():
            exact(spec, ['set'])
            if type(spec['set']) is not dict: raise ValueError('action_effect_mapping_required')
            for variable, value in spec['set'].items(): self.validate_value(variable, value)
        if type(d['transitions']) is not list or not d['transitions'] or len(d['transitions']) > 256:
            raise ValueError('transitions_required')
        self.guards = {}
        for edge in d['transitions']:
            exact(edge, ['id', 'from', 'to', 'on', 'when', 'outcome', 'reason'])
            identifier(edge['id'])
            if edge['id'] in self.guards or edge['from'] not in d['states'] or edge['to'] not in d['states']:
                raise ValueError('invalid_transition')
            if type(edge['on']) is not list or not edge['on'] or any(x not in d['event_kinds'] for x in edge['on']):
                raise ValueError('invalid_transition_event')
            if edge['outcome'] not in ('allow', 'block', 'halt') or type(edge['reason']) is not str:
                raise ValueError('invalid_transition_outcome')
            expr = Expression(edge['when'], self.symbols)
            if 'outcome' in edge['when'] or 'after.' in edge['when']: raise ValueError('guard_cannot_read_future')
            self.guards[edge['id']] = expr
        if type(d['properties']) is not list or not d['properties']: raise ValueError('properties_required')
        self.assertions = {}
        for prop in d['properties']:
            exact(prop, ['id', 'type', 'at', 'expression'])
            identifier(prop['id'])
            if prop['id'] in self.assertions or prop['id'] in ('no_deadlock', 'complete_decisions'):
                raise ValueError('duplicate_or_reserved_property')
            if prop['type'] not in ('invariant', 'reachable') or prop['at'] not in ('decision', 'observation'):
                raise ValueError('unsupported_property')
            self.assertions[prop['id']] = Expression(prop['expression'], self.symbols)

    def validate_value(self, name, value):
        if name not in self._data['variables']: raise ValueError('unknown_variable:' + str(name))
        spec = self._data['variables'][name]
        ok = (type(value) is bool if spec['type'] == 'bool' else
              type(value) is str and value in spec['values'] if spec['type'] == 'enum' else
              type(value) is int and spec['min'] <= value <= spec['max'])
        if not ok: raise ValueError('invalid_variable_value:' + name)

    def validate_facts(self, facts):
        if type(facts) is not dict or set(facts) != set(self._data['variables']): raise ValueError('facts_schema_mismatch')
        for name, value in facts.items(): self.validate_value(name, value)

    @property
    def initial_facts(self): return {k: v['initial'] for k, v in self._data['variables'].items()}

    @property
    def property_ids(self): return ['no_deadlock', 'complete_decisions'] + [p['id'] for p in self._data['properties']]
