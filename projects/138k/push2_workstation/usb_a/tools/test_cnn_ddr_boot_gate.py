#!/usr/bin/env python3
"""Check initial PLL settling, short LOCK pulse, asynchronous reset and rearm."""
from pathlib import Path
import subprocess,tempfile,json,argparse
r=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);a=p.parse_args();cases=[]
with tempfile.TemporaryDirectory(prefix='cnn_ddr_boot_gate_') as t:
 for hold in [1,8,31,0,50_000_001]:
  exe=Path(t)/'sim';cmd=['iverilog','-g2012','-s','tb_ddr_boot_gate',f'-Ptb_ddr_boot_gate.HOLD={hold}','-o',str(exe),str(r/'sim/model_flash/tb_ddr_boot_gate.sv'),str(r/'rtl/music/basic_pitch_ddr_boot_gate.sv')]
  c=subprocess.run(cmd,capture_output=True,text=True);assert c.returncode==0,c.stdout+c.stderr
  v=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=10);invalid=hold in [0,50_000_001]
  assert (v.returncode!=0 and 'hold cycles must be' in v.stdout) if invalid else (v.returncode==0 and 'PASS DDR boot gate' in v.stdout),v.stdout+v.stderr
  cases.append({'hold_cycles':hold,'invalid_config_rejected':invalid,'passed':True,'log':v.stdout.strip()})
report={'passed':True,'cases':cases,'hardware_root_cause_proven':False,'notes':'Gate only staggers initial DDR reset; does not replace PHY/calibration or normal recovery.'}
if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
