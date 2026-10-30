#!/usr/bin/env python3
"""Default-off BLE external sealing: real recorder, wire protocol and staged chain."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
REPOSITORY=ROOT.parents[3]
PROTOCOL=REPOSITORY/'projects/25k/example/RTL8723DS_PROTOCOL'
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'sim'))
from tools import workstation_bluetooth,workstation_pinout
from test_workstation_pinout import fixture
from ble_seal_protocol_fixture import build

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def run(output,protocol_result=None):
    output.mkdir(parents=True,exist_ok=False)
    (output/'pinout').mkdir()
    maintained=[ROOT/'rtl/bluetooth/workstation_bluetooth.sv',ROOT/'tools/workstation_bluetooth.py',
        ROOT/'rtl/bluetooth/WORKSTATION_BLE_SEAL_CONTRACT.md',
        ROOT/'tools/workstation_pinout.py',ROOT/'sim/test_workstation_pinout.py',
        ROOT/'boards/custom_138k/bluetooth.json',ROOT/'boards/custom_138k/pinout.json',
        PROTOCOL/'tests/tb_protocol_recording.sv',Path(__file__).resolve(),
        Path(__file__).with_name('ble_seal_protocol_fixture.py'),Path(__file__).with_name('tb_workstation_ble_seal.sv'),
        Path(__file__).with_name('tb_workstation_ble_seal_chain.sv')]
    profile,payloads,core=fixture()
    netlists={role:workstation_pinout.Netlist(payload) for role,payload in payloads.items()}
    plan=workstation_pinout.resolve(profile,netlists,core)
    with patch.object(workstation_pinout,'load_sources',return_value=(netlists,{})):
        metadata=workstation_bluetooth.prepare(ROOT,output,output,output/'pinout',plan)
    (output/'prepare.json').write_text(json.dumps(metadata,indent=2)+'\n')
    maintained += [REPOSITORY/name for name in metadata['source_snapshot_sha256']]
    staged=[output/name for name in metadata['sources']]
    maintained += staged+[output/'native_bluetooth/patch_path.vh']
    tb_protocol=output/'tb_ble_seal_protocol.sv'
    tb_protocol.write_text(build(PROTOCOL/'tests/tb_protocol_recording.sv'));maintained.append(tb_protocol)
    before={str(p):digest(p) for p in maintained}
    identity=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()
    result=dict(schema=1,passed=False,identity='native-ble-external-seal-v1-'+identity[:16],
        source_set_sha256=identity,input_sha256=before,prepare=metadata,hardware_tested=False,profile_changed=False,
        validation_stage='offline-real-BLE-recorder-protocol-and-staged-five-layer-seal',
        limits='Protocol framing/CRC/request-cache and recorder RAM/CRC are real; staged chain forces only BLE initialization/connection and direct command injection. Original UART/H5 full regression separately verifies default link. No external rate-switch aggregator, routed CDC/timing, synthesis, P&R, board or deployment acceptance.')
    recording=PROTOCOL/'rtl/ble_recording.v';command=PROTOCOL/'rtl/ble_protocol_command.v'
    tb_unit=Path(__file__).with_name('tb_workstation_ble_seal.sv')
    def execute(name,top,sources,cwd,expect=None):
        compile_argv=['iverilog','-g2012','-Wall','-I',str(output),'-s',top,'-o',str(output/(name+'.vvp')),*map(str,sources)]
        compiled=subprocess.run(compile_argv,cwd=cwd,text=True,capture_output=True,timeout=90)
        (output/(name+'_compile.log')).write_text(compiled.stdout+compiled.stderr)
        if compiled.returncode:raise RuntimeError(compiled.stdout+compiled.stderr)
        executed=subprocess.run(['vvp',str(output/(name+'.vvp'))],cwd=cwd,text=True,capture_output=True,timeout=90)
        log=executed.stdout+executed.stderr;(output/(name+'_run.log')).write_text(log)
        entry=dict(compile_argv=compile_argv,returncode=executed.returncode,
            compile_log_sha256=digest(output/(name+'_compile.log')),run_log_sha256=digest(output/(name+'_run.log')),
            metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',log)})
        result[name]=entry
        if expect is None:
            if executed.returncode or 'PASS ble_external_seal' not in log:raise RuntimeError(log)
            print(log,end='')
        else:
            entry.update(rejected=executed.returncode!=0 and any(marker in log for marker in expect),run_log=log)
            if not entry['rejected']:raise ValueError('Negative control escaped: '+log)
        return entry
    try:
        execute('unit','tb_workstation_ble_seal',[tb_unit,recording],ROOT)
        execute('protocol','tb_protocol_recording',[tb_protocol,command,recording],PROTOCOL)
        execute('staged_chain','tb_workstation_ble_seal_chain',[
            Path(__file__).with_name('tb_workstation_ble_seal_chain.sv'),ROOT/'rtl/bluetooth/workstation_bluetooth.sv',*staged],output)
        source=recording.read_text()
        anchor='        recording_active && capture_state==0 && recording_id==seal_recording_id_o;'
        if source.count(anchor)!=1:raise ValueError('Early commit negative anchor drift')
        early=output/'ble_recording_early_commit_negative.v'
        early.write_text(source.replace(anchor,'        recording_active && recording_id==seal_recording_id_o;'))
        entry=execute('early_crc_negative','tb_workstation_ble_seal',[tb_unit,early],ROOT,
            ['sealed prefix differs','seal ACK escaped committed identity/CRC proof'])
        entry['mutant_sha256']=digest(early)
        anchor='    wire external_mutation_hold=EXTERNAL_SEAL_PROTOCOL && (seal_hold_i || seal_request_i || seal_pending_o);'
        if source.count(anchor)!=1:raise ValueError('Mutation barrier negative anchor drift')
        barrier=output/'ble_recording_mutation_barrier_negative.v'
        barrier.write_text(source.replace(anchor,"    wire external_mutation_hold=1'b0;"))
        entry=execute('mutation_barrier_negative','tb_protocol_recording',[tb_protocol,command,barrier],PROTOCOL,
            ['Status 01 expected 82','assembled START crossed seal barrier'])
        entry['mutant_sha256']=digest(barrier)
        mask=source
        for old,new,count in [
            ('    wire seal_source_lost=seal_requires_source && (!enable || (EXTERNAL_PCM && (!source_ready_i || source_fault_i)));',
             '    wire seal_source_lost=seal_requires_source && (!enable || (EXTERNAL_PCM && source_fault_i));',1),
            ('if(seal_commit && enable && !(EXTERNAL_PCM && (!source_ready_i || source_fault_i)))begin',
             'if(seal_commit && enable && !(EXTERNAL_PCM && source_fault_i))begin',1),
            ('(!source_ready_i || source_fault_i || (!external_capture_hold && pcm_valid_i && capture_state!=0))',
             '(source_fault_i || (!external_capture_hold && pcm_valid_i && capture_state!=0))',1)]:
            if mask.count(old)!=count:raise ValueError('Source loss negative anchor drift')
            mask=mask.replace(old,new)
        masked=output/'ble_recording_source_mask_negative.v';masked.write_text(mask)
        entry=execute('source_mask_negative','tb_workstation_ble_seal',[tb_unit,masked],ROOT,['seal result timeout','source loss masqueraded as normal seal'])
        entry['mutant_sha256']=digest(masked)
        result['default_protocol_regression_attached']=False
        if protocol_result is not None:
            original=json.loads(protocol_result.read_text())
            if not original.get('passed') or not original.get('cases') or not all(c['passed'] for c in original['cases'].values()):
                raise ValueError('Original protocol regression did not pass')
            for name,sha in original['source_sha256'].items():
                if digest(PROTOCOL/name)!=sha:raise ValueError('Original protocol regression input drift: '+name)
            result['default_protocol_regression_attached']=True
            result['default_protocol_regression']=dict(report=str(protocol_result),sha256=digest(protocol_result),
                cases=len(original['cases']),case_passed={k:v['passed'] for k,v in original['cases'].items()},
                source_sha256=original['source_sha256'])
        result['inputs_unchanged_during_run']=before=={p:digest(Path(p)) for p in before}
        if not result['inputs_unchanged_during_run']:raise ValueError('Input drift')
        result['passed']=True
    finally:(output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--protocol-result',type=Path)
    args=parser.parse_args();run(args.output.resolve(),args.protocol_result.resolve() if args.protocol_result else None)
