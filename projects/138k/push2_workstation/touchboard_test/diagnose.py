#!/usr/bin/env python3
"""Read temporary DG1 pad/pair diagnostic telemetry, keeping all evidence."""
import argparse
import binascii
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parent
PORT='/dev/serial/by-id/usb-SIPEED_USB_Debugger_2025030317-if01-port0'

def decode(line):
    fields=line.split()
    if len(fields)!=3 or fields[0]!=b'DG1': raise ValueError('not DG1')
    b=bytes.fromhex(fields[1].decode())
    if len(b)!=32 or binascii.crc_hqx(b,0xffff)!=int(fields[2],16): raise ValueError('CRC/size')
    return dict(timestamp=datetime.now().astimezone().isoformat(),sequence=int.from_bytes(b[0:4],'little'),
                kind=b[4],scl=b[5]+5,sda=b[6]+5,address=b[7],error=b[8],idle=b[9],low=b[10],released=b[11],
                data=list(b[12:19]),peak_stretch_ticks=int.from_bytes(b[20:24],'little'),
                nominal_i2c_hz=int.from_bytes(b[24:28],'little'))

def summarize(records):
    pins={}
    pairs=Counter()
    ack=Counter()
    for r in records:
        if r['kind']==0:
            pins.setdefault(r['scl'],[]).append({k:r[k] for k in ('idle','low','released')})
        else:
            pairs[(r['scl'],r['sda'],r['address'],r['error'])]+=1
            if r['error']==0:
                ack[(r['scl'],r['sda'],r['address'],tuple(r['data']))]+=1
    return dict(records=len(records),pins=pins,
                ack=[dict(scl=k[0],sda=k[1],address=k[2],data=list(k[3]),count=v) for k,v in ack.items()],
                pairs=[dict(scl=k[0],sda=k[1],address=k[2],error=k[3],count=v) for k,v in pairs.items()],
                error_counts=dict(Counter(r['error'] for r in records if r['kind']!=0)))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',default=PORT)
    parser.add_argument('--seconds',type=float,default=20)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    import serial
    records=[]; rejected=0; raw=[]
    connection=serial.Serial(port=None,baudrate=115200,timeout=.5,exclusive=True)
    connection.dtr=False; connection.rts=False; connection.port=args.port; connection.open(); connection.reset_input_buffer()
    deadline=time.monotonic()+args.seconds
    with connection, (args.output/'capture.jsonl').open('w') as log:
        while time.monotonic()<deadline:
            line=connection.read_until(b'\n',4096)
            if not line:continue
            raw.append(line)
            try:r=decode(line)
            except (ValueError,UnicodeError):rejected+=1;continue
            records.append(r);log.write(json.dumps(r)+'\n');log.flush()
            if r['kind']==0:print('PIN',r['scl'],f"idle={r['idle']:02x} low={r['low']:02x} release={r['released']:02x}",flush=True)
            elif r['error']==0:print('ACK',r,flush=True)
    (args.output/'raw.txt').write_bytes(b''.join(raw))
    result=summarize(records);result['rejected_lines']=rejected
    (args.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print('SUMMARY',json.dumps({k:v for k,v in result.items() if k!='pairs'},indent=2),flush=True)
    if not records:raise SystemExit('No diagnostic telemetry received')

if __name__=='__main__':main()
