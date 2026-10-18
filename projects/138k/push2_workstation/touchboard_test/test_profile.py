#!/usr/bin/env python3
"""Test the exact staged RTL of a profile, including every raw UART channel."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import monitor

ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();build=args.build.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    meta=json.loads((build/'build.json').read_text());profile=meta.get('profile',{})
    for name,digest in meta['inputs'].items():
        assert hashlib.sha256((build/name).read_bytes()).hexdigest()==digest,name
    burst=profile.get('burst',2);mask=profile.get('key_mask',0xffff)
    enabled=lambda k:burst if mask & (1<<k) else 0
    text=(ROOT/'tests/tb_touchboard.sv').read_text()
    old='u1.mem[54]!=1 || u1.mem[69]!=1 || u2.mem[61]!=1'
    assert old in text
    text=text.replace(old,f'u1.mem[54]!={enabled(0)} || u1.mem[69]!={enabled(15)} || u2.mem[61]!={enabled(7)}')
    # At accelerated 1MHz model clock, budget one polling period plus the
    # worst 32x(pointer+word) sweep, if enabled, plus rounding/STOP overhead.
    poll=profile.get('poll_ms',16)
    limit=(poll+140 if profile.get('raw_words') else poll+40)*10000
    text=text.replace('$time-touch_started>400000',f'$time-touch_started>{limit}')
    text=text.replace('repeat(12000000)','repeat(24000000)')
    (out/'tb_touchboard.sv').write_text(text)
    subprocess.run(['iverilog','-g2012','-s','tb_touchboard','-o',str(out/'run')]+
                   [str(p) for p in sorted(build.glob('*.sv'))]+[str(build/'uart_tx.v'),
                   str(ROOT/'tests/i2c_device_model.sv'),str(out/'tb_touchboard.sv')],check=True)
    r=subprocess.run(['vvp',str(out/'run')],cwd=out,text=True,capture_output=True,timeout=100)
    (out/'run.log').write_text(r.stdout+r.stderr)
    print(r.stdout,r.stderr,flush=True)
    if r.returncode:raise SystemExit(r.returncode)
    lines=(out/'uart.txt').read_bytes().splitlines()
    frames=[]
    for line in lines:
        if line.startswith(b'TB2 ') and len(line.strip())==113:frames.append(monitor.decode(line))
    assert frames and any(f['key_device']['keys']==0x8005 for f in frames)
    channels=[set(),set()]
    for f in frames:
        for bit,name in enumerate(('key_device','slider_device')):
            d=f[name]
            if d['raw_valid'] and monitor.ready(d):
                k=d['diagnostic_channel'];channels[bit].add(k)
                assert d['signals'][k]==1000-k,(name,k,d['signals'][k])
                assert d['references'][k]==1000,(name,k,d['references'][k])
    assert all(c==set(range(16)) for c in channels),channels
    latency=re.search(r'STATUS_LATENCY_MODEL_NS=(\d+)',r.stdout)
    assert latency, 'missing latency observation'
    latency_ms=int(latency[1])/10000
    if not profile.get('raw_words') and not profile.get('audit_config'):
        assert latency_ms <= poll+12, ('status latency',latency_ms)
    report=dict(passed=True,build=str(build),profile=profile,uart_frames=len(frames),
                model_injected_touch_status_latency_ms=latency_ms,
                checks=['exact staged RTL inputs hash','all 32 raw signal/reference channels',
                        'all complete UART frames have valid hex/CRC','multi-key and slider status',
                        'identity/configuration guards','disconnect/reconnect and alternate address',
                        'sleep write/readback diagnostic command']+(['runtime fixed-config corruption detection and recovery'] if profile.get('audit_config') else []))
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
