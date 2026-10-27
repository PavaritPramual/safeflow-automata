import copy
import itertools
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from safeflow.core.definition import Definition
from safeflow.core.expressions import Expression
from safeflow.core.runtime import Runtime
from safeflow.service import Session
from safeflow.monitoring import check_records, check_file
from safeflow.verification import compile_model, build_bundle, VerificationGate, validate_bundle_files


EXAMPLE = Path(__file__).resolve().parents[1] / 'examples/smart-home/policy.yaml'


class MemorySink:
    def __init__(self): self.rows = []
    def write(self, row): self.rows.append(copy.deepcopy(row))


class TestGate:
    """An injected test double, never a production receipt or CLI bypass."""
    def require(self, definition): return {'status': 'passed', 'origin': 'test_double'}


def make_session():
    sink = MemorySink()
    return Session(Definition.load(EXAMPLE), TestGate(), sink), sink


def apply(session, action, *, source='ai', advance=30, kind='proposal', event_id=None):
    event_id = event_id or 'e' + str(len(session.decisions))
    decision = session.submit(event_id, source, kind, action, raw={'actual_input': action})
    if decision['outcome'] != 'halt':
        session.observe(event_id, session.expected_facts(event_id), session.runtime.time_s + advance, session.runtime.time_s)
    return decision


class DefinitionTests(unittest.TestCase):
    def test_readable_yaml_and_no_shared_mutation(self):
        d = Definition.load(EXAMPLE)
        data = d.data; data['parameters']['rest_s'] = 1
        self.assertEqual(d.data['parameters']['rest_s'], 180)
        self.assertEqual(d.data['transitions'][0]['on'][0], 'invalid_output')

    def test_reject_duplicate_yaml_unsafe_tags_and_aliases(self):
        for text in ('id: a\nid: b\n', '!!python/object:os.system {}', 'a: &x [1]\nb: *x\n'):
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / 'bad.yaml'; p.write_text(text)
                with self.assertRaises(ValueError): Definition.load(p)

    def test_no_executable_or_untyped_expressions(self):
        symbols = {'facts.x': 'number', 'facts.ok': 'bool'}
        for expr in ("__import__('os')", 'facts.x[0]', 'facts.x + 1 > 0', 'facts.x', 'facts.x == True', 'facts.ok > False'):
            with self.assertRaises(ValueError): Expression(expr, symbols)
        self.assertTrue(Expression('facts.ok and facts.x >= 2', symbols).evaluate({'facts.ok': True, 'facts.x': 3}))

    def test_enum_and_integer_contracts(self):
        for mutate in (
            lambda d: d['variables']['ac'].update(initial='unknown'),
            lambda d: d['variables'].update(n={'type': 'int', 'min': 0, 'max': 4, 'initial': 8}),
            lambda d: d['transitions'][0].update(when="source == 'unknown'"),
            lambda d: d['variables'].update(n={'type': 'float', 'initial': 2.0}),
        ):
            value = Definition.load(EXAMPLE).data; mutate(value)
            with self.assertRaises(ValueError): Definition(value)

    def test_generic_domain_rename_and_parameter_change(self):
        data = Definition.load(EXAMPLE).data
        data['variables']['compressor'] = data['variables'].pop('ac')
        for action in data['actions'].values():
            if 'ac' in action['set']: action['set']['compressor'] = action['set'].pop('ac')
        for group, field in (('transitions', 'when'), ('properties', 'expression')):
            for item in data[group]:
                for prefix in ('facts', 'before', 'after'): item[field] = item[field].replace(prefix + '.ac', prefix + '.compressor')
        data['clocks']['rest']['reset_when'] = data['clocks']['rest']['reset_when'].replace('.ac', '.compressor')
        data['parameters']['rest_s'] = 90
        d = Definition(data); r = Runtime(d, d.initial_facts)
        self.assertEqual(r.consider({'source': 'ai', 'kind': 'proposal', 'action': 'ac_cool'})['outcome'], 'allow')
        xml, _ = compile_model(d)
        self.assertIn('v_compressor', xml)
        self.assertNotIn('v_ac', xml)

    def test_bool_integer_actions_and_explicit_control_states(self):
        d = Definition({'format_version':1,'id':'other_site','parameters':{},
            'variables':{'enabled':{'type':'bool','initial':False},'level':{'type':'int','min':0,'max':3,'initial':0}},
            'clocks':{},'sources':['controller'],'event_kinds':['proposal'],'actions':{'start':{'set':{'enabled':True,'level':2}}},
            'states':['Idle','Running'],'initial':'Idle',
            'transitions':[{'id':'start','from':'Idle','to':'Running','on':['proposal'],'when':'True','outcome':'allow','reason':'start'},
                           {'id':'again','from':'Running','to':'Running','on':['proposal'],'when':'True','outcome':'allow','reason':'repeat'}],
            'properties':[{'id':'finite_level','type':'invariant','at':'observation','expression':'after.level <= 3'}]})
        r=Runtime(d,d.initial_facts);event={'source':'controller','kind':'proposal','action':'start'}
        result=r.observed(event,r.consider(event),{'enabled':True,'level':2},1,0)
        self.assertEqual(result.state,'Running')
        self.assertEqual(result.facts['level'],2)
        xml,_=compile_model(d)
        self.assertIn('int[0,3] v_level=0;',xml)


class RuntimeTests(unittest.TestCase):
    def test_independent_requirement_oracle(self):
        """Expected answers computed independently, without legacy/engine helpers."""
        d = Definition.load(EXAMPLE)
        for ac, heater, elapsed, source, action in itertools.product(('off', 'cool'), ('off', 'on'), (None, 0, 179, 180, 181), ('ai', 'human'), d.data['actions']):
            r = Runtime(d, {**d.initial_facts, 'ac': ac, 'heater': heater}, 200)
            r.resets['rest'] = None if elapsed is None else 200-elapsed
            conflict = (action == 'ac_cool' and heater == 'on') or (action == 'heater_on' and ac == 'cool')
            resting = action == 'ac_cool' and ac == 'off' and elapsed is not None and elapsed < 180
            expected = 'block' if source == 'ai' and (conflict or resting) else 'allow'
            self.assertEqual(r.consider(dict(source=source, kind='proposal', action=action))['outcome'], expected)

    def test_actual_off_reset_repeat_off_and_boundary(self):
        for elapsed in (179, 180, 181):
            s, _ = make_session()
            apply(s, 'ac_cool', advance=0)
            apply(s, 'ac_off', advance=elapsed)
            apply(s, 'ac_off', advance=0)
            self.assertEqual(s.runtime.snapshot()['clocks']['rest']['elapsed_s'], elapsed)
            self.assertEqual(apply(s, 'ac_cool')['outcome'], 'block' if elapsed < 180 else 'allow')

    def test_human_override_and_ai_resumes_from_actual(self):
        s, _ = make_session()
        apply(s, 'heater_on', source='human')
        self.assertEqual(apply(s, 'ac_cool', source='human')['outcome'], 'allow')
        self.assertEqual(s.runtime.facts['ac'], 'cool')
        self.assertEqual(apply(s, 'heater_on')['outcome'], 'block')
        self.assertEqual(apply(s, 'heater_off')['outcome'], 'allow')

    def test_invalid_and_timeout_are_policy_transitions(self):
        s, sink = make_session()
        for kind in ('invalid_output', 'timeout', 'adapter_error'):
            self.assertEqual(apply(s, None, kind=kind)['transition'], 'malformed')
        self.assertEqual(s.runtime.time_s, 90)
        self.assertEqual(sink.rows[1]['event'], 'received')
        data = s.runtime.definition.data
        data['transitions'][0]['outcome'] = 'halt'
        r = Runtime(Definition(data), s.runtime.definition.initial_facts)
        self.assertEqual(r.consider(dict(source='ai', kind='timeout', action=None))['outcome'], 'halt')

    def test_unknown_or_ambiguous_events_halt(self):
        s, _ = make_session()
        self.assertEqual(s.submit('x', 'ai', 'unexpected')['outcome'], 'halt')
        data = Definition.load(EXAMPLE).data
        data['transitions'].append({**data['transitions'][-1], 'id': 'duplicate'})
        d = Definition(data)
        self.assertEqual(Runtime(d,d.initial_facts).consider(dict(source='ai',kind='proposal',action='hold'))['outcome'], 'halt')

    def test_single_pending_order_and_idempotence(self):
        s, sink = make_session()
        value = s.submit('a', 'ai', 'proposal', 'ac_cool')
        count = len(sink.rows)
        self.assertEqual(value, s.submit('a', 'ai', 'proposal', 'ac_cool'))
        self.assertEqual(len(sink.rows), count)
        with self.assertRaises(ValueError): s.submit('b', 'ai', 'proposal', 'hold')
        with self.assertRaises(ValueError): s.observe('wrong', s.runtime.facts, 30, 0)
        facts = s.expected_facts('a')
        out = s.observe('a', facts, 30, 0)
        self.assertEqual(out, s.observe('a', facts, 30, 0))
        with self.assertRaises(ValueError): s.submit('a', 'human', 'proposal', 'ac_cool')

    def test_effect_mismatch_halts_and_keeps_old_state(self):
        s, sink = make_session()
        s.submit('a', 'ai', 'proposal', 'ac_cool')
        with self.assertRaisesRegex(ValueError, 'observed_effect_mismatch'): s.observe('a', s.runtime.facts, 30, 0)
        self.assertTrue(s.halted)
        self.assertEqual(s.runtime.facts['ac'], 'off')
        self.assertEqual(sink.rows[-1]['event'], 'fault')

    def test_backwards_or_delayed_application_halts(self):
        for time_s, applied in ((-1, 0), (30, 1)):
            s, _ = make_session(); s.submit('a', 'ai', 'proposal', 'hold')
            with self.assertRaises(ValueError): s.observe('a', s.runtime.facts, time_s, applied)
            self.assertTrue(s.halted)

    def test_log_failure_prevents_permission_and_state_commit(self):
        s, sink = make_session()
        def fail(row): raise OSError('disk failure')
        sink.write = fail
        with self.assertRaises(OSError): s.submit('a', 'ai', 'proposal', 'ac_cool')
        self.assertTrue(s.halted)
        self.assertEqual(s.runtime.facts['ac'], 'off')


class MonitoringTests(unittest.TestCase):
    def test_completed_path_and_first_mismatch(self):
        s, sink = make_session(); apply(s, 'ac_cool'); apply(s, 'ac_off'); s.finish()
        report = check_records(sink.rows)
        self.assertEqual(report['status'], 'conforms')
        self.assertEqual(report['steps'], 2)
        bad = copy.deepcopy(sink.rows); bad[2]['result']['outcome'] = 'block'
        result = check_records(bad)
        self.assertEqual(result['issue']['line'], 3)
        self.assertEqual(result['issue']['field'], 'decision')
        self.assertIn('expected', result['issue'])

    def test_truncated_and_live_prefix_are_explicit(self):
        s, sink = make_session(); apply(s, 'hold')
        self.assertEqual(check_records(sink.rows)['status'], 'inconclusive')
        self.assertEqual(check_records(sink.rows, require_seal=False)['integrity'], 'live_prefix')
        self.assertEqual(check_records(sink.rows[:-1])['status'], 'inconclusive')
        bad = copy.deepcopy(sink.rows); bad[2]['event_seq'] = 9
        self.assertEqual(check_records(bad)['status'], 'nonconforming')

    def test_partial_tail_is_incomplete_but_corrupt_complete_line_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'trace.jsonl'
            path.write_text('{"event":')
            self.assertEqual(check_file(path)['integrity'],'incomplete')
            path.write_text('{"event":\n')
            self.assertEqual(check_file(path)['integrity'],'invalid')

    def test_observation_write_failure_keeps_pending_without_committing_state(self):
        session,sink=make_session()
        session.submit('one','ai','proposal','ac_cool')
        sink.write=lambda row: (_ for _ in ()).throw(OSError('disk full'))
        with self.assertRaises(OSError): session.observe('one',session.expected_facts('one'),30,0)
        self.assertTrue(session.halted)
        self.assertEqual(session.pending,'one')
        self.assertEqual(session.runtime.facts['ac'],'off')
        self.assertEqual(session.runtime.time_s,0)


class CompilerTests(unittest.TestCase):
    def test_compiler_is_deterministic_and_clocks_are_guards(self):
        d = Definition.load(EXAMPLE)
        xml, queries = compile_model(d)
        self.assertEqual((xml, queries), compile_model(d))
        root = ET.fromstring(xml)
        tags=[x.tag for x in root.find('template')]
        self.assertEqual(tags,sorted(tags,key={'name':0,'location':1,'init':2,'transition':3}.__getitem__))
        self.assertEqual([q['id'] for q in queries], d.property_ids)
        self.assertTrue(any('c_rest' in (x.text or '') for x in root.findall('.//label[@kind="guard"]')))
        self.assertFalse(any('c_rest<' in (x.text or '') for x in root.findall('.//label[@kind="assignment"]')))
        # No hand-written home-specific permit() function or cooling constant.
        self.assertNotIn('permit()', xml)

    def test_bundle_hashes_and_no_receipt_cannot_activate(self):
        d = Definition.load(EXAMPLE)
        with tempfile.TemporaryDirectory() as tmp:
            build_bundle(d, tmp); validate_bundle_files(d, tmp)
            with self.assertRaises(FileNotFoundError): VerificationGate(tmp).require(d)
            (Path(tmp) / 'verification.json').write_text(json.dumps({'status': 'passed'}))
            with self.assertRaises(ValueError): VerificationGate(tmp).require(d)
            (Path(tmp) / 'model.xml').write_text('changed')
            with self.assertRaises(ValueError): validate_bundle_files(d, tmp)

    def test_changed_property_or_definition_invalidates_bundle(self):
        d = Definition.load(EXAMPLE)
        with tempfile.TemporaryDirectory() as tmp:
            build_bundle(d, tmp)
            changed = d.data; changed['parameters']['rest_s'] = 90
            with self.assertRaises(ValueError): validate_bundle_files(Definition(changed), tmp)
            (Path(tmp) / 'query-000.q').write_text('A[] true\n')
            with self.assertRaisesRegex(ValueError, 'query_mismatch'): validate_bundle_files(d, tmp)

    def test_mutation_keeps_independent_property(self):
        d = Definition.load(EXAMPLE).data
        original_properties = copy.deepcopy(d['properties'])
        d['transitions'][2]['outcome'] = 'allow'
        mutated = Definition(d)
        self.assertEqual(mutated.data['properties'], original_properties)
        r = Runtime(mutated, {**mutated.initial_facts, 'heater': 'on'})
        self.assertEqual(r.consider(dict(source='ai',kind='proposal',action='ac_cool'))['reason'], 'runtime_property_violation:no_ai_conflict')
        xml, _ = compile_model(mutated)
        self.assertIn('bad_0=true', xml)
