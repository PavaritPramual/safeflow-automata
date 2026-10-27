"""Bounded acceptance against real Ollama + the existing owned HA lab.

Requires an existing lab refresh token. Never bootstraps an account, fabricates
model responses, changes provider prompts, or bypasses verification.
"""
import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from safeflow.configuration import load_key


def request(url, data=None, token=None, form=False):
    body=None if data is None else (urlencode(data) if form else json.dumps(data)).encode()
    headers={'Content-Type':'application/x-www-form-urlencoded' if form else 'application/json'}
    if token: headers['Authorization']='Bearer '+token
    with urlopen(Request(url,data=body,headers=headers),timeout=150) as response: return json.load(response)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',required=True)
    p.add_argument('--rounds',type=int,default=8)
    p.add_argument('--credentials',default='logs/ha-credentials.json')
    p.add_argument('--backend',default='http://127.0.0.1:8765')
    p.add_argument('--home-assistant',default='http://127.0.0.1:8123')
    args=p.parse_args()
    output=Path(args.output)
    if output.exists(): raise RuntimeError('refusing_to_overwrite_live_evidence')
    if not 2<=args.rounds<=100: raise ValueError('rounds_must_be_2_to_100')
    key=load_key();backend=args.backend.rstrip('/');ha=args.home_assistant.rstrip('/')
    if request(backend+'/health')['readiness']!='ready': raise RuntimeError('verified_service_not_ready')
    stored=json.loads(Path(args.credentials).read_text(encoding='utf-8'))
    token=request(ha+'/auth/token',{'grant_type':'refresh_token','refresh_token':stored['refresh_token'],'client_id':ha+'/'},form=True)['access_token']
    baseline=request(backend+'/state',token=key)
    request(ha+'/api/services/number/set_value',{'entity_id':'number.safeflow_target_temperature','value':24},token)
    request(ha+'/api/services/switch/turn_on',{'entity_id':'switch.safeflow_light_required'},token)
    request(ha+'/api/services/switch/turn_on',{'entity_id':'switch.safeflow_heater'},token)
    target=baseline['steps']+args.rounds;deadline=time.monotonic()+300
    while time.monotonic()<deadline:
        current=request(backend+'/state',token=key)
        if current['halted']: raise RuntimeError('session_halted:'+str(current.get('issue')))
        if current['steps']>=target and current['last_result']['source']=='ai' and not current['pending_requests']: break
        time.sleep(0.5)
    else: raise TimeoutError('live_acceptance_deadline_exceeded')
    states={s['entity_id']:s for s in request(ha+'/api/states',token=token)}
    assert states['sensor.safeflow_readiness']['state']=='ready'
    assert current['target_c']==24 and current['light_required']
    report={'type':'real_ollama_autonomous_loop_with_real_home_assistant_request',
            'session_id':current['session_id'],'baseline_steps':baseline['steps'],'final_steps':current['steps'],
            'simulation_time_s':current['simulation_time_s'],'human_request':{'device':'heater','mode':'on'},
            'goals':{'target_c':24,'light_required':True},'final_result':current['last_result'],
            'provider':current['model'],'definition_sha256':current['definition_sha256'],
            'home_assistant_readiness':states['sensor.safeflow_readiness']['state'],'not_prepared_ai_commands':True}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'session_id':current['session_id'],'steps':current['steps'],'last_source':current['last_result']['source']}))


if __name__=='__main__': main()
