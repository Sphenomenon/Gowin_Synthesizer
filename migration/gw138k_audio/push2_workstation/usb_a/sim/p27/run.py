#!/usr/bin/env python3
"""Focused P27 Push binding, services and audio-owner checks; no hardware access."""
from pathlib import Path
from datetime import datetime
import hashlib,json,shutil,subprocess,sys,xml.etree.ElementTree as ET

build=Path(sys.argv[1]).resolve();project=build/'Prj1';here=Path(__file__).resolve().parent
out=build/datetime.now().strftime('p27_controls_%H%M%S_%f');out.mkdir();print(out,flush=True)
(out/'sim').symlink_to(project/'sim',target_is_directory=True)
tests={name:out/name for name in ['tb_p27_push.sv','tb_p27_services.sv','tb_p27_audio.sv']}
for name,dest in tests.items():shutil.copy2(here/name,dest)
all_sources=[project/f.get('path') for f in ET.parse(project/'Prj1.gprj').find('FileList') if f.get('type')=='file.verilog']
audio_sources=[f for f in all_sources if not any(x in str(f.relative_to(project)) for x in
    ['vendor/','src/memory/','src/storage/','src/platform/','src/top/','src/ae350/riscv_','workstation_top.v','workstation_top.sv',
     'gw138k_cpu_pll_cell.v','gw138k_audio_clock.v'])]
commands=[
 ('push_compile',['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_p27_push',
    '--Mdir',str(out/'push_obj'),str(project/'src/push2/push2_controls.sv'),
    str(project/'src/push2/push2_lights.sv'),str(tests['tb_p27_push.sv'])]),
 ('push_sim',[str(out/'push_obj/Vtb_p27_push')]),
 ('services_compile',['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_p27_services',
    '--Mdir',str(out/'services_obj'),str(project/'src/ae350/gw138k_controlled_services.sv'),
    str(project/'legacy/rtl/input/score_led_player.sv'),str(tests['tb_p27_services.sv'])]),
 ('services_sim',[str(out/'services_obj/Vtb_p27_services')]),
 ('audio_compile',['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_p27_audio',
    '--Mdir',str(out/'audio_obj'),'-I'+str(project),'-I'+str(project/'src/usb_a'),
    *map(str,audio_sources),str(tests['tb_p27_audio.sv'])]),
 ('audio_sim',[str(out/'audio_obj/Vtb_p27_audio')])]
inputs=set([Path(__file__),*tests.values(),*audio_sources,project/'src/push2/push2_controls.sv',
    project/'src/push2/push2_lights.sv',project/'src/ae350/gw138k_controlled_services.sv',
    project/'legacy/rtl/input/score_led_player.sv'])
(out/'inputs.json').write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(inputs)},indent=2)+'\n')
passed=False
try:
    for name,cmd in commands:
        with (out/(name+'.log')).open('w') as log:r=subprocess.run(cmd,cwd=project,stdout=log,stderr=subprocess.STDOUT)
        print(name,r.returncode,flush=True)
        if r.returncode:print((out/(name+'.log')).read_text()[-8000:]);raise SystemExit(r.returncode)
        if name.endswith('_sim'):print((out/(name+'.log')).read_text().strip())
    passed=True
finally:
    (out/'verification.json').write_text(json.dumps(dict(passed=passed,hardware_tested=False,
        scope='CC85 score, CC86 record, CC62/63 mode, CC28 effect master, existing CC29 PANIC; score remains LED-only'),indent=2)+'\n')
