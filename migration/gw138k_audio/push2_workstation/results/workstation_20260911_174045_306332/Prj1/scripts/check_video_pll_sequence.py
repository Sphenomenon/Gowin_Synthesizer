"""Verify the actual PLL initialization control sequence; no analog PLL model."""
from pathlib import Path
import argparse
import os
from gowin_paths import gowin_simlib
import shutil
import hashlib
import json
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'build/video_pll_init'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--simlib',type=Path,default=os.environ.get('GOWIN_PRIMITIVES'))
args=parser.parse_args()
for tool in ('iverilog','vvp'):
    if not shutil.which(tool):
        parser.error(f'{tool} is required; run inside WSL or install Icarus Verilog')
BUILD.mkdir(parents=True,exist_ok=True)
LIB=args.simlib or gowin_simlib()/'prim_sim.v'
lib=LIB.read_text(encoding='utf-8')
declarations=re.search(r'^module PLL \(.*?(?=^wire resetn;)',lib,re.M|re.S)
if not declarations:
    raise SystemExit('PLL declaration boundary not found')
stub=BUILD/'pll_control_stubs.v'
stub.write_text('// Declaration-only inert PLL/CLKDIV. TB injects raw LOCK.\n'+declarations[0]+
    '\nassign LOCK=0;\nassign CLKOUT0=0;\nendmodule\n'
    'module CLKDIV(input HCLKIN,RESETN,CALIB,output CLKOUT);\n'
    'parameter DIV_MODE="5";\nassign CLKOUT=0;\nendmodule\n')
helper=ROOT/'vendor/sipeed_dvi/video_pll_init.v'
wrapper=ROOT/'vendor/sipeed_dvi/video_pll_1080p_gw5a.v'
tb=ROOT/'sim/primitives/tb_video_pll_init.sv'
log=[]
def run(source,tag,expected_pass):
    binary=BUILD/(tag+'.vvp')
    command=['iverilog','-g2012','-s','tb_video_pll_init','-o',str(binary),str(stub),str(helper),str(source),str(tb)]
    compile_result=subprocess.run(command,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
    if compile_result.returncode:
        raise SystemExit(compile_result.stdout)
    result=subprocess.run(['vvp',str(binary)],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
    log.append(tag+':\n'+compile_result.stdout+result.stdout)
    if expected_pass:
        if result.returncode or 'PASS tb_video_pll_init:' not in result.stdout:
            raise SystemExit(result.stdout)
    elif result.returncode==0 or 'FATAL:' not in result.stdout:
        raise SystemExit('Negative mutation was not rejected: '+tag)
    return result.stdout.strip()

print(run(wrapper,'control_sequence',True))
text=wrapper.read_text()
bad=BUILD/'raw_lock_bypass.v'
if text.count('.O_LOCK(lock)')!=1:
    raise SystemExit('Unexpected O_LOCK topology')
bad.write_text(text.replace('.O_LOCK(lock)','.O_LOCK()',1).replace('wire pll_raw_lock, pll_reset;','wire pll_raw_lock, pll_reset;\nassign lock=pll_raw_lock;',1))
print(run(bad,'reject_raw_lock_bypass',False))
(BUILD/'run.log').write_text('\n'.join(log))
evidence={'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (helper,wrapper,tb)},
          'official_primitive_declarations_sha256':hashlib.sha256(LIB.read_bytes()).hexdigest(),
          'test_only_clk_period_override':250000,'test_only_lock_stable_cycles':4,
          'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'startup_and_recovery_cases':4,'raw_lock_bypass_rejected':True,
          'limits':'PLL and CLKDIV are inert declaration-compatible stubs; raw LOCK is injected. Verifies actual helper/wrapper sequencing and analog control wiring, not physical clocks, jitter or analog stability.'}
(BUILD/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
print('Evidence: '+str(BUILD/'evidence.json'))
