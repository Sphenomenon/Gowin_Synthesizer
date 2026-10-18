#!/usr/bin/env python3
"""Restore saved workstation controls after a verified SRAM download."""
from pathlib import Path
from datetime import datetime
import argparse,json,sys,time
import serial
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE.parent/'ae350/scripts'))
from midi_serial import DEFAULT_PORT,decode_record,performance,expression
def get_controls(port,seconds,logfile,after_sequence=None):
    latest_cpu=None;latest_state=None
    deadline=time.monotonic()+seconds
    with logfile.open('ab') as raw:
        while time.monotonic()<deadline:
            line=port.read_until(b'\n',size=1024)
            if not line:continue
            raw.write(line);raw.flush()
            try: decoded=decode_record(line)
            except ValueError: continue
            if not decoded:continue
            kind,words=decoded
            if after_sequence is not None and not 0<((words[0]-after_sequence)&0xffffffff)<0x80000000:continue
            if kind=='C350' and words[4]==0x43505531 and words[5]==0x50415353 and words[7]==0:
                latest_cpu=words[0]
            if kind=='K138' and words[0]==latest_cpu:
                latest_state=performance(words)
            if kind=='E138' and latest_state and words[0]==latest_state['sequence']:
                return dict(state=latest_state,expression=expression(words))
    raise RuntimeError('No fresh matching C350/K138/E138 ready snapshot')


def main():
 p=argparse.ArgumentParser();p.add_argument('controls',type=Path);p.add_argument('--port',default=DEFAULT_PORT);a=p.parse_args()
 previous=json.loads(a.controls.read_text());out=BASE/'results'/datetime.now().strftime('controls_restored_%Y%m%d_%H%M%S_%f');out.mkdir();print(out,flush=True)
 port=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=1,exclusive=True);port.dtr=False;port.rts=False;port.port=a.port
 with port:
  end=time.monotonic()+2
  while time.monotonic()<end:port.read_until(b'\n',size=1024)
  initial=get_controls(port,15,out/'runtime.raw')
  wanted=previous['state'];expr=previous['expression']
  packets=[bytes([0xb0,80,['A','B','C'].index(wanted['mode'])]),bytes([0xc0,dict(flute=73,strings=40,trumpet=56,marimba=12,piano=0)[wanted['sound']]]),bytes([0xb0,82,['stereo','left','right','mute'].index(wanted['route'])]),bytes([0xb0,81,wanted['effects']]),bytes([0xb0,7,wanted['gain_q15']//256]),bytes([0xb0,11,127]),bytes([0xb0,1,expr['vibrato']]),bytes([0xb0,5,expr['glide']]),bytes([0xe0,(expr['bend']+8192)&127,(expr['bend']+8192)>>7])]
  payload=b''.join(packets);assert port.write(payload)==len(payload);port.flush()
  after=get_controls(port,8,out/'runtime.raw',after_sequence=initial['state']['sequence'])
  passed=all(after['state'][k]==wanted[k] for k in ['mode','sound','route','effects','gain_q15']) and all(after['expression'][k]==expr[k] for k in ['vibrato','glide','bend_index']) and after['state']['pc_input_errors']==0
  (out/'result.json').write_text(json.dumps(dict(passed=passed,initial=initial,after=after,source=str(a.controls.resolve()),transmitted_hex=[x.hex(' ') for x in packets]),indent=2)+'\n');assert passed
  print('controls and AE350 ready verified',flush=True)
if __name__=='__main__':main()
