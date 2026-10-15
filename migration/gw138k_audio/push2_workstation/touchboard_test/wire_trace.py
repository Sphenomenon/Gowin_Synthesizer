#!/usr/bin/env python3
"""Decode TW1 independent physical-pad I2C listener records; never hide failures."""
import argparse
import binascii
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import time

PORT='/dev/serial/by-id/usb-SIPEED_USB_Debugger_2025030317-if01-port0'

def complete_lines(buffer,chunk):
    parts=(buffer+chunk).split(b'\n')
    return [line+b'\n' for line in parts[:-1]],parts[-1]

def decode(line,clock_hz=50000000):
    fields=line.split()
    if len(fields)!=3 or fields[0] not in (b'TW1',b'TA1'):raise ValueError('not TW1/TA1')
    b=bytes.fromhex(fields[1].decode())
    if len(b)!=(249 if fields[0]==b'TA1' else 225) or binascii.crc_hqx(b,0xffff)!=int(fields[2],16):raise ValueError('size/CRC')
    length,count=b[8],b[9]
    if length>64 or count>65:raise ValueError('length/count')
    master=list(b[22:22+length]);rise=list(b[86:86+count]);late=list(b[151:151+count])
    mask=int.from_bytes(b[216:225],'little');nacks=[(mask>>i)&1 for i in range(count)]
    flags=b[10]
    faults=[]
    if b[7]:faults.append('master-error')
    if b[4]!=b[5]:faults.append('pointer-mismatch')
    if b[7]==0 and count!=length+1:faults.append('byte-count')
    if not(flags&4):faults.append('no-stop')
    if flags&8:faults.append('overflow')
    if flags&16 or rise!=late:faults.append('sample-window-mismatch')
    if rise and rise[0]!=0x1b:faults.append('address-byte')
    if b[7]==0 and master!=rise[1:]:faults.append('master-wire-mismatch')
    if b[7]==0 and nacks!=([0]*length+[1]):faults.append('ack-sequence')
    gap=int.from_bytes(b[18:22],'little')
    if gap<clock_hz//20000:faults.append('stop-start-below-50us')
    result=dict(timestamp=datetime.now().astimezone().isoformat(),sequence=int.from_bytes(b[:4],'little'),
                pointer_master=b[4],pointer_wire=b[5],state=b[6],error=b[7],length=length,count=count,
                flags=flags,io=b[11],burst=b[12],raw_words=bool(b[13]&1),device='U2' if b[13]&128 else 'U1',peak_stretch_ticks=int.from_bytes(b[14:18],'little'),
                start_gap_ticks=gap,master=master,wire_rise=rise,wire_late=late,nacks=nacks,faults=faults)
    if fields[0]==b'TA1':
        raw=int.from_bytes(b[225:227],'little')
        result['power_adc']=dict(raw=raw,minimum_raw=int.from_bytes(b[227:229],'little'),maximum_raw=int.from_bytes(b[229:231],'little'),
                                count=int.from_bytes(b[231:235],'little'),timeouts=int.from_bytes(b[235:239],'little'),
                                age_ticks=int.from_bytes(b[239:243],'little'),duration_ticks=int.from_bytes(b[243:247],'little'),
                                flags=b[247],source_bank=b[248],valid=bool(b[247]&1),
                                voltage_v=raw/256 if b[247]&1 else None,
                                measurement_scope='FPGA VCCIO4 SOM rail; separate from PMOD peripheral 3V3')
    return result

def summarize(records):
    counts=Counter();words={};status=[]
    for r in records:
        counts.update(r['faults'])
        if r['faults']:continue
        data=r['master'];ptr=r['pointer_master']
        if ptr==0 and len(data)>=7:status.append(dict(general=data[2],keys=data[3]+256*data[4]))
        for offset in range(0,len(data)-1,2):
            addr=ptr+offset
            if 100<=addr<164 and addr%2==0:words.setdefault(addr,[]).append(data[offset]+256*data[offset+1])
    summary=dict(device_counts=dict(Counter(r.get('device','U1') for r in records)),records=len(records),fault_counts=dict(counts),transaction_errors=dict(Counter(r['error'] for r in records if r['error'])),wire_verified_records=sum(not r['faults'] for r in records),
                pointer_counts=dict(Counter(r['pointer_master'] for r in records)),
                status_records=len(status),status_any_key=sum(bool(s['keys']) for s in status),
                status_all_keys=sum(s['keys']==65535 for s in status),
                words={a:dict(samples=len(v),minimum=min(v),maximum=max(v),unique=len(set(v)),zeros=v.count(0)) for a,v in sorted(words.items())},
                start_gap_min_ticks=min((r['start_gap_ticks'] for r in records),default=None),
                peak_stretch_max_ticks=max((r['peak_stretch_ticks'] for r in records),default=None))
    adc=[r['power_adc'] for r in records if r.get('power_adc',{}).get('valid')]
    if any('power_adc' in r for r in records):
        summary['power_adc']=dict(valid_records=len(adc),
                                  distinct_count_observations=len({r['count'] for r in adc}),
                                  maximum_count=max((r['count'] for r in adc),default=0),
                                  minimum_v=min((r['minimum_raw']/256 for r in adc),default=None),
                                  maximum_v=max((r['maximum_raw']/256 for r in adc),default=None),
                                  maximum_timeouts=max((r['timeouts'] for r in adc),default=0),
                                  scope='FPGA SOM VCCIO4 rail, separate regulator from PMOD 3V3; does not measure QT supply or bound high-frequency ripple')
    return summary

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',default=PORT)
    p.add_argument('--seconds',type=float,default=40);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--input',type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    records=[];raw=[];rejected=0
    def accept(line):
        nonlocal rejected
        try:r=decode(line)
        except (ValueError,UnicodeError):rejected+=1;return
        records.append(r)
        if r['faults']:print('FAULT',r['sequence'],r['faults'],flush=True)
    if a.input:
        raw=a.input.read_bytes().splitlines(keepends=True)
        for line in raw:accept(line)
    else:
        import serial
        connection=serial.Serial(port=None,baudrate=115200,timeout=.5,exclusive=True)
        connection.dtr=False;connection.rts=False;connection.port=a.port;connection.open();connection.reset_input_buffer()
        # FTDI may deliver old USB packets even after the initial buffer purge.
        # Drain for one second through a newline boundary before timed capture;
        # preserve every discarded byte for review.
        startup=[];warmup_end=time.monotonic()+1
        while time.monotonic()<warmup_end:
            chunk=connection.read_until(b'\n',4096)
            if chunk:startup.append(chunk)
        (a.output/'startup_raw.txt').write_bytes(b''.join(startup))
        deadline=time.monotonic()+a.seconds
        buffer=b''
        with connection:
            while time.monotonic()<deadline:
                line=connection.read_until(b'\n',4096)
                if line:
                    raw.append(line)
                    complete,buffer=complete_lines(buffer,line)
                    for frame in complete:accept(frame)
        if buffer:rejected+=1
    (a.output/'raw.txt').write_bytes(b''.join(raw))
    # FTDI buffers can contain the prior programming session. Retain raw evidence,
    # but report the suffix after the last observed sequence rollback.
    cut=0
    for i in range(1,len(records)):
        if records[i]['sequence']<records[i-1]['sequence']:cut=i
    previous=len(records);records=records[cut:]
    (a.output/'capture.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
    summary=summarize(records);summary.update(rejected_lines=rejected,prior_session_records=cut,total_decoded_records=previous)
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)
    if not records:raise SystemExit('No TW1 telemetry')

if __name__=='__main__':main()
