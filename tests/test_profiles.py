"""Profile reuse contracts. HTTP fixtures are labelled and are not real AI runs."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from tools.profile_acceptance import ROOT,PROFILES,ORACLE,run_profile,load_script
from safeflow.core.definition import Definition
from safeflow.adapters.smart_home import SmartHomeEnvironment
from safeflow.runner import Loop
from safeflow.service import Session
from test_core import TestGate,MemorySink

LIVE=load_script('live_acceptance','check-live-loop.py')


def definition(tag):
    config=PROFILES[tag][0]
    return Definition.load(config.parent/'policy.yaml')


class ProfileTests(unittest.TestCase):
    def test_b_changes_only_the_threshold(self):
        a=definition('A').data;b=definition('B').data
        a['parameters']['rest_s']=90
        self.assertEqual(a,b)

    def test_c_is_b_with_explicit_aliases_only(self):
        b=definition('B').data;c=definition('C').data
        c['variables']['ac']=c['variables'].pop('cooling_unit')
        c['actions']={('ac_cool' if k=='cooling_on' else 'ac_off' if k=='cooling_off' else k):v for k,v in c['actions'].items()}
        for item in c['actions'].values():
            if 'cooling_unit' in item['set']:item['set']['ac']=item['set'].pop('cooling_unit')
        def back(value):return value.replace('.cooling_unit','.ac').replace("'cooling_on'","'ac_cool'").replace("'cooling_off'","'ac_off'")
        for item in c['transitions']:item['when']=back(item['when'])
        for item in c['properties']:item['expression']=back(item['expression'])
        for item in c['clocks'].values():item['reset_when']=back(item['reset_when'])
        self.assertEqual(b,c)
        self.assertNotEqual(definition('B').sha256,definition('C').sha256)

    def test_all_boundaries_and_bindings_over_fixture_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            results=[run_profile(tag,Path(tmp)/tag,_test_gate=TestGate()) for tag in PROFILES]
        self.assertEqual([next(c['found'] for c in r['cases'] if c['case']=='restart_boundary' and c['elapsed_s']==120) for r in results],['block','allow','allow'])
        for r in results:
            self.assertEqual(r['verification_origin'],'test_double')
            self.assertTrue(r['not_real_ai'])
            self.assertEqual(r['actual_llm_calls'],0)


class AliasOracleTests(unittest.TestCase):
    def trace(self,path):
        d=definition('C');sink=MemorySink()
        env=SmartHomeEnvironment(d,{'cooling_unit':'air_conditioner','heater':'heater','fan':'ventilation_fan','light':'light'})
        class FixtureProposer:
            action='cooling_on'
            def metadata(self):return {'provider':'fixture','not_real_ai':True}
            def propose(self,*args):return {'raw':{'message':{'content':json.dumps({'action':self.action})}}}
            def normalize(self,raw):return {'kind':'proposal','action':json.loads(raw['raw']['message']['content'])['action']}
        proposer=FixtureProposer();loop=Loop(Session(d,TestGate(),sink),proposer,env,env.human_action)
        loop.step();loop.enqueue({'device':'air_conditioner','mode':'off'});loop.step()
        loop.step();proposer.action='hold';loop.step();proposer.action='cooling_on';loop.step();loop.finish()
        path.write_text(''.join(json.dumps(row)+'\n' for row in sink.rows),encoding='utf-8')

    def test_contract_aliases_and_threshold_are_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fixture.jsonl';self.trace(path)
            spec=ORACLE.contract(PROFILES['C'][1])
            self.assertEqual(ORACLE.check(path,requirements=spec)['checked'],5)
            wrong=copy.deepcopy(spec);wrong['rest_s']=180
            with self.assertRaises(AssertionError):ORACLE.check(path,requirements=wrong)
            with self.assertRaises(AssertionError):ORACLE.check(path)

    def test_rejects_unknown_and_colliding_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'requirements.json'
            for facts in ({'ac':'heater'},{'unknown':'x'}):
                path.write_text(json.dumps({'format_version':1,'rest_s':90,'facts':facts,'actions':{}}))
                with self.assertRaises(ValueError):ORACLE.contract(path)
        self.assertEqual(ORACLE.contract()['rest_s'],180)


class NativeResponseEvidenceTests(unittest.TestCase):
    def test_counts_native_invalid_content_but_not_timeouts_or_nonmodel_errors(self):
        rows=[]
        for seq,source,raw in [(1,'ai',{'raw':None,'error_kind':'timeout'}),
            (3,'ai',{'raw':{'model':'qwen3:0.6b','message':None}}),
            (5,'human',{'device':'air_conditioner','mode':'cool'}),
            (7,'ai',{'raw':{'model':'qwen3:0.6b','message':{'content':'not JSON'}},'request':{'options':{'seed':0}}})]:
            event_id=str(seq)
            rows.extend([{'event':'received','event_seq':seq,'event_id':event_id,'source':source,'raw':raw},
                         {'event':'observation','event_seq':seq+1,'event_id':event_id}])
        result=LIVE.response_counts(rows,'qwen3:0.6b')
        self.assertEqual(result['actual_model_responses'],1)
        self.assertEqual(result['completed_human_requests'],1)
        self.assertTrue(result['ai_resumed_after_human'])
        self.assertEqual(result['request_options'],[{'seed':0}])
        self.assertEqual(LIVE.response_counts(rows,'other-model')['actual_model_responses'],0)

    def test_live_prefix_does_not_parse_a_partial_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'live.jsonl';path.write_bytes(b'{"event":"one"}\n{"partial":')
            self.assertEqual(LIVE.trace_prefix(path),[{'event':'one'}])
