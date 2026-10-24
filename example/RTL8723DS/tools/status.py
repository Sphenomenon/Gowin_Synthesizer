#!/usr/bin/env python3
"""Capture 138K RF13 status at 115200 8N1 using standard-library POSIX serial IO."""
import argparse, datetime, json, os, re, select, termios, time
from pathlib import Path
ERRORS={0:'none',0x11:'response_timeout',0x12:'response_frame',0x13:'response_crc_or_index',
        0x14:'dat0_busy_timeout',0x20:'r5_error',0x21:'no_sdio_function',0x22:'incompatible_voltage',
        0x23:'ocr_ready_timeout',0x24:'rca_error',0x25:'select_error',0x26:'cis_pointer_invalid',
        0x27:'cis_walk_limit',0x28:'manfid_missing',0x29:'tuple_bounds',0x2a:'manfid_short',
        0x2b:'unexpected_vendor_device',0x2c:'function1_ready_timeout'}
def decode(line):
    if not re.fullmatch(rb'RF13 [0-9A-F]{256}',line): return None
    words=[int(line[5+i*8:13+i*8],16) for i in range(32)]
    if words[0]!=0x42545647 or words[24]!=0x5344494f: return None
    f=words[2]; w=words[25]; error=w>>24
    return {'ble':{'active':bool(f&1),'link_up':bool(f&2),'initialized':bool(f&4),
            'connected':bool(f&8),'subscribed':bool(f&16),'failed':bool(f&32),
            'session_ended':bool(f&64),'uptime_ms':words[3],'states':f'{words[4]:08x}',
            'last_error_status_opcode':f'{words[5]:08x}','patch_fragments':words[7],
            'rx_frames':words[8],'tx_frames':words[9],'retries':words[10],
            'uart_errors':words[11],'protocol_errors':words[12],'notifications':words[13],
            'rom_version':words[20]&255},
        'wifi':{'wl_enable':bool(w&1),'done':bool(w&2),'identified':bool(w&4),
            'failed':bool(w&8),'state':(w>>4)&15,'step':(w>>10)&63,
            'dat_pins':(w>>16)&15,'error':f'{error:02x}','error_name':ERRORS.get(error,'unknown'),
            'ocr':f'{words[26]:08x}','rca':f'{words[27]>>16:04x}',
            'cccr_revision':(words[27]>>8)&255,'card_capabilities':words[27]&255,
            'function_interface':words[28]>>24,'cis_pointer':f'{words[28]&0xffffff:06x}',
            'vendor_id':f'{words[29]>>16:04x}','device_id':f'{words[29]&65535:04x}',
            'last_response':f'{words[30]:08x}','commands':words[31]},'words':[f'{x:08x}' for x in words]}
def capture(port,seconds):
    fd=os.open(port,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
    old=termios.tcgetattr(fd)
    samples=[]; raw=bytearray(); pending=bytearray()
    try:
        a=termios.tcgetattr(fd); a[0]=0; a[1]=0; a[2]=termios.CS8|termios.CREAD|termios.CLOCAL
        a[3]=0; a[4]=termios.B115200; a[5]=termios.B115200; a[6][termios.VMIN]=0; a[6][termios.VTIME]=0
        termios.tcsetattr(fd,termios.TCSANOW,a)
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if not select.select([fd],[],[],min(0.25,max(0,end-time.monotonic())))[0]: continue
            data=os.read(fd,65536); raw.extend(data); pending.extend(data)
            while b'\n' in pending:
                line,_,rest=pending.partition(b'\n'); pending=bytearray(rest)
                item=decode(line.rstrip(b'\r'))
                if item:
                    item['captured_at']=datetime.datetime.now().astimezone().isoformat(); samples.append(item)
    finally:
        termios.tcsetattr(fd,termios.TCSANOW,old); os.close(fd)
    return raw,samples

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',default='/dev/cu.usbserial-31201'); p.add_argument('--seconds',type=float,default=10)
    p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    raw,samples=capture(a.port,a.seconds)
    result={'port':a.port,'seconds':a.seconds,'samples':samples,'sample_count':len(samples),'passed':False}
    if samples:
        last=samples[-1]; result['last']=last
        result['passed']=(last['ble']['initialized'] and not last['ble']['failed'] and
            last['wifi']['done'] and last['wifi']['identified'] and not last['wifi']['failed'])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n'); a.output.with_suffix('.raw').write_bytes(raw)
    print(json.dumps({k:v for k,v in result.items() if k!='samples'},indent=2))
    return 0 if result['passed'] else 1
if __name__=='__main__': raise SystemExit(main())
