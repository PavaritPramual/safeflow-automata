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


def contract(path=None, rest_s=None):
    """External expected aliases/threshold, independent from tested policy guards."""
    spec={'format_version':1,'rest_s':180,'facts':{},'actions':{}}
    if path is not None:
        def unique(pairs):
            result={}
            for k,v in pairs:
                if k in result:raise ValueError('duplicate_requirement_key')
                result[k]=v
            return result
        value=json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=unique)
        if set(value)!=set(spec) or value['format_version']!=1:raise ValueError('invalid_requirement_contract')
        spec=value
    if rest_s is not None:
        if path is not None:raise ValueError('choose_contract_or_rest_s')
        spec['rest_s']=rest_s
    if type(spec['rest_s']) is not int or spec['rest_s']<0:raise ValueError('invalid_requirement_rest')
    for field,known in (('facts',BINDINGS),('actions',EFFECTS)):
        aliases=spec[field]
        if type(aliases) is not dict or set(aliases)-set(known):raise ValueError('unknown_requirement_alias')
        merged={k:aliases.get(k,k) for k in known}
        if any(type(v) is not str or not v for v in merged.values()) or len(set(merged.values()))!=len(merged):
            raise ValueError('ambiguous_requirement_alias')
        spec[field]=merged
    return spec


def check(path,rest_s=180,requirements=None):
    spec=requirements or contract(rest_s=rest_s)
    fact_aliases=spec['facts'];action_roles={v:k for k,v in spec['actions'].items()}
    def facts(values):
        assert set(values)==set(fact_aliases.values()),'unexpected formal fact schema'
        return {k:values[v] for k,v in fact_aliases.items()}
    rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    assert rows[0]['event']=='session_start' and rows[-1]['event']=='session_end','sealed v4 session required'
    received={r['event_id']:r for r in rows if r['event']=='received'}
    observed={r['event_id']:r for r in rows if r['event']=='observation'}
    result=[];raw_snapshots=0
    for row in rows:
        if row['event']!='decision':continue
        event_id=row['event_id'];e=row['normalized'];b=row['before'];native_action=e['action']
        assert native_action is None or native_action in action_roles,(event_id,'unknown_action_alias_in_contract',native_action)
        a=None if native_action is None else action_roles[native_action];clock=b['clocks']['rest'];before=facts(b['facts'])
        assert e['source'] in ('ai','human')
        conflict=(a=='ac_cool' and before['heater']=='on') or (a=='heater_on' and before['ac']=='cool')
        resting=a=='ac_cool' and before['ac']=='off' and clock['active'] and clock['elapsed_s']<spec['rest_s']
        expected='block' if e['kind']!='proposal' or (e['source']=='ai' and (conflict or resting)) else 'allow'
        assert row['result']['outcome']==expected,(event_id,'decision')
        if e['kind']=='proposal' and e['source']=='ai':
            assert json.loads(received[event_id]['raw']['raw']['message']['content'])=={'action':native_action},(event_id,'native action')
        elif e['kind']=='proposal' and e['source']=='human':
            raw=received[event_id]['raw']
            assert {BINDINGS[k]:v for k,v in EFFECTS[a].items()}=={raw['device']:raw['mode']},(event_id,'human mapping')
        obs=observed[event_id]['observation'];after=observed[event_id]['after']
        actual=facts(obs['facts'])
        assert actual=={**before,**(EFFECTS[a] if expected=='allow' else {})},(event_id,'effect')
        delta=obs['time_s']-b['time_s'];assert delta==30,(event_id,'time')
        reset=before['ac']=='cool' and actual['ac']=='off'
        assert after['clocks']['rest']=={'active':reset or clock['active'],'elapsed_s':delta if reset else clock['elapsed_s']+delta},(event_id,'clock')
        if obs.get('evidence') is not None:
            native=obs['evidence'];raw_snapshots+=1
            assert {k:native['devices'][v] for k,v in BINDINGS.items()}==actual,(event_id,'native facts')
            assert native['simulation_time_s']==obs['time_s']
            assert all(k in native for k in ('temperature_c','energy_wh','power_w'))
        result.append({'event_id':event_id,'source':e['source'],'action':native_action,'canonical_action':a,'expected':expected,'found':row['result']['outcome']})
    return {'trace':str(path),'session_id':rows[0]['session_id'],'checked':len(result),
            'native_snapshots_checked':raw_snapshots,'status':'passed','rows':result}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('traces',nargs='+',type=Path)
    parser.add_argument('--rest-s',type=int)
    parser.add_argument('--contract',type=Path,help='Independent expected threshold and aliases; never a runtime policy')
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    spec=contract(args.contract,args.rest_s)
    if args.output.exists():raise RuntimeError('refusing_to_overwrite_oracle_evidence')
    results=[check(p,requirements=spec) for p in args.traces]
    report={'type':'independent_home_requirement_oracle','rest_s':spec['rest_s'],'requirements':spec,
            'checked':sum(r['checked'] for r in results),'mismatches':0,'traces':results}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checked':report['checked'],'mismatches':0}))


if __name__=='__main__':main()
