"""Independent concrete stepping of generated XML, not UPPAAL verification.

This catches exporter/interpreter data-flow differences on sampled paths. It does
not implement UPPAAL's symbolic zones, prove all paths, or issue an activation
receipt. Real verifier tests remain a separate acceptance prerequisite.
"""
import ast
import itertools
import operator
import re
import unittest
import xml.etree.ElementTree as ET
from safeflow.core.definition import Definition
from safeflow.core.runtime import Runtime
from safeflow.verification import compile_model
from test_core import EXAMPLE


def concrete(expression, values):
    text = expression.replace('&&', ' and ').replace('||', ' or ')
    text = re.sub(r'!(?!=)', ' not ', text)
    text = re.sub(r'\btrue\b', 'True', text); text = re.sub(r'\bfalse\b', 'False', text)
    node = ast.parse(text.strip(), mode='eval').body
    compare = {ast.Eq:operator.eq, ast.NotEq:operator.ne, ast.Lt:operator.lt,
               ast.Gt:operator.gt, ast.LtE:operator.le, ast.GtE:operator.ge}
    def run(n):
        if isinstance(n, ast.Constant): return n.value
        if isinstance(n, ast.Name): return values[n.id]
        if isinstance(n, ast.BoolOp):
            return all(run(v) for v in n.values) if isinstance(n.op, ast.And) else any(run(v) for v in n.values)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not): return not run(n.operand)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub): return -run(n.operand)
        if isinstance(n, ast.BinOp) and isinstance(n.op,ast.Add): return run(n.left)+run(n.right)
        if isinstance(n, ast.Compare):
            return all(compare[type(op)](run(a),run(b)) for a,op,b in zip([n.left]+n.comparators,n.ops,n.comparators))
        raise AssertionError('Unsupported test expression: '+ast.dump(n))
    return run(node)


class XmlMachine:
    def __init__(self, definition):
        self.definition = definition
        self.root = ET.fromstring(compile_model(definition)[0])
        self.values, self.clocks = {}, []
        for line in self.root.find('declaration').text.splitlines():
            if line.startswith('//'): continue
            match = re.fullmatch(r'(?:const )?(clock|bool|int(?:\[[^\]]*\])?) (.*);', line)
            if not match: raise AssertionError(line)
            kind, variables = match.groups()
            for var in variables.split(','):
                pair = var.strip().split('=',1)
                self.values[pair[0]] = concrete(pair[1],self.values) if len(pair)==2 else 0
                if kind == 'clock': self.clocks.append(pair[0])
        template = self.root.find('template')
        self.locations = {loc.find('name').text:loc.get('id') for loc in template.findall('location')}
        self.edges = {}
        for tr in template.findall('transition'):
            self.edges.setdefault(tr.find('source').get('ref'), []).append(tr)
        self.current = self.locations['Idle']
        data = definition.data
        strings = set(data['sources']+data['event_kinds']+list(data['actions'])+['none','allow','block','halt'])
        for variable in data['variables'].values():
            if variable['type']=='enum': strings.update(variable['values'])
        self.enums = {s:i for i,s in enumerate(sorted(strings))}

    def updates(self, edge):
        assignment = edge.find("label[@kind='assignment']")
        result = {}
        if assignment is not None:
            for statement in assignment.text.split(','):
                name,expr = statement.strip().split('=',1)
                result[name] = concrete(expr,self.values)
        return result

    def take(self, edge):
        self.values.update(self.updates(edge))
        self.current = edge.find('target').get('ref')

    def automatic(self, until):
        for _ in range(4096):
            if self.current == self.locations[until]: return
            enabled=[]
            for edge in self.edges[self.current]:
                guard=edge.find("label[@kind='guard']")
                if guard is None or concrete(guard.text,self.values): enabled.append(edge)
            if len(enabled)!=1: raise AssertionError(('nonunique XML transition',self.current,len(enabled)))
            self.take(enabled[0])
        raise AssertionError('XML stepping did not terminate')

    def step(self,event,delay):
        expected = {k:self.enums[event.get(k) or 'none'] for k in ('source','kind','action')}
        starts=[e for e in self.edges[self.locations['Idle']] if all(self.updates(e).get(k)==v for k,v in expected.items())]
        if len(starts)!=1: raise AssertionError('missing input encoding')
        self.take(starts[0]);self.automatic('AfterDecision')
        outcome=next(k for k in ('allow','block','halt') if self.values['outcome']==self.enums[k])
        if outcome=='halt': self.automatic('Stopped')
        else:
            self.automatic('Waiting')
            for clock in self.clocks: self.values[clock]+=delay
            self.take(self.edges[self.current][0]);self.automatic('Idle')
        if any(v for k,v in self.values.items() if k.startswith('bad_')): raise AssertionError('XML property flag raised')
        facts={}
        for name,spec in self.definition.data['variables'].items():
            value=self.values['v_'+name]
            facts[name]=next(s for s in spec['values'] if self.enums[s]==value) if spec['type']=='enum' else value
        return outcome,facts


class XmlConformanceTests(unittest.TestCase):
    def compare_path(self,events):
        d=Definition.load(EXAMPLE); runtime=Runtime(d,d.initial_facts); xml=XmlMachine(d)
        for source,kind,action,delay in events:
            event=dict(source=source,kind=kind,action=action)
            decision=runtime.consider(event)
            expected_facts=dict(runtime.facts)
            if decision['outcome']=='allow': expected_facts.update(d.data['actions'][action]['set'])
            self.assertEqual(xml.step(event,delay),(decision['outcome'],expected_facts))
            runtime=runtime.observed(event,decision,expected_facts,runtime.time_s+delay,runtime.time_s)
            for name,clock in runtime.snapshot()['clocks'].items():
                self.assertEqual(xml.values['active_'+name],clock['active'])
                self.assertEqual(xml.values['c_'+name],clock['elapsed_s'])

    def test_generated_xml_matches_runtime_clock_boundaries_and_humans(self):
        for delay in (0,30,179,180,181):
            self.compare_path([
                ('ai','proposal','hold',42),('ai','proposal','ac_cool',0),
                ('ai','proposal','ac_off',delay),('ai','proposal','ac_off',0),
                ('ai','proposal','ac_cool',30),('human','proposal','heater_on',30),
                ('human','proposal','ac_cool',30),('ai','proposal','heater_on',30),
                ('ai','invalid_output',None,30),('ai','timeout',None,30)])

    def test_all_two_action_paths_from_verified_initial_state(self):
        d=Definition.load(EXAMPLE)
        for first,second,source in itertools.product(d.data['actions'],d.data['actions'],('ai','human')):
            self.compare_path([('ai','proposal',first,30),(source,'proposal',second,30)])

    def test_declared_halt_has_no_observation_or_time_advance(self):
        data=Definition.load(EXAMPLE).data;data['transitions'][0]['outcome']='halt'
        d=Definition(data);xml=XmlMachine(d)
        outcome,facts=xml.step({'source':'ai','kind':'timeout','action':None},30)
        self.assertEqual(outcome,'halt');self.assertEqual(facts,d.initial_facts)
        self.assertEqual(xml.values['c_rest'],0)
