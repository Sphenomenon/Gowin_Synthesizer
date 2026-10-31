#!/usr/bin/env python3
"""Exercise real selected-top recording wiring; unrelated providers are black boxes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
SOURCES=(
    'rtl/workstation/workstation_profile_r00_no_local_panel.sv',
    'rtl/workstation/workstation_recording_runtime.sv',
    'rtl/services/workstation_recording_ddr_service.sv',
    'rtl/services/workstation_recording_seal_bridge.sv',
    'rtl/audio/workstation_pcm_ddr_backend.sv',
    'rtl/audio/workstation_pcm_observation_bridge.sv',
    'rtl/memory/workstation_ble_raw_ddr_store.sv',
    'rtl/memory/workstation_recording_ddr_authority.sv',
    'rtl/memory/workstation_recording_ddr_owner_mux.sv',
    'rtl/memory/workstation_recording_ddr_native_bridge.sv',
    'rtl/memory/workstation_runtime_memory_guard.sv',
    'rtl/memory/workstation_sdp.sv','rtl/music/music_async_fifo.sv',
    'sim/memory/tb_ble_ddr_top_composition.sv',
)
DEPENDENCIES=('rtl/workstation/workstation_profile_r00_runtime.sv',
    'rtl/workstation/workstation_profile_no_cnn_runtime.sv',
    'rtl/workstation/workstation_profile_runtime.sv',
    'rtl/workstation/workstation_profile_hdmi.sv',
    'rtl/workstation/gw138k_push_workstation_top.v',
    'rtl/workstation/workstation_hdmi_display.sv','rtl/ddr_address_map.vh')

def sha(data):return hashlib.sha256(data).hexdigest()

def run(output):
    output.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(ROOT))
    from tools.workstation_baselines import load_baseline
    baseline=load_baseline(ROOT,'resource_rework_route0')
    counter=baseline.read_bytes('src/migration/gw138k_counter_cdc.sv')
    (output/'gw138k_counter_cdc.sv').write_bytes(counter)
    header=output/'src/memory/ddr_address_map.vh';header.parent.mkdir(parents=True)
    header.write_bytes((ROOT/'rtl/ddr_address_map.vh').read_bytes())
    names=(*SOURCES,*DEPENDENCIES,str(Path(__file__).resolve().relative_to(ROOT)))
    hashes={n:sha((ROOT/n).read_bytes()) for n in names}
    result=dict(schema=1,passed=False,source_sha256=hashes,baseline=baseline.evidence(),
        counter_sha256=sha(counter),scope='real selected top + recording runtime/service/CDC/backend + raw store + owner8 mux + boot authority',
        fixtures='BLE raw and CPU command owner ports; global DDR slot/native/response model; unrelated full-system modules ignored with Icarus -i',
        ble_business_protocol_tested=False,full_ddr_arbiter_tested=False,
        synthesis=False,pnr=False,physical_cdc_accepted=False,hardware_tested=False,cases={})
    try:
        header_text=header.read_text()
        def changed_macro(text,name,value):
            changed,count=re.subn(r'(?m)^(`define[ \t]+'+name+r'[ \t]+)[^\r\n]+',lambda m:m.group(1)+value,text)
            if count!=1:raise ValueError('allocation mutation anchor drift: '+name)
            return changed
        mutations={
            'bad_capacity_bytes':{'BLE_BYTES':"32'h0002_0000"},
            'bad_byte_native_units':{'BLE_APP_BASE':"29'h0c14_4008"},
            'truncated_final_bl8':{'BLE_APP_LAST':"29'h0c14_7ff7"},
            'overlap_cpu':{'BLE_BYTE_BASE':"32'h3050_0000",'BLE_BYTE_LAST':"32'h3050_ffff",
                           'BLE_APP_BASE':"29'h0c14_0000",'BLE_APP_LAST':"29'h0c14_3fff"},
            'outside_recording_pool':{'BLE_BYTE_BASE':"32'h3060_0000",'BLE_BYTE_LAST':"32'h3060_ffff",
                                     'BLE_APP_BASE':"29'h0c18_0000",'BLE_APP_LAST':"29'h0c18_3fff"},
        }
        jobs=[(0,'concurrent_windows_download_and_late_return',None),(1,'pre_ready_ledger_epoch_loss',None),
              (2,'root_release_waits_for_memory_clock',None)]
        jobs += [(0,name,changes) for name,changes in mutations.items()]
        for index,name,changes in jobs:
            stage=output/name;stage.mkdir()
            if changes:
                text=header_text
                for key,value in changes.items():text=changed_macro(text,'PRJ1_DDR_RECORDING_'+key,value)
                altered_header=stage/'rtl/ddr_address_map.vh';altered_header.parent.mkdir(parents=True)
                altered_header.write_text(text)
            argv=['iverilog','-g2012','-i','-s','tb_ble_ddr_top_composition',
                '-Ptb_ble_ddr_top_composition.CASE='+str(index),'-I',str(stage),'-I',str(ROOT),'-I',str(output),
                '-o',str(stage/'test.vvp'),*[str(ROOT/n) for n in SOURCES],str(output/'gw138k_counter_cdc.sv')]
            # Icarus searches its current directory before -I paths. Compile
            # from this case so allocation mutants cannot resolve the real
            # project's unmodified rtl/ddr_address_map.vh first.
            compile_run=subprocess.run(argv,cwd=stage,capture_output=True,text=True,timeout=30)
            compile_log=compile_run.stdout+compile_run.stderr;(stage/'compile.log').write_text(compile_log)
            if compile_run.returncode or compile_log.strip():raise ValueError('compile diagnostics: '+compile_log)
            execution=subprocess.run(['vvp',str(stage/'test.vvp')],capture_output=True,text=True,timeout=30)
            log=execution.stdout+execution.stderr;(stage/'run.log').write_text(log)
            match=re.search(r'PASS BLE_DDR_TOP_COMPOSITION (.*)',log)
            entry=dict(case=index,compile_argv=argv,compile_returncode=compile_run.returncode,
                run_returncode=execution.returncode,compile_log_sha256=sha(compile_log.encode()),log=log,log_sha256=sha(log.encode()))
            result['cases'][name]=entry
            if changes:
                expected='invalid top BLE DDR byte/native allocation, capacity or complete BL8 window'
                entry.update(mutation=changes,expected_failure=expected,rejected=execution.returncode!=0 and expected in log)
                if not entry['rejected']:raise ValueError(name+' allocation mutation escaped: '+log)
                print('PASS rejected '+name,flush=True)
            else:
                if execution.returncode or not match:raise ValueError(name+' failed: '+log)
                entry['metrics']={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',match.group(1))}
                print(match.group(0),flush=True)
        result['source_inputs_unchanged_during_run']=hashes=={n:sha((ROOT/n).read_bytes()) for n in names}
        if not result['source_inputs_unchanged_during_run']:raise ValueError('source changed during run')
        result['passed']=True
    finally:(output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output.resolve())
