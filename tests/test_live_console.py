"""Console contracts use a labelled fixture proposer, never actual-AI evidence."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from safeflow.application import Application
from safeflow.monitoring import check_file
from tools.live_console import Console, make_server
from test_core import TestGate

ROOT = Path(__file__).resolve().parents[1]


def wait_for(predicate, timeout=5):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if predicate(): return
        time.sleep(.01)
    raise AssertionError('condition_not_reached')


class Fixture:
    def __init__(self, blocked=False):
        self.entered, self.release = threading.Event(), threading.Event()
        if not blocked: self.release.set()
        self.calls = 0

    def metadata(self):
        return {'provider':'fixture','model':'fixture','not_real_ai':True,'command_origin':'prepared_test'}

    def propose(self, sample, seed=0):
        self.calls += 1
        self.entered.set()
        if not self.release.wait(5): raise TimeoutError('fixture_release_missing')
        return {'raw':{'model':'fixture','message':{'content':'{"action":"light_on"}'}},
                'request':{'messages':[{'role':'user','content':json.dumps(sample)}]}}

    def normalize(self, response):
        return {'kind':'proposal','action':'light_on'}


def application(directory, fixture):
    app = Application(ROOT/'examples/smart-home/lab.yaml', logs=directory,
                      verification=Path(directory)/'intentionally_missing_test_bundle')
    app.gate = TestGate()  # Unit injection only; CLI has no bypass.
    app._lab().proposer = fixture
    return app


class ConsoleTests(unittest.TestCase):
    def test_pause_finishes_round_human_input_is_responsive_and_FIFO(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(blocked=True)
            c = Console(application(tmp, fixture), interval=.2)
            try:
                c.start(); self.assertTrue(fixture.entered.wait(2))
                self.assertTrue(c.snapshot()['busy'])
                c.submit('light_off','human-1')
                c.submit('light_on','human-2')
                self.assertTrue(c.submit('light_off','human-1')['replayed'])
                self.assertEqual(c.snapshot()['pending'],2)
                c.pause(); fixture.release.set()
                wait_for(lambda:not c.snapshot()['busy'])
                self.assertEqual(c.snapshot()['state']['steps'],1)
                time.sleep(.25)
                self.assertEqual(fixture.calls,1)
                c.start()
                wait_for(lambda:c.snapshot()['state']['steps']>=3)
                c.pause(); wait_for(lambda:not c.snapshot()['busy'])
                rows=[e for e in c.snapshot()['events'] if e['kind']=='decision']
                self.assertEqual([e['data']['normalized']['source'] for e in rows[:3]],['ai','human','human'])
                self.assertEqual([e['data']['normalized']['action'] for e in rows[:3]],['light_on','light_off','light_on'])
                self.assertEqual(c.snapshot()['pending'],0)
            finally:
                fixture.release.set(); c.pause(); c.close()
            trace=next(Path(tmp).glob('session-*.jsonl'))
            self.assertEqual(check_file(trace)['integrity'],'complete')

    def test_unverified_definition_cannot_start_or_enqueue(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=Application(ROOT/'examples/smart-home/lab.yaml',logs=tmp,verification=Path(tmp)/'missing')
            c=Console(app)
            try:
                self.assertFalse(c.ready)
                with self.assertRaises(RuntimeError):c.start()
                with self.assertRaises(RuntimeError):c.submit('light_on','test-request')
                self.assertFalse(list(Path(tmp).glob('session-*.jsonl')))
            finally:c.close()

    def test_decision_log_failure_stops_loop_before_device_operation(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=application(tmp,Fixture());sink=app.loop.session.sink
            class FailDecision:
                def write(self,row):
                    if row['event']=='decision':raise OSError('injected_fixture_log_failure')
                    sink.write(row)
            app.loop.session.sink=FailDecision()
            c=Console(app,interval=.05)
            try:
                c.start();wait_for(lambda:c.snapshot()['error'] is not None)
                self.assertFalse(c.snapshot()['running'])
                self.assertEqual(app.loop.environment.home.time_s,0)
                with self.assertRaises(RuntimeError):c.start()
            finally:c.close()

    def test_renamed_policy_hides_stale_image_and_maps_human_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=Application(ROOT/'examples/smart-home/variants/renamed-90/lab.yaml',
                            logs=tmp,verification=Path(tmp)/'missing_fixture_bundle')
            app.gate=TestGate();app._lab().proposer=Fixture()
            c=Console(app,interval=.2)
            try:
                self.assertFalse(c.rules()['overview_matches'])
                self.assertEqual(c.rules()['definition']['parameters']['rest_s'],90)
                c.submit('cooling_on','renamed-request');c.start()
                wait_for(lambda:c.snapshot()['state']['steps']>=1)
                c.pause();wait_for(lambda:not c.snapshot()['busy'])
                self.assertEqual(c.snapshot()['state']['facts']['cooling_unit'],'cool')
                self.assertEqual(c.snapshot()['state']['last_result']['source'],'human')
            finally:c.close()

    def test_http_requires_local_session_and_rules_match_loaded_definition(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Console(application(tmp,Fixture()));server=make_server(c,0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url='http://127.0.0.1:'+str(server.server_port)
            def request(path,data=None,auth=False,host=None):
                headers={'Content-Type':'application/json'}
                if auth:headers.update(Origin=url,Cookie='console_session='+c.token)
                if host:headers['Host']=host
                r=Request(url+path,data=None if data is None else json.dumps(data).encode(),headers=headers)
                try:
                    with urlopen(r,timeout=3) as response:
                        payload=response.read();return response.status,json.loads(payload) if response.headers.get_content_type()=='application/json' else payload
                except HTTPError as exc:return exc.code,json.load(exc)
            try:
                self.assertEqual(request('/')[0],200)
                self.assertEqual(request('/',host='external.example')[0],403)
                self.assertEqual(request('/api/start',{})[0],403)
                status,rules=request('/api/rules');self.assertEqual(status,200)
                self.assertEqual(rules['sha256'],c.app.definition.sha256)
                self.assertTrue(rules['overview_matches'])
                self.assertEqual(request('/api/human',{'action':'light_off','request_id':'http-1'},True)[0],202)
                self.assertEqual(request('/api/human',{'action':'light_on','request_id':'http-1'},True)[0],400)
                self.assertEqual(c.snapshot()['pending'],1)
                self.assertEqual(request('/api/events?after=-1')[0],400)
            finally:
                server.shutdown();server.server_close();thread.join();c.close()


if __name__=='__main__':unittest.main()
