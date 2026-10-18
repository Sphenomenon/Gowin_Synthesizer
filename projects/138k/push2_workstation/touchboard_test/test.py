#!/usr/bin/env python3
"""Exercise the real I2C state machines and decode actual UART serial bits."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import queue
import threading
import monitor
from netlist import connector_wiring

ROOT=Path(__file__).resolve().parent
out=ROOT/'results'/datetime.now().strftime('sim_%Y%m%d_%H%M%S_%f')
out.mkdir(parents=True)
header,wiring=connector_wiring()
assert header==dict(sda1=3,scl1=5,sda2=4,scl2=6,sda3=10,scl3=8,change_n=9,ws2812_din=7)
assert wiring==dict(sda1=12,scl1=10,sda2=11,scl2=9,sda3=5,scl3=7,change_n=6,ws2812_din=8)
checks=['netlist resistor-array/U4/PMOD wiring']
for top in ('tb_i2c_faults','tb_touchboard'):
    command=['iverilog','-g2012','-s',top,'-o',str(out/top)]
    command += [str(p) for p in sorted((ROOT/'rtl').glob('*'))]
    command += [str(ROOT/'tests/i2c_device_model.sv'),str(ROOT/'tests'/f'{top}.sv')]
    subprocess.run(command,check=True)
    result=subprocess.run(['vvp',str(out/top)],cwd=out,capture_output=True,text=True,timeout=180)
    (out/(top+'.log')).write_text(result.stdout+result.stderr)
    print(result.stdout,result.stderr,flush=True)
    if result.returncode or 'PASS' not in result.stdout: raise SystemExit('RTL simulation failed')
    checks.append(top)
lines=(out/'uart.txt').read_bytes().splitlines()
frames=[monitor.decode(line) for line in lines if line.startswith((b'TB1 ',b'TB2 ')) and len(line.strip()) in (113,345)]
assert len(frames)>5, len(frames)
active=[f for f in frames if monitor.ready(f['key_device']) and f['key_device']['keys']==0x8005]
assert active, 'touch frame missing'
assert any(f['slider_device']['slider_detect'] and f['slider_device']['slider_position']==173 for f in active)
assert any(f['key_device']['raw_valid'] and f['key_device']['signals'][1]==999 for f in active)
assert any(not f['key_device']['online'] and f['key_device']['error']==1 for f in frames)
assert monitor.ready(frames[-1]['key_device']), 'reconnect frame'
assert any(0x40 in f['scan_ack'] for f in frames), 'I2C3 PCA9685 address ACK'
assert any(f['key_device']['sleeping'] and f['slider_device']['sleeping'] for f in frames), 'sleep flags missing from UART'
assert frames[-1]['key_device']['i2c_address']==0x17, 'alternate address missing from UART'
assert all((b['sequence']-a['sequence'])==1 for a,b in zip(frames,frames[1:])), 'UART sequence continuity'
collector=monitor.Reader('',queue.Queue(),threading.Event(),None)
all_channels=[False,False]
for f in frames:
    collector.publish(f)
    for bit,name in enumerate(('key_device','slider_device')):
        d=f[name]
        if monitor.ready(d) and all(value is not None for value in d['signals']):
            assert d['signals']==[1000-k for k in range(16)]
            assert d['references']==[1000]*16
            all_channels[bit]=True
assert all(all_channels),'all 16 diagnostic channels must reach UART and cache'
checks.append('all 32 signal/reference channels delivered and cached')
bad=bytearray(lines[1]);bad[12]=ord('0') if bad[12]!=ord('0') else ord('1')
try: monitor.decode(bytes(bad))
except ValueError: checks.append('CRC corruption rejected')
else: raise AssertionError('CRC accepted corrupted telemetry')
checks += ['wrong ID blocks configuration', 'bad readback blocks ready/calibration', 'UART 8N1 to parser','16-key multi-touch and release','slider touch/position',
           'contiguous raw signals/references','alternate address discovery + UART reporting','LP/BREP/DI readback','offline invalidation and reconnect','I2C3 PCA9685 0x40 address ACK']
report=dict(passed=True,checks=checks,frames=len(frames),hardware_tested=False,
            inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for folder in ('rtl','tests') for p in sorted((ROOT/folder).glob('*')) if p.is_file()})
(out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
(ROOT/'LATEST_TEST.txt').write_text(str(out)+'\n')
print(json.dumps(report,indent=2));print(out)
