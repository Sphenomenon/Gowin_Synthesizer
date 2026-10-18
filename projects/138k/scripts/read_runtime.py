#!/usr/bin/env python3
"""Read-only 115200 bring-up capture; never sends commands or modifies the GUI."""
import argparse
import binascii
from datetime import datetime
import json
from pathlib import Path
import re
import struct
import time


def decode(line):
    match=re.fullmatch(rb'A138 ((?:[0-9A-F]{8} ){8})([0-9A-F]{4})\r?\n',line)
    if not match: raise ValueError('Invalid telemetry framing')
    words=[int(v,16) for v in match[1].split()]
    if binascii.crc_hqx(struct.pack('<8I',*words),0xffff)!=int(match[2],16):
        raise ValueError('CRC mismatch')
    video=struct.pack('<4I',*words[4:])
    return {'sequence':words[0],'flags':words[1],'audio_samples':words[2],
        'audio_status':words[3],'audio_pll_locked':bool(words[1]&1),
        'audio_reset_released':bool(words[1]&2),'memory_flags':(words[1]>>8)&255,
        'dac_underruns_low16':words[3]>>16,'audio_core_faults_low16':words[3]&65535,
        'video_schema':video[0],'video_flags':video[1],
        'pixel_clock_mhz':int.from_bytes(video[2:4],'little')*0.1024,
        'vblank_count':int.from_bytes(video[4:8],'little'),
        'rendered_frames':int.from_bytes(video[8:12],'little'),
        'display_underruns':int.from_bytes(video[12:16],'little')}


def analyze(records):
    intervals=[]
    for previous,current in zip(records,records[1:]):
        delta=(current['audio_samples']-previous['audio_samples'])&0xffffffff
        interval={'from_sequence':previous['sequence'],'to_sequence':current['sequence'],
            'samples_per_50M_reference_clocks':delta,
            'sequence_contiguous':(current['sequence']-previous['sequence'])&0xffffffff==1,
            'audio_lock_continuous':all(r['audio_pll_locked'] and r['audio_reset_released'] for r in (previous,current)),
            'nominal_48k':abs(delta-48000)<=1,
            'scan_advances':(current['vblank_count']-previous['vblank_count'])&0xffffffff>0,
            'renderer_advances':(current['rendered_frames']-previous['rendered_frames'])&0xffffffff>0}
        intervals.append(interval)
    state_ok=all(r['memory_flags']&0xcb==0xcb and r['memory_flags']&0x34==0 and
        r['audio_status']==0 and r['display_underruns']==0 and r['video_schema']==1 and
        r['video_flags']&0x3e==0x2e and abs(r['pixel_clock_mhz']-148.5)<0.2 for r in records)
    interval_ok=all(all(p[k] for k in ('sequence_contiguous','audio_lock_continuous','nominal_48k','scan_advances','renderer_advances')) for p in intervals)
    return {'digital_runtime_pass':len(records)>=3 and state_ok and interval_ok,
        'record_count':len(records),'state_checks_pass':state_ok,'intervals':intervals,
        'analog_audio_tested':False,'hdmi_receiver_tested':False,
        'limitation':'Counts are relative to the board 50MHz reference. UART does not verify analog audio, cable/display reception, all DDR addresses or Flash boot.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--seconds',type=float,default=10)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.seconds<=0 or args.seconds>60: parser.error('--seconds must be in (0,60]')
    out=args.output or Path(__file__).resolve().parents[1]/'results'/datetime.now().strftime('runtime_capture_%Y%m%d_%H%M%S_%f')
    out.mkdir(parents=True,exist_ok=False)
    import serial
    port=serial.Serial(port=None,baudrate=115200,timeout=0.3)
    port.dtr=False;port.rts=False;port.port=args.port
    records=[];rejected=[];partial_lines=0
    with port, (out/'raw_uart.bin').open('wb') as raw:
        deadline=time.monotonic()+args.seconds
        while time.monotonic()<deadline:
            line=port.read_until(b'\n',size=1024)
            if not line: continue
            raw.write(line)
            if not line.startswith(b'A138 '): partial_lines+=1;continue
            try:
                item=decode(line);item['host_time']=datetime.now().astimezone().isoformat();records.append(item)
                print(f"seq={item['sequence']} audio={item['audio_samples']} memory=0x{item['memory_flags']:02x} faults=0x{item['audio_status']:08x} pixel={item['pixel_clock_mhz']:.4f}MHz",flush=True)
            except ValueError as error: rejected.append({'line':line.hex(),'error':str(error)})
    summary=analyze(records)
    summary.update(port=args.port,records=records,rejected=rejected,partial_lines=partial_lines,
        requested_seconds=args.seconds,host_writes=0)
    summary['digital_runtime_pass']=summary['digital_runtime_pass'] and not rejected
    (out/'runtime.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(out, 'PASS digital runtime' if summary['digital_runtime_pass'] else 'NOT PASSED',flush=True)
    return 0 if summary['digital_runtime_pass'] else 1


if __name__=='__main__': raise SystemExit(main())
