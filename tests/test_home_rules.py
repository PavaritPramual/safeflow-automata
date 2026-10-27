"""Independent requirements for all four simulated devices, not copied guards."""
import itertools
import json
import os
import unittest
from pathlib import Path
from safeflow.core.definition import Definition
from safeflow.core.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
# Expected command effects and thresholds are specified independently of YAML.
EFFECTS = {'hold': {}, 'ac_cool': {'ac':'cool'}, 'ac_off': {'ac':'off'},
           'heater_on': {'heater':'on'}, 'heater_off': {'heater':'off'},
           'fan_on': {'fan':'on'}, 'fan_off': {'fan':'off'},
           'light_on': {'light':'on'}, 'light_off': {'light':'off'}}
PROFILES = [('A','examples/smart-home/policy.yaml',180,False),
            ('B','examples/smart-home/variants/cooldown-90/policy.yaml',90,False),
            ('C','examples/smart-home/variants/renamed-90/policy.yaml',90,True)]


class HomeRulesTests(unittest.TestCase):
    def test_all_devices_sources_actions_and_time_boundaries(self):
        counts = {}
        for profile,path,rest,renamed in PROFILES:
            definition = Definition.load(ROOT/path); count = 0
            def action_id(name):
                return {'ac_cool':'cooling_on','ac_off':'cooling_off'}.get(name,name) if renamed else name
            def facts(values):
                return {('cooling_unit' if renamed and k=='ac' else k):v for k,v in values.items()}
            self.assertEqual(set(definition.data['actions']), {action_id(k) for k in EFFECTS})
            for ac,heater,fan,light,elapsed,source,command in itertools.product(
                    ('off','cool'),('off','on'),('off','on'),('off','on'),
                    (None,0,30,rest-1,rest,rest+1),('ai','human'),EFFECTS):
                with self.subTest(profile=profile,ac=ac,heater=heater,fan=fan,light=light,elapsed=elapsed,source=source,command=command):
                    before={'ac':ac,'heater':heater,'fan':fan,'light':light}
                    runtime=Runtime(definition,facts(before),time_s=300)
                    runtime.resets['rest']=None if elapsed is None else 300-elapsed
                    event={'source':source,'kind':'proposal','action':action_id(command)}
                    # Only starting AC or heater can violate the two requirements.
                    denied = source=='ai' and (
                        (command=='ac_cool' and (heater=='on' or (ac=='off' and elapsed is not None and elapsed<rest)))
                        or (command=='heater_on' and ac=='cool'))
                    decision=runtime.consider(event)
                    self.assertEqual(decision['outcome'],'block' if denied else 'allow')
                    after=dict(before)
                    if not denied:after.update(EFFECTS[command])
                    observed=runtime.observed(event,decision,facts(after),330,300)
                    self.assertEqual(observed.facts,facts(after))
                    old_reset=None if elapsed is None else 300-elapsed
                    self.assertEqual(observed.resets['rest'],300 if before['ac']=='cool' and after['ac']=='off' else old_reset)
                    count+=1
            counts[profile]=count
        self.assertEqual(counts,{'A':1728,'B':1728,'C':1728})
        if os.environ.get('SAFEFLOW_DEVICE_TEST_OUTPUT'):
            Path(os.environ['SAFEFLOW_DEVICE_TEST_OUTPUT']).write_text(json.dumps({
                'status':'passed','cases':counts,'total_cases':sum(counts.values()),
                'origin':'controlled_requirement_test_not_real_ai','expected_effects':EFFECTS},indent=2),encoding='utf-8')

    def test_bad_events_never_execute_any_device(self):
        for profile,path,_,_ in PROFILES:
            d=Definition.load(ROOT/path)
            for source,kind in itertools.product(('ai','human'),('invalid_output','timeout','adapter_error')):
                r=Runtime(d,d.initial_facts)
                e={'source':source,'kind':kind,'action':None};decision=r.consider(e)
                self.assertEqual(decision['outcome'],'block')
                observed=r.observed(e,decision,d.initial_facts,30,0)
                self.assertEqual(observed.facts,d.initial_facts)
                self.assertEqual(observed.time_s,30)
            for e in [dict(source='ai',kind='proposal',action='unknown_device'),
                      dict(source='unknown',kind='proposal',action='hold'),
                      dict(source='ai',kind='unknown',action=None)]:
                self.assertEqual(Runtime(d,d.initial_facts).consider(e)['outcome'],'halt')

    def test_formal_properties_detect_unrelated_device_effect(self):
        # Deliberately wire light_on to both light and fan. The property is an
        # independent requirement; changing action effects cannot rewrite it.
        for _,path,_,_ in PROFILES:
            data=Definition.load(ROOT/path).data
            data['actions']['light_on']['set']['fan']='on'
            d=Definition(data);r=Runtime(d,d.initial_facts)
            e={'source':'ai','kind':'proposal','action':'light_on'}
            decision=r.consider(e)
            wrong={**d.initial_facts,'light':'on','fan':'on'}
            with self.assertRaisesRegex(ValueError,'light_affects_only_itself'):
                r.observed(e,decision,wrong,30,0)


if __name__=='__main__':unittest.main()
