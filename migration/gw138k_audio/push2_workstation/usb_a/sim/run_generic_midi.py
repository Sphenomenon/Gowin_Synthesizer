#!/usr/bin/env python3
"""Offline production-C and MMIO/CDC/synth regression for auto USB MIDI mode."""
from pathlib import Path
from datetime import datetime
import hashlib,json,shutil,subprocess,sys,xml.etree.ElementTree as ET

here=Path(__file__).resolve().parent
build=Path(sys.argv[1]).resolve();project=build/'Prj1';fw=build/'firmware'
out=build/datetime.now().strftime('generic_midi_%H%M%S_%f');out.mkdir();print(out,flush=True)
assert (here.parent/'firmware.c').read_bytes()==(fw/'firmware.c').read_bytes()
# Preserve the test and production firmware together so include paths bind to
# this exact candidate, even if another session edits the working tree later.
shutil.copy2(fw/'firmware.c',out/'firmware.c');(out/'sim').mkdir()
for name in ['test_generic_midi.c','test_hotplug.c','tb_generic_midi.sv']:
    shutil.copy2(here/name,out/'sim'/name)
sources=[project/f.get('path') for f in ET.parse(project/'Prj1.gprj').find('FileList') if f.get('type')=='file.verilog']
sources=[f for f in sources if not any(x in str(f.relative_to(project)) for x in
    ['vendor/','src/memory/','src/platform/','src/top/','src/ae350/riscv_',
     'workstation_top.v','workstation_top.sv','gw138k_cpu_pll_cell.v','gw138k_audio_clock.v'])]
inputs=[*sources,Path(__file__),out/'firmware.c',*sorted((out/'sim').iterdir())]
(out/'inputs.json').write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in inputs},indent=2)+'\n')
commands=[]
for name in ['generic_midi','hotplug']:
    commands += [(name+'_compile',['gcc','-std=c99','-O2','-fsanitize=address,undefined',
        '-fno-omit-frame-pointer','-I'+str(fw),'-I'+str(fw/'usb'),
        str(out/'sim'/('test_'+name+'.c')),'-o',str(out/name)]),
        (name+'_test',[str(out/name)]+([str(out/'generic_events.mem')] if name=='generic_midi' else []))]
commands += [('rtl_compile',['verilator','--binary','--timing','-j','4','-Wno-fatal',
    '--top-module','tb_generic_midi','--Mdir',str(out/'obj'),'-I'+str(project),
    '-I'+str(project/'src/usb_a'),*map(str,sources),str(out/'sim/tb_generic_midi.sv')]),
    ('rtl_test',[str(out/'obj/Vtb_generic_midi')])]
# Keep memory data relative to the real staged project, not the editable tree.
for name in ['data','matlab']:
    (out/'sim'/name).symlink_to(project/'sim'/name,target_is_directory=True)
passed=False
try:
    for name,cmd in commands:
        with (out/(name+'.log')).open('w') as log:
            r=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT)
        print(name,r.returncode,flush=True)
        if r.returncode:print((out/(name+'.log')).read_text()[-6000:]);raise SystemExit(1)
        if name.endswith('_test'):print((out/(name+'.log')).read_text(),flush=True)
    passed=True
finally:
    (out/'verification.json').write_text(json.dumps(dict(passed=passed,hardware_tested=False,
        scope='production USB mode/descriptor/event C + MMIO/CDC/synth PCM, full FIFO, disconnect PANIC, Push hotplug/screen/LED'),indent=2)+'\n')
