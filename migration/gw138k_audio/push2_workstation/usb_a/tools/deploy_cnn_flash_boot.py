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
import sys
import time
from build_cnn_flash_image import validate_image,gowin_data_fs
from audit_clk50_timing import audit as audit_clk50
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1'
BASE_SHA='7f96a42b0adf4e87863089d610a454e570876a78c7917d892949116918015444'
B138=re.compile(rb'B138 ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8})')

def configured_clean(status):
    # UG704 table 5-1: bit13 DONE; bits0..3 config errors; bit4
    # Auto_Boot_2nd_Fail; bit9 Auto_Boot_1st_Fail. SRAM download can
    # report DONE with these failures still latched: not Flash-boot proof.
    return bool(status & (1<<13)) and not (status & 0x21f)

def audit_previous_positive_clocks(build):
    # Parse the routed summary, not nominal PLL settings. Do not silently
    # accept a new CPU/video failure merely because clk50 passed.
    def clocks(directory):
        text=(directory/'Prj1/impl/pnr/Prj1.tr').read_text()
        matches=list(re.finditer(r'2\.3 Max Frequency Summary(.*?)2\.4 Total Negative Slack Summary',text,re.S))
        assert matches,'missing routed frequency summary'
        values={n:(float(required),float(actual)) for n,required,actual in re.findall(
            r'^\s*\d+\s+(\w+)\s+([\d.]+)\(MHz\)\s+([\d.]+)\(MHz\)',matches[-1][1],re.M)}
        assert values,'empty routed clock summary'
        return values
    baseline=clocks(BASE);candidate=clocks(build)
    previous={name:value for name,value in baseline.items() if value[1]>=value[0]}
    failures=[]
    for name,(required,_) in previous.items():
        if name not in candidate or candidate[name][0]!=required or candidate[name][1]<required:
            failures.append(name)
    return dict(passed=not failures,failed_clocks=failures,baseline=str(BASE),
                previous_positive_clocks=previous,candidate_clocks=candidate)

def verify_debugger_identity(port,location):
    assert '2025030317' in port and Path(port).exists(),'wrong/missing debugger UART'
    assert location==53 and Path('/sys/bus/usb/devices/3-5/serial').read_text().strip()=='2025030317','debugger USB location changed'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('build',type=Path)
    ap.add_argument('--program',action='store_true')
    ap.add_argument('--exercise-live',action='store_true',help='after three Flash boots test live scope under the same lock; failure rolls back full85 and its model')
    ap.add_argument('--allow-clk50-open','--allow-clock-regression',dest='allow_clk50_open',action='store_true',help='explicit temporary diagnostic only; bypass clk50/previous-positive-clock gate and never promote')
    ap.add_argument('--expected-code',default='0x00000085')
    ap.add_argument('--location',type=int,default=53)
    ap.add_argument('--port',default='/dev/serial/by-id/usb-SIPEED_USB_Debugger_2025030317-if01-port0')
    ap.add_argument('--output',type=Path)
    args=ap.parse_args()
    build=args.build.resolve();fs=build/'Prj1/impl/pnr/Prj1.fs';model=build/'cnn_model.bin'
    bundle=json.loads((build/'flash_bundle.json').read_text())
    build_meta=json.loads((build/'build_metadata.json').read_text())
    if args.program and build_meta.get('ddr_initial_aux_settle_ms') and not build_meta.get('startup_panic_aligns_delay_history'):
        ap.error('deferred DDR startup lacks cold P10 history alignment; use a fresh aligned candidate')
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
    previous_clocks=audit_previous_positive_clocks(build)
    if args.program and (not clk50['clk50_closed'] or not previous_clocks['passed']) and not args.allow_clk50_open:
        ap.error('routed clock timing regressed/open: '+','.join(previous_clocks['failed_clocks'])+'; --allow-clock-regression is only for a temporary boot diagnostic')
    programmer=Path.home()/'.local/opt/gowin-1.9.12.03/Programmer/bin/programmer_cli'
    common=[str(programmer),'--device','GW5AST-138C','--cable-index','5','--location',str(args.location),'--frequency','0.9MHz']
    # Native Arora V C-Bin operation needs BOTH: --fsFile satisfies the CLI
    # data-file check; --mcuFile supplies the raw bytes. Either one alone
    # produced no data. Both were programmed and cross-verified via text .fs.
    model_args=['--operation_index','56','--fsFile',str(model),
                '--mcuFile',str(model),'--spiaddr','0x600000']
    fs_args=['--operation_index','54','--fsFile',str(fs),'--spiaddr','0x000000']
    print(json.dumps(dict(build=str(build),target_code=code,model_bytes=model.stat().st_size,
        program_model=common+model_args,program_bitstream=common+fs_args,programming_requested=args.program,previous_positive_clock_audit=previous_clocks),indent=2),flush=True)
    if not args.program:return
    import serial
    output=(args.output or build/'flash_deploy').resolve();output.mkdir(parents=True,exist_ok=False)
    result=dict(started_at=datetime.now().astimezone().isoformat(),build=str(build),user_code=code,
                commands=[],boots=[],passed=False,uart_model_upload_used=False,sram_download_used=False,sram_erased_before_each_boot=True,
                physical_power_cycle_tested=False,board_serial='2025030317',uart_hardware_drain_seconds=2,
                clk50_closed=clk50['clk50_closed'],previous_positive_clock_audit=previous_clocks,diagnostic_timing_override=args.allow_clk50_open,
                model_transport=build_meta.get('transport','direct'),live_smoke_requested=args.exercise_live,live_smoke_passed=False,startup_panic_aligns_delay_history=build_meta.get('startup_panic_aligns_delay_history',False))
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
        verify_debugger_identity(args.port,args.location)
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
                    run('erase_sram_'+str(index),['--operation_index','24'])
                    port.reset_input_buffer()
                    run('reprogram_'+str(index),['--operation_index','1'])
                    # Native Flash reload can outlast the command itself.
                    # Do not interpret UART/DDR telemetry until the exact new
                    # UserCode and the board's normal configured status appear.
                    code_deadline=time.monotonic()+180;attempt=0
                    while True:
                        text=run('configuration_code_'+str(index)+'_'+str(attempt),['--operation_index','0'])
                        codes=re.findall(r'User\s*Code(?:\s+is)?\s*[:=]\s*(0x[0-9a-fA-F]+)',text,re.I)
                        statuses=re.findall(r'Status\s*Code(?:\s+is)?\s*[:=]\s*(0x[0-9a-fA-F]+)',text,re.I)
                        if codes and int(codes[-1],16)==int(code,16) and statuses and configured_clean(int(statuses[-1],16)):break
                        assert time.monotonic()<code_deadline,'Flash configuration did not reach target UserCode/normal status'
                        attempt+=1;time.sleep(2)
                    port.reset_input_buffer()
                    # FTDI can retain hardware packets after a driver purge.
                    # Drain real traffic before accepting this boot's source/E.
                    drain_deadline=time.monotonic()+2
                    while time.monotonic()<drain_deadline:port.readline()
                    port.reset_input_buffer()
                    deadline=time.monotonic()+45;lines=[];observed=[]
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
                    if not ok:run('failed_boot_code_'+str(index),['--operation_index','0'])
                    assert ok,'Flash->DDR CRC/auto boot not proven; UART fallback is not a pass'
            if args.exercise_live:
                smoke_path=output/'live_smoke.json'
                smoke=subprocess.run([sys.executable,str(ROOT/'tools/capture_scope_smoke.py'),
                    '--port',args.port,'--seconds','8','--exercise-live','--output',str(smoke_path)],
                    capture_output=True,text=True,timeout=90)
                (output/'live_smoke.log').write_text(smoke.stdout+smoke.stderr)
                assert smoke.returncode==0 and json.loads(smoke_path.read_text())['passed'],'live workstation smoke failed'
                if build_meta.get('startup_panic_aligns_delay_history'):
                    assert json.loads(smoke_path.read_text())['startup_panic_epoch']>=1,'cold startup Panic not observed before host controls'
                result['live_smoke_passed']=True;save()
            result['passed']=True
        except Exception as exc:
            result['error']=str(exc);save()
            if wrote:
                try:
                    run('rollback_full85',['--operation_index','54','--fsFile',str(oldfs),'--spiaddr','0x000000'],r'Program and Verify Flash successfully')
                    run('rollback_erase_sram',['--operation_index','24'])
                    run('rollback_reprogram',['--operation_index','1'])
                    rollback_deadline=time.monotonic()+180;attempt=0
                    while True:
                        text=run('rollback_code_'+str(attempt),['--operation_index','0'])
                        codes=re.findall(r'User\s*Code(?:\s+is)?\s*[:=]\s*(0x[0-9a-fA-F]+)',text,re.I)
                        statuses=re.findall(r'Status\s*Code(?:\s+is)?\s*[:=]\s*(0x[0-9a-fA-F]+)',text,re.I)
                        if codes and int(codes[-1],16)==0x85 and statuses and configured_clean(int(statuses[-1],16)):break
                        assert time.monotonic()<rollback_deadline,'rollback full85 did not configure cleanly'
                        attempt+=1;time.sleep(2)
                    result['rollback_bitstream_restored']=True;save()
                    # Full85 has a volatile UART model, so bitstream recovery
                    # alone would leave the prior workstation without CNN.
                    recovery=subprocess.run([sys.executable,str(ROOT/'tools/upload_cnn_ddr_uart.py'),
                        '--port',args.port,'--timeout','90'],capture_output=True,text=True,timeout=120)
                    recovery_log=recovery.stdout+recovery.stderr
                    (output/'rollback_model_uart.log').write_text(recovery_log)
                    assert recovery.returncode==0 and 'model_status=E' in recovery_log,'rollback UART model CRC failed'
                    result['rollback_uart_model_restored']=True;save()
                    smoke_path=output/'rollback_smoke.json'
                    smoke=subprocess.run([sys.executable,str(ROOT/'tools/capture_scope_smoke.py'),
                        '--port',args.port,'--seconds','4','--output',str(smoke_path)],
                        capture_output=True,text=True,timeout=60)
                    (output/'rollback_smoke.log').write_text(smoke.stdout+smoke.stderr)
                    assert smoke.returncode==0 and json.loads(smoke_path.read_text())['passed'],'rollback workstation smoke failed'
                    result['rollback_workstation_smoke_passed']=True
                except Exception as restore:
                    result['rollback_error']=str(restore)
            raise
        finally:
            result['finished_at']=datetime.now().astimezone().isoformat();save()
    print('PASS: three Flash boots, source=Flash, model_status=E; '+str(output),flush=True)
if __name__=='__main__':main()
