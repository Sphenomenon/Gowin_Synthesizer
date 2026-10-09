#!/usr/bin/env python3
"""Frozen CPU audio selftest event sequence and48k-sample CC123 deadline."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('build',type=Path)
a=p.parse_args();project=a.build.resolve()/'Prj1'
out=a.build.resolve()/datetime.now().strftime('cpu_release_%H%M%S_%f')
out.mkdir();(out/'sim').symlink_to(project/'sim',target_is_directory=True)
(out/'rtl').symlink_to(project/'rtl',target_is_directory=True)
all_sources=[project/f.get('path') for f in ET.parse(project/'Prj1.gprj').find('FileList') if f.get('type')=='file.verilog']
sources=[f for f in all_sources if not any(x in str(f.relative_to(project)) for x in
    ['vendor/','src/memory/','src/storage/','src/platform/','src/top/','src/ae350/riscv_','workstation_top.v','workstation_top.sv',
     'gw138k_cpu_pll_cell.v','gw138k_audio_clock.v'])]
tb=ROOT/'sim/p23/tb_cpu_release.sv';sources.append(tb)
(out/'inputs.json').write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},indent=2)+'\n')
report=dict(passed=False,hardware_tested=False,pcm_saved=False,build=str(a.build),
    scope='Frozen event-workstation synthesizer/control CC123 CPU preset73/all-effects, dry, sustained two notes; algorithm/48kframe check, not physical DDR timing proof')
commands=[('compile',['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_cpu_release','--Mdir',str(out/'obj'),'-I'+str(project),'-I'+str(project/'src/usb_a'),'-I'+str(project/'rtl/music'),*map(str,sources)]),
          ('simulation',[str(out/'obj/Vtb_cpu_release')])]
print(out,flush=True)
try:
 for label,cmd in commands:
  with (out/(label+'.log')).open('w') as log:
   r=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=300)
  print(label,r.returncode,flush=True)
  assert r.returncode==0,(out/(label+'.log')).read_text()[-6000:]
 report['log']=(out/'simulation.log').read_text();assert 'PASS CPU release' in report['log']
 report['passed']=True;print(report['log'],flush=True)
finally:
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
