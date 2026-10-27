"""Reproducible prepared-command demo. Never presented as real model output."""
import argparse
import hashlib
import json
from pathlib import Path
from safeflow.behavior import check_file, path_plantuml
from safeflow.commands import Command, validate_command
from safeflow.controller import Controller
from .diagrams import export_policy
from safeflow.environment import Home
from safeflow.policy import Policy, DEFAULT_POLICY
from safeflow.trace import Trace, replay


class PreparedAgent:
    def metadata(self):
        return {'model': 'prepared-demo-commands', 'command_origin': 'prepared_test', 'not_real_ai': True}

    def propose(self, state, seed=0):
        c = self.command
        return {'raw': {'message': {'tool_calls': [{'function': {'name': c.name, 'arguments': {} if c.name == 'hold' else {'device': c.device, 'mode': c.mode}}}]}},
                'prompt': None, 'latency_ms': 0, 'output_mode': 'tools'}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def render_viewer(runs, policy):
    payload = json.dumps(runs, ensure_ascii=False).replace('<', '\\u003c')
    return '''<!doctype html><html lang="th"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>SafeFlow AI — ผลสาธิต</title><style>
*{box-sizing:border-box}body{font:20px Arial,Tahoma,sans-serif;color:#152d43;background:#edf1f5;margin:0}
header{background:#123b58;color:white;padding:22px 5%}h1{font-size:30px;margin:0 0 8px}header p{margin:0;font-size:18px}
main{max-width:1240px;margin:auto;padding:24px}select,button{font:inherit;padding:10px;border:1px solid #123b58;background:white;color:#123b58;border-radius:4px}
nav{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.card{background:white;border:1px solid #222;padding:20px;min-height:230px}
h2{font-size:23px;margin:0 0 18px}p{line-height:1.6}.pill{padding:10px 14px;display:inline-block;background:#123b58;color:white;font-weight:bold}.block{background:#a64d00}.muted{font-size:17px;color:#4c5d6b}.evidence{background:white;padding:20px;margin-top:18px;border:1px solid #222}a{color:#005c95}#counter{padding:12px}
@media(max-width:800px){.grid{grid-template-columns:1fr}}
</style><header><h1>SafeFlow AI: จากออโตมาตาสู่ผลการทำงาน</h1><p>ผลรันที่บันทึกไว้ • ใช้คำสั่งทดสอบที่กำหนดไว้ในบทบาท AI • ไม่ใช่คำตอบจากโมเดลจริง</p></header>
<main><nav><select id="run" aria-label="เลือกเหตุการณ์"></select><button id="prev">← รอบก่อน</button><button id="next">รอบถัดไป →</button><span id="counter"></span></nav>
<div class="grid"><section class="card"><h2>1. สถานะก่อนคำสั่ง</h2><div id="before"></div></section><section class="card"><h2>2. ข้อเสนอและผลพิจารณา</h2><div id="decision"></div></section><section class="card"><h2>3. ผลจริงในบ้านจำลอง</h2><div id="after"></div></section></div>
<section class="evidence"><h2>A → บันทึก → X → ผลตรวจ</h2><div id="proof"></div><p class="muted">180 วินาทีเป็นค่าทดลอง เมื่อปฏิเสธ โหมดอุปกรณ์คงเดิม แต่เวลาจำลองเดินต่อรอบละ 30 วินาที ผลตรวจครอบคลุมเฉพาะเส้นทางที่บันทึกได้ ไม่ใช่ผลทวนสอบ UPPAAL</p>
<a href="A/transition-table.md">ตารางนิยาม A</a> · <a href="A/policy.json">ไฟล์นิยามที่โปรแกรมใช้</a></section></main>
<script>const runs=PAYLOAD;let index=0;const by=id=>document.getElementById(id);const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names={air_conditioner:'แอร์',heater:'ฮีเตอร์',ventilation_fan:'พัดลม',light:'ไฟ'};
const reasons={ac_heater_conflict:'คำสั่งขัดกับอุปกรณ์ที่เปิดอยู่',ac_cooldown:'แอร์ยังพักไม่ครบเวลาที่กำหนด'};
const modes={allow:'อนุญาต',block:'ปฏิเสธ',human_bypass:'อนุญาตตามข้อยกเว้นคน',execute_unshielded:'ดำเนินการโดยไม่ใช้ตัวกำกับ',reject_invalid:'คำสั่งผิดรูปแบบ'};
function state(s){return `<p>แอร์: <b>${s.ac?'เปิด':'ปิด'}</b><br>ฮีเตอร์: <b>${s.heater?'เปิด':'ปิด'}</b><br>เวลาจำลอง: <b>${s.time_s} วินาที</b><br>หลังปิดแอร์จริง: <b>${s.elapsed===null?'ยังไม่เคยปิด':s.elapsed+' วินาที'}</b></p>`}
function command(c){return !c?'ไม่มีคำสั่งดำเนินการ':c.name==='hold'?'คงโหมดอุปกรณ์':`${names[c.device]||escape(c.device)} → ${c.mode==='off'?'ปิด':'เปิด'}`}
runs.forEach((r,i)=>by('run').add(new Option(`${r.title} — ${r.enforcement?'มีตัวกำกับ':'ไม่มีตัวกำกับ'}`,i)));
function show(){const r=runs[by('run').value||0],p=r.report.episodes.flatMap(e=>e.path),s=p[index];by('counter').textContent=`รอบ ${index+1} / ${p.length}`;by('prev').disabled=index===0;by('next').disabled=index===p.length-1;
by('before').innerHTML=state(s.before);by('after').innerHTML=state(s.after)+`<p class="muted">คำสั่งที่ดำเนินการ: ${command(s.executed)}</p>`;
by('decision').innerHTML=`<p>ผู้ส่ง: <b>${s.source==='human'?'คน':'บทบาท AI (คำสั่งทดสอบ)'}</b><br>ข้อเสนอ: <b>${command(s.event)}</b></p><span class="pill ${s.decision==='block'?'block':''}">${modes[s.decision]}</span><p>${s.reasons.map(x=>reasons[x]||escape(x)).join('<br>')||'ไม่พบเหตุปฏิเสธตามสองกฎ'}</p>`;
by('proof').innerHTML=`<p>สถานะ A: <b>${escape(Object.values(s.states_before).join(' / '))}</b> → <b>${escape(Object.values(s.states_after).join(' / '))}</b><br>ผลตรวจ X เทียบ A: <b>${({conforms:'สอดคล้อง',nonconforming:'ไม่สอดคล้อง',inconclusive:'ข้อมูลไม่ครบ'})[r.report.status]}</b> (${r.report.steps} รอบ)</p><p class="muted">รหัสข้อเสนอ: ${escape(s.proposal_id)}<br>บรรทัดต้นทาง: ${escape(JSON.stringify(s.lines))}</p><a href="${escape(r.trace)}">บันทึกต้นทาง</a> · <a href="${escape(r.report_path)}">ผลตรวจและเส้นทาง X</a>`}
by('run').onchange=()=>{index=0;show()};by('prev').onclick=()=>{index--;show()};by('next').onclick=()=>{index++;show()};show();</script></html>'''.replace('PAYLOAD', payload)


def run_demo(output, scenarios, policy):
    scenarios = json.loads(Path(scenarios).read_text(encoding='utf-8-sig'))
    if scenarios.get('format_version') != 1 or not scenarios.get('scenarios'):
        raise ValueError('unsupported_scenario_format')
    ids = set()
    for case in scenarios['scenarios']:
        if not case['id'].isidentifier() or case['id'] in ids: raise ValueError('invalid_scenario_id')
        ids.add(case['id'])
        if not case['steps'] or len(case['steps']) != len(case['expected_shielded']): raise ValueError('missing_scenario_oracle')
        for step in case['steps']:
            if step['source'] not in ('ai', 'human'): raise ValueError('unknown_command_source')
            validate_command(Command(**step['command']))
    out = Path(output); out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'scenarios-F.json', scenarios)
    export_policy(policy, out / 'A')
    runs = []
    for case in scenarios['scenarios']:
        for enabled in (False, True):
            stem = case['id'] + ('-shielded' if enabled else '-unshielded')
            path = out / (stem + '.jsonl')
            agent = PreparedAgent()
            controller = Controller(Home(), agent, Trace(path), enforcement=enabled, policy=policy)
            controller.reset(case['initial'])
            decisions = []
            for step in case['steps']:
                agent.command = Command(**step['command'])
                if step['source'] == 'human':
                    controller.enqueue(agent.propose({}, 0)['raw']['message']['tool_calls'][0])
                decisions.append(controller.step()['last_result']['decision'])
            controller.finish()
            if enabled and decisions != case['expected_shielded']: raise AssertionError((stem, decisions))
            report = check_file(path)
            if report['integrity'] != 'complete': raise AssertionError(report)
            if report['status'] != ('conforms' if enabled else 'nonconforming'): raise AssertionError(report)
            records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
            if replay(records, Home()) != controller.home.snapshot(): raise AssertionError('replay_failed')
            write_json(out / (stem + '-X.json'), report)
            episode = next(e for e in report['episodes'] if e['path'])
            (out / (stem + '-X.puml')).write_text(path_plantuml(episode), encoding='utf-8')
            runs.append({'id': case['id'], 'title': case['title'], 'enforcement': enabled, 'trace': path.name,
                         'report_path': stem + '-X.json', 'report': report, 'replay_passed': True})
    (out / 'index.html').write_text(render_viewer(runs, policy), encoding='utf-8')
    summary = {'type': 'prepared_test_commands_not_model_outputs', 'policy_version': policy.version,
               'policy_sha256': policy.sha256, 'runs': [{k: v for k, v in r.items() if k != 'report'} | {'status': r['report']['status'], 'steps': r['report']['steps']} for r in runs]}
    write_json(out / 'summary.json', summary)
    manifest = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
    write_json(out / 'manifest.json', manifest)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, help='New directory only; evidence is never overwritten')
    parser.add_argument('--scenarios', default='tools/prepared_demo/scenarios.json')
    parser.add_argument('--policy', default=str(DEFAULT_POLICY))
    args = parser.parse_args()
    summary = run_demo(args.output, args.scenarios, Policy.load(args.policy))
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == '__main__': main()
