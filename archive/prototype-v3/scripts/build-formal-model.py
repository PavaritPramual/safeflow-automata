"""Generate the reviewed UPPAAL policy model; no verifier result is fabricated."""
from pathlib import Path
import xml.etree.ElementTree as ET

root = ET.Element('nta')
ET.SubElement(root,'declaration').text = '''// smart-home-v1. Commands: hold, AC off/on, heater off/on, fan off/on, light off/on.
clock rest;
bool ac=false, heater=false, fan=false, light=false, has_off=false;
int[0,8] command=0;
int[0,1] source=0; // 0 AI, 1 human
bool allowed=false;
bool bad_conflict=false, bad_cooldown=false, bad_block=false;
bool before_ac=false, before_heater=false;
bool human_conflict_seen=false, ai_open_seen=false, expired_open_seen=false, block_seen=false;
bool conflict() { return (command==2 && heater) || (command==4 && ac); }
bool resting() { return command==2 && !ac && has_off && rest<180; }
bool permit() { return source==1 || (!conflict() && !resting()); }
void execute() {
  if (allowed) {
    if (source==0 && conflict()) bad_conflict=true;
    if (source==0 && resting()) bad_cooldown=true;
    if (command==1) { if(ac) { rest=0; has_off=true; } ac=false; }
    if (command==2) { if(source==0 && !ac && has_off && rest>=180) expired_open_seen=true; ac=true; if(source==0) ai_open_seen=true; }
    if (command==3) heater=false;
    if (command==4) heater=true;
    if (command==5) fan=false;
    if (command==6) fan=true;
    if (command==7) light=false;
    if (command==8) light=true;
    if (source==1 && ac && heater) human_conflict_seen=true;
  } else {
    block_seen=true;
    if(ac!=before_ac || heater!=before_heater) bad_block=true;
  }
}'''

def template(name, locations, transitions):
    t=ET.SubElement(root,'template'); ET.SubElement(t,'name').text=name
    for ident, committed in locations:
        loc=ET.SubElement(t,'location',id=name+ident,x='0',y='0')
        ET.SubElement(loc,'name').text=ident
        if committed: ET.SubElement(loc,'committed')
    ET.SubElement(t,'init',ref=name+locations[0][0])
    for start,end,labels in transitions:
        tr=ET.SubElement(t,'transition'); ET.SubElement(tr,'source',ref=name+start); ET.SubElement(tr,'target',ref=name+end)
        for kind,value in labels: ET.SubElement(tr,'label',kind=kind).text=value

# Shared rendezvous channels make checking and applying instantaneous and ordered.
root.find('declaration').text += '\nchan proposal, decision, done;'
template('Proposer',[('Ready',False),('Waiting',True)], [
 ('Ready','Waiting',[('select','c:int[0,8], s:int[0,1]'),('synchronisation','proposal!'),('assignment','command=c, source=s, before_ac=ac, before_heater=heater')]),
 ('Waiting','Ready',[('synchronisation','done?')])])
template('Guard',[('Idle',False),('Check',True),('Apply',True)],[
 ('Idle','Check',[('synchronisation','proposal?')]),
 ('Check','Apply',[('assignment','allowed=permit()')]),
 ('Apply','Idle',[('synchronisation','decision!')])])
template('Plant',[('Idle',False),('Execute',True),('Finish',True)],[
 ('Idle','Execute',[('synchronisation','decision?')]),
 ('Execute','Finish',[('assignment','execute()')]),
 ('Finish','Idle',[('synchronisation','done!')])])
ET.SubElement(root,'system').text='P=Proposer(); G=Guard(); E=Plant(); system P,G,E;'
queries=ET.SubElement(root,'queries')
for formula,comment in [
 ('A[] not deadlock','No structural deadlock; does not prove scheduling fairness.'),
 ('A[] !bad_conflict','No permitted AI request opens a conflicting device.'),
 ('A[] !bad_cooldown','No permitted AI off-to-on request violates rest.'),
 ('A[] !bad_block','Blocked proposal preserves device state.'),
 ('E<> human_conflict_seen','Human override can reach both-on.'),
 ('E<> ai_open_seen','Policy does not block all AI openings.'),
 ('E<> block_seen','Blocking is reachable.'),
 ('E<> expired_open_seen','Clock expiry and AI opening are reachable.')]:
    q=ET.SubElement(queries,'query'); ET.SubElement(q,'formula').text=formula; ET.SubElement(q,'comment').text=comment
out=Path('formal/smart-home.xml'); out.parent.mkdir(exist_ok=True)
ET.indent(root)
out.write_bytes(b'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE nta PUBLIC "-//Uppaal Team//DTD Flat System 1.1//EN" "http://www.it.uu.se/research/group/darts/uppaal/flat-1_2.dtd">\n'+ET.tostring(root,encoding='utf-8'))
print(out)
