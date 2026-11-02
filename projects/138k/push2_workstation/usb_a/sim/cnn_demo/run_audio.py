#!/usr/bin/env python3
"""Check the selected candidate's actual minimal instrument and DAC path."""
from pathlib import Path
import argparse, subprocess, hashlib, json
p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();stage=a.project.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
u=Path(__file__).resolve().parents[2]
names=['rtl/workstation/workstation_cnn_demo_primitives.sv','rtl/workstation/workstation_cnn_demo_audio.sv','rtl/workstation/workstation_cnn_demo_adapter.sv','rtl/audio/gw138k_event_workstation.sv','rtl/audio/workstation_runtime_oscillator_engine.sv','rtl/audio/workstation_runtime_div147.sv','rtl/control/workstation_session.sv','rtl/control/workstation_parameters.sv','rtl/audio/scope_vec/scope_tf_control.sv','src/ae350/gw138k_three_event_arbiter.sv','src/usb_a/gw138k_usb_lifecycle_merge.sv','src/migration/gw138k_stream_cdc.sv','src/migration/gw138k_counter_cdc.sv','rtl/audio/workstation_frame_delivery.sv','src/audio/pt8211_tx.v','src/audio/pt8211_observer.v','rtl/audio/workstation_fpc_audio.sv']
sources=[stage/n for n in names]+[Path(__file__).with_name('tb_cnn_demo_audio.sv')]
(out/'inputs.json').write_text(json.dumps({str(s):hashlib.sha256(s.read_bytes()).hexdigest() for s in sources},indent=2)+'\n')
commands=[['verilator','--binary','--timing','--build-jobs','4','-Wno-fatal','--top-module','tb_cnn_demo_audio','--Mdir',str(out/'obj'),'-I'+str(stage),*map(str,sources)],[str(out/'obj/Vtb_cnn_demo_audio')]]
for i,cmd in enumerate(commands):
 r=subprocess.run(cmd,cwd=stage,capture_output=True,text=True,timeout=180)
 (out/f'{i}.log').write_text(r.stdout+r.stderr)
 if r.returncode:print((r.stdout+r.stderr)[-6000:]);raise SystemExit(r.returncode)
 if i==1:
  print(r.stdout)
  if 'PASS CNN demo audio:' not in r.stdout:raise SystemExit('missing PASS')
