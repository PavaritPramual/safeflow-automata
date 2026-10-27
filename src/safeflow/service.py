"""Single-writer sessions. No provider, device, physics or HTTP imports."""
import copy
import threading
import uuid
from .core.definition import canonical, digest
from .core.runtime import Runtime
from .ports import EventSink, VerificationPort


class Session:
    def __init__(self, definition, gate: VerificationPort, sink: EventSink, facts=None, time_s=0, context=None, session_id=None):
        # Run this before logging a start or letting any client execute an action.
        self.verification = gate.require(definition)
        facts = definition.initial_facts if facts is None else facts
        if facts != definition.initial_facts: raise ValueError('initial_facts_not_covered_by_verification')
        self.runtime, self.sink = Runtime(definition, facts, time_s), sink
        self.id, self.seq = str(uuid.UUID(session_id)) if session_id else str(uuid.uuid4()), 0
        self.lock = threading.RLock()
        self.halted, self.sealed, self.issue = False, False, None
        self.received, self.decisions, self.observations = {}, {}, {}
        self.pending = None
        self._log('session_start', definition=definition.data, definition_sha256=definition.sha256,
                  ir_sha256=definition.ir_sha256, verification=self.verification,
                  snapshot=self.runtime.snapshot(), context=copy.deepcopy(context or {}), schema_version=4)

    def _log(self, event, **fields):
        try:
            self.seq += 1
            self.sink.write({'schema_version': 4, 'session_id': self.id, 'event_seq': self.seq, 'event': event, **fields})
        except Exception:
            self.halted = True
            raise

    def _active(self):
        if self.halted or self.sealed: raise RuntimeError('session_halted_or_closed')

    def _fault(self, reason, **details):
        self.halted = True
        if self.issue is None: self.issue = {'reason': reason, **copy.deepcopy(details)}
        self._log('fault', issue=self.issue)

    def receive(self, event_id, source, raw, metadata=None):
        """Persist raw bytes/JSON before the in-process adapter normalizes them."""
        with self.lock:
            self._active()
            if type(event_id) is not str or not 1 <= len(event_id) <= 128 or type(source) is not str:
                raise ValueError('invalid_event_envelope')
            if metadata is not None and type(metadata) is not dict: raise ValueError('metadata_object_required')
            value = {'source': source, 'raw': copy.deepcopy(raw), 'metadata': copy.deepcopy(metadata or {})}
            canonical(value)  # Reject non-JSON/NaN before reserving anything.
            if event_id in self.received:
                if value != self.received[event_id]: raise ValueError('duplicate_event_content_mismatch')
                return
            if self.pending is not None or set(self.received) - set(self.decisions):
                raise ValueError('event_pending_observation_or_decision')
            self._log('received', event_id=event_id, **value)
            self.received[event_id] = value

    def decide(self, event_id, event):
        with self.lock:
            self._active()
            if event_id not in self.received: raise ValueError('raw_event_must_be_received_first')
            if type(event) is not dict or set(event) != {'kind', 'action'} or type(event['kind']) is not str or (event['action'] is not None and type(event['action']) is not str):
                raise ValueError('invalid_normalized_event')
            normalized = {'source': self.received[event_id]['source'], **event}
            if event_id in self.decisions:
                old_event, result = self.decisions[event_id]
                if old_event != normalized: raise ValueError('duplicate_event_content_mismatch')
                return copy.deepcopy(result)
            if self.pending is not None: raise ValueError('event_pending_observation')
            result = {**self.runtime.consider(normalized), 'event_id': event_id,
                      'definition_sha256': self.runtime.definition.sha256}
            self._log('decision', event_id=event_id, normalized=normalized, result=result,
                      before=self.runtime.snapshot())
            self.decisions[event_id] = (copy.deepcopy(normalized), copy.deepcopy(result))
            if result['outcome'] == 'halt':
                self.halted = True
                self.issue = {'reason': result['reason'], 'event_id': event_id}
                edge = next((e for e in self.runtime.spec['transitions'] if e['id']==result['transition']),None)
                expected = bool(edge and edge['outcome']=='halt' and edge['reason']==result['reason'])
                self._log('session_halt',event_id=event_id,expected=expected,issue=self.issue,snapshot=self.runtime.snapshot())
                self.sealed = True
            else: self.pending = event_id
            return copy.deepcopy(result)

    def submit(self, event_id, source, kind, action=None, raw=None, metadata=None):
        with self.lock:
            self.receive(event_id, source, raw, metadata)
            return self.decide(event_id, {'kind': kind, 'action': action})

    def observe(self, event_id, facts, time_s, applied_at_s, evidence=None):
        with self.lock:
            self._active()
            observation = {'facts': copy.deepcopy(facts), 'time_s': time_s, 'applied_at_s': applied_at_s,
                           'evidence': copy.deepcopy(evidence)}
            canonical(observation)
            if event_id in self.observations:
                old, result = self.observations[event_id]
                if old != observation: raise ValueError('duplicate_observation_content_mismatch')
                return copy.deepcopy(result)
            if self.pending != event_id: raise ValueError('observation_reference_out_of_order')
            event, decision = self.decisions[event_id]
            try:
                candidate = self.runtime.observed(event, decision, facts, time_s, applied_at_s)
            except ValueError as exc:
                self._fault(str(exc), event_id=event_id, expected=self.expected_facts(event_id), found=observation)
                raise
            result = candidate.snapshot()
            self._log('observation', event_id=event_id, observation=observation, after=result)
            self.runtime, self.pending = candidate, None
            self.observations[event_id] = (observation, result)
            return copy.deepcopy(result)

    def expected_facts(self, event_id):
        event, decision = self.decisions[event_id]
        facts = copy.deepcopy(self.runtime.facts)
        if decision['outcome'] == 'allow': facts.update(self.runtime.spec['actions'][event['action']]['set'])
        return facts

    def fault(self, reason, **details):
        with self.lock: self._fault(reason, **details)

    def finish(self):
        with self.lock:
            self._active()
            if self.pending or set(self.received) - set(self.decisions): raise ValueError('cannot_close_pending_session')
            self._log('session_end', snapshot=self.runtime.snapshot(), events=len(self.decisions))
            self.sealed = True

    def snapshot(self):
        with self.lock:
            return {'session_id': self.id, **self.runtime.snapshot(), 'halted': self.halted, 'sealed': self.sealed,
                    'pending_event_id': self.pending, 'issue': copy.deepcopy(self.issue),
                    'definition_sha256': self.runtime.definition.sha256, 'verification_status': self.verification['status']}
