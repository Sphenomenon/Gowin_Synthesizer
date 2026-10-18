#!/usr/bin/env python3
"""Validate the actual frozen merge, including the Vex CPU bus and audio core."""
from pathlib import Path
from datetime import datetime
import hashlib,json,shutil,subprocess,sys,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
b=Path(sys.argv[1]).resolve();p=b/'Prj1';out=b/datetime.now().strftime('cpu_audio_sim_%H%M%S_%f');out.mkdir();print(out,flush=True)
fw=out/'firmware';shutil.copytree(b/'firmware',fw,ignore=shutil.ignore_patterns('*.o','*.elf','*.bin'))
shutil.copy2(ROOT/'sim/cpu_audio_probe.c',fw/'firmware.c')
prefix=str(Path.home()/'.local/opt/amd/2025.2.1/gnu/riscv/lin/bin/riscv64-unknown-elf')
with (out/'firmware_compile.log').open('w') as log:
    def run(cmd):subprocess.run(cmd,cwd=fw,stdout=log,stderr=subprocess.STDOUT,check=True)
    for name in ['start.S','firmware.c']:
        run([prefix+'-gcc','-O2','-mabi=ilp32','-march=rv32i','-ffreestanding','-c',name,'-o',str(Path(name).with_suffix('.o'))])
    run([prefix+'-gcc','-mabi=ilp32','-march=rv32i','-Wl,--build-id=none,-Bstatic,-T,baremetal.ld','-nostdlib','start.o','firmware.o','-lgcc','-o','test.elf'])
    run([prefix+'-objcopy','-O','binary','test.elf','test.bin'])
data=(fw/'test.bin').read_bytes().ljust(65536,b'\0')
(out/'push2_usb_a.hex').write_text(''.join(f'{int.from_bytes(data[i:i+4],"little"):08x}\n' for i in range(0,len(data),4)))
# ROM paths must resolve to the frozen build. Link only read-only source data.
(out/'sim').symlink_to(p/'sim',target_is_directory=True)
sources=[p/f.get('path') for f in ET.parse(p/'Prj1.gprj').find('FileList') if f.get('type')=='file.verilog']
# legacy_audio.sv already contains the source package and synthesis defines.
# Remove unrelated encrypted physical DDR/AE350/PLL/HDMI top-level IP.
sources=[f for f in sources if not any(x in str(f.relative_to(p)) for x in ['vendor/','src/memory/','src/storage/','src/platform/','src/top/','src/ae350/riscv_','workstation_top.v','workstation_top.sv','gw138k_cpu_pll_cell.v','gw138k_audio_clock.v'])]
sources+=[ROOT/'sim/tb_cpu_audio.sv']
(out/'inputs.json').write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources+[ROOT/'sim/cpu_audio_probe.c']},indent=2)+'\n')
commands=[['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_cpu_audio','--Mdir',str(out/'obj'),'-I'+str(p),'-I'+str(p/'src/usb_a'),*map(str,sources)],
          [str(out/'obj/Vtb_cpu_audio')]]
for name,cmd in zip(['compile','simulation'],commands):
    with (out/(name+'.log')).open('w') as log:r=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT)
    print(name,r.returncode,flush=True)
    if r.returncode:print((out/(name+'.log')).read_text()[-5000:]);raise SystemExit(1)
print((out/'simulation.log').read_text())
(out/'verification.json').write_text(json.dumps(dict(passed=True,hardware_tested=False),indent=2)+'\n')
