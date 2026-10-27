"""Post-shutdown checks of actual model runs. No fabricated provider results."""
import argparse
import hashlib
import json
from pathlib import Path
from tools.profile_acceptance import ROOT,EVIDENCE,PROFILES,ORACLE,write_json
from safeflow.monitoring import check_file
from safeflow.core.definition import Definition
from safeflow.adapters.smart_home import SmartHomeEnvironment

CASES=(('B-17','B',5),('C-17','C',5),('C-06','C',20))


def check_case(case,tag,interval,output):
    directory=EVIDENCE/'live'/case
    run=json.loads((directory/'report.json').read_text(encoding='utf-8'))
    spec=ORACLE.contract(PROFILES[tag][1]);traces=[];prompts=[];bindings=[]
    assert run['status']=='passed' and run['response_evidence']['actual_model_responses']>=4
    assert run['response_evidence']['completed_human_requests']>=1 and run['response_evidence']['ai_resumed_after_human']
    for path in sorted((directory/'traces').glob('*.jsonl')):
        check=check_file(path)
        assert check['status']=='conforms' and check['integrity']=='complete',(path,check['issue'])
        oracle=ORACLE.check(path,requirements=spec)
        rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        decisions=[r for r in rows if r['event']=='decision'];context=rows[0]['context'];cfg=context['config']
        prompts.append(cfg['proposer']['prompt']);bindings.append(cfg['bindings'])
        env=SmartHomeEnvironment(Definition(rows[0]['definition']),cfg['bindings'],physics=cfg['physics'],step_s=cfg['step_s'])
        initial=context['initial_observation']['measurements']
        env.reset({k:initial[k] for k in ('temperature_c','outdoor_c','target_c','light_required')})
        saved={};matched_prompts=matched_observations=0
        for row in rows:
            if row['event']=='goals':env.set_goals(row['values'])
            elif row['event']=='received' and row['source']=='ai':
                assert json.loads(row['raw']['prompt'][1]['content'])==env.sample()
                assert row['raw']['request']['model']==run['model_identity']['model']
                matched_prompts+=1
            elif row['event']=='decision':saved[row['event_id']]=row
            elif row['event']=='observation':
                decision=saved[row['event_id']]
                result=env.execute(decision['normalized']['action'] if decision['result']['outcome']=='allow' else None)
                assert result['measurements']==row['observation']['evidence']
                assert result['facts']==row['observation']['facts'];matched_observations+=1
        traces.append({'trace':path.name,'session_id':rows[0]['session_id'],'conformance':check['status'],'integrity':check['integrity'],
            'steps':check['steps'],'ai_responses':sum(r['normalized']['source']=='ai' for r in decisions),
            'human':sum(r['normalized']['source']=='human' for r in decisions),
            'blocked':sum(r['result']['outcome']=='block' for r in decisions),
            'invalid':sum(r['normalized']['kind']=='invalid_output' for r in decisions),'oracle':oracle,
            'matched_prompt_snapshots':matched_prompts,'matched_native_observations':matched_observations})
    assert any(t['session_id']==run['session_id'] for t in traces)
    report={'case':case,'profile':tag,'policy_sha256':run['definition_sha256'],'model':run['model_identity'],
        'post_baseline_evidence':run['response_evidence'],'status':'passed','traces':traces,
        'wall_interval_s':interval,'simulation_step_s':30,'prompt_config':prompts[0],'bindings':bindings[0],
        'comparison_scope':'Interface and governing correctness, not model quality or speed.'}
    write_json(output/(case+'.json'),report);return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    cases=[check_case(case,tag,interval,args.output) for case,tag,interval in CASES]
    assert cases[1]['policy_sha256']==cases[2]['policy_sha256']
    assert cases[1]['model']['digest']!=cases[2]['model']['digest']
    assert cases[1]['post_baseline_evidence']['request_options']==cases[2]['post_baseline_evidence']['request_options']
    assert cases[1]['prompt_config']==cases[2]['prompt_config'] and cases[1]['bindings']==cases[2]['bindings']
    before=json.loads((EVIDENCE/'baseline.json').read_text(encoding='utf-8'))['normalized_source_sha256']
    after={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest() for p in sorted((ROOT/'src/safeflow').rglob('*.py'))}
    assert before==after,'production source changed'
    report={'status':'passed','production_source_unchanged':True,'production_python_files':len(before),
            'C_policy_hash_equal_across_models':True,'C_actual_request_options_equal':True,'C_prompt_and_bindings_equal':True,
            'scheduler_note':'C-06 uses a 20-second wall pause for clean shutdown; all simulations advance 30 seconds/round. This is not a timing benchmark.',
            'cases':cases}
    write_json(args.output/'summary.json',report)
    print(json.dumps({'status':'passed','source_unchanged':True,'cases':[{'case':r['case'],'steps':sum(t['steps'] for t in r['traces']),
        'native_responses_after_baseline':r['post_baseline_evidence']['actual_model_responses'],'blocked':sum(t['blocked'] for t in r['traces'])} for r in cases]}))


if __name__=='__main__':main()
