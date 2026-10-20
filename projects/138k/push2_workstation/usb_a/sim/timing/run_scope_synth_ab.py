#!/usr/bin/env python3
"""Check real Gowin vector synthesis against RTL, including initialized ROMs."""
from datetime import datetime
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def run(command,cwd,log,timeout=600):
    with log.open('w') as stream:
        subprocess.run(command,cwd=cwd,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=timeout)

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('project',type=Path)
p.add_argument('--reference',type=Path,required=True)
p.add_argument('--simlib',type=Path,default=Path.home()/'.local/opt/gowin-1.9.12.03/IDE/simlib/gw5a/prim_sim.v')
a=p.parse_args();project=a.project.resolve();reference=a.reference.resolve()
out=ROOT/'results'/datetime.now().strftime('scope_synth_ab_%Y%m%d_%H%M%S_%f')
stage=out/'Prj1';stage.mkdir(parents=True)
rel='rtl/audio/scope_vec/scope_vec_engine.sv'
assets=[project/rel,*sorted((project/'rtl/audio/scope_vec/data').glob('*.mem')),
        project/'sim/matlab/output/stage13_note_voice/stage13_adsr_q24.mem']
for source in assets:
    dest=stage/source.relative_to(project);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
sdc=stage/'scope.sdc';sdc.write_text('create_clock -name audio -period 13.020833 [get_ports {clk_i}]\n')
tree=ET.parse(project/'Prj1.gprj');files=tree.find('FileList');files.clear()
ET.SubElement(files,'File',path=rel,type='file.verilog',enable='1')
ET.SubElement(files,'File',path='scope.sdc',type='file.sdc',enable='1')
tree.write(stage/'Prj1.gprj',encoding='utf-8',xml_declaration=True)
tcl=stage/'build.tcl';tcl.write_text('''open_project Prj1.gprj
set_option -top_module scope_vec_engine
set_option -output_base_name Scope
set_option -verilog_std sysv2017
run syn
''')
old=reference/rel;ref=out/'scope_vec_engine_reference.sv'
text=old.read_text();anchor='module scope_vec_engine'
if text.count(anchor)!=1:raise ValueError('bad reference module')
ref.write_text(text.replace(anchor,anchor+'_reference',1))
bench=HERE/'tb_scope_event_ab.sv'
inputs=assets+[old,bench,a.simlib,Path(__file__).resolve(),stage/'Prj1.gprj',sdc,tcl]
hashes={str(x):sha(x) for x in inputs}
(out/'inputs.json').write_text(json.dumps(hashes,indent=2)+'\n')
result=dict(passed=False,hardware_tested=False,scope='standalone Gowin vector netlist; not full-board timing')
print(out,flush=True)
try:
    run([str(Path.home()/'.local/bin/gw_sh'),'build.tcl'],stage,out/'synthesis.log')
    netlist=stage/'impl/gwsynthesis/Scope.vg'
    result['netlist_sha256']=sha(netlist)
    # Vendor DFF models use procedural assign/deassign. Icarus preserves their
    # four-state functional semantics; do not replace or blackbox those models.
    binary=out/'simv'
    run(['iverilog','-g2012','-DSCOPE_NETLIST','-s','tb_scope_event_ab','-o',str(binary),
         str(netlist),str(a.simlib),str(ref),str(bench)],stage,out/'compile.log')
    run(['vvp',str(binary)],stage,out/'run.log',timeout=1800)
    if 'PASS scope_event_ab' not in (out/'run.log').read_text():raise ValueError('missing synthesized PASS')
    if hashes!={str(x):sha(x) for x in inputs}:raise ValueError('input drift')
    result['passed']=True
    print((out/'run.log').read_text(),flush=True)
finally:
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
