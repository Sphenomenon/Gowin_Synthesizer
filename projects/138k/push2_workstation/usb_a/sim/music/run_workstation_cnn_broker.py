#!/usr/bin/env python3
"""Verify native owner5 acknowledgement, routing, fairness and quarantine."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'rtl/music/workstation_cnn_ddr_broker.sv'
    fixture = ROOT / 'sim/music/tb_workstation_cnn_broker.sv'
    variants = {
        'actual': None,
        'ack_local_slot': ('live && state==NATIVE && !stage_owner && native_accept_i',
                           'live && state==SUBMIT && !stage_owner && slot_ready_i'),
        'route_wrong_return': ('live && state==RETURN && !stage_owner && response_i',
                               'live && state==RETURN && stage_owner && response_i'),
        'disable_timeout': ("else if(timer==TIMER_BITS'(TIMEOUT_CYCLES-1))fault_o<=1;",
                            "else if(1'b0)fault_o<=1;")}
    results = {}
    for name, mutation in variants.items():
        destination = output / name
        destination.mkdir()
        selected = source
        if mutation:
            text = source.read_text()
            before, after = mutation
            if text.count(before) != 1:
                raise ValueError(f'mutation anchor drift: {name}')
            selected = destination / source.name
            selected.write_text(text.replace(before, after))
        argv = ['iverilog', '-g2012', '-s', 'tb_workstation_cnn_broker', '-o', str(destination/'test.vvp'), str(selected), str(fixture)]
        built = subprocess.run(argv, text=True, capture_output=True, cwd=ROOT)
        (destination / 'build.log').write_text(built.stdout + built.stderr)
        if built.returncode:
            raise RuntimeError(f'broker compile failed: {name}')
        simulated = subprocess.run(['vvp', str(destination/'test.vvp')], text=True, capture_output=True, cwd=ROOT, timeout=30)
        log = simulated.stdout + simulated.stderr
        (destination / 'run.log').write_text(log)
        passed = simulated.returncode == 0 and 'PASS CNN_native_broker' in log
        results[name] = dict(compile_exit=built.returncode, run_exit=simulated.returncode,
                             passed=passed, log=log, run_log_sha256=sha(destination/'run.log'))
        if passed != (mutation is None):
            raise RuntimeError(f'broker behavior or mutation survived: {name}')
    header=ROOT/'rtl/ddr_address_map.vh'
    guard=ROOT/'rtl/ddr_address_map_guard.v'
    map_fixture=ROOT/'sim/tf_audio/tb_ddr_address_map.sv'
    map_variants={
        'actual':None,
        'overlap_recording_pool':('W_CNN_PCM_POOL_BYTE_BASE 32\'h3110_0000','W_CNN_PCM_POOL_BYTE_BASE 32\'h3100_0000'),
        'native_unit_mismatch':('W_CNN_PCM_APP_BASE       29\'h0c44_0000','W_CNN_PCM_APP_BASE       29\'h0c44_0008'),
        'capacity_mismatch':('W_CNN_PCM_CAPACITY_FRAMES 32\'d96_000','W_CNN_PCM_CAPACITY_FRAMES 32\'d96_001'),
        'invalid_tail_alignment':('W_CNN_PCM_LAST_BEAT      29\'h0c45_76f8','W_CNN_PCM_LAST_BEAT      29\'h0c45_76f9')}
    map_results={}
    for name,mutation in map_variants.items():
        destination=output/('map_'+name)
        include=destination/'src/memory'
        include.mkdir(parents=True)
        text=header.read_text()
        if mutation:
            before,after=mutation
            if text.count(before)!=1:raise ValueError(f'map mutation anchor drift: {name}')
            text=text.replace(before,after)
        (include/header.name).write_text(text)
        built=subprocess.run(['iverilog','-g2012','-I'+str(destination),'-s','tb_ddr_address_map',
                              '-o',str(destination/'test.vvp'),str(guard),str(map_fixture)],
                             text=True,capture_output=True,cwd=ROOT)
        log=built.stdout+built.stderr
        (destination/'build.log').write_text(log)
        if mutation:
            if built.returncode==0 or 'PRJ1_DDR_MAP_ERROR_TASK3_W_CNN_' not in log:
                raise RuntimeError(f'invalid CNN pool guard survived: {name}')
            map_results[name]=dict(build_exit=built.returncode,rejected=True,log=log)
        else:
            if built.returncode:raise RuntimeError('actual CNN pool map compile failed')
            simulated=subprocess.run(['vvp',str(destination/'test.vvp')],text=True,capture_output=True,cwd=ROOT,timeout=30)
            log=simulated.stdout+simulated.stderr
            (destination/'run.log').write_text(log)
            if simulated.returncode or 'PASS tb_ddr_address_map' not in log:raise RuntimeError('actual map simulation failed')
            map_results[name]=dict(build_exit=0,run_exit=0,passed=True,log=log)
    result = dict(schema=1, passed=True, scope='owner5_native_CNN_and_staging_broker_and_bounded_PCM_address_map',
                  source_sha256={str(p):sha(p) for p in [source,fixture,header,guard,map_fixture,Path(__file__)]}, variants=results,
                  address_map=map_results,
                  hardware_tested=False, bitstream_identity=None)
    (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output.resolve())
