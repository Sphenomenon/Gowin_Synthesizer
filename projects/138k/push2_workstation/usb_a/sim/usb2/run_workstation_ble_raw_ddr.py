#!/usr/bin/env python3
"""Default-off checked BLE DDR adaptation: real owner, protocol and staged chain."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
REPOSITORY=ROOT.parents[3]
PROTOCOL=REPOSITORY/'projects/25k/example/RTL8723DS_PROTOCOL'
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'sim'))
from tools import workstation_bluetooth,workstation_bluetooth_ddr as ddr,workstation_pinout
from test_workstation_pinout import fixture
from ble_seal_protocol_fixture import build


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_wires():
    return '\n'.join(line.strip().replace('input wire','wire').replace('output wire','wire').rstrip(',')+';'
        for line in ddr.PORTS.splitlines() if line.strip() and not line.strip().startswith('//'))+'\n'


def storage_fixture():
    """Simulation only; the actual unmodified store/native bridge are compiled."""
    ports=ddr.PORTS.replace('output wire','INPUT').replace('input wire','output wire').replace('INPUT','input wire')
    binds=','.join('.'+signal[:-1]+('i' if signal.endswith('_o') else 'o')+'(raw_'+signal+')' for signal in ddr.SIGNALS)
    return '''`timescale 1ns/1ps
module ble_raw_ddr_fixture(input wire clk,resetn,'''+ports+''');
    reg memory_clk=0;always #7 memory_clk=~memory_clk;
    wire slot_valid,slot_ready,native_accept,write_enable;
    wire [28:0] address;wire [255:0] write_data;wire [31:0] mask;
    reg response=0;reg [255:0] response_data=0;
    workstation_ble_raw_ddr_store #(.CAPACITY_FRAMES(16384)) store(
        .clk_i(clk),.memory_clk_i(memory_clk),.rst_ni(resetn),'''+binds+''',
        .slot_valid_o(slot_valid),.slot_ready_i(slot_ready),.native_accept_i(native_accept),.ddr_write_o(write_enable),
        .ddr_address_o(address),.ddr_data_o(write_data),.ddr_mask_o(mask),.read_response_i(response),.read_data_i(response_data),
        .transport_fault_i(1'b0),.native_protocol_fault_o());
    reg submitted=0,read_pending=0,write_q=0,native=0;
    reg [28:0] address_q=0,read_address_q=0;
    reg [255:0] data_q=0;reg [31:0] mask_q=0;
    integer delay=0,read_delay=0,i;
    reg [255:0] memory[0:2047];
    assign slot_ready=!submitted && !read_pending;
    assign native_accept=native;
    always @(negedge memory_clk)begin
        native=resetn && submitted && delay==0;
        response=resetn && read_pending && read_delay==0;
        response_data=memory[read_address_q>>3];
    end
    always @(posedge memory_clk or negedge resetn)begin
        if(!resetn)begin submitted<=0;read_pending<=0;delay<=0;read_delay<=0;end
        else begin
            if(slot_valid && slot_ready)begin
                submitted<=1;address_q<=address;write_q<=write_enable;data_q<=write_data;mask_q<=mask;delay<=2;
            end
            if(submitted && delay>0)delay<=delay-1;
            if(native)begin
                submitted<=0;
                if(write_q)begin for(i=0;i<32;i=i+1)if(!mask_q[i])memory[address_q>>3][i*8+:8]<=data_q[i*8+:8];end
                else begin read_pending<=1;read_address_q<=address_q;read_delay<=3;end
            end
            if(read_pending && read_delay>0)read_delay<=read_delay-1;
            if(response)read_pending<=0;
        end
    end
endmodule
'''


def protocol_fixture():
    text=build(PROTOCOL/'tests/tb_protocol_recording.sv')
    text=ddr.replace(text,'.EXTERNAL_SEAL_PROTOCOL(1)) dut',
        '.EXTERNAL_SEAL_PROTOCOL(1),.EXTERNAL_RAW_STORE(1),.RAW_DRAIN_TIMEOUT_CYCLES(50000)) dut')
    anchor='    ble_protocol_command #('
    text=ddr.replace(text,anchor,raw_wires()+'    ble_raw_ddr_fixture raw_fixture(.clk(clk),.resetn(resetn),'+ddr.CONNECTIONS.rstrip().rstrip(',')+');\n'+anchor)
    anchor='        .pcm_valid_i(pcm_valid),.pcm_pair_i(pcm),.source_ready_i(source_ready),.source_fault_i(1\'b0),\n'
    return ddr.replace(text,anchor,anchor+ddr.CONNECTIONS)


def chain_fixture():
    text=Path(__file__).with_name('tb_workstation_ble_seal_chain.sv').read_text()
    text=ddr.replace(text,'.EXTERNAL_SEAL_PROTOCOL(1),',
        '.EXTERNAL_SEAL_PROTOCOL(1),.EXTERNAL_RAW_STORE(1),.RAW_DRAIN_TIMEOUT_CYCLES(50000),')
    anchor='    workstation_bluetooth #('
    text=ddr.replace(text,anchor,raw_wires()+'    ble_raw_ddr_fixture raw_fixture(.clk(clk),.resetn(rst_n),'+ddr.CONNECTIONS.rstrip().rstrip(',')+');\n'+anchor)
    anchor='        .seal_hold_i(seal_hold),.seal_request_i(seal_request),.seal_ready_o(ready),\n'
    text=ddr.replace(text,anchor,anchor+ddr.CONNECTIONS)
    anchor='        if(dut.u_core.application.command_endpoint.recording.record_state!=1)'
    text=ddr.replace(text,anchor,'        wait(dut.u_core.application.command_endpoint.recording.record_state==1);@(negedge clk);\n'+anchor)
    return text


def run(output,raw_source_root):
    output.mkdir(parents=True,exist_ok=False)
    stage=output/'stage';stage.mkdir();(stage/'pinout').mkdir();(stage/'rtl/bluetooth').mkdir(parents=True)
    profile,payloads,core=fixture();netlists={role:workstation_pinout.Netlist(payload) for role,payload in payloads.items()}
    plan=workstation_pinout.resolve(profile,netlists,core)
    with patch.object(workstation_pinout,'load_sources',return_value=(netlists,{})):
        legacy=workstation_bluetooth.prepare(ROOT,stage,stage,stage/'pinout',plan)
    shutil.copyfile(ROOT/'rtl/bluetooth/workstation_bluetooth.sv',stage/'rtl/bluetooth/workstation_bluetooth.sv')
    raw_sources={name:(raw_source_root/name if name in (ddr.RAW_STORE_PATH,ddr.RAW_CONTRACT_PATH) else ROOT/name) for name in (
        ddr.RAW_STORE_PATH,ddr.RAW_CONTRACT_PATH,'rtl/memory/workstation_sdp.sv',
        'rtl/music/music_async_fifo.sv','rtl/memory/workstation_recording_ddr_native_bridge.sv')}
    maintained=[Path(__file__),Path(ddr.__file__),Path(__file__).with_name('tb_workstation_ble_raw_ddr.sv'),
        Path(__file__).with_name('ble_seal_protocol_fixture.py'),Path(__file__).with_name('tb_workstation_ble_seal_chain.sv'),
        Path(__file__).with_name('tb_workstation_ble_recording.sv'),
        ROOT/'rtl/bluetooth/WORKSTATION_BLE_RAW_DDR_ADAPTATION.md',
        ROOT/'tools/workstation_bluetooth.py',ROOT/'tools/workstation_pinout.py',ROOT/'sim/test_workstation_pinout.py',
        PROTOCOL/'tests/tb_protocol_recording.sv',*raw_sources.values(),
        *[REPOSITORY/name for name in legacy['source_snapshot_sha256']],
        *[REPOSITORY/name for name in ddr.UPSTREAM_SHA256]]
    before={str(path):sha(path) for path in maintained}
    identity=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()
    result=dict(schema=1,passed=False,identity='native-ble-raw-ddr-adaptation-v1-'+identity[:16],
        source_set_sha256=identity,input_sha256=before,legacy_prepare=legacy,
        validation_stage='offline-real-BLE-object-owner-store-native-DDR-protocol-five-layer-chain',
        synthesis=False,pnr=False,physical_cdc_accepted=False,hardware_tested=False,
        sram_programmed=False,flash_written=False,deployment_allowed=False,cases={},negative_controls={})
    # A self-contained source closure exercises prepare/verify without installing
    # another agent's not-yet-integrated source in this checkout.
    closure=output/'closure';mirror_root=closure/'projects/138k/push2_workstation/usb_a'
    for name in ddr.UPSTREAM_SHA256:
        target=closure/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REPOSITORY/name,target)
    for name in (ddr.RAW_STORE_PATH,ddr.RAW_CONTRACT_PATH):
        target=mirror_root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(raw_sources[name],target)
    inputs={name:(stage/path).read_bytes() for name,path in ddr.STAGED_PATHS.items()}
    snapshot={str(path):sha(path) for path in stage.rglob('*') if path.is_file()}
    disabled=ddr.prepare(mirror_root,stage)
    if disabled['enabled'] or disabled['modified_files'] or snapshot!={str(p):sha(p) for p in stage.rglob('*') if p.is_file()}:
        raise ValueError('default-off adaptation changed bytes')
    result['disabled_prepare_byte_preserved']=True
    result['prepare']=ddr.prepare(mirror_root,stage,enabled=True)
    result['verify_prepared']=ddr.verify_prepared(mirror_root,stage,result['prepare'])
    outputs={name:(stage/path).read_bytes() for name,path in ddr.STAGED_PATHS.items()}
    (output/'prepare.json').write_text(json.dumps(result['prepare'],indent=2)+'\n')
    fixture_path=output/'raw_ddr_fixture.sv';fixture_path.write_text(storage_fixture())
    protocol=output/'tb_ble_raw_protocol.sv';protocol.write_text(protocol_fixture())
    chain=output/'tb_ble_raw_chain.sv';chain.write_text(chain_fixture())
    result['generated_fixture_sha256']={str(p.relative_to(output)):sha(p) for p in (fixture_path,protocol,chain)}
    sources=[raw_sources[name] for name in raw_sources if name.endswith('.sv')]
    def execute(name,top,files,cwd=ROOT,expected=None,parameters=None):
        argv=['iverilog','-g2012','-I',str(stage/'native_bluetooth'),'-s',top,'-o',str(output/(name+'.vvp'))]
        argv += ['-P'+top+'.'+key+'='+str(value) for key,value in (parameters or {}).items()]
        argv += list(map(str,files))
        compiled=subprocess.run(argv,cwd=cwd,capture_output=True,text=True,timeout=60)
        log=compiled.stdout+compiled.stderr;(output/(name+'_compile.log')).write_text(log)
        if compiled.returncode or log.strip():raise RuntimeError(name+' compile: '+log)
        run=subprocess.run(['vvp',str(output/(name+'.vvp'))],cwd=cwd,capture_output=True,text=True,timeout=90)
        log=run.stdout+run.stderr;(output/(name+'_run.log')).write_text(log)
        entry=dict(compile_argv=argv,returncode=run.returncode,run_log_sha256=sha(output/(name+'_run.log')),
            compile_log_sha256=sha(output/(name+'_compile.log')),metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',log)})
        if expected:
            entry.update(rejected=run.returncode!=0 and expected in log,expected_failure=expected)
            if not entry['rejected']:raise RuntimeError(name+' negative escaped: '+log)
            print('PASS rejected '+name+': '+expected,flush=True);result['negative_controls'][name]=entry
        else:
            if run.returncode or 'PASS ' not in log:raise RuntimeError(name+': '+log)
            print(log,end='',flush=True);result['cases'][name]=entry
    def rejects(name,callback):
        try:callback()
        except (ValueError,FileNotFoundError) as error:
            result['negative_controls'][name]=dict(rejected=True,error=str(error));return
        raise ValueError('negative control escaped: '+name)
    try:
        recorder=stage/'native_bluetooth/ble_recording.v';command=stage/'native_bluetooth/ble_protocol_command.v'
        execute('legacy_live','tb_workstation_ble_recording',[Path(__file__).with_name('tb_workstation_ble_recording.sv'),recorder])
        tb=Path(__file__).with_name('tb_workstation_ble_raw_ddr.sv')
        execute('owner_async_memory','tb_workstation_ble_raw_ddr',[tb,recorder,*sources])
        execute('owner_100mhz_memory','tb_workstation_ble_raw_ddr',[tb,recorder,*sources],parameters=dict(MEM_HALF=5))
        execute('real_protocol','tb_protocol_recording',[protocol,fixture_path,command,recorder,*sources],PROTOCOL)
        chain_files=[chain,fixture_path,stage/'rtl/bluetooth/workstation_bluetooth.sv',
            *[stage/path for path in legacy['sources']],*sources]
        execute('staged_five_layer_chain','tb_workstation_ble_seal_chain',chain_files,stage)
        # Each mutant removes a safety boundary exercised by real transactions.
        mutations=(
            ('early_ready',"if(EXTERNAL_RAW_STORE)begin raw_closing<=1;record_state<=3;if(!stop_pending)stop_reason<=2;end",
             "if(EXTERNAL_RAW_STORE)begin raw_closing<=1;record_state<=4;if(!stop_pending)stop_reason<=2;end",'READY requires actual native drain'),
            ('late_ready_after_timeout','if(record_state!=5 && enable && source_ready_i && !source_fault_i && !raw_fault_i && !raw_expired &&',
             'if(enable && source_ready_i && !source_fault_i && !raw_fault_i &&','late native drain cannot resurrect READY'),
            ('source_failure_overwritten','if(record_state!=5 && enable && source_ready_i && !source_fault_i && !raw_fault_i && !raw_expired &&',
             'if(record_state!=5 && !raw_fault_i && !raw_expired &&','same-edge source loss outranks native-drain READY'),
            ('reuse_old_cache','C_RAW_FETCH_REQ: if(raw_fetch_valid_o && raw_fetch_ready_i)begin',
             'C_RAW_FETCH_REQ: if(raw_cache_valid_i)begin raw_cache_owned<=1;state<=C_BLOCK_PREP;end else if(raw_fetch_valid_o && raw_fetch_ready_i)begin',
             'command terminal/status'),
            ('clear_caller_lifetime','else begin if(!EXTERNAL_RAW_STORE || state!=C_RAW_CLEAR)state<=C_IDLE;transfer_valid<=0;end',
             'else begin state<=C_IDLE;transfer_valid<=0;end','accepted CLEAR survives disconnected observer'),
        )
        for name,anchor,replacement,expected in mutations:
            mutant_text=ddr.replace(recorder.read_text(),anchor,replacement)
            if name=='late_ready_after_timeout':
                # Both guards are intentional: remove the terminal latch AND
                # its saturated-timeout guard to recreate late promotion.
                mutant_text=ddr.replace(mutant_text,'(raw_expired && raw_waiting) ||',"1'b0 ||")
            mutant=output/(name+'.v');mutant.write_text(mutant_text)
            execute(name,'tb_workstation_ble_raw_ddr',[tb,mutant,*sources],expected=expected)
        disconnected=output/'bt_gatt_disconnected.v'
        disconnected.write_text(ddr.replace((stage/'native_bluetooth/bt_gatt.v').read_text(),
            '.raw_close_valid_o(raw_close_valid_o),','.raw_close_valid_o(),'))
        execute('missing_layer_close','tb_workstation_ble_seal_chain',
            [disconnected if path==stage/'native_bluetooth/bt_gatt.v' else path for path in chain_files],stage,
            expected='staged chain seal timeout')
        for name in inputs:
            bad=dict(inputs);bad[name]=bad[name]+b'\n'
            rejects('input_drift_'+name,lambda bad=bad:ddr.adapt_sources(bad))
        rejects('input_inventory',lambda:ddr.adapt_sources({}))
        rejects('anchor_drift',lambda:ddr.recorder(inputs['ble_recording.v'].decode().replace('    reg [3:0] state;','    reg [4:0] state;')))
        rejects('protected_codec',lambda:ddr.protected_regions(inputs['ble_recording.v'].replace(b'module ble_rice_encoder',b'module bad_rice_encoder')))
        for name,path in ddr.STAGED_PATHS.items():
            target=stage/path;target.write_bytes(outputs[name]+b'\n')
            rejects('output_tamper_'+name,lambda:ddr.verify_prepared(mirror_root,stage,result['prepare']))
            forged=copy.deepcopy(result['prepare']);forged['output_sha256'][name]=sha(target)
            rejects('forged_output_evidence_'+name,lambda:ddr.verify_prepared(mirror_root,stage,forged))
            target.write_bytes(outputs[name])
        raw_path=mirror_root/ddr.RAW_STORE_PATH;raw_bytes=raw_path.read_bytes();raw_path.write_bytes(raw_bytes+b'\n')
        rejects('raw_store_tamper',lambda:ddr.verify_prepared(mirror_root,stage,result['prepare']));raw_path.write_bytes(raw_bytes)
        contract_path=mirror_root/ddr.RAW_CONTRACT_PATH;contract_bytes=contract_path.read_bytes();contract_path.write_bytes(contract_bytes+b'\n')
        rejects('raw_contract_tamper',lambda:ddr.verify_prepared(mirror_root,stage,result['prepare']));contract_path.write_bytes(contract_bytes)
        for name,path in ddr.STAGED_PATHS.items():(stage/path).write_bytes(inputs[name])
        upstream_path=closure/next(iter(ddr.UPSTREAM_SHA256));upstream=upstream_path.read_bytes();upstream_path.write_bytes(upstream+b'\n')
        rejects('upstream_tamper_before_publication',lambda:ddr.prepare(mirror_root,stage,enabled=True))
        if any((stage/path).read_bytes()!=inputs[name] for name,path in ddr.STAGED_PATHS.items()):raise ValueError('failed prepare partially published')
        result['failed_prepare_published_no_bytes']=True;upstream_path.write_bytes(upstream)
        for name,path in ddr.STAGED_PATHS.items():(stage/path).write_bytes(outputs[name])
        result['final_verify']=ddr.verify_prepared(mirror_root,stage,result['prepare'])
        result['source_inputs_unchanged_during_run']=before=={p:sha(Path(p)) for p in before}
        if not result['source_inputs_unchanged_during_run']:raise ValueError('input drift during run')
        result['protected_region_sha256']=ddr.protected_regions(recorder.read_bytes())
        result['limits']='Real raw store/native DDR handshake, BLE framing/CRC/cache and five layers; chain forces BLE link initialization/connection and direct command injection only. Native DDR model and shortened endpoint test budget; no physical RAM/CDC/timing, synthesis, P&R, board or deployment acceptance.'
        result['passed']=True
        print('PASS checked source/output/evidence negative controls='+str(len(result['negative_controls'])),flush=True)
    finally:(output/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--raw-source-root',type=Path,default=ROOT,help='usb_a root containing the sealed raw store/contract')
    args=parser.parse_args();run(args.output.resolve(),args.raw_source_root.resolve())
