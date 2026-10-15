#!/usr/bin/env python3
"""Independently exercise pad listener and complete TW1 UART/CRC transport."""
import argparse
import binascii
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import wire_trace
ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,default=ROOT/'rtl')
    parser.add_argument('--power-adc',action='store_true')
    parser.add_argument('--wire-device',choices=('U1','U2'),default='U1')
    parser.add_argument('--safe-gpio',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();source=a.build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    if (source/'build.json').exists():
        meta=json.loads((source/'build.json').read_text())
        for name,digest in meta['inputs'].items():assert hashlib.sha256((source/name).read_bytes()).hexdigest()==digest,name
    subprocess.run(['iverilog','-g2012','-s','test_i2c_listener','-o',str(out/'listener'),str(source/'tb_i2c_listener.sv'),str(ROOT/'tests/tb_i2c_listener.sv')],check=True)
    unit=subprocess.run(['vvp',str(out/'listener')],capture_output=True,text=True,timeout=20)
    (out/'listener.log').write_text(unit.stdout+unit.stderr)
    assert unit.returncode==0,unit.stdout+unit.stderr
    print(unit.stdout,flush=True)
    def run(words):
        p=out/str(words);p.mkdir(exist_ok=True)
        command=['iverilog','-g2012','-s','tb_wire_trace','-P',f'tb_wire_trace.RAW_WORDS={words}','-P',f'tb_wire_trace.SAFE_GPIO={int(a.safe_gpio)}','-P',f'tb_wire_trace.POWER_ADC={int(a.power_adc)}','-P',f'tb_wire_trace.PROBE_SLIDER={int(a.wire_device=="U2")}','-o',str(p/'run')]+[str(x) for x in source.iterdir() if x.suffix in ('.sv','.v') and not(a.power_adc and x.name=='touch_power_adc.v')]+([str(ROOT/'tests/power_adc_model.sv')] if a.power_adc else [])+[str(ROOT/'tests/i2c_device_model.sv'),str(ROOT/'tests/tb_wire_trace.sv')]
        subprocess.run(command,check=True,capture_output=True,text=True)
        result=subprocess.run(['vvp',str(p/'run')],cwd=p,capture_output=True,text=True,timeout=120)
        (p/'run.log').write_text(result.stdout+result.stderr)
        assert result.returncode==0,result.stdout+result.stderr
        records=[wire_trace.decode(x,1000000) for x in (p/'wire_uart.txt').read_bytes().splitlines()]
        assert all(x['device']==a.wire_device for x in records),'wire-device tag mismatch'
        assert all(not x['faults'] for x in records),[(x['sequence'],x['faults']) for x in records if x['faults']]
        assert {r['length'] for r in records}>={7,58,(2 if words else 64)}
        assert any(r['pointer_master']==100 and r['master'][:2]==[196,9] for r in records),'bad raw value 2500 must remain visible'
        assert any(r['pointer_master']==0 and r['master'][3:5]==[255,255] for r in records),'all-key status must remain visible'
        summary=wire_trace.summarize(records)
        assert set(summary['words'])==set(range(100,164,2)), 'all 32 raw words must be covered'
        if a.power_adc:
            assert summary['power_adc']['valid_records']>30
            assert summary['power_adc']['maximum_count']>100
            assert summary['power_adc']['minimum_v']==820/256
            assert summary['power_adc']['maximum_v']==870/256
            assert summary['power_adc']['maximum_timeouts']==0
        summary['pass']=True
        (p/'verification.json').write_text(json.dumps(summary,indent=2)+'\n')
        return dict(raw_words=words,frames=len(records),passed=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,(0,1)))
    line=(out/'1/wire_uart.txt').read_bytes().splitlines()[-1]
    fields=line.split();b=bytearray.fromhex(fields[1].decode());b[22]^=1
    bad=fields[0]+b' '+b.hex().encode()+b' '+f'{binascii.crc_hqx(b,0xffff):04X}'.encode()
    assert 'master-wire-mismatch' in wire_trace.decode(bad,1000000)['faults']
    # A failed read address has no valid payload; do not compare stale RX data.
    b[7]=1;b[9]=1
    b[86:151]=bytes([27])+bytes(64);b[151:216]=bytes([27])+bytes(64)
    b[216:225]=(1).to_bytes(9,'little')
    nack=fields[0]+b' '+b.hex().encode()+b' '+f'{binascii.crc_hqx(b,0xffff):04X}'.encode()
    assert wire_trace.decode(nack,1000000)['faults']==['master-error']
    report=dict(passed=True,wire_device=a.wire_device,power_adc=a.power_adc,safe_gpio=a.safe_gpio,source=str(source),profiles=results,
                checks=['independent manually driven 65-byte pad bitstream','all ACK/NACK bits','STOP/START gap',
                        'overflow guard',f'{249 if a.power_adc else 225}-byte hex UART and CRC','word and full-block reads',
                        'bad raw values and all-key status remain visible','CRC-valid injected master/wire mismatch is detected'])
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
