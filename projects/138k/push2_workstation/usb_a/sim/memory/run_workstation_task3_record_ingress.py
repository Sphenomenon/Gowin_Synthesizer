#!/usr/bin/env python3
"""Bounded recording ingress against the actual engine, including mutations."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    module=ROOT/'rtl/workstation/workstation_task3_record_ingress.sv'
    engine=ROOT/'rtl/bluetooth/cpu_owner/workstation_ble_record_data_engine.sv'
    tb=ROOT/'sim/memory/tb_workstation_task3_record_ingress.sv'
    inputs={str(p):sha(p)for p in(module,engine,tb,Path(__file__).resolve())}
    cases=[('actual',None,None),
           ('unsafe-engine-pacing','cooldown==0','cooldown<=2'),
           ('silenced-overflow','identity_bad || count==DEPTH','identity_bad'),
           ('silenced-generation',
            'expected_key={session_o,generation_o,physical_epoch_o,expected_sequence}',
            'expected_key={session_o,frame_generation_i,physical_epoch_o,expected_sequence}')]
    evidence=[]
    for name,before,after in cases:
        directory=out/name;directory.mkdir()
        source=module
        if before is not None:
            text=module.read_text()
            if text.count(before)!=1:raise ValueError('test mutation anchor drift')
            source=directory/module.name;source.write_text(text.replace(before,after,1))
        build=['verilator','--binary','--timing','--build-jobs','4','-Wno-fatal','--top-module',
               'tb_workstation_task3_record_ingress','--Mdir',str(directory/'obj'),str(source),str(engine),str(tb)]
        with(directory/'build.log').open('w')as log:p=subprocess.run(build,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        if p.returncode:raise RuntimeError('ingress test compile failed: '+str(directory/'build.log'))
        with(directory/'run.log').open('w')as log:p=subprocess.run([str(directory/'obj/Vtb_workstation_task3_record_ingress')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        text=(directory/'run.log').read_text()
        passed=p.returncode==0 and 'PASS task3_record_ingress'in text
        if (before is None)!=passed:raise RuntimeError('record ingress test/mutation survived incorrectly: '+str(directory/'run.log'))
        evidence.append(dict(name=name,run_exit=p.returncode,expected_failure=before is not None,
            log=text,run_log_sha256=sha(directory/'run.log'),build_log_sha256=sha(directory/'build.log')))
        print(name+': '+('PASS'if passed else 'mutation rejected'),flush=True)
    if inputs!={str(p):sha(p)for p in(module,engine,tb,Path(__file__).resolve())}:raise ValueError('ingress source changed')
    result=dict(schema=1,passed=True,source_sha256=inputs,cases=evidence,FIFO_frames=256,minimum_engine_cycles=5,
        source_lease_cycles_at_50MHz=200000,actual_maintained_engine_tested=True,
        actual_test_FIFO_frames=16,actual_test_source_lease_cycles=512,
        LCD_transport_verified=False,production_profile_selected=False,synthesis=False,hardware_operated=False)
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output.resolve())
