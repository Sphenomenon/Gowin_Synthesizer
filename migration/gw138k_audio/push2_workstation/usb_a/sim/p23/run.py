#!/usr/bin/env python3
"""P23 focused PANIC audio/Push/UI checks; no hardware access."""
from pathlib import Path
from datetime import datetime
import hashlib,json,shutil,subprocess,sys,xml.etree.ElementTree as ET
build=Path(sys.argv[1]).resolve();project=build/'Prj1';here=Path(__file__).resolve().parent
out=build/datetime.now().strftime('p23_panic_%H%M%S_%f');out.mkdir();print(out,flush=True)
(out/'sim').symlink_to(project/'sim',target_is_directory=True)
all_sources=[project/f.get('path') for f in ET.parse(project/'Prj1.gprj').find('FileList') if f.get('type')=='file.verilog']
audio_sources=[f for f in all_sources if not any(x in str(f.relative_to(project)) for x in
    ['vendor/','src/memory/','src/platform/','src/top/','src/ae350/riscv_','workstation_top.v','workstation_top.sv',
     'gw138k_cpu_pll_cell.v','gw138k_audio_clock.v'])]
tests={name:out/name for name in ['tb_panic_audio.sv','tb_panic_push.sv','test_ui_panic.c','test_keyboard_panic.py']}
for name,dest in tests.items():shutil.copy2(here/name,dest)
inputs=set(audio_sources+[project/'src/push2/push2_controls.sv',project/'src/push2/push2_surface_pixels.sv',
    project/'src/video/video_font_5x7.v',project/'firmware/ui_model.h',
    Path(__file__),*tests.values(),Path(__file__).parents[4]/'ae350/scripts/keyboard_midi.py',
    Path(__file__).parents[4]/'ae350/scripts/midi_serial.py'])
(out/'inputs.json').write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(inputs)},indent=2)+'\n')
commands=[
 ('audio_compile',['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_panic_audio','--Mdir',str(out/'audio_obj'),'-I'+str(project),'-I'+str(project/'src/usb_a'),*map(str,audio_sources),str(tests['tb_panic_audio.sv'])]),
 ('audio_sim',[str(out/'audio_obj/Vtb_panic_audio')]),
 ('push_compile',['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_panic_push','--Mdir',str(out/'push_obj'),str(project/'src/push2/push2_controls.sv'),str(project/'src/push2/push2_surface_pixels.sv'),str(project/'src/video/video_font_5x7.v'),str(tests['tb_panic_push.sv'])]),
 ('push_sim',[str(out/'push_obj/Vtb_panic_push')]),
 ('ui_compile',['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(project/'firmware'),str(tests['test_ui_panic.c']),'-o',str(out/'test_ui_panic')]),
 ('ui_test',[str(out/'test_ui_panic')]),
 ('keyboard_test',[sys.executable,str(tests['test_keyboard_panic.py']),str(Path(__file__).parents[4]/'ae350/scripts/keyboard_midi.py')])]
passed=False
try:
    for name,cmd in commands:
        with (out/(name+'.log')).open('w') as log:r=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT)
        print(name,r.returncode,flush=True)
        if r.returncode:
            print((out/(name+'.log')).read_text()[-8000:]);raise SystemExit(1)
    for name in ['audio_sim','push_sim','ui_test','keyboard_test']:print((out/(name+'.log')).read_text().strip())
    passed=True
finally:
    (out/'verification.json').write_text(json.dumps(dict(passed=passed,hardware_tested=False,
        scope='CC120 hard PANIC vs CC123 release; audio allocator/effects, Push mapper/screen snapshot, AE350 UI gate and computer UI feedback'),indent=2)+'\n')
