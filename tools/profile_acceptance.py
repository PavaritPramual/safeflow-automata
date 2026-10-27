"""Controlled requirement tests through the real HTTP API; never LLM evidence.

The expected plant/action semantics and threshold come from a separate contract,
not from runtime guards. Production source is deliberately not modified here.
"""
import argparse
import importlib.util
import json
import secrets
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import yaml
from safeflow.application import Application
from safeflow.api import make_server
from safeflow.environment import Home, Physics
from safeflow.commands import Command
from safeflow.adapters.smart_home import SmartHomeEnvironment
from safeflow.monitoring import check_file

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'experiments/prepresentation-2026-10-27'
VARIANTS=ROOT/'examples/smart-home/variants'
PROFILES={
    'A':(ROOT/'examples/smart-home/lab.yaml',VARIANTS/'requirements-180.json'),
    'B':(VARIANTS/'cooldown-90/lab.yaml',VARIANTS/'cooldown-90/requirements.json'),
    'C':(VARIANTS/'renamed-90/lab.yaml',VARIANTS/'renamed-90/requirements.json'),
}


def load_script(name,filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/filename)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


ORACLE=load_script('home_requirements','check-home-trace.py')


def write_json(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


class Api:
    def __init__(self,app):
        self.app=app;self.key=secrets.token_urlsafe(32)
        self.server=make_server(app,self.key,port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.url='http://127.0.0.1:'+str(self.server.server_address[1])

    def __enter__(self):self.thread.start();return self
    def __exit__(self,*args):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)

    def call(self,path,data=None):
        req=Request(self.url+path,data=None if data is None else json.dumps(data).encode(),headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=15) as response:return response.status,json.load(response)
        except HTTPError as exc:return exc.code,json.load(exc)


class ControlledHome:
    def __init__(self,api,spec,physics):
        self.api,self.spec=api,spec;self.home=Home(Physics(**physics));self.seq=0
        status,start=api.call('/v1/sessions',{})
        assert status==201,('activation',status,start)
        self.id=start['session_id'];self.path='/v1/sessions/'+self.id

    def act(self,action=None,source='ai',kind='proposal',advance=0):
        """Literal C effects and expected answers are independent of policy."""
        before=self.home.snapshot();devices=before['devices'];elapsed=before['ac_off_elapsed_s']
        conflict=(action=='ac_cool' and devices['heater']=='on') or (action=='heater_on' and devices['air_conditioner']=='cool')
        resting=action=='ac_cool' and devices['air_conditioner']=='off' and elapsed is not None and elapsed<self.spec['rest_s']
        expected='block' if kind!='proposal' or (source=='ai' and (conflict or resting)) else 'allow'
        self.seq+=1;event_id='controlled-'+str(self.seq)
        native_action=None if action is None else self.spec['actions'][action]
        body={'event_id':event_id,'source':source,'kind':kind,'action':native_action,
              'raw':{'prepared_action':native_action,'not_real_ai':True},
              'metadata':{'command_origin':'prepared_test','not_real_ai':True}}
        status,result=self.api.call(self.path+'/events',body)
        assert status==200 and result['outcome']==expected,('decision',action,expected,status,result)
        if expected=='allow':
            for role,mode in ORACLE.EFFECTS[action].items():self.home.apply(Command('set_device',ORACLE.BINDINGS[role],mode))
        raw=self.home.advance(advance)
        facts={self.spec['facts'][role]:raw['devices'][device] for role,device in ORACLE.BINDINGS.items()}
        status,after=self.api.call(self.path+'/observations',{'event_id':event_id,'facts':facts,'time_s':raw['simulation_time_s'],
            'applied_at_s':before['simulation_time_s'],'evidence':raw})
        assert status==200,('observation',status,after)
        active=raw['ac_off_elapsed_s'] is not None
        assert after['clocks']['rest']=={'active':active,'elapsed_s':raw['ac_off_elapsed_s'] if active else raw['simulation_time_s']}
        return {'action':native_action,'canonical_action':action,'source':source,'kind':kind,
                'before_elapsed_s':elapsed,'expected':expected,'found':result['outcome'],'reason':result['reason']}

    def close(self):
        status,result=self.api.call(self.path+'/close',{})
        assert status==200 and result['sealed']


def run_profile(tag,output,*,verification=None,_test_gate=None):
    """_test_gate is used only by unit fixtures; CLI never exposes a bypass."""
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    config_path,contract_path=PROFILES[tag];spec=ORACLE.contract(contract_path)
    app=Application(config_path,logs=output/'traces',verification=verification)
    if _test_gate is not None:app.gate=_test_gate
    cases=[]
    with Api(app) as api:
        for elapsed in (0,89,90,91,120,179,180,181):
            home=ControlledHome(api,spec,app.config['physics'])
            home.act('ac_cool');home.act('ac_off',advance=elapsed)
            probe=home.act('ac_cool');home.close()
            cases.append({'case':'restart_boundary','elapsed_s':elapsed,**probe})
        home=ControlledHome(api,spec,app.config['physics'])
        first=home.act('ac_cool');home.act('ac_off',advance=60)
        repeat=home.act('ac_off');probe=home.act('ac_cool');home.close()
        cases.extend([{'case':'first_use',**first},{'case':'repeated_off',**repeat},{'case':'after_repeated_off',**probe}])
        home=ControlledHome(api,spec,app.config['physics'])
        home.act('ac_cool',source='human',advance=30)
        human=home.act('heater_on',source='human',advance=30)
        resumed=home.act('heater_on',advance=30);recovery=home.act('heater_off',advance=30);home.close()
        cases.extend([{'case':'human_exception',**human},{'case':'ai_resumes_from_actual',**resumed},{'case':'recover',**recovery}])
        home=ControlledHome(api,spec,app.config['physics'])
        for kind in ('invalid_output','timeout'):
            cases.append({'case':kind,**home.act(kind=kind,advance=30)})
        home.close()
    # Exercise production bindings against native C, not the independent plant.
    env=SmartHomeEnvironment(app.definition,app.config['bindings'],physics=app.config['physics'])
    on=env.execute(spec['actions']['ac_cool']);off=env.execute(spec['actions']['ac_off'])
    assert on['measurements']['devices']['air_conditioner']=='cool'
    assert on['facts'][spec['facts']['ac']]=='cool'
    assert off['measurements']['devices']['air_conditioner']=='off'
    assert all(on['measurements']['devices'][name]=='off' for name in ('heater','ventilation_fan','light'))
    reports=[]
    for trace in sorted((output/'traces').glob('*.jsonl')):
        result=check_file(trace);assert result['status']=='conforms' and result['integrity']=='complete',result
        reports.append({'trace':trace.name,'steps':result['steps'],'status':result['status']})
    report={'type':'controlled_requirements_test','profile':tag,'not_real_ai':True,'actual_llm_calls':0,
            'verification_origin':app.gate.require(app.definition).get('origin'),'definition_sha256':app.definition.sha256,
            'rest_s':spec['rest_s'],'requirements':spec,'status':'passed','cases':cases,
            'native_bindings':'passed','traces':reports}
    write_json(output/'report.json',report)
    return report


def check_wrong_bundle(tag,bundle,output,config_path=None):
    app=Application(config_path or PROFILES[tag][0],logs=output,verification=bundle)
    with Api(app) as api:status,body=api.call('/v1/sessions',{})
    assert status==503 and 'mismatch' in body.get('reason',''),(status,body)
    assert not list(Path(output).glob('*.jsonl'))
    return {'profile':tag,'bundle':str(bundle),'http_status':status,'reason':body['reason'],'traces_created':0}


def run_rejections(output,*,verification_root=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    cases=[]
    bundles={tag:Path(verification_root)/tag if verification_root else Application(PROFILES[tag][0]).gate.directory for tag in PROFILES}
    for tag in PROFILES:
        for other in PROFILES:
            if tag!=other:cases.append(check_wrong_bundle(tag,bundles[other],output/(tag+'-with-'+other)))
    # Change only the definition after its bundle was verified.
    path=output/'changed-policy.yaml'
    original=(PROFILES['B'][0].parent/'policy.yaml').read_text(encoding='utf-8')
    path.write_text(original.replace('rest_s: 90','rest_s: 91'),encoding='utf-8')
    cfg=yaml.safe_load(PROFILES['B'][0].read_text(encoding='utf-8'))
    cfg['policy']=str(path.resolve());cfg['physics_file']=str((ROOT/'configs/home.json').resolve())
    changed=output/'changed-lab.yaml';changed.write_text(yaml.safe_dump(cfg,sort_keys=False),encoding='utf-8')
    cases.append(check_wrong_bundle('B',bundles['B'],output/'changed',changed))
    report={'type':'activation_rejections','not_real_ai':True,'status':'passed','cases':cases}
    write_json(output/'report.json',report);return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--verification-root',type=Path,help='Optional A/B/C bundle directory; defaults to each current lab.yaml')
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    reports=[run_profile(tag,args.output/tag,verification=args.verification_root/tag if args.verification_root else None) for tag in PROFILES]
    reject=run_rejections(args.output/'rejections',verification_root=args.verification_root)
    table=[{'profile':r['profile'],'rest_s':r['rest_s'],'at_120':next(c['found'] for c in r['cases'] if c['case']=='restart_boundary' and c['elapsed_s']==120)} for r in reports]
    assert [r['at_120'] for r in table]==['block','allow','allow']
    write_json(args.output/'summary.json',{'status':'passed','not_real_ai':True,'table':table,'activation_rejections':len(reject['cases'])})
    print(json.dumps(table))


if __name__=='__main__':main()
