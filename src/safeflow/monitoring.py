"""Ordered observed path X, checked against the pinned definition A.

Replay uses the runtime interpreter and is not an independent formal proof.
Independent requirement oracles and UPPAAL comparisons live in tests.
"""
import copy
import json
from pathlib import Path
from collections import deque
from .core.definition import Definition
from .core.runtime import Runtime


def check_records(records, require_seal=True):
    rows = list(records)
    report = {'status': 'inconclusive', 'integrity': 'incomplete', 'issue': None, 'path': [], 'steps': 0}
    runtime = None
    session = None
    received, decided, observed = {}, {}, set()
    pending = None
    sealed = False
    human_queue = deque()

    def same(expected, found, field):
        if expected != found: raise ValueError((field, expected, found))

    try:
        for line, row in enumerate(rows, 1):
            same(line, row.get('event_seq'), 'event_seq')
            same(4, row.get('schema_version'), 'schema_version')
            if sealed: raise ValueError(('event_after_seal', None, row.get('event')))
            name = row.get('event')
            if line == 1:
                same('session_start', name, 'first_event')
                definition = Definition(row['definition'])
                same(definition.sha256, row['definition_sha256'], 'definition_sha256')
                same(definition.ir_sha256, row['ir_sha256'], 'ir_sha256')
                initial = row['snapshot']
                same(definition.initial_facts, initial['facts'], 'initial_facts')
                runtime = Runtime(definition, initial['facts'], initial['time_s'])
                same(runtime.snapshot(), initial, 'initial_snapshot')
                session = row['session_id']
                continue
            same(session, row.get('session_id'), 'session_id')
            event_id = row.get('event_id')
            if name == 'human_request':
                if row['request_id'] in [x[0] for x in human_queue]: raise ValueError(('duplicate_human_request', None, row['request_id']))
                human_queue.append((row['request_id'], row['raw']))
            elif name == 'queue_cancelled':
                same([x[0] for x in human_queue], row['request_ids'], 'cancelled_requests')
                human_queue.clear()
            elif name == 'goals':
                if type(row.get('values')) is not dict: raise ValueError(('invalid_goal_record', None, row))
            elif name == 'received':
                if pending or set(received)-set(decided) or event_id in received:
                    raise ValueError(('received_order', None, event_id))
                received[event_id] = row
                if row['source'] == 'human' and human_queue:
                    request_id, raw = human_queue.popleft()
                    same(request_id, event_id, 'human_request_order')
                    same(raw, row['raw'], 'human_request_raw')
            elif name == 'decision':
                if event_id not in received or event_id in decided or pending:
                    raise ValueError(('decision_order', None, event_id))
                event = row['normalized']
                same(received[event_id]['source'], event['source'], 'source')
                same(runtime.snapshot(), row['before'], 'decision_before')
                result = {**runtime.consider(event), 'event_id': event_id, 'definition_sha256': definition.sha256}
                same(result, row['result'], 'decision')
                decided[event_id] = (event, result)
                if result['outcome'] == 'halt':
                    report['integrity'] = 'complete'
                    raise ValueError(('halted_decision', None, result))
                pending = event_id
            elif name == 'observation':
                same(pending, event_id, 'observation_reference')
                if event_id in observed: raise ValueError(('duplicate_observation', None, event_id))
                event, result = decided[event_id]
                obs = row['observation']
                candidate = runtime.observed(event, result, obs['facts'], obs['time_s'], obs['applied_at_s'])
                same(candidate.snapshot(), row['after'], 'observation_after')
                report['path'].append({'event_id': event_id, 'line': line, 'source': event['source'],
                                       'action': event['action'], 'decision': result['outcome'],
                                       'transition': result['transition'], 'before': runtime.snapshot(), 'after': candidate.snapshot()})
                runtime, pending = candidate, None
                observed.add(event_id)
            elif name == 'fault':
                raise ValueError(('runtime_fault', None, row['issue']))
            elif name == 'session_end':
                if pending or human_queue or set(received)-set(decided): raise ValueError(('unfinished_event', None, pending))
                same(len(decided), row['events'], 'event_count')
                same(runtime.snapshot(), row['snapshot'], 'final_snapshot')
                sealed = True
            else: raise ValueError(('unknown_record', None, name))
        if runtime is None or pending or human_queue or set(received)-set(decided) or (require_seal and not sealed):
            report['issue'] = {'line': len(rows)+1, 'reason': 'incomplete_or_live_session'}
        else: report.update(status='conforms', integrity='complete' if sealed else 'live_prefix')
    except (KeyError, TypeError, ValueError) as exc:
        value = exc.args[0] if exc.args else str(exc)
        issue = {'line': locals().get('line', 0)}
        if isinstance(value, tuple) and len(value) == 3:
            issue.update(field=value[0], expected=value[1], found=value[2])
        else: issue['reason'] = str(value)
        report.update(status='nonconforming', integrity='invalid', issue=issue)
    report['steps'] = len(report['path'])
    return report


def check_file(path, require_seal=True):
    try:
        text = Path(path).read_text(encoding='utf-8')
    except (OSError, UnicodeError) as exc:
        return {'status': 'inconclusive', 'integrity': 'incomplete', 'issue': {'reason': str(exc)}, 'steps': 0, 'path': []}
    lines, rows = text.splitlines(), []
    for index, line in enumerate(lines, 1):
        try:
            if not line.strip(): raise ValueError('blank_trace_line')
            row = json.loads(line)
            if type(row) is not dict: raise ValueError('record_object_required')
            rows.append(row)
        except ValueError as exc:
            truncated = index == len(lines) and not text.endswith('\n')
            return {'status': 'inconclusive' if truncated else 'nonconforming',
                    'integrity': 'incomplete' if truncated else 'invalid',
                    'issue': {'line': index, 'reason': str(exc)}, 'steps': 0, 'path': []}
    return check_records(rows, require_seal=require_seal)
