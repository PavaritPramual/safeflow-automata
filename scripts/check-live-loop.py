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


def trace_prefix(path):
    if not path.exists():return []
    return [json.loads(line.decode('utf-8')) for line in path.read_bytes().split(b'\n')[:-1] if line]


def response_counts(rows,model,after_seq=0):
    observed={r['event_id'] for r in rows if r['event']=='observation'}
    received=[r for r in rows if r['event']=='received' and r['event_seq']>after_seq and r['event_id'] in observed]
    actual=[]
    for row in received:
        payload=row.get('raw') or {}
        native=payload.get('raw') if isinstance(payload,dict) else None
        message=native.get('message') if isinstance(native,dict) else None
        if row['source']=='ai' and isinstance(native,dict) and native.get('model')==model and isinstance(message,dict) and isinstance(message.get('content'),str):
            actual.append(row)
    human=[r for r in received if r['source']=='human']
    resumed=bool(human and any(r['event_seq']>max(h['event_seq'] for h in human) for r in actual))
    options=[]
    for row in actual:
        value=row['raw'].get('request',{}).get('options')
        if value not in options:options.append(value)
    return {'actual_model_responses':len(actual),'completed_human_requests':len(human),'ai_resumed_after_human':resumed,'request_options':options}


def model_identity(model):
    if model.get('provider')!='ollama':raise ValueError('this_acceptance_tool_requires_ollama')
    tags=request(model['url'].rstrip('/')+'/api/tags')['models']
    item=next(x for x in tags if x['name']==model['model'])
    return {'model':item['name'],'digest':item['digest'],'size_bytes':item.get('size')}


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
    p.add_argument('--trace-dir',type=Path,help='Local server trace directory; enables actual-response acceptance checks')
    p.add_argument('--min-ai-responses',type=int,default=4)
    p.add_argument('--human-device',choices=('air_conditioner','heater','ventilation_fan','light'),default='heater')
    args=p.parse_args()
    output=Path(args.output)
    if output.exists(): raise RuntimeError('refusing_to_overwrite_live_evidence')
    if not 2<=args.rounds<=100: raise ValueError('rounds_must_be_2_to_100')
    if not 1<=args.min_ai_responses<=100:raise ValueError('invalid_minimum_responses')
    key=load_key();backend=args.backend.rstrip('/');ha=args.home_assistant.rstrip('/')
    if request(backend+'/health')['readiness']!='ready': raise RuntimeError('verified_service_not_ready')
    stored=json.loads(Path(args.credentials).read_text(encoding='utf-8'))
    token=request(ha+'/auth/token',{'grant_type':'refresh_token','refresh_token':stored['refresh_token'],'client_id':ha+'/'},form=True)['access_token']
    baseline=request(backend+'/state',token=key)
    identity=model_identity(baseline['model']) if args.trace_dir else None
    trace=args.trace_dir/('session-'+baseline['session_id']+'.jsonl') if args.trace_dir else None
    prefix=trace_prefix(trace) if trace else []
    after_seq=max((r['event_seq'] for r in prefix),default=0)
    request(ha+'/api/services/number/set_value',{'entity_id':'number.safeflow_target_temperature','value':24},token)
    request(ha+'/api/services/switch/turn_on',{'entity_id':'switch.safeflow_light_required'},token)
    request(ha+'/api/services/switch/turn_on',{'entity_id':'switch.safeflow_'+args.human_device},token)
    target=baseline['steps']+args.rounds;deadline=time.monotonic()+300
    counts=None
    while time.monotonic()<deadline:
        current=request(backend+'/state',token=key)
        if current['session_id']!=baseline['session_id']:raise RuntimeError('session_changed_during_acceptance')
        if current['halted']: raise RuntimeError('session_halted:'+str(current.get('issue')))
        counts=response_counts(trace_prefix(trace),current['model']['model'],after_seq) if trace else None
        enough=counts is None or (counts['actual_model_responses']>=args.min_ai_responses and counts['completed_human_requests']>=1 and counts['ai_resumed_after_human'])
        if current['steps']>=target and current['last_result']['source']=='ai' and not current['pending_requests'] and enough: break
        time.sleep(0.5)
    else:
        failed={'status':'failed','reason':'insufficient_actual_model_responses_or_human_resumption','response_evidence':counts}
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(failed,indent=2)+'\n',encoding='utf-8')
        raise TimeoutError('live_acceptance_deadline_exceeded')
    states={s['entity_id']:s for s in request(ha+'/api/states',token=token)}
    assert states['sensor.safeflow_readiness']['state']=='ready'
    assert current['target_c']==24 and current['light_required']
    if identity is not None and model_identity(current['model'])!=identity:raise RuntimeError('model_tag_changed_during_acceptance')
    report={'type':'real_ollama_autonomous_loop_with_real_home_assistant_request',
            'session_id':current['session_id'],'baseline_steps':baseline['steps'],'final_steps':current['steps'],
            'status':'passed','simulation_time_s':current['simulation_time_s'],
            'human_request':{'device':args.human_device,'mode':'cool' if args.human_device=='air_conditioner' else 'on'},
            'goals':{'target_c':24,'light_required':True},'final_result':current['last_result'],
            'provider':current['model'],'definition_sha256':current['definition_sha256'],
            'home_assistant_readiness':states['sensor.safeflow_readiness']['state'],'not_prepared_ai_commands':True,
            'model_identity':identity,'response_evidence':counts,'baseline_event_seq':after_seq,
            'response_check':'actual_native_responses' if trace else 'not_requested'}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'session_id':current['session_id'],'steps':current['steps'],'last_source':current['last_result']['source']}))


if __name__=='__main__': main()
