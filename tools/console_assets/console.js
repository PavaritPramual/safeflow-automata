'use strict';
let cursor=0, polling=false;
const $=id=>document.getElementById(id);
const titles={session:'SESSION',info:'INFO',round_start:'ROUND',ai_request:'AI REQUEST',ai_output:'AI OUTPUT (raw)',human_queued:'HUMAN QUEUED',human_delivered:'HUMAN DELIVERED',human_command:'HUMAN COMMAND',decision:'DECISION',observation:'OBSERVATION',round_end:'ROUND END',error:'ERROR',fault:'FAULT',session_halt:'HALTED',session_end:'CLOSED'};
function json(value){return typeof value==='string'?value:JSON.stringify(value,null,2);}
function addEvent(e){
  const box=document.createElement('div');box.className='entry '+e.kind;
  const title=document.createElement('h4');title.textContent=`${e.time} | round ${e.round} | ${titles[e.kind]||e.kind}`;box.append(title);
  const pre=document.createElement('pre');
  if(e.kind==='ai_output'){
    $('output-title').textContent='Latest AI output | round '+e.round;
    $('last-output').textContent=typeof e.content==='string'?e.content:'No model response';
    pre.textContent=typeof e.content==='string'?e.content:'No model response\n'+json(e.data);box.append(pre);
    const details=document.createElement('details'),summary=document.createElement('summary'),native=document.createElement('pre');
    summary.textContent='Native response';native.textContent=json(e.data);details.append(summary,native);box.append(details);
  }else if(e.kind==='ai_request'){
    const messages=e.data&&e.data.messages;
    const user=Array.isArray(messages)?messages.findLast(m=>m.role==='user'):null;
    let data=user?user.content:e.data;
    if(typeof data==='string'){try{data=JSON.parse(data);}catch{}}
    pre.textContent=json(data);box.append(pre);
    const details=document.createElement('details'),summary=document.createElement('summary'),request=document.createElement('pre');
    summary.textContent='Full request';request.textContent=json(e.data);details.append(summary,request);box.append(details);
  }else{
    let data=e.data;
    if(e.kind==='info'){
      const labels={'เริ่มวนรอบอัตโนมัติ':'Auto loop started','รับคำขอหยุดแล้ว รอบที่กำลังทำจะจบก่อน แล้วจึงหยุด':'Stopping after current round','หยุดวนรอบแล้ว กดเริ่มเพื่อทำต่อได้':'Paused'};
      data=labels[data]||data;
    }
    if(e.kind==='human_queued')data={request_id:e.data.request_id,action:e.data.action,status:'queued for next round'};
    pre.textContent=json(data);box.append(pre);
  }
  if(e.kind==='decision'){
    const n=e.data.normalized,r=e.data.result;
    $('last-decision').textContent=JSON.stringify({source:n.source,action:n.action,outcome:r.outcome,reason:r.reason});
  }
  $('console').append(box);
  while($('console').children.length>400)$('console').firstElementChild.remove();
}
async function post(path,data={}){
  const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const body=await response.json();if(!response.ok)throw Error(body.error||'Request failed');return body;
}
async function action(fn){try{await fn();$('notice').textContent='';await poll();}catch(e){$('notice').textContent='Request failed: '+e.message+' (not retried)';}}
$('start').onclick=()=>action(()=>post('/api/start'));
$('stop').onclick=()=>action(()=>post('/api/stop'));
$('human').onsubmit=async event=>{
  event.preventDefault();$('send').disabled=true;
  try{await post('/api/human',{action:$('action').value,request_id:crypto.randomUUID()});$('notice').textContent='Queued for next round.';await poll();}
  catch(e){$('notice').textContent='Request failed: '+e.message+' (not retried)';}
  finally{$('send').disabled=false;}
};
async function poll(){
  if(polling)return;polling=true;
  try{
    const response=await fetch('/api/events?after='+cursor);if(!response.ok)throw Error('Cannot read log');const d=await response.json();
    if(d.dropped)addEvent({kind:'info',time:'',round:d.round,data:'Showing recent events. Full trace is saved to JSONL.'});
    for(const e of d.events)addEvent(e);cursor=d.cursor;
    if(d.events.length&&$('follow').checked)$('console').scrollTop=$('console').scrollHeight;
    const s=d.state,model=(s.model||{}).model||'No model';
    const phase=d.error?'Error':!d.ready?'Not ready':d.busy?(d.running?'Running':'Finishing current round'):d.running?'Running':'Paused';
    $('status').textContent=`${phase} | ${model} | round ${d.round} | sim ${s.simulation_time_s??0}s | interval ${d.interval}s`;
    $('pending').textContent=`Pending: ${d.pending}`;
    $('start').disabled=!d.ready||d.running||!!d.error;$('stop').disabled=!d.running;
    $('action').disabled=!d.ready||!!d.error;
    if(d.error)$('notice').textContent='Stopped: '+d.error;
  }catch(e){$('status').textContent='Disconnected. Retrying status only.';}
  finally{polling=false;}
}
async function loadRules(){
  try{
    const response=await fetch('/api/rules');if(!response.ok)throw Error();const r=await response.json(),d=r.definition;
    for(const cmd of r.commands){const option=document.createElement('option');option.value=cmd.id;option.textContent=cmd.id;$('action').append(option);}
    const results=(r.verification&&r.verification.results)||[];
    const rest=d.parameters.rest_s;
    $('policy').textContent=`${d.id} | ${rest===undefined?JSON.stringify(d.parameters):'AC rest: '+rest+'s'} | UPPAAL: ${results.filter(x=>x.status==='passed').length}/${results.length} passed`;
    $('overview').hidden=!r.overview_matches;
    $('overview-caption').textContent=r.overview_matches?'':'Overview hidden: loaded definition differs.';
  }catch(e){$('notice').textContent='Cannot load rules. Reload the page.';$('send').disabled=true;}
}
loadRules();poll();setInterval(poll,500);
