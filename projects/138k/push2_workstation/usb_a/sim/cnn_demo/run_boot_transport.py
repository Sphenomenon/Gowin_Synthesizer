#!/usr/bin/env python3
"""Check automatic boot across actual BIST/CDC/DDR transport, and the D7 bug."""
from pathlib import Path
import argparse, hashlib, json, subprocess

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--project',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();stage=a.project.resolve();out=a.output.resolve()
out.mkdir(parents=True,exist_ok=False)
root=Path(__file__).resolve().parents[2]
for name in ('rtl','src'):(out/name).symlink_to(stage/name,target_is_directory=True)
names=['rtl/workstation/workstation_cnn_demo_model_loader.sv','rtl/music/music_async_fifo.sv',
       'rtl/music/basic_pitch_ddr_command_buffer.sv','rtl/music/basic_pitch_ddr16_port.sv',
       'rtl/memory/workstation_cnn_demo_memory.sv','rtl/memory/workstation_ddr_bist.v',
       'rtl/timing/basic_pitch_ddr_client_queues.sv','rtl/timing/basic_pitch_ddr_arbiter_pipeline.sv']
sources=[stage/n for n in names]+[Path(__file__).with_name('tb_cnn_demo_boot_transport.sv')]
prior=out/'D7_memory.sv'
prior.write_bytes(subprocess.check_output(['git','show','a12539fe:projects/138k/push2_workstation/usb_a/rtl/memory/workstation_cnn_demo_memory.sv'],cwd=root))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
metadata=dict(scope='real_BIST_CDC_DDR16_client_slots_arbiter_native_DDR_model',
    sources={str(s):sha(s) for s in sources},negative_D7_sha256=sha(prior),
    model_preloaded=False,model_ready_forced=False,physical_DDR_tested=False,tests={})
for label,negative in [('fixed',False),('D7_negative',True)]:
    selected=[prior if negative and s.name=='workstation_cnn_demo_memory.sv' else s for s in sources]
    commands=[['verilator','--binary','--timing','--build-jobs','4','-Wno-fatal',
        '--top-module','tb_cnn_demo_boot_transport','--Mdir',str(out/label),
        '-I'+str(stage),'-I'+str(stage/'rtl/music'),f'-GEXPECT_REJECT={int(negative)}',
        *map(str,selected)],[str(out/label/'Vtb_cnn_demo_boot_transport')]]
    for i,cmd in enumerate(commands):
        log=out/f'{label}-{i}.log'
        with log.open('w') as f:r=subprocess.run(cmd,cwd=out,stdout=f,stderr=subprocess.STDOUT,timeout=180)
        if r.returncode:print(log.read_text()[-5000:]);raise SystemExit(r.returncode)
    text=log.read_text();assert 'PASS' in text;text=text[:text.index('- ')] if '- ' in text else text
    metadata['tests'][label]=text.strip();print(text,flush=True)
(out/'result.json').write_text(json.dumps(metadata,indent=2)+'\n')
