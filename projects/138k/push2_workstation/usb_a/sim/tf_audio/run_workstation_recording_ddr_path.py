#!/usr/bin/env python3
"""Verify unselected owner8 DDR components against literal legacy components."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
REPOSITORY=ROOT.parents[3]
PREFIX='projects/138k/push2_workstation/usb_a/'
REFERENCE='728eac7a9888ef617dec0c05a57a8ea24f3ec521'
LEGACY=('rtl/timing/basic_pitch_ddr_arbiter_pipeline.sv','rtl/timing/basic_pitch_ddr_client_queues.sv')
CORE='rtl/memory/workstation_recording_ddr_arbiter_pipeline.sv'
QUEUES='rtl/memory/workstation_recording_ddr_client_queues.sv'
BRIDGE='rtl/memory/workstation_recording_ddr_native_bridge.sv'
FIXTURE='sim/tf_audio/workstation_recording_ddr_path_tb.sv'
FAULT_FIXTURE='sim/tf_audio/workstation_recording_ddr_fault_tb.sv'
CONTRACT='rtl/memory/RECORDING_DDR_NATIVE_CONTRACT.md'

def sha(data):return hashlib.sha256(data).hexdigest()

def once(text,anchor,replacement):
    if text.count(anchor)!=1:raise ValueError('negative-control anchor drift: '+anchor)
    return text.replace(anchor,replacement)

def run(output):
    output.mkdir(parents=True,exist_ok=False)
    names=[*LEGACY,CORE,QUEUES,BRIDGE,FIXTURE,FAULT_FIXTURE,CONTRACT,str(Path(__file__).resolve().relative_to(ROOT))]
    hashes={name:sha((ROOT/name).read_bytes()) for name in names}
    for name in LEGACY:
        original=subprocess.check_output(['git','show',REFERENCE+':'+PREFIX+name],cwd=REPOSITORY)
        if sha(original)!=hashes[name]:raise ValueError('legacy input changed: '+name)
    identity=sha(json.dumps(hashes,sort_keys=True).encode())
    result=dict(schema=1,passed=False,identity='native-recording-ddr-owner8-v1-'+identity[:16],source_set_sha256=identity,
        source_sha256=hashes,immutable_reference=REFERENCE,legacy_bytes_unchanged=True,
        default_mode='literal legacy instance; no recording slot/tag/fairness state',
        enabled_mode='owner8; four-bit owner entries; TAG_BITS remains FIFO depth index; original owners0..7 unchanged',
        native_acceptance='actual app_en and stored command_owner; writes require joint app_ready/app_write_ready',
        arbitration_limit='background recording/CPU-writer turn only; unconstrained scan/audio/delay may still starve; no D01 deadline guarantee',
        profile_selected=False,production_owner8_selected=False,final_PCM_CDC_integrated=False,
        r00_complete=False,synthesis=False,pnr=False,hardware_tested=False,sram_programmed=False,flash_written=False,cases={})

    def execute(name,parameters=None,fault=False,mutant=None,expected_failure=None):
        parameters=parameters or {};stage=output/name;stage.mkdir()
        files={n:ROOT/n for n in (CORE,QUEUES,BRIDGE)}
        if mutant:
            owner,text=mutant;files[owner]=stage/Path(owner).name;files[owner].write_text(text)
        top='tb_workstation_recording_ddr_fault' if fault else 'tb_workstation_recording_ddr_path'
        fixture=FAULT_FIXTURE if fault else FIXTURE
        argv=['iverilog','-g2012','-Wall','-s',top,'-o',str(stage/'test.vvp')]
        argv+=['-P'+top+'.'+k+'='+str(v) for k,v in parameters.items()]
        argv+=[*[str(ROOT/n) for n in LEGACY],*[str(files[n]) for n in (CORE,QUEUES,BRIDGE)],str(ROOT/fixture)]
        c=subprocess.run(argv,capture_output=True,text=True,timeout=45)
        log=c.stdout+c.stderr;(stage/'compile.log').write_text(log)
        if c.returncode:raise RuntimeError(name+' compile failed: '+log)
        run_argv=['vvp',str(stage/'test.vvp')]
        v=subprocess.run(run_argv,capture_output=True,text=True,timeout=90)
        run_log=v.stdout+v.stderr;(stage/'run.log').write_text(run_log)
        case=dict(parameters=parameters,top=top,compile_argv=argv,run_argv=run_argv,returncode=v.returncode,
            compiled_source_sha256={n:sha(p.read_bytes()) for n,p in files.items()},
            compile_log=log,compile_log_sha256=sha(log.encode()),run_log=run_log,run_log_sha256=sha(run_log.encode()),
            metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',run_log)})
        case['per_owner']={owner:dict(slot=int(slot),core=int(core),native=int(native))
            for owner,slot,core,native in re.findall(r'OWNER index=(\d+) slot=(\d+) core=(\d+) native=(\d+)',run_log)}
        case['core_trace_available']=bool(parameters.get('RECORDING_ENABLE',1))
        if expected_failure:
            case['expected_failure']=expected_failure;case['rejected']=v.returncode!=0 and expected_failure in run_log
            if not case['rejected']:raise RuntimeError(name+' mutant escaped: '+run_log)
            print('PASS rejected '+name+': '+expected_failure,flush=True)
        else:
            if v.returncode or 'PASS ' not in run_log:raise RuntimeError(name+' failed: '+run_log)
            print(name+': '+run_log.splitlines()[0],flush=True)
        return name,case

    try:
        scenarios=[]
        for bits,seed in ((2,7),(3,31),(5,127)):
            common=dict(BITS=bits,SEED=seed)
            for mode,enabled,used in (('disabled',0,0),('idle',1,0),('active',1,1)):
                scenarios.append(('queues_'+mode+'_bits'+str(bits),dict(common,RECORDING_ENABLE=enabled,USE_RECORDING=used)))
                for registered in (0,1):
                    scenarios.append(('core_'+mode+'_grants'+str(registered)+'_bits'+str(bits),
                        dict(common,RECORDING_ENABLE=enabled,USE_RECORDING=used,CORE_ONLY=1,REGISTER_GRANTS=registered)))
        with ThreadPoolExecutor(max_workers=3)as pool:
            for name,case in pool.map(lambda args:execute(*args),scenarios):result['cases'][name]=case
        for fault_case in range(6):
            name,case=execute('fault_bridge_'+str(fault_case),dict(CASE=fault_case),fault=True);result['cases'][name]=case
        core=(ROOT/CORE).read_text();bridge=(ROOT/BRIDGE).read_text()
        negatives=[
            ('owner8_tag_truncated',dict(),False,CORE,once(core,'reg [3:0] tags[0:DEPTH-1];','reg [2:0] tags[0:DEPTH-1];'),'response lost/reordered/memory mismatch'),
            ('recording_mask_lost',dict(),False,CORE,once(core,'({32{effective_grant[8]}}&recording_mask)',"32'd0"),'per-client native command order/data changed'),
            ('core_ack_is_not_native',dict(),False,CORE,once(core,"assign native_accept_o[client]=app_en && command_owner==4'(client);",'assign native_accept_o[client]=core_accept_o[client];'),'nonexclusive three-stage acceptance'),
            ('write_commit_without_write_ready',dict(),False,CORE,once(core,'(!command_write || app_write_ready) && (command_write || read_room);',"1'b1 && (command_write || read_room);"),'native command/write data not jointly accepted'),
            ('returned_data_not_paired',dict(),False,CORE,once(core,'response_data<=app_response_data;',"response_data<=256'd0;"),'response lost/reordered/memory mismatch'),
            ('invalid_owner_fault_ignored',dict(CASE=1),True,CORE,once(core,'wire response_fault_now=app_response && (count==0 || invalid_return_owner);','wire response_fault_now=app_response && count==0;'),'missing same-edge empty/invalid owner fault'),
            ('empty_owner_fault_ignored',dict(CASE=0),True,CORE,once(core,'wire response_fault_now=app_response && (count==0 || invalid_return_owner);','wire response_fault_now=app_response && count!=0 && invalid_return_owner;'),'missing same-edge empty/invalid owner fault'),
            ('bridge_reenqueues_after_core_ack',dict(CASE=4),True,BRIDGE,once(bridge,'else if(slot_valid_o && slot_ready_i)submitted_o<=1;','else if(slot_valid_o && slot_ready_i)submitted_o<=1;\n            else if(submitted_o && slot_ready_i)submitted_o<=0;'),'core/local ACK duplicated submitted command'),
            ('bridge_acks_local_slot',dict(CASE=4),True,BRIDGE,once(bridge,'assign native_ready_o=native_accept_i && submitted_o;','assign native_ready_o=slot_valid_o && slot_ready_i;'),'slot ACK mistaken for native acceptance'),
            ('bridge_fault_delayed_one_edge',dict(CASE=3),True,BRIDGE,once(bridge,
                'assign transport_fault_o=transport_fault_i || protocol_fault_o || protocol_fault_now;',
                'assign transport_fault_o=transport_fault_i || protocol_fault_o;'),'bridge protocol fault not visible before edge'),
            ('default_grant_path_changed',dict(CORE_ONLY=1,REGISTER_GRANTS=1,RECORDING_ENABLE=0,USE_RECORDING=0),False,CORE,once(core,'.REGISTER_GRANTS(REGISTER_GRANTS)) u_legacy(','.REGISTER_GRANTS(0)) u_legacy('),'default/idle owner8 legacy cycle miter mismatch'),
        ]
        for name,parameters,fault,owner,text,expected in negatives:
            key,case=execute(name,parameters,fault,(owner,text),expected);result['cases'][key]=case
        result['lint']={}
        for enabled in (0,1):
            argv=['verilator','--lint-only','--top-module','workstation_recording_ddr_client_queues',
                '-GRECORDING_ENABLE='+str(enabled),*[str(ROOT/n) for n in (*LEGACY,CORE,QUEUES)]]
            c=subprocess.run(argv,capture_output=True,text=True,timeout=45)
            result['lint'][str(enabled)]=dict(argv=argv,returncode=c.returncode,log=c.stdout+c.stderr)
            if c.returncode:raise RuntimeError('strict lint failed: '+c.stdout+c.stderr)
        result['source_inputs_unchanged_during_run']=hashes=={n:sha((ROOT/n).read_bytes()) for n in names}
        if not result['source_inputs_unchanged_during_run']:raise ValueError('source changed during verification')
        result['passed']=True
    finally:(output/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output.resolve())
