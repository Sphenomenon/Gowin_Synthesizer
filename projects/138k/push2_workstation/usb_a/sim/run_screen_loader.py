#!/usr/bin/env python3
"""Targeted offline checks for the screen FIFO loader and production scheduler."""
from pathlib import Path
from datetime import datetime
import hashlib,json,subprocess,sys

root=Path(__file__).resolve().parents[1]
build=Path(sys.argv[1]).resolve()
out=build/datetime.now().strftime('screen_loader_sim_%H%M%S_%f')
out.mkdir();print(out,flush=True)
src=build/'Prj1/src/usb_a'
fw=build/'firmware'
sources=[src/'push2_screen_packet_loader.sv',root/'sim/tb_screen_packet_loader.sv']
sources += [src/name for name in ['usbh_core.sv','usbh_sie.sv','usbh_crc5.sv','usbh_crc16.sv','usbh_fifo.sv']]
# The C regression includes the production source directly.
assert (root/'firmware.c').read_bytes()==(fw/'firmware.c').read_bytes()
inputs=sources+[root/'firmware.c',root/'sim/test_hotplug.c',fw/'usb/usb_hw.h']
(out/'inputs.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},indent=2)+'\n')
commands=[
    ('rtl_compile',['iverilog','-g2012','-s','tb_screen_packet_loader','-I'+str(src),'-o',str(out/'rtl_test'),*map(str,sources)]),
    ('rtl_simulation',['vvp',str(out/'rtl_test')]),
    ('firmware_compile',['gcc','-std=c99','-O2','-I'+str(fw),'-I'+str(fw/'usb'),str(root/'sim/test_hotplug.c'),'-o',str(out/'firmware_test')]),
    ('firmware_simulation',[str(out/'firmware_test')]),
]
for name,cmd in commands:
    log=out/(name+'.log')
    with log.open('w') as stream:
        result=subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT)
    if result.returncode:
        print(log.read_text()[-4000:]);raise SystemExit(result.returncode)
    for line in log.read_text().splitlines():
        if line.startswith(('PASS','packet=')):print(line)
(out/'verification.json').write_text(json.dumps(dict(passed=True,hardware_tested=False),indent=2)+'\n')
