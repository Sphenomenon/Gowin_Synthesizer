#!/usr/bin/env python3
"""Use a local pseudo-terminal to verify serial framing/reconnection and GUI rendering."""
import binascii
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import monitor

out=ROOT/'results'/datetime.now().strftime('monitor_test_%Y%m%d_%H%M%S')
out.mkdir()
sim=Path((ROOT/'LATEST_TEST.txt').read_text().strip())
lines=[line for line in (sim/'uart.txt').read_bytes().splitlines() if line.startswith((b'TB1 ',b'TB2 ')) and len(line.strip()) in (113,345)]
line=next(line for line in lines if monitor.decode(line)['key_device']['raw_valid'] and monitor.decode(line)['key_device']['keys']==0x8005 and monitor.decode(line)['key_device']['signals'][1]==999)
payload=bytearray(bytes.fromhex(line.split()[1].decode()))
def frame(sequence):
    payload[:4]=sequence.to_bytes(4,'little')
    return b'TB2 '+payload.hex().encode()+f' {binascii.crc_hqx(payload,0xffff):04X}\r\n'.encode()

master,slave=os.openpty()
port=out/'pseudo_uart'
port.symlink_to(os.ttyname(slave))
events,stop=queue.Queue(),threading.Event()
reader=monitor.Reader(str(port),events,stop,out/'simulated_capture.jsonl')
reader.start()
checks=[]
def event(kind,predicate=lambda value:True,timeout=7):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try: k,v=events.get(timeout=.2)
        except queue.Empty: continue
        if k==kind and predicate(v):return v
    raise AssertionError(f'missing {kind} event')
try:
    event('state',lambda s:'串口已连接' in s)
    invalid=bytearray(frame(0));invalid[12]=ord('1') if invalid[12]!=ord('1') else ord('2')
    os.write(master,invalid)
    encoded=frame(0)
    # Fragmented writes exercise the actual buffered pyserial read path.
    os.write(master,encoded[:27]);os.write(master,encoded[27:])
    first=event('frame')
    assert first['crc_errors']==1 and first['sequence']==0
    assert first['key_device']['keys']==0x8005
    assert first['slider_touch_count']==1 and first['slider_last_touch_position']==173
    os.write(master,frame(3))
    second=event('frame')
    assert second['dropped']==2
    checks += ['PTY/pyserial partial frame reads','corrupt frame rejected','sequence gap counted']
    payload[19] &= ~1
    os.write(master,frame(4))
    released=event('frame')
    assert not released['slider_device']['slider_detect']
    assert released['slider_touch_count']==1 and released['slider_last_touch_position']==173
    payload[19] |= 1
    checks.append('brief slider touch remains visible as event count and last position after release')
    event('state',lambda s:'2 秒内没有' in s)
    checks.append('serial silence is marked stale')
    os.close(master);os.close(slave)
    event('state',lambda s:'等待下载器 UART' in s)
    master,slave=os.openpty()
    port.unlink();port.symlink_to(os.ttyname(slave))
    event('state',lambda s:'串口已连接' in s)
    os.write(master,frame(0));again=event('frame')
    assert again['sequence']==0 and again['dropped']==2
    checks.append('port disconnect/reconnect resets sequence baseline')
    gui=monitor.Dashboard(queue.Queue(),threading.Event(),None,True)
    gui.root.withdraw();gui.render(first);gui.root.update_idletasks()
    assert gui.slider['value']==173
    assert str(gui.tables[0].item('1')['values'][1])=='999'
    gui.render(released)
    assert '1 次' in gui.slider_history.cget('text') and '173' in gui.slider_history.cget('text')
    invalid_raw = dict(first)
    invalid_raw['slider_device'] = dict(first['slider_device'], references=[0]*16, signals=[0]*16)
    gui.render(invalid_raw)
    assert gui.slider['value']==0 and '基准全零' in gui.slider_label.cget('text')
    checks.append('GUI does not present SDET with zero references as valid slider position')
    gui.invalidate();gui.root.update_idletasks()
    assert gui.slider['value']==0 and gui.tables[0].item('1')['values'][1]=='--'
    gui.close()
    checks += ['GUI renders real decoded model frame','GUI invalidates stale key/slider/raw values']
finally:
    stop.set();reader.join(timeout=2)
    os.close(master);os.close(slave)
    if port.exists():port.unlink()
report=dict(passed=True,checks=checks,hardware_used=False,source_simulation=str(sim))
(out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2));print(out)
