"""Composition root: select concrete ports here, not inside the automata."""
import copy
import json
import threading
import uuid
from pathlib import Path
from .core.definition import Definition, StrictLoader
from .verification import VerificationGate
from .service import Session
from .trace import Trace
from .runner import Loop
from .api import NotReady
from .adapters.proposers import OllamaProposer, OpenAICompatibleProposer
from .adapters.smart_home import SmartHomeEnvironment
import yaml


PROPOSERS = {'ollama': OllamaProposer, 'openai_compatible': OpenAICompatibleProposer}


class Application:
    def __init__(self, config_path, logs='logs', verification=None):
        path = Path(config_path).resolve()
        self.config = yaml.load(path.read_text(encoding='utf-8-sig'), Loader=StrictLoader)
        self.definition = Definition.load(path.parent / self.config['policy'])
        self.gate = VerificationGate(verification or path.parent / self.config['verification'])
        self.logs = Path(logs)
        self.sessions, self.loop = {}, None
        self.lock = threading.RLock()
        self.readiness_error = None
        self._verification = None
        try: self._verification = self.gate.require(self.definition)
        except (OSError, ValueError, KeyError) as exc: self.readiness_error = str(exc)

    def _require_ready(self):
        try:
            self._verification = self.gate.require(self.definition)
            self.readiness_error = None
            return self._verification
        except (OSError, ValueError, KeyError) as exc:
            self._verification, self.readiness_error = None, str(exc)
            raise NotReady(str(exc)) from exc

    def _session(self, facts=None, time_s=0, context=None):
        self._require_ready()
        return Session(self.definition, self.gate, Trace(self.logs / ('session-' + str(uuid.uuid4()) + '.jsonl')),
                       facts, time_s, context=context)

    def create_session(self, facts=None, time_s=0):
        with self.lock:
            session = self._session(facts, time_s)
            self.sessions[session.id] = session
            return session

    def get_session(self, ident):
        with self.lock: return self.sessions[ident]

    def health(self):
        try: self._require_ready()
        except NotReady: pass
        return {'status': 'ok', 'readiness': 'ready' if self._verification else 'not_ready',
                'stage': 'automata', 'api_version': 1}

    def verification_status(self):
        try: self._require_ready()
        except NotReady: pass
        try:
            report = json.loads((self.gate.directory / 'verification.json').read_text(encoding='utf-8'))
        except (OSError, ValueError): report = None
        return {'ready': self._verification is not None, 'reason': self.readiness_error,
                'definition_sha256': self.definition.sha256, 'report': report}

    def _start_lab(self, scenario=None):
        self._require_ready()
        config = self.config
        environment = SmartHomeEnvironment(self.definition, config['bindings'], physics=config.get('physics'), step_s=config.get('step_s', 30))
        environment.reset(scenario)
        p = config['proposer']
        try: cls = PROPOSERS[p['provider']]
        except KeyError as exc: raise ValueError('unsupported_proposer_provider') from exc
        kwargs = {'model': p['model'], 'url': p['url'], 'prompt': p['prompt'], 'actions': self.definition.data['actions'],
                  'timeout': p.get('timeout_s', 120), 'options': p.get('options')}
        if p['provider'] == 'openai_compatible': kwargs['api_key_env'] = p.get('api_key_env')
        proposer = cls(**kwargs)
        session = self._session(environment.sample()['facts'], environment.sample()['time_s'],
                                context={'environment': 'smart_home', 'config': config,
                                         'initial_observation': environment.sample(), 'proposer': proposer.metadata()})
        self.loop = Loop(session, proposer, environment, environment.human_action)
        return self.loop

    def _lab(self): return self.loop or self._start_lab()

    def lab_state(self):
        with self.lock:
            try:
                result = self._lab().snapshot()
                # Display-only mapping stays in this case-study composition root.
                clock = result['clocks'].get('rest')
                rest = self.definition.data['parameters'].get('rest_s', 0)
                result['automata']['cooldown'] = 'resting' if clock and clock['active'] and clock['elapsed_s'] < rest else 'ready'
                result['readiness'] = 'ready'
                return result
            except NotReady as exc:
                return {'halted': True, 'readiness': 'not_ready', 'enforcement': 'not_ready', 'model': {},
                        'automata': {}, 'pending_requests': 0, 'last_result': None, 'issue': str(exc)}

    def lab_step(self, seed=0, request_id=None):
        with self.lock: return self._lab().step(seed, request_id)

    def lab_enqueue(self, data):
        with self.lock: return self._lab().enqueue(data)

    def lab_goals(self, data):
        with self.lock: return self._lab().goals(data)

    def lab_reset(self, scenario):
        with self.lock:
            if type(scenario) is not dict: raise ValueError('invalid_reset')
            # Validate reset before closing the current session.
            validator = SmartHomeEnvironment(self.definition, self.config['bindings'], step_s=self.config.get('step_s', 30))
            validator.reset(scenario)
            if self.loop and not self.loop.session.halted and not self.loop.session.sealed:
                if self.loop.queue:
                    self.loop.session._log('queue_cancelled', request_ids=[x[0] for x in self.loop.queue])
                    self.loop.queue.clear()
                self.loop.finish()
            return self._start_lab(scenario).snapshot()

    def close(self):
        with self.lock:
            if self.loop and not self.loop.session.halted and not self.loop.session.sealed and not self.loop.queue:
                self.loop.finish()
