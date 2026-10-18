#!/usr/bin/env python3
"""Exercise native DDR16/FIFO request and response ordering under reservation."""
from pathlib import Path
import argparse,json,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);a=p.parse_args();cases=[]
with tempfile.TemporaryDirectory(prefix='cnn_ddr_credit_') as temp:
 for seed in [7,31,127]:
  exe=Path(temp)/'sim'
  files=['sim/model_flash/tb_ddr_read_credit.sv','rtl/music/basic_pitch_ddr_read_credit.sv','rtl/music/basic_pitch_ddr16_port.sv','rtl/music/music_async_fifo.sv']
  c=subprocess.run(['iverilog','-g2012','-s','tb_ddr_read_credit',f'-Ptb_ddr_read_credit.SEED={seed}','-o',str(exe)]+[str(ROOT/f) for f in files],capture_output=True,text=True)
  assert c.returncode==0,c.stdout+c.stderr
  v=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=30)
  assert v.returncode==0 and 'PASS DDR read credit' in v.stdout,v.stdout+v.stderr
  cases.append(dict(seed=seed,passed=True,log=v.stdout.strip()))
report=dict(passed=True,cases=cases,bsram_added=0,pcm_saved=False,hardware_tested=False)
if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
