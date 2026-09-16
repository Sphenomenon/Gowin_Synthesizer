#!/usr/bin/env python3
"""PC UART -> existing event queues -> synth/effect chain/PT8211; no board access."""
from pathlib import Path
from datetime import datetime
import hashlib,json,shutil,subprocess,sys,xml.etree.ElementTree as ET
build=Path(sys.argv[1]).resolve();p=build/'Prj1'
out=build/datetime.now().strftime('p22_audio_sim_%H%M%S_%f');out.mkdir();print(out,flush=True)
(out/'sim').symlink_to(p/'sim',target_is_directory=True)
tb=out/'tb_keyboard_audio.sv';shutil.copy2(Path(__file__).with_name(tb.name),tb)
sources=[p/f.get('path') for f in ET.parse(p/'Prj1.gprj').find('FileList') if f.get('type')=='file.verilog']
sources=[f for f in sources if not any(x in str(f.relative_to(p)) for x in ['vendor/','src/memory/','src/platform/','src/top/','src/ae350/riscv_','workstation_top.v','workstation_top.sv','gw138k_cpu_pll_cell.v','gw138k_audio_clock.v'])]+[tb]
(out/'inputs.json').write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},indent=2)+'\n')
passed=False
try:
    for name,cmd in [('compile',['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_keyboard_audio','--Mdir',str(out/'obj'),'-I'+str(p),'-I'+str(p/'src/usb_a'),*map(str,sources)]),('simulation',[str(out/'obj/Vtb_keyboard_audio')])]:
        with (out/(name+'.log')).open('w') as log:
            r=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT)
        print(name,r.returncode,flush=True)
        if r.returncode:
            print((out/(name+'.log')).read_text()[-5000:]);raise SystemExit(1)
    print((out/'simulation.log').read_text());passed=True
finally:
    (out/'verification.json').write_text(json.dumps(dict(passed=passed,hardware_tested=False,scope='PC115200/G1 UART, byte CDC, MIDI queues, Push event input, ABC voices, effects and PT8211; no physical acceptance'),indent=2)+'\n')
