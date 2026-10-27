"""Compose ports into a lab loop; the session owns automata decisions."""
import copy
import threading
import uuid
from collections import deque
from .ports import Proposer, Environment


class Loop:
    def __init__(self, session, proposer: Proposer, environment: Environment, human_decoder):
        self.session, self.proposer, self.environment = session, proposer, environment
        self.human_decoder = human_decoder
        self.queue, self.lock = deque(), threading.RLock()
        self.last_result = None
        self.steps = 0
        self.requests = {}
        self.environment_failed = False
        self.stop_requested = threading.Event()

    def request_stop(self):
        self.stop_requested.set()

    def enqueue(self, raw):
        with self.lock:
            self.session._active()
            if self.stop_requested.is_set(): raise RuntimeError('loop_stopping')
            event_id = str(uuid.uuid4())
            # The queue receipt is kept in its own durable record. Normalization
            # occurs only when the command replaces an AI round.
            self.session._log('human_request', request_id=event_id, raw=raw)
            self.queue.append((event_id, copy.deepcopy(raw)))
            return event_id

    def step(self, seed=0, request_id=None):
        with self.lock:
            if request_id is not None and request_id in self.requests:
                old_seed, snapshot = self.requests[request_id]
                if old_seed != seed: raise ValueError('step_request_content_mismatch')
                return copy.deepcopy(snapshot)
            self.session._active()
            if self.stop_requested.is_set(): raise RuntimeError('loop_stopping')
            sample = self.environment.sample()
            if sample['facts'] != self.session.runtime.facts or sample['time_s'] != self.session.runtime.time_s:
                self.session.fault('environment_state_changed_outside_session', expected=self.session.runtime.snapshot(), found=sample)
                raise ValueError('environment_state_changed_outside_session')
            human = bool(self.queue)
            if human:
                event_id, raw = self.queue[0]
                response, metadata = raw, {'origin': 'human'}
            else:
                event_id = str(uuid.uuid4())
                try: response = self.proposer.propose(sample, seed)
                except Exception as exc:
                    response = {'raw': None, 'error_kind': 'adapter_error', 'error': type(exc).__name__}
                metadata = self.proposer.metadata()
            self.session.receive(event_id, 'human' if human else 'ai', response, metadata)
            if self.stop_requested.is_set():
                self.session.fault('shutdown_requested', event_id=event_id)
                raise RuntimeError('loop_stopping')
            try:
                event = self.human_decoder(response) if human else self.proposer.normalize(response)
                decision = self.session.decide(event_id, event)
            except Exception as exc:
                self.session.fault('normalization_or_decision_failed', error=type(exc).__name__, event_id=event_id)
                raise
            if human: self.queue.popleft()
            if decision['outcome'] == 'halt':
                self.last_result = {**decision, 'decision': 'halt'}
                return self.snapshot()
            try:
                result = self.environment.execute(event['action'] if decision['outcome'] == 'allow' else None)
                self.session.observe(event_id, result['facts'], result['time_s'], result['applied_at_s'])
            except Exception as exc:
                self.environment_failed = True
                if not self.session.halted: self.session.fault('environment_or_observation_failed', event_id=event_id, error=type(exc).__name__)
                raise
            self.steps += 1
            self.last_result = {**decision, 'decision': decision['outcome'], 'source': 'human' if human else 'ai',
                                'action': event['action'], 'validation': 'valid' if event['kind'] == 'proposal' else 'invalid'}
            snapshot = self.snapshot()
            if request_id is not None: self.requests[request_id] = (seed, copy.deepcopy(snapshot))
            return snapshot

    def snapshot(self):
        with self.lock:
            sample = self.environment.sample()
            runtime = self.session.snapshot()
            return {**sample['measurements'], **runtime, 'automata': runtime,
                    'pending_requests': len(self.queue), 'last_result': copy.deepcopy(self.last_result),
                    'model': self.proposer.metadata(), 'enforcement': 'automata', 'steps': self.steps}

    def goals(self, values):
        with self.lock:
            self.session._active()
            # Goal changes do not change formal facts or simulated time.
            self.environment.set_goals(values)
            self.session._log('goals', values=values)
            return self.snapshot()

    def finish(self):
        with self.lock:
            if self.queue: raise ValueError('human_requests_pending')
            self.session.finish()
