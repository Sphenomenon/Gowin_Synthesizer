#!/usr/bin/env python3
"""Exercise the unselected R00 storage owner and the actual timing arbiter."""
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
BACKEND='rtl/audio/workstation_pcm_ddr_backend.sv'
CONTRACT='rtl/audio/PCM_DDR_BACKEND_CONTRACT.md'
MAP='rtl/ddr_address_map.vh'
FIXTURE='sim/tf_audio/workstation_pcm_ddr_backend_tb.sv'
DEPENDENCIES=(
    'rtl/memory/workstation_sdp.sv','rtl/ddr_address_map_guard.v',
    'rtl/timing/basic_pitch_ddr_client_queues.sv','rtl/timing/basic_pitch_ddr_arbiter_pipeline.sv',
    'rtl/music/basic_pitch_ddr_map.svh',
)
NATIVE=(
    'rtl/memory/workstation_recording_ddr_arbiter_pipeline.sv',
    'rtl/memory/workstation_recording_ddr_client_queues.sv',
    'rtl/memory/workstation_recording_ddr_native_bridge.sv',
)

def sha(data):return hashlib.sha256(data).hexdigest()

def replace_once(text,anchor,replacement):
    if text.count(anchor)!=1:raise ValueError('Negative-control anchor drift: '+anchor)
    return text.replace(anchor,replacement)

def defines(text):
    return dict(re.findall(r'^`define[ \t]+(\w+)[ \t]+([^\n]+)',text,re.M))

def number(value):
    match=re.fullmatch(r"\d+'([hd])(\w+)",value.strip())
    if not match:raise ValueError('Nonliteral address value: '+value)
    return int(match[2].replace('_',''),16 if match[1]=='h' else 10)

def run(output):
    output.mkdir(parents=True,exist_ok=False)
    names=[BACKEND,CONTRACT,MAP,FIXTURE,str(Path(__file__).resolve().relative_to(ROOT)),*DEPENDENCIES,*NATIVE,
        'rtl/memory/RECORDING_DDR_NATIVE_CONTRACT.md']
    hashes={name:sha((ROOT/name).read_bytes()) for name in names}
    protected={}
    for name in DEPENDENCIES:
        original=subprocess.check_output(['git','show',REFERENCE+':'+PREFIX+name],cwd=REPOSITORY)
        if sha(original)!=hashes[name]:raise ValueError('Actual primitive/arbiter/reference input changed: '+name)
        protected[name]=hashes[name]
    original_map=subprocess.check_output(['git','show',REFERENCE+':'+PREFIX+MAP],cwd=REPOSITORY).decode()
    old_defines=defines(original_map);new_defines=defines((ROOT/MAP).read_text())
    if any(new_defines.get(key)!=value for key,value in old_defines.items()):raise ValueError('Existing DDR map allocation drift')
    allowed={'PRJ1_DDR_BP_HISTORY_BYTE_BASE','PRJ1_DDR_BP_HISTORY_BYTE_LAST','PRJ1_DDR_RECORDING_BYTE_BASE',
        'PRJ1_DDR_RECORDING_BYTE_LAST','PRJ1_DDR_RECORDING_BYTES','PRJ1_DDR_RECORDING_APP_BASE','PRJ1_DDR_RECORDING_STAGE_BYTES'}
    allowed.update('PRJ1_DDR_RECORDING_'+owner+'_'+field for owner in ('CPU','BLE')
        for field in ('BYTE_BASE','BYTE_LAST','BYTES','APP_BASE','APP_LAST'))
    if set(new_defines)-set(old_defines)!=allowed:raise ValueError('Unexpected DDR map additions')
    bp=defines((ROOT/DEPENDENCIES[-1]).read_text())
    bp_history=[number(bp[name]) for name in ('BP_DDR_NOTE_BYTE_BASE','BP_DDR_ONSET_BYTE_BASE','BP_DDR_ANALYSIS_BYTE_BASE','BP_DDR_BPTR_BYTE_BASE')]
    if sorted(bp_history)!=[0x30100000,0x30200000,0x30300000,0x30400000] or number(bp['BP_DDR_LAST_BYTE'])!=0x304fffff:
        raise ValueError('Basic Pitch history occupancy changed')
    if number(new_defines['PRJ1_DDR_RECORDING_BYTE_BASE'])!=0x30500000 or number(new_defines['PRJ1_DDR_RECORDING_BYTE_LAST'])!=0x305fffff:
        raise ValueError('Recording allocation identity mismatch')
    subregions={}
    for owner in ('CPU','BLE'):
        region={field.lower():number(new_defines['PRJ1_DDR_RECORDING_'+owner+'_'+field])
            for field in ('BYTE_BASE','BYTE_LAST','BYTES','APP_BASE','APP_LAST')}
        if (region['byte_base']%32 or region['byte_last']-region['byte_base']+1!=region['bytes'] or
            region['bytes']!=65536 or region['app_base']!=region['byte_base']//4 or
            region['app_last']!=region['byte_last']//4 or
            not 0x30500000<=region['byte_base']<=region['byte_last']<=0x305fffff):
            raise ValueError('Recording suballocation geometry mismatch: '+owner)
        subregions[owner]=region
    if (subregions['CPU']['byte_base']!=0x30500000 or
        subregions['CPU']['app_base']!=number(new_defines['PRJ1_DDR_RECORDING_APP_BASE']) or
        subregions['CPU']['bytes']!=number(new_defines['PRJ1_DDR_RECORDING_STAGE_BYTES']) or
        subregions['CPU']['byte_last']>=subregions['BLE']['byte_base']):
        raise ValueError('Recording suballocation identity/overlap mismatch')
    identity=sha(json.dumps(hashes,sort_keys=True).encode())
    result=dict(schema=1,passed=False,identity='native-pcm-ddr-backend-v4-'+identity[:16],source_set_sha256=identity,
        source_sha256=hashes,immutable_reference=REFERENCE,immutable_dependency_sha256=protected,
        previous_map_sha256=sha(original_map.encode()),existing_allocations_unchanged=True,
        allocation=dict(byte_base='0x30500000',byte_last='0x305fffff',native_word_base='0x0c140000',
            granule_bytes=1048576,stage_capacity_bytes=65536,stage_capacity_frames=16384,subregions=subregions),
        source_policy='maintained CPU backend explicitly bound to original suballocation; BLE raw suballocation reserved; original actual timing queues/core/SDP/guard untouched',
        arbiter_test_boundary='unselected native queues/core enabled in fixture; recording owner8 with simultaneous music/NN owner5 and all legacy memory traffic; actual native acceptance bridge; no production/profile integration',
        owner8_component_tested=True,production_owner8_selected=False,
        command_priority_policy='invalidation blocks all admission; EMPTY clear blocks create; clear blocks reference acquire; release blocks reference acquire/download/output; current held reference is required before download admission',
        profile_selected=False,top_changed=False,ble_wire_changed=False,android_changed=False,
        final_PCM_CDC_integrated=False,actual_owner8_integrated=False,physical_resource_saving_proven=False,
        r00_complete=False,r01_complete=False,synthesis=False,pnr=False,hardware_tested=False,
        sram_programmed=False,flash_written=False,cases={})

    def execute(name,parameters,source=None,fixture=None,map_text=None,expected_failure=None,bridge_source=None):
        stage=output/name;include=stage/'src/memory';include.mkdir(parents=True)
        (include/'ddr_address_map.vh').write_text(map_text if map_text is not None else (ROOT/MAP).read_text())
        source=source or ROOT/BACKEND;fixture=fixture or ROOT/FIXTURE
        command=['iverilog','-g2012','-Wall','-I',str(stage),'-s','tb_workstation_pcm_ddr_backend',
            '-o',str(stage/'test.vvp')]
        command+=['-Ptb_workstation_pcm_ddr_backend.'+key+'='+str(value) for key,value in parameters.items()]
        native_paths={name:(bridge_source if name==NATIVE[2] and bridge_source is not None else ROOT/name) for name in NATIVE}
        command += [str(source),*[str(ROOT/name) for name in DEPENDENCIES[:-1]],*[str(path) for path in native_paths.values()],str(fixture)]
        compiled=subprocess.run(command,cwd=stage,capture_output=True,text=True,timeout=45)
        compile_log=compiled.stdout+compiled.stderr;(stage/'compile.log').write_text(compile_log)
        if compiled.returncode:raise RuntimeError(name+' compile failed: '+compile_log)
        run_command=['vvp',str(stage/'test.vvp')]
        executed=subprocess.run(run_command,cwd=stage,capture_output=True,text=True,timeout=120)
        log=executed.stdout+executed.stderr;(stage/'run.log').write_text(log)
        case=dict(parameters=parameters,compile_argv=command,run_argv=run_command,
            backend_sha256=sha(source.read_bytes()),fixture_sha256=sha(fixture.read_bytes()),
            native_inputs_sha256={name:sha(path.read_bytes()) for name,path in native_paths.items()},
            map_sha256=sha((include/'ddr_address_map.vh').read_bytes()),returncode=executed.returncode,
            compile_log_sha256=sha(compile_log.encode()),compile_log=compile_log,
            run_log_sha256=sha(log.encode()),run_log=log,
            metrics={key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',log)})
        if expected_failure:
            case['expected_failure']=expected_failure
            case['rejected']=executed.returncode!=0 and expected_failure in log
            if not case['rejected']:raise RuntimeError(name+' negative escaped: '+log)
            print('PASS rejected '+name+': '+expected_failure,flush=True)
        else:
            if executed.returncode or 'PASS workstation_pcm_ddr_backend:' not in log:raise RuntimeError(name+' failed: '+log)
            print(log.splitlines()[0],flush=True)
        return name,case

    try:
        scenarios=[]
        for rate in (0,1):
            for competition in (0,1):scenarios.append(('rate'+str(rate)+'_bounded_'+str(competition),
                dict(CASE=0,RATE_44K1=rate,COMPETITION=competition,FIFO_BITS=9)))
            scenarios.append(('rate'+str(rate)+'_64KiB_competition',dict(CASE=1,RATE_44K1=rate,COMPETITION=1,FIFO_BITS=9)))
            scenarios.append(('rate'+str(rate)+'_faults',dict(CASE=2,RATE_44K1=rate,FIFO_BITS=9,DDR_BUDGET=2048)))
            scenarios.append(('rate'+str(rate)+'_cancel_reset',dict(CASE=3,RATE_44K1=rate,FIFO_BITS=9)))
            for competition in (0,1):scenarios.append(('rate'+str(rate)+'_command_collisions_'+str(competition),
                dict(CASE=4,RATE_44K1=rate,COMPETITION=competition,FIFO_BITS=9)))
            for competition in (0,1):
                scenarios.append(('rate'+str(rate)+'_transport_fault_'+str(competition),
                    dict(CASE=5,RATE_44K1=rate,COMPETITION=competition,FIFO_BITS=9)))
                scenarios.append(('rate'+str(rate)+'_transport_default_disabled_'+str(competition),
                    dict(CASE=6,RATE_44K1=rate,COMPETITION=competition,FIFO_BITS=9,FAULT_ENABLE=0)))
            scenarios.append(('rate'+str(rate)+'_actual_native_transport_fault',
                dict(CASE=7,RATE_44K1=rate,COMPETITION=1,FIFO_BITS=9)))
            scenarios.append(('rate'+str(rate)+'_cancel_local_core_stages',
                dict(CASE=8,RATE_44K1=rate,COMPETITION=1,FIFO_BITS=9)))
            scenarios.append(('rate'+str(rate)+'_bridge_fault_admission',
                dict(CASE=9,RATE_44K1=rate,COMPETITION=1,FIFO_BITS=9)))
        with ThreadPoolExecutor(max_workers=3)as pool:
            for name,case in pool.map(lambda args:execute(*args),scenarios):result['cases'][name]=case
        native=(ROOT/BACKEND).read_text()
        negatives=[
            ('premature_ready',dict(CASE=0),replace_once(native,
                'if(state_o==SEALING && fifo_count==0 && pack_frames==0 && quiescent_o &&\n               committed_frames_o==frames_o && !invalidate)state_o<=READY;',
                'if(state_o==SEALING && fifo_count==0 && pack_frames==0 && !invalidate)state_o<=READY;'),
                'seal published before real final write acceptance'),
            ('unmasked_tail',dict(CASE=0),replace_once(native,"ddr_mask_o<=32'hffffffff<<(pack_frames*4);",'ddr_mask_o<=0;'),
                'tail mask overwrote'),
            ('clear_held_reference',dict(CASE=0),replace_once(native,
                'assign clear_ready_o=rst_ni && state_o!=CAPTURE && state_o!=SEALING && quiescent_o && !reference_held_o && !invalidate;',
                'assign clear_ready_o=rst_ni && state_o!=CAPTURE && state_o!=SEALING && quiescent_o && !invalidate;'),
                'clear bypassed download reference'),
            ('forget_cancelled_read',dict(CASE=3),replace_once(native,
                'if(invalidate)begin','if(invalidate)begin\n                read_outstanding<=0;'),
                'old read escaped generation fence'),
            ('native_word_step',dict(CASE=0),replace_once(native,'write_address<=write_address+`PRJ1_DDR_APP_ADDR_STEP;',
                "write_address<=write_address+29'd1;"),'unaligned native BL8'),
            ('clear_admits_create',dict(CASE=4),replace_once(native,
                'assign create_ready_o=rst_ni && state_o==EMPTY && quiescent_o && !reference_held_o && !invalidate && !clear_i;',
                'assign create_ready_o=rst_ni && state_o==EMPTY && quiescent_o && !reference_held_o && !invalidate;'),
                'clear admitted simultaneous create'),
            ('release_admits_reference',dict(CASE=4),replace_once(native,
                'assign reference_ready_o=rst_ni && state_o==READY && !reference_held_o && !invalidate && !clear_i && !reference_release_i;',
                'assign reference_ready_o=rst_ni && state_o==READY && !reference_held_o && !invalidate && !clear_i;'),
                'release admitted new reference'),
            ('fault_admits_download',dict(CASE=4),replace_once(native,
                '!download_active && quiescent_o && !invalidate && !reference_release_i;',
                '!download_active && quiescent_o && !cancel_i && !soft_reset_i && !reference_release_i;'),
                'fault admitted simultaneous download'),
            ('transport_fault_ignored_in_ready',dict(CASE=5,FAULT_START_PHASE=1),replace_once(native,
                'wire transport_bad=TRANSPORT_FAULT_ENABLE && transport_fault_i;',
                'wire transport_bad=1\'b0;'),'transport fault left admission/output open'),
            ('terminal_transport_fault_rearms_clear',dict(CASE=5),replace_once(native,
                'wire invalidate=cancel_i || soft_reset_i || transport_bad || fault_event;',
                'wire invalidate=cancel_i || soft_reset_i || fault_event;'),
                'soft reset/clear recovered sticky transport fault'),
        ]
        for name,parameters,text,expected_failure in negatives:
            source=output/(name+'.sv');source.write_text(text)
            key,case=execute(name,parameters,source=source,expected_failure=expected_failure);result['cases'][key]=case
        fixture=output/'local_slot_acceptance_fixture.sv'
        fixture.write_text(replace_once((ROOT/FIXTURE).read_text(),'assign request_ready=record_native_ready;',
            'assign request_ready=request && !submitted && local_ready;'))
        key,case=execute('local_slot_is_not_native_acceptance',dict(CASE=0,COMPETITION=1,FAULT_ENABLE=0),fixture=fixture,
            expected_failure='seal published before real final write acceptance');result['cases'][key]=case
        overlapping=replace_once((ROOT/MAP).read_text(),
            "`define PRJ1_DDR_RECORDING_BYTE_BASE     32'h3050_0000",
            "`define PRJ1_DDR_RECORDING_BYTE_BASE     32'h3040_0000")
        key,case=execute('overlap_recording_allocation',dict(CASE=0),map_text=overlapping,
            expected_failure='PCM recording allocation overlaps/misaligns');result['cases'][key]=case
        for label,old,new in (
            ('cpu_suballocation_units',"`define PRJ1_DDR_RECORDING_CPU_APP_BASE  29'h0c14_0000",
                                       "`define PRJ1_DDR_RECORDING_CPU_APP_BASE  29'h0c14_0008"),
            ('cpu_suballocation_end',"`define PRJ1_DDR_RECORDING_CPU_BYTE_LAST 32'h3050_ffff",
                                     "`define PRJ1_DDR_RECORDING_CPU_BYTE_LAST 32'h3050_ffdf"),
            ('ble_suballocation_overlap',"`define PRJ1_DDR_RECORDING_BLE_BYTE_BASE 32'h3051_0000",
                                         "`define PRJ1_DDR_RECORDING_BLE_BYTE_BASE 32'h3050_0000")):
            invalid=replace_once((ROOT/MAP).read_text(),old,new)
            key,case=execute(label,dict(CASE=0),map_text=invalid,
                expected_failure='PCM recording allocation overlaps/misaligns');result['cases'][key]=case
        delayed_bridge=output/'delayed_bridge_fault.sv'
        delayed_bridge.write_text(replace_once((ROOT/NATIVE[2]).read_text(),
            'assign transport_fault_o=transport_fault_i || protocol_fault_o || protocol_fault_now;',
            'assign transport_fault_o=transport_fault_i || protocol_fault_o;'))
        key,case=execute('bridge_protocol_fault_admits_request',dict(CASE=9,COMPETITION=1,FIFO_BITS=9),
            bridge_source=delayed_bridge,expected_failure='bridge protocol fault admitted same-edge owner request/output');result['cases'][key]=case
        lint=['verilator','--lint-only','--top-module','workstation_pcm_ddr_backend','-I'+str(output/'rate0_bounded_0'),
            str(ROOT/BACKEND),str(ROOT/DEPENDENCIES[0])]
        checked=subprocess.run(lint,capture_output=True,text=True,cwd=output,timeout=45)
        result['lint']=dict(argv=lint,returncode=checked.returncode,log=checked.stdout+checked.stderr)
        if checked.returncode:raise RuntimeError('Strict lint failed: '+result['lint']['log'])
        result['source_inputs_unchanged_during_run']=hashes=={name:sha((ROOT/name).read_bytes()) for name in names}
        if not result['source_inputs_unchanged_during_run']:raise ValueError('Frozen test input drift')
        result['passed']=True
    finally:
        (output/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output.resolve())
