#!/usr/bin/env python3
"""Independent UART bits/stop timing, cold control once, passthrough and rearm."""
from pathlib import Path
import subprocess,tempfile,json,argparse
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);a=p.parse_args();cases=[]
with tempfile.TemporaryDirectory(prefix='cnn_startup_control_') as temp:
 for bits in [16,434]:
  exe=Path(temp)/'sim'
  c=subprocess.run(['iverilog','-g2012','-s','tb_startup_panic',f'-Ptb_startup_panic.BIT_CLOCKS={bits}','-o',str(exe),str(root/'sim/model_flash/tb_startup_panic.sv'),str(root/'rtl/music/basic_pitch_startup_panic.sv'),str(root/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1/src/control/uart_tx.v')],capture_output=True,text=True)
  assert c.returncode==0,c.stdout+c.stderr
  v=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=20)
  assert v.returncode==0 and 'PASS startup Panic' in v.stdout,v.stdout+v.stderr
  cases.append(dict(clocks_per_bit=bits,passed=True,log=v.stdout.strip()))
report=dict(passed=True,cases=cases,audio_data_saved=False,notes='Six decoded bytes per case are two cold-start MIDI Panic control events, not PCM. Existing P10 ordered flush remains unmodified; this is not a physical effect acceptance.')
if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
