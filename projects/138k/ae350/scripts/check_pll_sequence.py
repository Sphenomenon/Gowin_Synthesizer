#!/usr/bin/env python3
"""Check the retimed vendor PLL helper; no analog PLL simulation is claimed."""
import datetime,hashlib,json,re,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
workspace=root.parents[2]
out=root.parent/'results'/datetime.datetime.now().strftime('ae350_pll_sim_%Y%m%d_%H%M%S_%f')
out.mkdir()
lib=Path('/home/sphenicidition/.local/opt/gowin-1.9.12.03/IDE/simlib/gw5a/prim_sim.v')
decl=re.search(r'^module PLL \(.*?(?=^wire resetn;)',lib.read_text(),re.M|re.S)
assert decl
stub=out/'pll_stub.v'
stub.write_text(decl[0]+'\nassign LOCK=0;assign CLKOUT0=0;assign CLKOUT1=0;endmodule\n')
sources=[stub,workspace/'Mega_138K/Dev/Prj1/vendor/sipeed_dvi/video_pll_init.v',root/'rtl/gw138k_cpu_pll_cell.v',root/'sim/tb_cpu_pll_init.sv']
command=['iverilog','-g2012','-s','tb_cpu_pll_init','-o',str(out/'test.vvp'),*map(str,sources)]
p=subprocess.run(command,capture_output=True,text=True)
log=p.stdout+p.stderr
if not p.returncode:
    p=subprocess.run(['vvp',str(out/'test.vvp')],capture_output=True,text=True,timeout=30)
    log+=p.stdout+p.stderr
(out/'run.log').write_text(log)
passed=p.returncode==0 and 'PASS tb_cpu_pll_init:' in log
(out/'verification.json').write_text(json.dumps({'passed':passed,'source_sha256':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},'primitive_library_sha256':hashlib.sha256(lib.read_bytes()).hexdigest(),'limits':'Digital control sequencing only; inert PLL and injected LOCK, accelerated helper wait counter.'},indent=2)+'\n')
print(log);print(out)
raise SystemExit(0 if passed else 1)
