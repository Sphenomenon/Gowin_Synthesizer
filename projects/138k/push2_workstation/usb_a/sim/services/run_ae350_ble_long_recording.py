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

def run(output,shared_memory=False,candidate=None):
    if shared_memory and candidate is None:raise ValueError('--shared-memory requires an immutable --candidate W output')
    if candidate is not None and not shared_memory:raise ValueError('--candidate requires --shared-memory')
    if candidate is not None and output.resolve().is_relative_to(candidate.resolve()):raise ValueError('output cannot be inside the candidate')
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
    if shared_memory:
        files += [Path(__file__).with_name('ae350_ble_shared_ddr_fixture.sv'),
            ROOT/'rtl/memory/workstation_recording_ddr_client_queues.sv',
            ROOT/'rtl/memory/workstation_recording_ddr_arbiter_pipeline.sv',
            ROOT/'rtl/music/basic_pitch_ddr_client_queues.sv',
            ROOT/'rtl/music/basic_pitch_ddr_arbiter_pipeline.sv']
    cfiles=[ROOT/'firmware/ae350'/n for n in ('business_mailbox.c','recording_service.c','ble_business_owner.c')]
    cpp=Path(__file__).with_name('ae350_ble_long_recording.cpp')
    tracked=[*files,*cfiles,cpp,Path(__file__),Path(__file__).with_name('ae350_ble_business_cosim.cpp'),
        *[ROOT/'firmware/ae350'/n for n in ('ble_business_owner.h','recording_service.h','business_mailbox.h','audio_services.h')],
        ROOT/'rtl/ddr_address_map.vh',ROOT/'rtl/ddr_address_map_guard.v']
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    binding=None
    if candidate is not None:
        from tools.workstation_task3_paired_audit import verify_prepared
        candidate=candidate.resolve()
        manifest=candidate/'integration_inputs.json'
        role,profile,_,_=verify_prepared(candidate,json.loads(manifest.read_text()))
        if role!='W':raise ValueError('expected an immutable paired W candidate')
        metadata_path=candidate/'ae350_firmware/build_metadata.json'
        metadata=json.loads(metadata_path.read_text())
        if metadata['recording_capacity_frames']!=CAPACITY:raise ValueError('actual firmware capacity mismatch')
        paired_sources={}
        for source in [*files,ROOT/'rtl/ddr_address_map.vh']:
            if source.is_relative_to(ROOT/'rtl'):
                relative=source.relative_to(ROOT)
                compiled=candidate/'workstation/Prj1'/relative
                if digest(source)!=digest(compiled):raise ValueError('compiled component differs: '+str(relative))
                paired_sources[str(relative)]=digest(source);tracked.append(compiled)
        firmware_sources={}
        for source in [*cfiles,*[ROOT/'firmware/ae350'/n for n in ('ble_business_owner.h','recording_service.h','business_mailbox.h','audio_services.h')]]:
            relative=str(source.relative_to(ROOT))
            if digest(source)!=metadata['input_sha256'][relative]:raise ValueError('compiled firmware source differs: '+relative)
            firmware_sources[relative]=digest(source)
        tracked.extend([manifest,candidate/'workstation_profile.json',metadata_path])
        binding=dict(candidate=str(candidate),candidate_identity=profile['candidate_identity'],
            immutable_prepared_closure_verified=True,paired_RTL_sha256=paired_sources,
            firmware_source_sha256=firmware_sources,
            scope='Same selected component bytes; host-compiled C owner and modeled controller. No complete W/AE350/HCI/CNN execution.')
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
    rtlflags=[]
    if shared_memory:
        cppflags+=['-DA138_TASK3_SHARED_MEMORY_TEST']
        rtlflags+=['+define+TASK3_SHARED_RECORD_DDR','-I'+str(ROOT)]
    build=['verilator','--cc','--exe','--build','-j','2','--timing','-Wno-fatal','--top-module','ae350_ble_business_cosim',
        '+define+WORKSTATION_SINGLE_BLE_RECORDING',*rtlflags,f'-GCAPACITY_FRAMES={CAPACITY}','-GFAST_CAPTURE=1',f'-GBASE_APP={BASE}',
        '--Mdir',output/'obj','-CFLAGS',' '.join(cppflags),'-LDFLAGS',' '.join(map(str,objects)),*files,cpp]
    execute(build,'compile',300)
    if 'UNOPTFLAT' in (output/'compile.log').read_text():raise RuntimeError('combinational-loop warning in fixture')
    text=execute([output/'obj/Vae350_ble_business_cosim'],'long-run',600)
    metrics=re.search(r'PASS long single recording frames=(\d+) bytes=(\d+) blocks=(\d+) checks=(\d+) crc=([0-9a-f]+) last_native=([0-9a-f]+)',text)
    if not metrics:raise RuntimeError('missing full actual recording/download result')
    dropped=None
    if shared_memory:
        negative=[*build];negative[negative.index('--Mdir')+1]=output/'obj-drop'
        negative.insert(1,'+define+TASK3_SHARED_DROP_PCM')
        execute(negative,'drop-compile',300)
        failure=execute([output/'obj-drop/Vae350_ble_business_cosim'],'drop-run',600,expect=1)
        if 'FAIL BLE GET exposes same full CPU object/format/capacity/CRC' not in failure:
            raise RuntimeError('missing source-drop object-integrity rejection')
        dropped=dict(frame_sequence=17000,rejected=True,
            reason='Independent source sequence advances while one PCM-valid pulse is suppressed; sealed CRC disagrees with the complete source image.')
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
    if shared_memory:
        shared=re.search(r'SHARED_DDR music_commands=(\d+) delay_commands=(\d+) recording_writes=(\d+) cycles=(\d+)',text)
        resumed=re.search(r'RESUMED long object offset=(\d+) old_transfer=(\d+) new_transfer=(\d+)',text)
        if not shared or not resumed:raise RuntimeError('missing actual shared-fabric/reconnect evidence')
        result.update(shared_production_queues_and_arbiter=True,
            competing_music_native_commands=int(shared[1]),competing_delay_native_commands=int(shared[2]),
            shared_recording_native_writes=int(shared[3]),memory_cycles=int(shared[4]),
            resumed_at_byte_offset=int(resumed[1]),old_transfer=int(resumed[2]),new_transfer=int(resumed[3]),
            competing_traffic_is_synthetic=True,CNN_inference=False,delay_DSP=False,
            controller_is_behavioral=True,BIST_tested=False,physical_deadline_verified=False)
        result['candidate_component_binding']=binding
        result['source_sequence_independent_of_recorder']=True
        result['dropped_PCM_negative_control']=dropped
    (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    if not result['passed']:raise RuntimeError('source drift during run')
    print(json.dumps({k:result[k] for k in ('passed','capacity_frames','downloaded_bytes','download_blocks','object_crc','last_native_beat')}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--shared-memory',action='store_true',help='production owner5/6/8 fabric, contention and reconnect')
    parser.add_argument('--candidate',type=Path,help='immutable paired W output for actual component hashes')
    args=parser.parse_args();run(args.output,args.shared_memory,args.candidate)
