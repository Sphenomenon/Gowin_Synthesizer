#!/usr/bin/env python3
"""Compare vector event timing optimization against an immutable old project."""
from datetime import datetime
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('project',type=Path)
p.add_argument('--reference',type=Path,required=True)
a=p.parse_args()
project=a.project.resolve();reference=a.reference.resolve()
out=ROOT/'results'/datetime.now().strftime('scope_event_ab_%Y%m%d_%H%M%S_%f')
out.mkdir()
rel='rtl/audio/scope_vec/scope_vec_engine.sv'
old=reference/rel;new=project/rel
text=old.read_text();anchor='module scope_vec_engine'
if text.count(anchor)!=1:raise ValueError('bad reference module')
ref=out/'scope_vec_engine_reference.sv';ref.write_text(text.replace(anchor,anchor+'_reference',1))
bench=HERE/'tb_scope_event_ab.sv'
inputs=[new,old,bench,Path(__file__).resolve()]
inputs+=sorted((project/'rtl/audio/scope_vec/data').glob('*.mem'))
inputs.append(project/'sim/matlab/output/stage13_note_voice/stage13_adsr_q24.mem')
hashes={str(x):sha(x) for x in inputs}
(out/'inputs.json').write_text(json.dumps(hashes,indent=2)+'\n')
result=dict(passed=False,hardware_tested=False)
print(out,flush=True)
try:
    binary=out/'obj/Vtb_scope_event_ab'
    for name,cmd in [('compile',['verilator','--binary','--timing','-j','4','-Wno-fatal',
        '--top-module','tb_scope_event_ab','--Mdir',str(binary.parent),str(new),str(ref),str(bench)]),
        ('run',[str(binary)])]:
        with (out/(name+'.log')).open('w') as log:
            subprocess.run(cmd,cwd=project,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
    if 'PASS scope_event_ab' not in (out/'run.log').read_text():raise ValueError('missing PASS')
    if hashes!={str(x):sha(x) for x in inputs}:raise ValueError('input drift')
    result['passed']=True
    print((out/'run.log').read_text())
finally:
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
