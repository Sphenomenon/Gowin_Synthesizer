#!/usr/bin/env python3
"""Capture CRC-checked production/Push telemetry; optional explicit USB Host gate."""
from pathlib import Path
from datetime import datetime
import argparse,binascii,json,re,struct,sys,time
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE.parent/'ae350/scripts'))
from midi_serial import DEFAULT_PORT,performance,expression

def decode(line,usb_a=False):
    m=re.fullmatch(rb'(A138|C350|K138|E138|U138|P138) ((?:[0-9A-F]{8} ){8})([0-9A-F]{4})\r?\n',line)
    if not m:return None
    w=[int(n,16) for n in m[2].split()]
    if binascii.crc_hqx(struct.pack('<8I',*w),0xffff)!=int(m[3],16):raise ValueError('telemetry CRC mismatch')
    kind=m[1].decode();value={'words':w}
    if kind=='K138':value=performance(w)
    if kind=='E138' and w[7]==0x43545231:value=expression(w)
    if kind=='P138':
        f=w[1]
        if usb_a:
            if (f & ~3)!=0x100:raise ValueError('not USB-A workstation telemetry')
            return kind,dict(sequence=w[0],transport='FPGA USB-A FS VexRiscv',
                enabled=bool(f&1),configured=bool(f&2),high_speed=False,
                received_words=w[2],mapped_events=w[3],commands_acked=w[4],
                frames_acked=w[5],usb_in_errors=None,out_errors=w[7])
        value=dict(sequence=w[0],enabled=bool(f&1),configured=bool(f&2),display_fault=bool(f&4),high_speed=bool(f&8),
            display_fault_code=(f>>4)&15,host_state=(f>>8)&255,enum_error=(f>>16)&255,hspi_errors=f>>24,
            replies=w[2],mapped_events=w[3],commands_acked=w[4],frames_acked=w[5],usb_in_errors=w[6],link_errors=w[7])
        if 0xf8<=value['enum_error']<=0xfd:
            index=value['enum_error']-0xf8
            names=['request_lengths','before_ack_lengths','after_ack_lengths','after_10us_lengths','before_ack_state','after_10us_state']
            value.update(bridge_trace_index=index,bridge_trace_name=names[index],bridge_trace_hex=f'{w[6]:08X}',usb_in_errors=None)
            if index==0:value.update(bridge_length_received=w[6]>>16,bridge_length_header=w[6]&65535)
            elif index<4:value.update(rx_len0=w[6]>>16,rx_len1=w[6]&65535)
            else:value.update(rx_sc=w[6]>>24,hspi_cfg=(w[6]>>16)&255,rtx_status=(w[6]>>8)&255,int_flags=w[6]&255)
        elif value['enum_error']&128:
            value.update(bridge_error_reason=value['enum_error']&127,bridge_length_received=w[6]>>16,bridge_length_header=w[6]&65535,usb_in_errors=None)

    return kind,value

def main():
    import serial
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',default=DEFAULT_PORT);ap.add_argument('--seconds',type=float,default=10)
    ap.add_argument('--host',choices=['enable','disable']);ap.add_argument('--quiet',action='store_true')
    ap.add_argument('--usb-a',action='store_true',help='decode USB-A workstation counters; no CH569 gate');args=ap.parse_args()
    if args.usb_a and args.host:ap.error('USB-A Host starts automatically; --host is CH569-only')
    out=BASE/'results'/datetime.now().strftime('capture_%Y%m%d_%H%M%S_%f');out.mkdir()
    print(out,flush=True)
    port=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=2,exclusive=True)
    port.dtr=False;port.rts=False;port.port=args.port
    records={};traces={};errors=0;result=dict(host_command=args.host,port=args.port,usb_a=args.usb_a)
    try:
        with port,(out/'serial.raw').open('wb') as raw,(out/'events.jsonl').open('w') as events:
            port.reset_input_buffer()
            # Drain stale FTDI/OS records across SRAM reload before acceptance.
            warmup=time.monotonic()+2
            while time.monotonic()<warmup:raw.write(port.read_until(b'\n',size=1024))
            if args.host:
                cmd=bytes.fromhex('f0 7d 50 55 53 48')+bytes([args.host=='enable',0xf7])
                port.write(cmd);port.flush();result['command_hex']=cmd.hex()
            end=time.monotonic()+args.seconds
            while time.monotonic()<end:
                line=port.read_until(b'\n',size=1024);raw.write(line)
                try:r=decode(line,usb_a=args.usb_a)
                except ValueError:errors+=1;continue
                if not r:continue
                k,v=r;records[k]=v
                if k=='P138' and 'bridge_trace_name' in v:
                    traces[v['bridge_trace_name']]=v
                event=dict(time=datetime.now().isoformat(),kind=k,**v)
                events.write(json.dumps(event)+'\n');events.flush()
                if not args.quiet and k in ['P138','K138']:print(json.dumps(event),flush=True)
    finally:
        result.update(last=records,bridge_traces=traces,crc_errors=errors)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
