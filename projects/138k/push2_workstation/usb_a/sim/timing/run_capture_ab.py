#!/usr/bin/env python3
"""Source-bound capture pipeline miter, including every RAM word and both triggers."""
from pathlib import Path
from datetime import datetime
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('build',type=Path);a=p.parse_args()
project=a.build.resolve()/'Prj1';out=ROOT/'results'/datetime.now().strftime('capture_input_ab_%Y%m%d_%H%M%S_%f');out.mkdir()
old=ROOT/'results/song_guide_full83_20261006_203125_607466/Prj1/src/video/feedback_capture.v'
new=project/'src/video/feedback_capture.v';tb=Path(__file__).with_name('tb_capture_input_ab.sv')
ref=out/'reference.v';ref.write_text(old.read_text().replace('module feedback_capture #','module feedback_capture_reference #'))
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
inputs={str(x):sha(x) for x in [old,new,tb,Path(__file__).resolve(),ref]}
(out/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n');print(out,flush=True)
for label,command in [('compile',['iverilog','-g2012','-s','tb_capture_input_ab','-o',str(out/'sim'),str(new),str(ref),str(tb)]),('run',['vvp',str(out/'sim')])]:
 with (out/(label+'.log')).open('w') as stream:r=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=120)
 if r.returncode:raise RuntimeError((out/(label+'.log')).read_text())
log=(out/'run.log').read_text();assert 'PASS capture_input_ab:' in log
assert all(sha(Path(n))==h for n,h in inputs.items())
(out/'verification.json').write_text(json.dumps(dict(passed=True,source_bound=True,project=str(project),hardware_tested=False,log=log.strip()),indent=2)+'\n');print(log)
