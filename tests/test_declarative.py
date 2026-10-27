import copy
import itertools
import json
import tempfile
import unittest
from pathlib import Path
from safeflow.automata import Automata
from safeflow.legacy_automata import Automata as Legacy
from safeflow.policy import Policy, Engine
from safeflow.behavior import check_records, check_file
from safeflow.commands import Command, MODES
from safeflow.controller import Controller
from safeflow.environment import Home
from safeflow.trace import Trace, replay
from test_runtime import Agent, response


class DeclarativeTests(unittest.TestCase):
    def test_matches_legacy_and_oracle(self):
        count = 0
        commands = [Command('hold')] + [Command('set_device', d, mode) for d, modes in MODES.items() for mode in modes]
        policy = Policy.load()
        for ac, heat, elapsed, source, command in itertools.product((False, True), (False, True), (None, 0, 120, 179, 180, 181), ('ai', 'human'), commands):
            home = Home()
            home.reset({'devices': {'air_conditioner': 'cool' if ac else 'off', 'heater': 'on' if heat else 'off'}})
            home.time_s = 200
            home.last_ac_off_s = None if elapsed is None else 200 - elapsed
            old, new = Legacy(), Automata(policy)
            old.reset(home.snapshot()); new.reset(home.snapshot())
            expected = old.evaluate(command, source, home.snapshot())
            actual = new.evaluate(command, source, home.snapshot())
            self.assertEqual((actual.outcome, actual.reason), (expected.outcome, expected.reason))
            count += 1
        self.assertEqual(count, 432)

    def test_changed_file_changes_behavior_without_python_edit(self):
        definition = Policy.load().definition
        definition['parameters']['rest_s'] = 90
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'policy.json'
            path.write_text(json.dumps(definition), encoding='utf-8')
            home = Home(); home.apply(Command('set_device', 'air_conditioner', 'cool'))
            home.apply(Command('set_device', 'air_conditioner', 'off')); home.advance(120)
            for policy, expected in ((Policy.load(), 'block'), (Policy.load(path), 'allow')):
                guard = Automata(policy); guard.reset(home.snapshot())
                self.assertEqual(guard.evaluate(Command('set_device', 'air_conditioner', 'cool'), 'ai', home.snapshot()).outcome, expected)

    def test_engine_has_no_home_specific_references(self):
        definition = Policy.load().definition
        definition['facts'] = {'switch': 'bool', 'elapsed': 'nullable_number', 'time_s': 'number'}
        definition['clocks'] = {}
        edge = dict(id='go', phase='proposal', **{'from': 'Idle'}, to='Idle', when=True, outcome='allow', reason=None)
        observed = {**edge, 'id': 'observe', 'phase': 'observed', 'outcome': 'observe'}
        definition['machines'] = [dict(id='Independent', initial='Idle', states={'Idle': True}, transitions=[edge, observed])]
        engine = Engine(Policy(definition)); facts = {'switch': False, 'elapsed': None, 'time_s': 0}
        engine.reset(facts)
        self.assertEqual(engine.consider({'name': 'custom', 'device': None, 'mode': None}, 'ai', facts)[0], 'allow')

    def test_policy_rejects_unknown_operations_references_and_targets(self):
        for edit in ('operation', 'reference', 'target', 'extra', 'parameter'):
            definition = Policy.load().definition
            edge = definition['machines'][0]['transitions'][0]
            if edit == 'operation': edge['when'] = {'eval': 'print(1)'}
            if edit == 'reference': edge['when'] = {'ref': '__class__'}
            if edit == 'target': edge['to'] = 'Unknown'
            if edit == 'extra': definition['execute_python'] = 'print(1)'
            if edit == 'parameter': definition['parameters']['rest_s'] = -1
            with self.subTest(edit=edit), self.assertRaises(ValueError): Policy(definition)

    def test_policy_duplicate_keys_and_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.json'; path.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError): Policy.load(path)
        policy = Policy.load(); original = policy.sha256
        external = policy.definition; external['parameters']['rest_s'] = 0
        self.assertEqual(policy.definition['parameters']['rest_s'], 180)
        self.assertEqual(policy.sha256, original)

    def test_malformed_policy_shapes_stop_before_running(self):
        for value in (None, [], {}, 'bad'):
            with self.subTest(value=value), self.assertRaises(ValueError): Policy(value)

    def test_ambiguous_missing_and_unknown_state_stop(self):
        for kind in ('ambiguous', 'missing', 'state'):
            definition = Policy.load().definition
            machine = definition['machines'][0]
            if kind == 'ambiguous':
                edge = copy.deepcopy(machine['transitions'][0]); edge['id'] += '.duplicate'; machine['transitions'].append(edge)
            elif kind == 'missing': machine['transitions'][0]['when'] = False
            else: machine['states']['BothOff'] = False
            guard = Automata(Policy(definition)); home = Home()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                guard.reset(home.snapshot())
                guard.evaluate(Command('hold'), 'human', home.snapshot())

    def test_all_block_reasons_retained(self):
        home = Home(); home.reset({'devices': {'heater': 'on'}})
        home.apply(Command('set_device', 'air_conditioner', 'cool'))
        home.apply(Command('set_device', 'air_conditioner', 'off'))
        guard = Automata(); guard.reset(home.snapshot())
        decision = guard.evaluate(Command('set_device', 'air_conditioner', 'cool'), 'ai', home.snapshot())
        self.assertEqual(decision.reasons, ('ac_heater_conflict', 'ac_cooldown'))


class BehaviorTests(unittest.TestCase):
    def fixture(self, enforcement=True):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'events.jsonl'
        controller = Controller(Home(), Agent(), Trace(path), enforcement=enforcement)
        return controller, path

    def rows(self, path): return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()]

    def test_raw_recorded_before_decode_and_apply(self):
        import safeflow.controller as module
        c, path = self.fixture(); original = module.decode_response
        def decode(*args):
            self.assertEqual(self.rows(path)[-1]['event'], 'received')
            self.assertEqual(c.home.time_s, 0)
            return original(*args)
        module.decode_response = decode
        try: c.step()
        finally: module.decode_response = original

    def test_sealed_path_has_source_lines_and_policy_copy(self):
        c, path = self.fixture(); c.step(); c.finish()
        report = check_file(path)
        self.assertEqual(report['status'], 'conforms')
        edge = report['episodes'][0]['path'][0]
        self.assertEqual(set(edge['lines']), {'received', 'proposal', 'decision', 'execution'})
        self.assertTrue((path.parent / 'policies' / (c.automata.policy.sha256 + '.json')).exists())
        self.assertEqual(replay(self.rows(path), Home()), c.home.snapshot())

    def test_unshielded_violation_replays_but_does_not_conform(self):
        c, path = self.fixture(False); c.reset({'devices': {'heater': 'on'}}); c.step(); c.finish()
        report = check_file(path)
        self.assertEqual((report['status'], report['integrity']), ('nonconforming', 'complete'))
        self.assertEqual(report['issue']['field'], 'command_permitted_by_A')
        self.assertEqual(replay(self.rows(path), Home()), c.home.snapshot())

    def test_human_both_on_then_ai_and_several_episodes(self):
        c, path = self.fixture(); c.step()
        c.enqueue(response('heater', 'on')['message']['tool_calls'][0]); c.step()
        self.assertEqual(c.step()['last_result']['decision'], 'block')
        c.finish(); c.reset(); c.step(); c.finish()
        report = check_file(path)
        self.assertEqual(report['status'], 'conforms')
        self.assertEqual(report['steps'], 4)

    def test_invalid_raw_and_model_error_are_preserved(self):
        for raw_error in ('raw', 'exception'):
            c, path = self.fixture()
            if raw_error == 'raw': c.agent.propose = lambda *a: {'raw': {'message': {'content': 'bad'}}}
            else: c.agent.propose = lambda *a: (_ for _ in ()).throw(RuntimeError('failure'))
            c.step(); c.finish()
            report = check_file(path)
            self.assertEqual(report['status'], 'conforms')
            self.assertIsNone(report['episodes'][0]['path'][0]['event'])

    def test_incomplete_deleted_and_reordered_records(self):
        c, path = self.fixture(); c.step(); c.finish(); rows = self.rows(path)
        variants = [rows[:-1], rows[:-2], rows[:2] + rows[3:]]
        reordered = copy.deepcopy(rows); reordered[2], reordered[3] = reordered[3], reordered[2]; variants.append(reordered)
        for records in variants:
            with self.subTest(length=len(records)):
                self.assertEqual(check_records(records)['status'], 'inconclusive')

    def test_mutated_decision_time_state_policy_and_raw_are_detected(self):
        c, path = self.fixture(); c.step(); c.finish(); rows = self.rows(path)
        for field in ('decision', 'time', 'state', 'policy', 'raw', 'source', 'transition', 'clock'):
            changed = copy.deepcopy(rows)
            events = {r['event']: r for r in changed}
            if field == 'decision': events['decision']['decision'] = 'block'
            if field == 'time': events['execution']['after']['simulation_time_s'] += 1
            if field == 'state': events['execution']['after']['devices']['heater'] = 'on'
            if field == 'policy': events['reset']['policy']['parameters']['rest_s'] = 1
            if field == 'raw': events['received']['raw'] = {}
            if field == 'source': events['proposal']['source'] = 'human'
            if field == 'transition': events['decision']['transitions'] = []
            if field == 'clock': events['execution']['after']['ac_off_elapsed_s'] = 0
            with self.subTest(field=field): self.assertEqual(check_records(changed)['status'], 'nonconforming')

    def test_failure_before_raw_capture_prevents_decode_and_execution(self):
        c, path = self.fixture(); writer = c.trace.write
        def fail(row):
            if row['event'] == 'received': raise OSError('full')
            writer(row)
        c.trace.write = fail
        with self.assertRaises(OSError): c.step()
        self.assertEqual(c.home.time_s, 0)
        self.assertTrue(c.halted)

    def test_fault_is_inconclusive_and_no_retry(self):
        c, path = self.fixture(); writer = c.trace.write
        def fail(row):
            if row['event'] == 'execution': raise OSError('full')
            writer(row)
        c.trace.write = fail
        with self.assertRaises(OSError): c.step()
        self.assertEqual(check_file(path)['status'], 'inconclusive')
        with self.assertRaises(RuntimeError): c.step()

    def test_historical_v2_trace_still_replays(self):
        root = Path(__file__).resolve().parents[1] / 'experiments' / 'smart-home-stage2'
        paths = list(root.glob('*shielded.jsonl'))
        self.assertTrue(paths)
        for path in paths:
            self.assertIn('devices', replay(self.rows(path), Home()))

    def test_trace_refuses_reusing_evidence_filename(self):
        _, path = self.fixture()
        with self.assertRaises(ValueError): Trace(path)

    def test_complete_demo_is_repeatable_and_never_overwrites(self):
        from safeflow.demo import run_demo
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'a', Path(tmp) / 'b'
            results = [run_demo(p, root / 'configs/demo-scenarios.json', Policy.load()) for p in (a,b)]
            self.assertEqual(results[0], results[1])
            for left in a.glob('*-X.json'):
                x, y = [json.loads(p.read_text(encoding='utf-8')) for p in (left, b / left.name)]
                normalize = lambda report: [(s['event'], s['decision'], s['before'], s['after']) for e in report['episodes'] for s in e['path']]
                self.assertEqual(normalize(x), normalize(y))
            with self.assertRaises(FileExistsError): run_demo(a, root / 'configs/demo-scenarios.json', Policy.load())


if __name__ == '__main__': unittest.main()
