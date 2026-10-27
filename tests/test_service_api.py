import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
from safeflow.application import Application
from safeflow.api import make_server, NotReady
from safeflow.adapters.proposers import OllamaProposer, OpenAICompatibleProposer
from safeflow.adapters.smart_home import SmartHomeEnvironment
from safeflow.core.definition import Definition
from safeflow.monitoring import check_records
from safeflow.runner import Loop
from safeflow.service import Session
from test_core import EXAMPLE, TestGate, MemorySink


ROOT = Path(__file__).resolve().parents[1]
KEY = 'test-only-api-key-' + 'x'*24
BINDINGS = {'ac': 'air_conditioner', 'heater': 'heater', 'fan': 'ventilation_fan', 'light': 'light'}


class FakeProposer:
    def __init__(self, action='ac_cool'): self.action, self.calls = action, 0
    def metadata(self): return {'provider': 'fixture', 'command_origin': 'prepared_test', 'not_real_ai': True}
    def propose(self, observation, seed=0):
        self.calls += 1
        return {'native_action': self.action}
    def normalize(self, raw): return {'kind': 'proposal', 'action': raw['native_action']}


class AdapterTests(unittest.TestCase):
    def test_both_real_provider_decoders_follow_same_contract(self):
        for cls, raw in ((OllamaProposer, {'message': {'content': '{"action":"hold"}'}}),
                         (OpenAICompatibleProposer, {'choices': [{'message': {'content': '{"action":"hold"}'}}]})):
            p = cls('test', 'http://fixture', 'choose', ['hold'])
            self.assertEqual(p.normalize({'raw': raw}), {'kind': 'proposal', 'action': 'hold'})
            self.assertEqual(p.normalize({'raw': {}}), {'kind': 'invalid_output', 'action': None})
            self.assertEqual(p.normalize({'raw': None, 'error_kind': 'timeout'}), {'kind': 'timeout', 'action': None})

    def test_unknown_and_duplicate_actions_do_not_get_repaired(self):
        p = OllamaProposer('test', 'http://fixture', 'choose', ['hold'])
        for value in ('{"action":"other"}', '{"action":"hold","action":"hold"}', 'hold', '{"action":"hold","extra":1}'):
            self.assertEqual(p.normalize({'raw': {'message': {'content': value}}})['kind'], 'invalid_output')

    def test_ollama_records_actual_request_without_executing_action(self):
        p = OllamaProposer('test', 'http://fixture', 'choose', ['hold'])
        with patch('safeflow.adapters.proposers.request_json', return_value={'message': {'content': '{"action":"hold"}'}}) as call:
            result = p.propose({'facts': {}}, seed=4)
            self.assertEqual(result['request']['options']['seed'], 4)
            self.assertEqual(p.normalize(result)['action'], 'hold')
            self.assertEqual(call.call_args.args[0], 'http://fixture/api/chat')

    def test_provider_failure_is_an_event_and_key_is_not_logged(self):
        p = OpenAICompatibleProposer('test', 'http://fixture', 'choose', ['hold'], api_key_env='SAFEFLOW_TEST_KEY')
        with patch.dict('os.environ', {'SAFEFLOW_TEST_KEY': 'secret-test-value'}):
            with patch('safeflow.adapters.proposers.request_json', side_effect=TimeoutError):
                result = p.propose({})
                self.assertEqual(p.normalize(result)['kind'], 'timeout')
                self.assertNotIn('secret-test-value', json.dumps(result))

    def test_environment_is_only_place_with_native_device_mapping(self):
        d = Definition.load(EXAMPLE)
        env = SmartHomeEnvironment(d, BINDINGS)
        self.assertEqual(env.sample()['facts'], d.initial_facts)
        result = env.execute('ac_cool')
        self.assertEqual(result['facts']['ac'], 'cool')
        self.assertEqual(result['time_s'], 30)
        self.assertEqual(result['applied_at_s'], 0)
        self.assertEqual(env.human_action({'device': 'heater', 'mode': 'on'})['action'], 'heater_on')
        self.assertEqual(env.human_action({'device': 'missing', 'mode': 'on'})['kind'], 'invalid_output')


class LoopTests(unittest.TestCase):
    def make_loop(self, proposer=None):
        d, sink = Definition.load(EXAMPLE), MemorySink()
        env = SmartHomeEnvironment(d, BINDINGS)
        session = Session(d, TestGate(), sink)
        return Loop(session, proposer or FakeProposer(), env, env.human_action), sink

    def test_human_one_round_then_ai_and_trace_path(self):
        loop, sink = self.make_loop()
        loop.enqueue({'device': 'heater', 'mode': 'on'})
        first = loop.step(); self.assertEqual(first['last_result']['source'], 'human')
        second = loop.step(); self.assertEqual(second['last_result']['decision'], 'block')
        self.assertEqual(loop.proposer.calls, 1)
        loop.finish()
        self.assertEqual(check_records(sink.rows)['status'], 'conforms')

    def test_raw_is_durable_before_normalization_and_failure_prevents_execution(self):
        loop, sink = self.make_loop()
        original = loop.proposer.normalize
        def normalize(raw):
            self.assertEqual(sink.rows[-1]['event'], 'received')
            return original(raw)
        loop.proposer.normalize = normalize
        loop.step()
        before = loop.environment.sample()
        def fail(row): raise OSError('disk full')
        sink.write = fail
        with self.assertRaises(OSError): loop.step()
        self.assertEqual(before, loop.environment.sample())

    def test_step_request_id_does_not_repeat_execution(self):
        loop, _ = self.make_loop()
        first = loop.step(request_id='same')
        self.assertEqual(first, loop.step(request_id='same'))
        self.assertEqual(loop.steps, 1)
        self.assertEqual(loop.proposer.calls, 1)

    def test_numeric_model_adapter_can_replace_llm_without_core_changes(self):
        class IndexAdapter:
            def metadata(self): return {'provider':'numeric-test-fixture','not_real_ai':True}
            def propose(self, observation, seed=0): return {'raw':3}
            def normalize(self, response):
                return {'kind':'proposal','action':{3:'light_on'}[response['raw']]}
        loop,sink=self.make_loop(IndexAdapter())
        snapshot=loop.step()
        self.assertEqual(snapshot['devices']['light'],'on')
        self.assertEqual(sink.rows[1]['raw'],{'raw':3})

    def test_malformed_proposer_is_controlled_by_definition(self):
        p = OllamaProposer('test', 'http://fixture', 'choose', ['hold'])
        p.propose = lambda *args: {'raw': {'message': {'content': 'nonsense'}}}
        loop, _ = self.make_loop(p)
        self.assertEqual(loop.step()['last_result']['decision'], 'block')
        self.assertEqual(loop.environment.sample()['time_s'], 30)

    def test_stop_during_model_call_logs_without_operating_environment(self):
        loop, sink = self.make_loop()
        def propose(*args):
            loop.request_stop()
            return {'native_action': 'ac_cool'}
        loop.proposer.propose = propose
        with self.assertRaisesRegex(RuntimeError, 'stopping'): loop.step()
        self.assertEqual(loop.environment.sample()['time_s'], 0)
        self.assertEqual(loop.environment.sample()['facts']['ac'], 'off')
        self.assertEqual([x['event'] for x in sink.rows], ['session_start','received','fault'])


class ApplicationTests(unittest.TestCase):
    def test_unverified_application_is_read_only_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Application(ROOT/'examples/smart-home/lab.yaml', logs=tmp, verification=Path(tmp)/'missing')
            self.assertEqual(app.health()['readiness'], 'not_ready')
            self.assertTrue(app.lab_state()['halted'])
            with self.assertRaises(NotReady): app.lab_step()
            self.assertEqual(list(Path(tmp).glob('session-*.jsonl')), [])

    def test_lab_reset_creates_new_trace_and_fixed_verified_initial_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Application(ROOT/'examples/smart-home/lab.yaml', logs=tmp)
            app.gate = TestGate()  # Explicit test-only injected port; not exposed by CLI/API.
            first = app.lab_state()
            app.lab_enqueue({'device': 'light', 'mode': 'on'})
            reset = app.lab_reset({'temperature_c': 29})
            self.assertNotEqual(first['session_id'], reset['session_id'])
            self.assertEqual(reset['temperature_c'], 29)
            self.assertEqual(reset['pending_requests'], 0)
            with self.assertRaises(ValueError): app.lab_reset({'devices': {'heater': 'on'}})
            app.close()
            for path in Path(tmp).glob('*.jsonl'):
                rows = [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()]
                self.assertEqual(check_records(rows)['status'], 'conforms')


class HttpTests(unittest.TestCase):
    def test_versioned_http_auth_sessions_and_not_ready_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Application(ROOT/'examples/smart-home/lab.yaml', logs=tmp, verification=Path(tmp)/'missing')
            server = make_server(app, KEY, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            base = 'http://127.0.0.1:' + str(server.server_address[1])
            def req(path, body=None, authenticated=True):
                headers = {'Authorization': 'Bearer '+KEY} if authenticated else {}
                request = Request(base+path, data=None if body is None else json.dumps(body).encode(), headers=headers)
                try:
                    with urlopen(request, timeout=5) as response: return response.status, json.load(response)
                except HTTPError as exc: return exc.code, json.load(exc)
            try:
                self.assertEqual(req('/health', authenticated=False)[1]['readiness'], 'not_ready')
                self.assertEqual(req('/v1/verification', authenticated=False)[0], 401)
                self.assertEqual(req('/v1/sessions', {})[0], 503)
                self.assertEqual(req('/step', {})[0], 503)
                app.gate = TestGate()
                status, value = req('/v1/sessions', {})
                self.assertEqual(status, 201)
                path = '/v1/sessions/'+value['session_id']
                payload = {'event_id': 'one', 'source': 'ai', 'kind': 'proposal', 'action': 'ac_cool', 'raw': 2}
                self.assertEqual(req(path+'/events', payload)[1]['outcome'], 'allow')
                self.assertTrue(req(path+'/events', payload)[1]['replayed'])
                facts = {**value['facts'], 'ac': 'cool'}
                self.assertEqual(req(path+'/observations', {'event_id':'one','facts':facts,'time_s':30,'applied_at_s':0})[0],200)
                self.assertTrue(req(path+'/events', payload)[1]['observation_recorded'])
                self.assertEqual(req(path+'/close', {})[1]['sealed'], True)
                self.assertEqual(req('/v1/sessions', {'policy': '../../bad'})[0], 400)
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=5)
