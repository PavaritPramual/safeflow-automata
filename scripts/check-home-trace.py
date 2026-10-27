"""Independent home requirement oracle; deliberately imports no runtime engine.

The fixed action/effect table and 180-second default are the case-study test
specification, not runtime policy hardcoding. Pass a different --rest-s only when
the external experimental requirement itself changes.
"""
import argparse
import json
from pathlib import Path

BINDINGS={'ac':'air_conditioner','heater':'heater','fan':'ventilation_fan','light':'light'}
EFFECTS={'hold':{},'ac_off':{'ac':'off'},'ac_cool':{'ac':'cool'},'heater_off':{'heater':'off'},
         'heater_on':{'heater':'on'},'fan_off':{'fan':'off'},'fan_on':{'fan':'on'},
         'light_off':{'light':'off'},'light_on':{'light':'on'}}


def check(path,rest_s):
    rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    assert rows[0]['event']=='session_start' and rows[-1]['event']=='session_end','sealed v4 session required'
    received={r['event_id']:r for r in rows if r['event']=='received'}
    observed={r['event_id']:r for r in rows if r['event']=='observation'}
    result=[];raw_snapshots=0
    for row in rows:
        if row['event']!='decision':continue
        event_id=row['event_id'];e=row['normalized'];b=row['before'];a=e['action'];clock=b['clocks']['rest']
        assert e['source'] in ('ai','human')
        conflict=(a=='ac_cool' and b['facts']['heater']=='on') or (a=='heater_on' and b['facts']['ac']=='cool')
        resting=a=='ac_cool' and b['facts']['ac']=='off' and clock['active'] and clock['elapsed_s']<rest_s
        expected='block' if e['kind']!='proposal' or (e['source']=='ai' and (conflict or resting)) else 'allow'
        assert row['result']['outcome']==expected,(event_id,'decision')
        if e['kind']=='proposal' and e['source']=='ai':
            assert json.loads(received[event_id]['raw']['raw']['message']['content'])=={'action':a},(event_id,'native action')
        elif e['kind']=='proposal' and e['source']=='human':
            raw=received[event_id]['raw']
            assert {BINDINGS[k]:v for k,v in EFFECTS[a].items()}=={raw['device']:raw['mode']},(event_id,'human mapping')
        obs=observed[event_id]['observation'];after=observed[event_id]['after']
        assert obs['facts']=={**b['facts'],**(EFFECTS[a] if expected=='allow' else {})},(event_id,'effect')
        delta=obs['time_s']-b['time_s'];assert delta==30,(event_id,'time')
        reset=b['facts']['ac']=='cool' and obs['facts']['ac']=='off'
        assert after['clocks']['rest']=={'active':reset or clock['active'],'elapsed_s':delta if reset else clock['elapsed_s']+delta},(event_id,'clock')
        if obs.get('evidence') is not None:
            native=obs['evidence'];raw_snapshots+=1
            assert {k:native['devices'][v] for k,v in BINDINGS.items()}==obs['facts'],(event_id,'native facts')
            assert native['simulation_time_s']==obs['time_s']
            assert all(k in native for k in ('temperature_c','energy_wh','power_w'))
        result.append({'event_id':event_id,'source':e['source'],'expected':expected,'found':row['result']['outcome']})
    return {'trace':str(path),'session_id':rows[0]['session_id'],'checked':len(result),
            'native_snapshots_checked':raw_snapshots,'status':'passed','rows':result}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('traces',nargs='+',type=Path)
    parser.add_argument('--rest-s',type=int,default=180)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.rest_s<0:raise ValueError('negative_requirement')
    if args.output.exists():raise RuntimeError('refusing_to_overwrite_oracle_evidence')
    results=[check(p,args.rest_s) for p in args.traces]
    report={'type':'independent_home_requirement_oracle','rest_s':args.rest_s,
            'checked':sum(r['checked'] for r in results),'mismatches':0,'traces':results}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checked':report['checked'],'mismatches':0}))


if __name__=='__main__':main()
