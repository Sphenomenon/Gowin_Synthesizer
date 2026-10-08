#!/usr/bin/env python3
"""Program/verify CNN model and workstation Flash partitions, prove auto boot.

Default is a read-only artifact check and command preview. --program performs
hardware I/O under the existing board lock. No SRAM download and no UART model
upload are used to establish success. Records are emitted but never silently
promoted to LATEST_WORKSTATION. A mismatched board UserCode aborts before writes.
"""
import argparse
from datetime import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from build_cnn_flash_image import validate_image,gowin_data_fs
from audit_clk50_timing import audit as audit_clk50
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1'
BASE_SHA='7f96a42b0adf4e87863089d610a454e570876a78c7917d892949116918015444'
B138=re.compile(rb'B138 ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8})')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('build',type=Path)
    ap.add_argument('--program',action='store_true')
    ap.add_argument('--allow-clk50-open',action='store_true',help='explicit temporary diagnostic only; do not promote a clk50 timing regression')
    ap.add_argument('--expected-code',default='0x00000085')
    ap.add_argument('--location',type=int,default=53)
    ap.add_argument('--port',default='/dev/serial/by-id/usb-SIPEED_USB_Debugger_2025030317-if01-port0')
    ap.add_argument('--output',type=Path)
    args=ap.parse_args()
    build=args.build.resolve();fs=build/'Prj1/impl/pnr/Prj1.fs';model=build/'cnn_model.bin'
    bundle=json.loads((build/'flash_bundle.json').read_text())
    inputs=json.loads((build/'workstation_inputs.json').read_text())
    assert all(sha(build/'Prj1'/p)==h for p,h in inputs.items()),'candidate source drift'
    assert sha(fs)==bundle['bitstream_fs_sha256'] and sha(model)==bundle['model_image_sha256'],'artifact drift'
    assert sha(build/'workstation_with_cnn.bin')==bundle['boot_image_sha256'],'boot bundle drift'
    assert bundle['flash_model_base']==0x600000 and bundle['payload_crc32']=='AF01A61B'
    validate_image(model.read_bytes())
    oldfs=BASE/'Prj1/impl/pnr/Prj1.fs'
    assert sha(oldfs)==BASE_SHA,'rollback artifact drift'
    code=bundle['user_code'].lower()
    assert re.search(r'//UserCode: (0x[0-9A-Fa-f]{8})',fs.read_text()[:1000])[1].lower()==code
    clk50=audit_clk50(build)
    if args.program and not clk50['clk50_closed'] and not args.allow_clk50_open:
        ap.error('clk50 timing regressed/open; use a closed candidate, or --allow-clk50-open only for a temporary boot diagnostic')
    programmer=Path.home()/'.local/opt/gowin-1.9.12.03/Programmer/bin/programmer_cli'
    common=[str(programmer),'--device','GW5AST-138C','--cable-index','5','--location',str(args.location),'--frequency','0.9MHz']
    # Native Arora V C-Bin operation needs BOTH: --fsFile satisfies the CLI
    # data-file check; --mcuFile supplies the raw bytes. Either one alone
    # produced no data. Both were programmed and cross-verified via text .fs.
    model_args=['--operation_index','56','--fsFile',str(model),
                '--mcuFile',str(model),'--spiaddr','0x600000']
    fs_args=['--operation_index','54','--fsFile',str(fs),'--spiaddr','0x000000']
    print(json.dumps(dict(build=str(build),target_code=code,model_bytes=model.stat().st_size,
        program_model=common+model_args,program_bitstream=common+fs_args,programming_requested=args.program),indent=2),flush=True)
    if not args.program:return
    import serial
    output=(args.output or build/'flash_deploy').resolve();output.mkdir(parents=True,exist_ok=False)
    result=dict(started_at=datetime.now().astimezone().isoformat(),build=str(build),user_code=code,
                commands=[],boots=[],passed=False,uart_model_upload_used=False,sram_download_used=False,
                physical_power_cycle_tested=False,board_serial='2025030317',
                clk50_closed=clk50['clk50_closed'],diagnostic_timing_override=args.allow_clk50_open)
    def save():(output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    def run(label,extra,require=None):
        print(label,flush=True)
        r=subprocess.run(common+extra,capture_output=True,text=True,timeout=360)
        text=r.stdout+r.stderr;(output/(label+'.log')).write_text(text)
        entry=dict(label=label,args=common+extra,exit_code=r.returncode,log=str(output/(label+'.log')))
        result['commands'].append(entry);save()
        if r.returncode or require and not re.search(require,text,re.I):
            raise RuntimeError(label+' failed: '+text[-2000:])
        return text
    lock=Path('/tmp/gw138k_2025030317.lock')
    wrote=False
    with lock.open('a+') as lf:
        fcntl.flock(lf.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        # Verify the by-id UART belongs to the intended debugger before JTAG I/O.
        assert '2025030317' in args.port and Path(args.port).exists(),'wrong/missing debugger UART'
        assert args.location==53 and Path('/sys/bus/usb/devices/3-5/serial').read_text().strip()=='2025030317','debugger USB location changed'
        text=run('before_code',['--operation_index','0'])
        codes=re.findall(r'User\s*Code(?:\s+is)?\s*[:=]\s*(0x[0-9a-fA-F]+)',text,re.I)
        assert codes and int(codes[-1],16)==int(args.expected_code,16),'board version changed; no write allowed'
        try:
            text=run('flash_id',['--operation_index','51'])
            assert re.search(r'(?:0x)?0[Bb]4018',text),'unexpected Flash capacity/ID'
            wrote=True
            run('program_model',model_args,r'Program and Verify Flash successfully')
            transport=output/'cnn_model.data.fs';transport.write_text(gowin_data_fs(model.read_bytes()))
            run('verify_model_bytes',['--operation_index','66','--fsFile',str(transport),'--spiaddr','0x600000'],r'Verify Flash successfully')
            # Prove raw model programming did not erase address-zero configuration.
            run('verify_preserved_full85',['--operation_index','66','--fsFile',str(oldfs),'--spiaddr','0x000000'],r'Verify Flash successfully')
            run('program_workstation',fs_args,r'Program and Verify Flash successfully')
            for index in range(3):
                # UART is opened for receive only; no write()/model upload.
                with serial.Serial(args.port,115200,timeout=.2) as port:
                    port.reset_input_buffer()
                    run('reprogram_'+str(index),['--operation_index','1'])
                    deadline=time.monotonic()+15;lines=[];observed=[]
                    while time.monotonic()<deadline:
                        line=port.readline();lines.append(line.decode(errors='replace'))
                        m=B138.search(line)
                        if not m:continue
                        sd=int(m.group(4),16)
                        observed.append(dict(status=(sd>>2)&15,source=(sd>>8)&3,line=m.group(0).decode()))
                        if len([o for o in observed if o['status']==14 and o['source']==1])>=3:break
                    (output/f'boot_{index}_uart.log').write_text(''.join(lines))
                    ok=len([o for o in observed if o['status']==14 and o['source']==1])>=3
                    result['boots'].append(dict(index=index,passed=ok,model_observations=observed));save()
                    assert ok,'Flash->DDR CRC/auto boot not proven; UART fallback is not a pass'
                text=run('after_code_'+str(index),['--operation_index','0'])
                codes=re.findall(r'User\s*Code(?:\s+is)?\s*[:=]\s*(0x[0-9a-fA-F]+)',text,re.I)
                assert codes and int(codes[-1],16)==int(code,16),'wrong post-Flash UserCode'
            result['passed']=True
        except Exception as exc:
            result['error']=str(exc);save()
            if wrote:
                try:
                    run('rollback_full85',['--operation_index','54','--fsFile',str(oldfs),'--spiaddr','0x000000'],r'Program and Verify Flash successfully')
                    run('rollback_reprogram',['--operation_index','1'])
                    result['rollback_bitstream_restored']=True
                except Exception as restore:
                    result['rollback_error']=str(restore)
            raise
        finally:
            result['finished_at']=datetime.now().astimezone().isoformat();save()
    print('PASS: three Flash boots, source=Flash, model_status=E; '+str(output),flush=True)
if __name__=='__main__':main()
