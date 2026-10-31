#!/usr/bin/env python3
"""Real C owner and API linked to the actual APB/parser/CRC/raw-DDR RTL."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,re,shlex
ROOT=Path(__file__).resolve().parents[2]
def run(output,diagnostics=False):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(ROOT))
    from tools.workstation_baselines import load_baseline
    from tools.workstation_resource_timing import apb
    baseline=load_baseline(ROOT,'resource_rework_route0')
    original=baseline.read_bytes('src/migration/gw138k_apb_cdc.sv')
    cdc=output/'gw138k_apb_cdc.sv';cdc.write_text(apb(original.decode()))
    cpp=Path(__file__).with_name('ae350_ble_business_cosim.cpp')
    files=[Path(__file__).with_name('ae350_ble_business_cosim.sv'),cdc,
        *[ROOT/'rtl/bluetooth/cpu_owner'/name for name in ('ble_protocol_command.v',
        'workstation_ble_record_data_engine.sv','workstation_ble_record_data_service.sv')],
        ROOT/'rtl/services/workstation_business_mailbox.sv',ROOT/'rtl/memory/workstation_ble_raw_ddr_store.sv',
        ROOT/'rtl/memory/workstation_recording_ddr_native_bridge.sv',ROOT/'rtl/memory/workstation_sdp.sv',
        ROOT/'rtl/music/music_async_fifo.sv']
    cfiles=[ROOT/'firmware/ae350'/name for name in ('business_mailbox.c','recording_service.c','ble_business_owner.c')]
    tracked=[*files,*cfiles,cpp,Path(__file__),*[ROOT/'firmware/ae350'/n for n in ('business_mailbox.h','recording_service.h','ble_business_owner.h','audio_services.h')],ROOT/'tools/workstation_resource_timing.py',ROOT/'tools/workstation_bluetooth_ddr.py']
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
    objects=[];commands=[];captured_stderr={}
    def execute(command,name,timeout=180):
        commands.append(command)
        result=subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
        captured_stderr[name]=result.stderr
        combined=result.stdout+('\nSTDERR\n'+result.stderr if result.stderr else '')
        (output/(name+'.log')).write_text(combined)
        if result.returncode:raise RuntimeError(name+' failed: '+ '\n'.join(line for line in combined.splitlines() if line.startswith(('FAIL ','facts ','engine ')))+'; log='+str(output/(name+'.log')))
        return result.stdout
    include=ROOT/'firmware/ae350'
    diagnostic_flags=['-DA138_BLE_BUSINESS_DIAGNOSTICS']if diagnostics else[]
    for p in cfiles:
        target=output/(p.stem+'.o');objects.append(target)
        execute(['cc','-std=c11','-O2','-DA138_BLE_BUSINESS',*diagnostic_flags,'-Wall','-Wextra','-Werror','-I'+str(include),'-c',str(p),'-o',str(target)],p.stem)
    execute(['verilator','--cc','--exe','--build','--timing','-Wno-fatal','--top-module','ae350_ble_business_cosim',
        '--Mdir',str(output/'obj'),'-CFLAGS',' '.join(['-I'+str(include),*diagnostic_flags]),'-LDFLAGS',' '.join(map(str,objects)),
        *map(str,files),str(cpp)],'compile')
    result=execute([str(output/'obj/Vae350_ble_business_cosim')],'run',60)
    # Reuse the compiled real RTL model, replacing only one maintained C
    # translation unit. Each runtime mutant must fail the same behavioral suite.
    mutants={
        'allow_full_task_slot':('return !t->valid ||','return 1 || !t->valid ||'),
        'succeed_before_first_frame':('t->opcode=(uint8_t)op;t->state=1;','t->opcode=(uint8_t)op;t->state=2;'),
        'skip_object_identity':('o->pending_object=o->object_counter+1u;','o->pending_object=o->object_counter+2u;'),
        'remove_uncertain_deadline':('o->fault=A138_OWNER_SUBMIT_UNOBSERVED;','o->fault=0;'),
        'remove_uncertain_completion_deadline':('o->fault=A138_OWNER_COMPLETE_UNOBSERVED;','o->fault=0;'),
        'retire_torn_observation':('/* STALE is an advisory torn snapshot, not proof this key was retired. */','else if(result==A138_BM_STALE)o->phase=IDLE;'),
        'ignore_ack_crc':('crc==t->pending_crc','1'),
        'ignore_combined_crc':('word(p+12)!=t->pending_crc','0'),
        'commit_combined_before_range':('if((!combined && offset!=t->offset)','if(combined)t->offset=offset;\n            if((!combined && offset!=t->offset)'),
        'ignore_confirmed_offset':('(!combined && offset!=t->offset)','0'),
        'remove_transfer_timeout':('>=30000u','>=UINT32_MAX'),
        'replay_mutates_cursor':('if(!o->active_replay && (r->flags&2u)) {','if(r->flags&2u) {'),
        'skip_replay_object_identity':('state!=4 || o->request_facts.object_id!=o->facts.object_id','state!=4'),
        'ignore_extended_limit':('return t->extended_limit;','return 8112;'),
        'commit_unstarted_read':('if(!o->active_replay && (r->flags&2u)) {','if(!o->active_replay) {'),
    }
    mutation_results={};owner_source=cfiles[-1].read_text()
    link=next(line for line in (output/'compile.log').read_text().splitlines() if line.startswith('c++ ') and line.rstrip().endswith(' -o Vae350_ble_business_cosim'))
    for name,(old,new) in mutants.items():
        if owner_source.count(old)!=1:raise ValueError('mutant anchor drift: '+name)
        source=output/(name+'.c');source.write_text(owner_source.replace(old,new))
        obj=output/(name+'.o')
        execute(['cc','-std=c11','-O2','-DA138_BLE_BUSINESS',*diagnostic_flags,'-Wall','-Wextra','-Werror','-I'+str(include),'-c',str(source),'-o',str(obj)],name+'-compile')
        command=shlex.split(link);command=[str(obj) if arg==str(objects[-1]) else arg for arg in command]
        command[command.index('-o')+1]=str(output/name)
        built=subprocess.run(command,cwd=output/'obj',text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
        (output/(name+'-link.log')).write_text(built.stdout)
        if built.returncode:raise RuntimeError('mutant link failed: '+name)
        failed=subprocess.run([str(output/name)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
        (output/(name+'-run.log')).write_text(failed.stdout)
        mutation_results[name]=dict(rejected=failed.returncode!=0 and 'FAIL ' in failed.stdout,returncode=failed.returncode)
        if not mutation_results[name]['rejected']:raise RuntimeError('behavioral mutant survived: '+name)

    # Same packet driver, source schedule, actual raw store and immutable DDR
    # bytes, with the locked legacy recorder as the behavioral reference.
    from tools import workstation_bluetooth_ddr as legacy
    repository=ROOT.parents[3]
    generated=output/'legacy';generated.mkdir()
    execute([sys.executable,str(repository/'projects/25k/example/RTL8723DS_PROTOCOL/prepare_adapted.py'),
        '--output',str(generated)],'legacy-gatt')
    original_inputs={}
    for name in legacy.INPUT_SHA256:
        source=(generated/name if name=='bt_gatt.v' else ROOT/'rtl/bluetooth'/name if name=='workstation_bluetooth.sv'
            else repository/'projects/25k/example/RTL8723DS_PROTOCOL'/('adaptations' if name=='bt_verilog_core.v' else 'rtl')/name)
        original_inputs[name]=source.read_bytes()
    old=legacy.adapt_sources(original_inputs)
    for name,data in old.items():(generated/name).write_bytes(data if isinstance(data,bytes) else data.encode())
    fixture=files[0].read_text()
    fixture=re.sub(r' \.business_owner_reset_ni\(command_reset\),.*? \.business_response_data_o\(bus_response_data\),\n','',fixture,flags=re.S)
    reference=generated/'ae350_ble_business_cosim.sv';reference.write_text(fixture)
    old_files=[reference,cdc,generated/'ble_protocol_command.v',generated/'ble_recording.v',*files[6:]]
    execute(['verilator','--cc','--exe','--build','--timing','-Wno-fatal','--top-module','ae350_ble_business_cosim',
        '--Mdir',str(output/'golden-obj'),'-CFLAGS',' '.join(['-DGOLDEN','-I'+str(include),*diagnostic_flags]),'-LDFLAGS',' '.join(map(str,objects)),
        *map(str,old_files),str(cpp)],'golden-compile')
    golden=execute([str(output/'golden-obj/Vae350_ble_business_cosim')],'golden-run',60)
    wire=lambda text:[line for line in text.splitlines() if line.startswith(('WIRE ','BLOCK '))]
    comparison=wire(result)==wire(golden)
    check_groups=[dict(name=m.group(1),checks=int(m.group(2))) for line in result.splitlines()
        if (m:=re.fullmatch(r'PASS (.*): (\d+) checks(?:;.*)?',line))]
    if len(check_groups)!=12:raise RuntimeError('behavioral check summary drift')
    after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
    evidence=dict(schema=1,passed=before==after and 'PASS real C/APB/parser/raw-DDR owner:' in result and comparison,
        input_sha256=before,inputs_unchanged=before==after,commands=commands,stdout=result,mutations=mutation_results,
        golden_stdout=golden,stderr=captured_stderr,golden_wire_equal=comparison,compared_messages=len(wire(result)),
        behavioral_checks=sum(group['checks'] for group in check_groups),check_groups=check_groups,
        clock_fixture=dict(timeprecision_ps=1,cpp_step_ps=1000,control_period_ns=20,memory_period_ns=14,
            historical_first_batch_control_period_ps=20,historical_first_batch_memory_period_ns=14,
            reconnect_hello_input_elapsed_ms=65536,wire_bytes_normalized=False),
        golden_input_sha256={n:hashlib.sha256(data).hexdigest() for n,data in original_inputs.items()},
        business_diagnostics_compiled=diagnostics,synthesis=False,pnr=False,hardware_tested=False,profile_selected=False)
    (output/'verification.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(dict(passed=evidence['passed'],compared_messages=evidence['compared_messages'],golden_wire_equal=comparison,evidence=str(output/'verification.json'))))
    if not evidence['passed']:raise RuntimeError('C business source drift, execution or golden-wire comparison failed')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--diagnostics',action='store_true',help='compile the selected business diagnostic counters in both C and C++')
    args=parser.parse_args();run(args.output,args.diagnostics)
