#!/usr/bin/env python3
"""Compare the actual parent/new parsers cycle-for-cycle; never invoke EDA."""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[2]
PARSER='rtl/bluetooth/cpu_owner/ble_protocol_command.v'
PARENT_COMMIT='525ead19b244145dbb33b0b4c260488b2f43c2fa'
PARENT_SHA256='e27e1dea4a07888b205b998be6e3b29141365f64605afaad1799aaeaf7214078'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def ports(text):
    header=text[text.index(') (')+3:text.index(');\n    localparam')]
    found=[]
    for row in re.finditer(r'\b(input|output)\s+(?:wire\s+|reg\s+)?(\[[^]]+\])?\s*(.*?)(?=\binput\b|\boutput\b|$)',header,re.S):
        direction,width,names=row.groups()
        names=re.sub(r'//[^\n]*','',names)
        for name in names.split(','):
            name=name.strip()
            if name:
                if not re.fullmatch(r'\w+',name):raise ValueError('unknown port declaration '+name)
                found.append((direction,width or '',name))
    return found

def prepare_cell_comparison(out,original,current,interface,dependencies):
    """Emit two same-function component inputs; synthesis is a separate action."""
    identities={}
    device=json.loads((ROOT/'boards/custom_138k/pinout.json').read_text())['device']
    for name,text,style in [('before',original,'distributed_ram'),('after',current,'block_ram')]:
        directory=out/'cell-comparison'/name;directory.mkdir(parents=True)
        (directory/'ble_protocol_command.v').write_text(text)
        for source in dependencies:shutil.copyfile(source,directory/source.name)
        declarations=[f'{direction} wire {width} {port}' for direction,width,port in interface]
        wrapper='module ble_replay_resource_top('+',\n'.join(declarations)+');\n'
        wrapper+='ble_protocol_command #(.EXTERNAL_PCM(1),.CAPACITY_FRAMES(16384),.EXTERNAL_SEAL_PROTOCOL(1),'+\
            '.EXTERNAL_RAW_STORE(1),.RAW_DRAIN_TIMEOUT_CYCLES(5000000),'+\
            f'.CACHE_METADATA_RAM_STYLE("{style}")) endpoint('+\
            ','.join(f'.{port}({port})' for _,_,port in interface)+');\nendmodule\n'
        (directory/'top.sv').write_text(wrapper)
        (directory/'clock.sdc').write_text('create_clock -name metadata_clk -period 20.000 [get_ports {clk}]\n')
        commands=['set root [file dirname [file normalize [info script]]]','cd $root',
            f'set_device {device} -device_version C','set_option -synthesis_tool gowinsynthesis',
            'set_option -top_module ble_replay_resource_top',
            'set_option -output_base_name replay_metadata_'+name,'set_option -verilog_std sysv2017',
            'set_option -include_path $root','set_option -gen_verilog_sim_netlist 1',
            'set_option -timing_driven 1',
            *[f'add_file -type verilog [file join $root {file}]' for file in
                ['top.sv','ble_protocol_command.v',*[p.name for p in dependencies]]],
            'add_file -type sdc [file join $root clock.sdc]','run syn']
        (directory/'synthesis.tcl').write_text('\n'.join(commands)+'\n')
        identities[name]={str(p.relative_to(directory)):sha(p) for p in sorted(directory.iterdir()) if p.is_file()}
        compile_command=['iverilog','-g2012','-s','ble_replay_resource_top','-o',str(out/('cell-'+name+'.ivl')),
            *map(str,sorted(directory.glob('*.v'))),*map(str,sorted(directory.glob('*.sv')))]
        compiled=subprocess.run(compile_command,text=True,capture_output=True)
        (out/('cell-'+name+'-elaborate.log')).write_text(compiled.stdout+compiled.stderr)
        assert compiled.returncode==0,compiled.stdout+compiled.stderr
    result=dict(identity='cpu-replay-metadata-cell-compare-v1',source_sha256=identities,
        device=device,clock_hz=50000000,top='ble_replay_resource_top',capacity_frames=16384,
        external_pcm=True,external_raw_store=True,external_seal=True,
        differences=['parent/current parser storage implementation','metadata storage parameter'],
        unchanged_common_sources=[p.name for p in dependencies],
        after_expected_metadata_sdpb=3,metadata_payload_bits=2464,
        resource_fields_to_compare=['Logic','LUT','ALU','Register','RAM16','synthesis_BSRAM'],
        required_memory_audit='3 metadata SDPB: 32/32/16-bit, read bypass, same50MHz clock, address5, full byte masks; no distributed metadata remnants',
        both_actual_source_closures_elaborated=True,synthesis_performed=False,pnr=False,physical_CLS_measured=False,
        whole_workstation_comparison=False,hardware_operated=False)
    (out/'cell-comparison/inputs.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def run(output,reference=None,vendor=None,mutations=True):
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    before={p:sha(ROOT/p) for p in [PARSER,'rtl/bluetooth/cpu_owner/workstation_bluetooth.sv',
        'rtl/bluetooth/cpu_owner/workstation_ble_record_data_engine.sv',
        'rtl/bluetooth/cpu_owner/workstation_ble_record_data_service.sv',
        'rtl/services/workstation_business_mailbox.sv','rtl/memory/workstation_sdp.sv',
        'sim/services/tb_ble_replay_metadata_body.svh','sim/services/run_ble_replay_metadata.py',
        'boards/custom_138k/pinout.json']}
    if reference:
        raw=Path(reference).read_bytes()
    else:
        repo=ROOT.parents[3]
        raw=subprocess.check_output(['git','show',PARENT_COMMIT+':projects/138k/push2_workstation/usb_a/'+PARSER],cwd=repo)
    if hashlib.sha256(raw).hexdigest()!=PARENT_SHA256:raise ValueError('parent parser source identity drift')
    text=(ROOT/PARSER).read_text();reference_text=raw.decode()
    if (ROOT/'rtl/bluetooth/cpu_owner/workstation_bluetooth.sv').read_text().count(
            '.CACHE_METADATA_RAM_STYLE("block_ram")')!=1:
        raise ValueError('native CPU adapter must select the verified block metadata path')
    assert reference_text.count('module ble_protocol_command #(')==1
    (out/'reference.v').write_text(reference_text.replace('module ble_protocol_command #(',
        'module ble_protocol_command_reference #(',1))
    interface=ports(text);assert interface==ports(reference_text)
    declarations=[];maps={'n':[],'g':[]};comparisons=[]
    defaults=[]
    values={'clk':"0",'resetn':"0",'enable':"1",'business_owner_reset_ni':"1",
        'boot_id':"64'h1122334455667788",'att_value_limit':"185",'boot_valid':"1",
        'response_subscribed':"1",'control_open':"1",'source_ready_i':"1",'transfer_subscribed':"1"}
    for direction,width,name in interface:
        if direction=='input':
            declarations.append(f'reg {width} {name};')
            defaults.append(f'{name}={values.get(name,"0")};')
            for key in maps:maps[key].append(f'.{name}({name})')
        else:
            for key in maps:
                declarations.append(f'wire {width} {key}_{name};')
                maps[key].append(f'.{name}({key}_{name})')
            gate='n_response_valid && response_addr<n_response_length && ' if name=='response_data' else 'n_transfer_valid && ' if name=='transfer_data' else ''
            comparisons.append(f'if({gate}n_{name}!==g_{name})$fatal(1,"output mismatch {name} cycle=%0d",cycles);')
    (out/'compare_outputs.svh').write_text('\n'.join(comparisons)+'\n')
    (out/'input_defaults.svh').write_text('\n'.join(defaults)+'\n')
    bench='`timescale 1ns/1ps\nmodule tb;\n`ifdef WORKSTATION_SDP_VENDOR_SIM\nGSR GSR(.GSRI(1\'b1));\n`endif\n'+'\n'.join(declarations)+'\n'
    for module,instance,key,style in [('ble_protocol_command','dut','n','block_ram'),
        ('ble_protocol_command_reference','reference','g','distributed_ram')]:
        bench+=f'{module} #(.EXTERNAL_PCM(1),.CAPACITY_FRAMES(16),.CACHE_METADATA_RAM_STYLE("{style}")) {instance}('+','.join(maps[key])+');\n'
    bench+='`include "tb_ble_replay_metadata_body.svh"\nendmodule\n'
    (out/'tb.sv').write_text(bench)
    shutil.copyfile(ROOT/'sim/services/tb_ble_replay_metadata_body.svh',out/'tb_ble_replay_metadata_body.svh')
    dependencies=[ROOT/'rtl/bluetooth/cpu_owner/workstation_ble_record_data_engine.sv',
        ROOT/'rtl/bluetooth/cpu_owner/workstation_ble_record_data_service.sv',
        ROOT/'rtl/services/workstation_business_mailbox.sv',ROOT/'rtl/memory/workstation_sdp.sv']
    commands=[]
    def execute(source,tag,primitive=None,negative=False):
        command=['iverilog','-g2012','-s','tb','-I',str(out),'-o',str(out/tag),str(out/'tb.sv'),
            str(source),str(out/'reference.v'),*map(str,dependencies)]
        if primitive:command[1:1]=['-DWORKSTATION_SDP_VENDOR_SIM'];command.append(str(primitive))
        compiled=subprocess.run(command,text=True,capture_output=True);commands.append(command)
        (out/(tag+'-compile.log')).write_text(compiled.stdout+compiled.stderr)
        assert compiled.returncode==0,compiled.stdout+compiled.stderr
        command=['vvp',str(out/tag)];commands.append(command)
        tested=subprocess.run(command,cwd=out,text=True,capture_output=True,timeout=60)
        stdout=tested.stdout+tested.stderr;(out/(tag+'-run.log')).write_text(stdout)
        if negative:
            assert tested.returncode!=0 and 'FATAL:' in stdout,(tag,stdout)
            return dict(rejected=True,returncode=tested.returncode,stdout=stdout)
        assert tested.returncode==0 and 'PASS real parser metadata equivalence' in stdout,stdout
        m=re.search(r'checks=(\d+) cycles=(\d+) bytes=(\d+) hit_mask=ffffffff',stdout);assert m,stdout
        return dict(passed=True,half_cycle_comparisons=int(m[1]),cycles=int(m[2]),compared_bytes=int(m[3]),
            all32_slots_hit=True,stdout=stdout)
    results={'behavioral':execute(ROOT/PARSER,'behavioral')}
    vendor=Path(vendor or os.environ.get('GOWIN_GW5A_SIMLIB',
        '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/simlib/gw5a/prim_sim.v'))
    if not vendor.is_file():raise ValueError('official GW5A simulation library is required')
    results['official_sdpb']=execute(ROOT/PARSER,'vendor-sdp',vendor)
    mutants={
        'stale-prefetch':('lookup_slot+5\'d1','lookup_slot'),
        'ignore-validity':('wire metadata_hit=cache_valid[lookup_slot] &&','wire metadata_hit='),
        'truncate-time':('.write_data_i(elapsed_ms)',".write_data_i({16'd0,elapsed_ms[15:0]})"),
        'wrong-length':('matched_reply_length<=lengths[12:6]','matched_reply_length<=lengths[11:5]')}
    failures={}
    if mutations:
        for name,(old,new) in mutants.items():
            assert text.count(old)==1,(name,'mutant anchor drift')
            path=out/(name+'.v');path.write_text(text.replace(old,new))
            failures[name]=execute(path,name,negative=True)
    comparison=prepare_cell_comparison(out,reference_text,text,interface,dependencies)
    assert before=={p:sha(ROOT/p) for p in before}
    evidence=dict(schema=1,identity='cpu-replay-metadata-bsram-v1',passed=True,
        parent_commit=PARENT_COMMIT,parent_parser_sha256=PARENT_SHA256,source_sha256=before,
        official_gw5a_simlib=dict(path=str(vendor),sha256=sha(vendor)),results=results,mutations=failures,
        commands=commands,cell_comparison_prepared=comparison,stored_payload_bits=77*32,physical_source_blocks=[
            dict(name='ids',data_width=32,address_width=5),dict(name='times',data_width=32,address_width=5),
            dict(name='sizes',data_width=16,address_width=5,used_width=13)],
        reset_policy='RAM unchanged; reset/disable clears32 valid bits and session',
        read_write_conflict='mutually exclusive parser states SESSION/LOOKUP vs CRC publication',
        external_latency_changed=False,capacity_changed=False,protocol_changed=False,
        business_owner_changed=False,synthesis_performed=False,pnr=False,hardware_operated=False)
    (out/'verification.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(dict(passed=True,results=results,mutants_rejected=len(failures)),indent=2))
    return evidence

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reference',type=Path);p.add_argument('--vendor',type=Path)
    a=p.parse_args();run(a.output,a.reference,a.vendor)
