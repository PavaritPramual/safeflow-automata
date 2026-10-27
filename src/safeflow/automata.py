"""Home adapter around the device-independent declarative automata engine."""
import copy
import math
from dataclasses import dataclass
from .commands import MODES, validate_command
from .policy import Engine, Policy


def home_facts(snapshot):
    devices = snapshot['devices']
    if set(devices) != set(MODES) or any(devices[d] not in MODES[d] for d in MODES):
        raise ValueError('unknown_observed_state')
    now, elapsed = snapshot['simulation_time_s'], snapshot['ac_off_elapsed_s']
    if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
        raise ValueError('invalid_observed_time')
    if elapsed is not None and (type(elapsed) not in (int, float) or not math.isfinite(elapsed) or not 0 <= elapsed <= now):
        raise ValueError('invalid_observed_clock')
    return {'ac': devices['air_conditioner'] == 'cool', 'heater': devices['heater'] == 'on',
            'elapsed': elapsed, 'time_s': now}


@dataclass(frozen=True)
class Decision:
    outcome: str
    reason: str | None = None
    reasons: tuple = ()
    transitions: tuple = ()


class Automata:
    def __init__(self, policy=None):
        self.policy = policy or Policy.load()
        self.engine = Engine(self.policy)

    def _sync(self, snapshot):
        facts = home_facts(snapshot)
        self.state = {'ac': facts['ac'], 'heater': facts['heater'],
                      'elapsed_s': facts['elapsed'], 'time_s': facts['time_s'],
                      'cooldown': 'resting' if self.engine.states['R2'] == 'Resting' else 'ready',
                      'machines': copy.deepcopy(self.engine.states)}
        self.expected = copy.deepcopy(snapshot)

    def reset(self, snapshot):
        self.engine.reset(home_facts(snapshot))
        self._sync(snapshot)

    def evaluate(self, command, source, snapshot):
        if snapshot != self.expected: raise ValueError('automata_state_mismatch')
        facts = home_facts(snapshot)
        if source not in ('ai', 'human'): raise ValueError('unknown_command_source')
        if command is None: return Decision('reject_invalid', 'invalid_proposal')
        validate_command(command)
        outcome, reasons, transitions = self.engine.consider(command.to_dict(), source, facts)
        return Decision(outcome, reasons[0] if reasons else None, reasons, transitions)

    def observe(self, before, command, after, advance_s, source='ai'):
        if before != self.expected: raise ValueError('automata_state_mismatch')
        devices = dict(before['devices'])
        if command:
            validate_command(command)
            if command.name == 'set_device': devices[command.device] = command.mode
        if after['devices'] != devices or after['simulation_time_s'] != before['simulation_time_s'] + advance_s:
            raise ValueError('unexpected_environment_transition')
        event = command.to_dict() if command else {'name': 'hold', 'device': None, 'mode': None}
        transitions = self.engine.observe(home_facts(after), event, source, advance_s)
        self._sync(after)
        return transitions
