#!/usr/bin/env python3
"""Exercise real W native quarantine and synchronized recording-source failure."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'sim/music'))
from run_bp_config_ab import MUSIC_SOURCES


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output):
    output.mkdir(parents=True,exist_ok=False)
    header=output/'include/src/memory/ddr_address_map.vh'
    header.parent.mkdir(parents=True)
    header.write_bytes((ROOT/'rtl/ddr_address_map.vh').read_bytes())
    music=['basic_pitch_nn_ddr.sv',*(n for n in MUSIC_SOURCES if n!='basic_pitch_nn_ddr.sv'),
        'basic_pitch_workstation_link.sv','basic_pitch_link_uart.sv','basic_pitch_ddr16_port.sv',
        'basic_pitch_ddr_command_buffer.sv','music_async_fifo.sv','workstation_cnn_ddr_broker.sv',
        'workstation_cnn_task_service.sv','basic_pitch_ddr_client_queues.sv',
        'basic_pitch_ddr_arbiter_pipeline.sv','workstation_task3_cnn_stream_w.sv']
    memory=['workstation_sdp.sv','workstation_ddr_bist.v','workstation_recording_ddr_client_queues.sv',
        'workstation_recording_ddr_arbiter_pipeline.sv','workstation_recording_ddr_native_bridge.sv',
        'workstation_media_memory.sv','workstation_ble_raw_ddr_store.sv']
    bench=ROOT/'sim/memory/tb_task3_w_record_fault_cdc.sv'
    board=ROOT/'rtl/workstation/workstation_task3_w_paired_board.svh'
    binding=re.findall(r'\.record_transport_fault_i\(([^()]*)\)',board.read_text())
    expected='!recording_channel_ready50 || raw_channel_fault'
    if binding!=[expected]:
        raise ValueError('actual W board fault binding differs from tested local boundary')
    if 'wire control_fault='+expected.replace('recording_channel_ready50','control_ready')+';' not in bench.read_text():
        raise ValueError('test local fault binding drift')
    sources=[*(ROOT/'rtl/music'/n for n in music),*(ROOT/'rtl/memory'/n for n in memory),
        ROOT/'rtl/ddr_address_map_guard.v',ROOT/'rtl/workstation/workstation_task3_w_paired.sv',
        ROOT/'rtl/workstation/workstation_task3_record_ingress.sv',
        ROOT.parent/'touchboard_test/rtl/uart_tx.v',bench]
    inputs={str(p):sha(p) for p in [*sources,board,ROOT/'rtl/ddr_address_map.vh',Path(__file__).resolve()]}
    command=['verilator','--binary','--timing','--build-jobs','4','-Wno-fatal',
        '--top-module','tb_task3_w_record_fault_cdc','--Mdir',str(output/'obj'),
        '-I'+str(output/'include'),'-I'+str(ROOT),'-I'+str(ROOT/'rtl/music'),*map(str,sources)]
    result=dict(schema=1,passed=False,build_argv=command,input_sha256=inputs,
        actual_paired_media_arbiter_raw_store=True,actual_native_unowned_return=True,
        full_board_source_binding_checked=True,HCI_recording_object_in_this_test=False,
        CNN_boot_or_inference_verified=False,physical_CDC_verified=False,hardware_operated=False)
    try:
        with (output/'build.log').open('w') as log:
            build=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=180)
        result['build_exit']=build.returncode
        if build.returncode or 'UNOPTFLAT' in (output/'build.log').read_text():
            raise RuntimeError('native fault CDC build failed: '+str(output/'build.log'))
        with (output/'run.log').open('w') as log:
            process=subprocess.run([str(output/'obj/Vtb_task3_w_record_fault_cdc')],cwd=ROOT,
                stdout=log,stderr=subprocess.STDOUT,timeout=60)
        log=(output/'run.log').read_text();print(log)
        result.update(run_exit=process.returncode,log=log)
        if process.returncode or 'PASS task3_W_record_fault_CDC' not in log:
            raise RuntimeError('native fault CDC behavior failed: '+str(output/'run.log'))
        result['metrics']={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',log)}
        result['inputs_unchanged']=all(sha(Path(p))==value for p,value in inputs.items())
        if not result['inputs_unchanged']:
            raise ValueError('fault CDC source drift during test')
        result['passed']=True
    finally:
        for name in ('build.log','run.log'):
            if (output/name).exists():result[name.replace('.','_')+'_sha256']=sha(output/name)
        (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    run(parser.parse_args().output.resolve())
