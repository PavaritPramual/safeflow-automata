"""The only new module that knows the one-room simulator's device API."""
import copy
from ..commands import Command
from ..environment import Home, Physics


class SmartHomeEnvironment:
    def __init__(self, definition, bindings, *, physics=None, step_s=30):
        self.definition, self.bindings = definition, copy.deepcopy(bindings)
        if type(step_s) not in (int, float) or step_s <= 0: raise ValueError('positive_step_required')
        self.step_s = step_s
        self.home = Home(Physics(**(physics or {})))
        if set(bindings) != set(definition.data['variables']): raise ValueError('bindings_must_cover_facts')
        if len(set(bindings.values())) != len(bindings): raise ValueError('duplicate_device_binding')
        for action in definition.data['actions'].values():
            if len(action['set']) > 1: raise ValueError('single_device_action_required_by_home_adapter')
            for name, value in action['set'].items():
                from ..commands import validate_command
                validate_command(Command('set_device', bindings[name], value))
        self.reset()

    def sample(self):
        snapshot = self.home.snapshot()
        facts = {name: snapshot['devices'][device] for name, device in self.bindings.items()}
        self.definition.validate_facts(facts)
        return {'facts': facts, 'time_s': snapshot['simulation_time_s'], 'measurements': snapshot}

    def execute(self, action):
        applied_at_s = self.home.time_s
        if action is not None:
            effects = self.definition.data['actions'][action]['set']
            for variable, value in effects.items(): self.home.apply(Command('set_device', self.bindings[variable], value))
        self.home.advance(self.step_s)
        return {**self.sample(), 'applied_at_s': applied_at_s}

    def set_goals(self, values):
        if type(values) is not dict or not values or set(values)-{'target_c', 'light_required'}: raise ValueError('invalid_goals')
        # Validate all values before mutating either goal.
        validator = Home(self.home.physics)
        validator.set_goals(**values)
        self.home.set_goals(**values)

    def reset(self, scenario=None):
        scenario = dict(scenario or {})
        if set(scenario)-{'temperature_c', 'outdoor_c', 'target_c', 'light_required'}:
            raise ValueError('reset_cannot_change_verified_device_initial_state')
        scenario['devices'] = {self.bindings[k]: v for k,v in self.definition.initial_facts.items()}
        self.home.reset(scenario)
        return self.sample()

    def human_action(self, request):
        if type(request) is not dict or set(request) != {'device', 'mode'}: return {'kind': 'invalid_output', 'action': None}
        matches = []
        for name, action in self.definition.data['actions'].items():
            if len(action['set']) != 1: continue
            variable, value = next(iter(action['set'].items()))
            if request['device'] == self.bindings[variable] and request['mode'] == value: matches.append(name)
        return {'kind': 'proposal', 'action': matches[0]} if len(matches) == 1 else {'kind': 'invalid_output', 'action': None}
