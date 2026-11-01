#!/usr/bin/env python3
"""Real C/APB/parser/CRC/native DDR capacity test; no profile or hardware.

The fixture accelerates PCM admission to one frame/8 control clocks while
preserving the real20ns/14ns clock ratio and every frame/CRC/native beat. It
tests a 60-second *capacity*, not wall-clock audio quality or latency.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
CAPACITY=2880000
BASE=0x0c180000

def run(output):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(ROOT))
    from tools.workstation_baselines import load_baseline
    from tools.workstation_resource_timing import apb
    original=load_baseline(ROOT,'resource_rework_route0').read_bytes('src/migration/gw138k_apb_cdc.sv')
    cdc=output/'gw138k_apb_cdc.sv';cdc.write_text(apb(original.decode()))
    files=[Path(__file__).with_name('ae350_ble_business_cosim.sv'),cdc,
        *[ROOT/'rtl/bluetooth/cpu_owner'/n for n in ('ble_protocol_command.v','workstation_ble_record_data_engine.sv','workstation_ble_record_data_service.sv')],
        ROOT/'rtl/services/workstation_business_mailbox.sv',ROOT/'rtl/memory/workstation_ble_raw_ddr_store.sv',
        ROOT/'rtl/memory/workstation_recording_ddr_native_bridge.sv',ROOT/'rtl/memory/workstation_sdp.sv',ROOT/'rtl/music/music_async_fifo.sv']
    cfiles=[ROOT/'firmware/ae350'/n for n in ('business_mailbox.c','recording_service.c','ble_business_owner.c')]
    cpp=Path(__file__).with_name('ae350_ble_long_recording.cpp')
    tracked=[*files,*cfiles,cpp,Path(__file__),Path(__file__).with_name('ae350_ble_business_cosim.cpp'),
        *[ROOT/'firmware/ae350'/n for n in ('ble_business_owner.h','recording_service.h','business_mailbox.h','audio_services.h')],
        ROOT/'rtl/ddr_address_map.vh',ROOT/'rtl/ddr_address_map_guard.v']
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before={str(p):digest(p) for p in tracked};commands=[]
    def execute(argv,name,timeout=180,expect=0):
        p=subprocess.run(list(map(str,argv)),capture_output=True,text=True,timeout=timeout)
        log=output/(name+'.log');log.write_text(p.stdout+p.stderr)
        commands.append(dict(argv=list(map(str,argv)),exit_code=p.returncode,log=str(log),log_sha256=digest(log)))
        if (p.returncode!=0)!=(expect!=0):raise RuntimeError(name+' unexpected exit: '+str(p.returncode)+'; '+str(log))
        return p.stdout+p.stderr
    include=ROOT/'firmware/ae350'
    flags=['-DA138_BLE_BUSINESS','-DA138_SINGLE_BLE_RECORDING',f'-DA138_BLE_RECORD_CAPACITY_FRAMES={CAPACITY}u']
    cbase=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(include)]
    objects=[]
    for p in cfiles:
        target=output/(p.stem+'.o');objects.append(target)
        execute([*cbase,*flags,'-c',p,'-o',target],p.stem)
    cppflags=[*flags,'-DA138_TASK3_LONG_RECORDING_TEST',f'-DTASK3_RECORD_BASE={BASE}u','-I'+str(include)]
    execute(['verilator','--cc','--exe','--build','-j','2','--timing','-Wno-fatal','--top-module','ae350_ble_business_cosim',
        '+define+WORKSTATION_SINGLE_BLE_RECORDING',f'-GCAPACITY_FRAMES={CAPACITY}','-GFAST_CAPTURE=1',f'-GBASE_APP={BASE}',
        '--Mdir',output/'obj','-CFLAGS',' '.join(cppflags),'-LDFLAGS',' '.join(map(str,objects)),*files,cpp], 'compile',300)
    text=execute([output/'obj/Vae350_ble_business_cosim'],'long-run',600)
    metrics=re.search(r'PASS long single recording frames=(\d+) bytes=(\d+) blocks=(\d+) checks=(\d+) crc=([0-9a-f]+) last_native=([0-9a-f]+)',text)
    if not metrics:raise RuntimeError('missing full actual recording/download result')
    # Same real compiled RTL; only C configuration differs. It must fail before
    # allocating an object, rather than advertising unsupported physical bytes.
    mismatch=output/'mismatched_owner.o'
    execute([*cbase,*flags[:-1],f'-DA138_BLE_RECORD_CAPACITY_FRAMES={CAPACITY+1}u','-c',cfiles[-1],'-o',mismatch],'mismatch-owner')
    log=(output/'compile.log').read_text()
    link=next(line for line in log.splitlines() if line.startswith('c++ ') and line.rstrip().endswith(' -o Vae350_ble_business_cosim'))
    argv=shlex.split(link);argv=[str(mismatch) if arg==str(objects[-1]) else arg for arg in argv]
    argv[argv.index('-o')+1]=str(output/'capacity-mismatch')
    # The generated library/object arguments in the tool's link line are
    # relative to its Mdir. Resolve execution directory without shell quoting.
    p=subprocess.run(argv,cwd=output/'obj',capture_output=True,text=True,timeout=60)
    (output/'mismatch-link.log').write_text(p.stdout+p.stderr)
    if p.returncode:raise RuntimeError('mismatch link failed')
    mismatch_result=execute([output/'capacity-mismatch','expect-mismatch'],'mismatch-run',60)
    if 'PASS capacity mismatch fails before object allocation' not in mismatch_result:raise RuntimeError('capacity mismatch escaped')
    # Compile-time C and elaboration-time map boundaries must fail closed.
    probe=output/'capacity_probe.c';probe.write_text('#include "ble_business_owner.h"\nint main(void){return 0;}\n')
    for value in (0,0x10000001,0xffffffff):
        execute([*cbase,f'-DA138_BLE_RECORD_CAPACITY_FRAMES={value}u','-c',probe,'-o',output/'bad.o'],'bad-c-'+str(value),expect=1)
    map_text=(ROOT/'rtl/ddr_address_map.vh').read_text();guard=ROOT/'rtl/ddr_address_map_guard.v'
    map_cases={'valid':None,
        'overlap_original_recording':("POOL_BYTE_BASE 32'h3060_0000","POOL_BYTE_BASE 32'h3050_0000"),
        'padding_exposed':("BYTE_LAST      32'h310f_c7ff","BYTE_LAST      32'h310f_ffff"),
        'wrong_native_word':("APP_LAST       29'h0c43_f1ff","APP_LAST       29'h0c43_f207"),
        'wrong_last_BL8':("LAST_BEAT      29'h0c43_f1f8","LAST_BEAT      29'h0c43_f1f0")}
    for name,change in map_cases.items():
        stage=output/('map-'+name);(stage/'src/memory').mkdir(parents=True)
        selected=map_text
        if change:
            if selected.count(change[0])!=1:raise RuntimeError('map mutation anchor drift')
            selected=selected.replace(*change)
        (stage/'src/memory/ddr_address_map.vh').write_text(selected)
        execute(['iverilog','-g2012','-s','ddr_address_map_guard','-I',stage,'-o',stage/'guard.vvp',guard],
            'map-'+name,expect=int(change is not None))
    after={str(p):digest(p) for p in tracked}
    result=dict(schema=1,passed=before==after,input_sha256=before,inputs_unchanged=before==after,
        scope='Maintained C/APB/parser/physical CRC/raw DDR components; no new W profile selected.',
        capacity_frames=CAPACITY,capacity_bytes=CAPACITY*4,format_id=1,rate_hz=48000,
        measured_frames=int(metrics[1]),downloaded_bytes=int(metrics[2]),download_blocks=int(metrics[3]),checks=int(metrics[4]),
        object_crc=metrics[5],last_native_beat='0x'+metrics[6],native_word_base=hex(BASE),
        capture_cadence='Accelerated fixture: one actual PCM frame per8 control clocks; counts represent60s at48000Hz, not measured wall-clock audio.',
        control_period_ns=20,memory_period_ns=14,full_download_checked=True,stop_partial_native_wait_checked=True,
        capacity_mismatch_fenced=True,C_invalid_capacity_controls=3,map_cases=list(map_cases),commands=commands,
        synthesis=False,pnr=False,profile_selected=False,hardware_tested=False,sram_programmed=False,flash_written=False,
        dual_rate_recording=False)
    (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    if not result['passed']:raise RuntimeError('source drift during run')
    print(json.dumps({k:result[k] for k in ('passed','capacity_frames','downloaded_bytes','download_blocks','object_crc','last_native_beat')}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
