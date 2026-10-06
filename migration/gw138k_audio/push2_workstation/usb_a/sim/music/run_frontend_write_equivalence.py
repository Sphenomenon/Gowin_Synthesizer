#!/usr/bin/env python3
"""Compare all frontend control/output cycles to accepted RTL across ring wraps."""
from pathlib import Path
import argparse
import json
import subprocess

ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',type=Path,default=ROOT/'results/clk50_fix_20261007/frontend_equivalence')
a=p.parse_args()
out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
prefix=subprocess.check_output(['git','rev-parse','--show-prefix'],cwd=ROOT,text=True).strip()
old=subprocess.check_output(['git','show','cnn83-accepted-20261006:'+prefix+'rtl/music/basic_pitch_cqt_frontend.sv'],cwd=ROOT,text=True)
ref=out/'frontend_reference.sv';ref.write_text(old.replace('module basic_pitch_cqt_frontend #','module basic_pitch_cqt_frontend_reference #',1))
image=out/'tb.vvp'
cmd=['iverilog','-g2012','-I'+str(ROOT/'rtl/music'),'-s','tb_frontend_write_equivalence','-o',str(image),
     str(ROOT/'sim/music/tb_frontend_write_equivalence.sv'),str(ref),str(ROOT/'rtl/music/basic_pitch_cqt_frontend.sv')]
build=subprocess.run(cmd,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(out/'compile.log').write_text(build.stdout)
build.check_returncode()
# Four coefficient-port models include long registered DDR stalls. Stream
# Icarus output unbuffered so timeouts preserve progress instead of losing it.
with (out/'run.log').open('w') as log:
    run=subprocess.run(['vvp','-i',str(image)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=600)
text=(out/'run.log').read_text()
print(text,end='');run.check_returncode()
assert 'PASS frontend write-decode equivalence both coefficient modes' in text
(out/'result.json').write_text(json.dumps({'passed':True,'reference':'cnn83-accepted-20261006','coefficient_modes':['local_combinational','DDR_combinational','local_synchronous_ROM','DDR_registered_payload'],'windows_per_mode':4,'writes_per_mode':512,'comparison':'every control and sample cycle; signed saturation, ring wraps, backpressure and next-window commits'},indent=2)+'\n')
