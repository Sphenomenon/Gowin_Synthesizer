#!/usr/bin/env python3
"""Read-only C350 boot probe capture; checks CPU writes, RAM result and heartbeat."""
import argparse,binascii,datetime,json,re,struct,time
from pathlib import Path
import serial

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--seconds',type=float,default=8)
    ap.add_argument('--port',default='/dev/serial/by-id/usb-SIPEED_USB_Debugger_2025030317-if01-port0')
    args=ap.parse_args()
    assert 0<args.seconds<=60
    out=Path(__file__).resolve().parents[2]/'results'/datetime.datetime.now().strftime('ae350_uart_%Y%m%d_%H%M%S_%f')
    out.mkdir();print(out,flush=True)
    port=serial.Serial(port=None,baudrate=115200,timeout=.3)
    port.dtr=False;port.rts=False;port.port=args.port
    records=[];rejected=[];partial=0
    with port,(out/'raw_uart.bin').open('wb') as raw:
        deadline=time.monotonic()+args.seconds
        while time.monotonic()<deadline:
            line=port.read_until(b'\n',size=1024)
            if not line:continue
            raw.write(line)
            m=re.fullmatch(rb'C350 ((?:[0-9A-F]{8} ){8})([0-9A-F]{4})\r?\n',line)
            if not m:partial+=1;continue
            words=[int(v,16) for v in m[1].split()]
            if binascii.crc_hqx(struct.pack('<8I',*words),0xffff)!=int(m[2],16):
                rejected.append(line.hex());continue
            records.append(words)
            print(' '.join(f'{v:08X}' for v in words),flush=True)
    state=bool(records) and all(r[4]==0x43505531 and r[5]==0x50415353 and r[7]==0 and 0x80000000<=r[3]<0x80004000 for r in records)
    # Uncached ROM execution takes slightly over one report interval per
    # million-iteration firmware delay. Require progress over the capture,
    # monotonic heartbeat and fetch activity in every adjacent report.
    advancing=len(records)>=3 and 0<((records[-1][6]-records[0][6])&0xffffffff)<100000 and all(
        ((b[0]-a[0])&0xffffffff)==1 and ((b[6]-a[6])&0xffffffff)<100000 and
        0<((b[2]-a[2])&0xffffffff)<100000000 for a,b in zip(records,records[1:]))
    passed=len(records)>=3 and state and advancing and not rejected
    (out/'capture.json').write_text(json.dumps(dict(passed=passed,records=records,rejected=rejected,partial=partial,host_writes=0,port=args.port,limits='Physical CPU ROM execution, specific RAM word/byte checks and APB register writes only. No DDR, audio, UI or cold boot acceptance.'),indent=2)+'\n')
    print('PASS CPU boot' if passed else 'NOT PASSED',flush=True)
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
