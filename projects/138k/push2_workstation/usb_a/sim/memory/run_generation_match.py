#!/usr/bin/env python3
"""Actual W generation-match capture: raw-store twins, no EDA or board use."""
from pathlib import Path
import sys,re,json,hashlib,importlib.util,argparse
u=Path(__file__).resolve().parents[2];sys.path.insert(0,str(u))
from tools import workstation_w_generation_match as selection
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();stage=args.stage.resolve();out=args.output.resolve()
out.mkdir(exist_ok=False,parents=True)
f=stage/selection.SOURCE;new=f.read_text();old=selection.restore(new)
assert selection.digest(new)==selection.SELECTED_SHA256
count=4
(out/'candidate.sv').write_text(new);(out/'reference.sv').write_text(old.replace('module workstation_ble_raw_ddr_store #(','module workstation_ble_raw_ddr_store_reference #(',1))
spec=importlib.util.spec_from_file_location('raw_twins',u/'sim/memory/prove_ble_raw_start_factor.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
ports,states,nets=h.inventories(old);ports={k:v for k,v in ports.items()if k not in('native_fault_probe_i','response_fault_probe_i')}
nba=set(re.findall(r'\b(\w+)(?:\[[^]\n]+\])?\s*<=',old))
for lhs in re.findall(r'\{([^}]+)\}\s*<=',old):nba.update(re.findall(r'\b\w+\b',lhs))
states=[s for s in states if s in nba and s not in('valid','payload')]
tb,inventory=h.twin_bench(old,ports,states,[])
for instance in('dut','reference'):
 for name,value in set(re.findall(r'\bforce\s+'+instance+r'\.(memory_generation)\s*=([^;]+);',tb)):
  token='force '+instance+'.'+name+'='+value+';';tb=tb.replace(token,token+'force '+instance+'.memory_generation_successor=('+value+")+32'd1;")
 tb=tb.replace('release '+instance+'.memory_generation;','release '+instance+'.memory_generation;release '+instance+'.memory_generation_successor;')
 match=re.search(r'workstation_ble_raw_ddr_store(?:_reference)? #\((.*?)\) '+instance+r'\((.*?)\);',tb,re.S);assert match;d=dict(re.findall(r'\.(\w+)\(([^()]*)\)',match[2]));t=d['transport_fault_i'];a=d['native_accept_i'];z=d['read_response_i'];extra=f",.native_fault_probe_i(({t}===1'b0)?{a}:~{a}),.response_fault_probe_i(({t}===1'b0)?{z}:~{z})";tb=tb[:match.end()-2]+extra+tb[match.end()-2:]
tb=tb.replace('    reg clk=0,memory_clk=0,rst_n=0,memory_run=1;', '''    reg clk=0,memory_clk=0,rst_n=0,memory_run=1;
    always @(negedge memory_clk)if(rst_n && dut.memory_command_start)begin
        if(dut.memory_next_generation_match !== (reference.memory_command_generation==reference.memory_generation_successor))$fatal(1,"captured successor compare stale");
        if(dut.memory_current_generation_match !== (reference.memory_command_generation==reference.memory_generation))$fatal(1,"captured current compare stale");
    end''',1)
assert 'captured successor compare stale'in tb
(out/'twin.sv').write_text(tb)
deps=[stage/p for p in('rtl/memory/workstation_sdp.sv','rtl/music/music_async_fifo.sv','rtl/memory/workstation_recording_ddr_native_bridge.sv')];results={}
for capture in(0,1):
 for half in(5,7,11):
  name=f'capture{capture}-mem{half}';results[name]=h.simulate(out,name,[out/'candidate.sv',out/'reference.sv',*deps,out/'twin.sv'],'tb_ble_raw_ddr_store',[('CAPTURE_COMMAND',capture),('MEM_HALF',half)],timeout=120);print(name,'PASS',flush=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
r={'passed':True,'diagnostic_only':False,'production_selected':True,'start_successor_comparisons':7,'fetch_current_comparisons':count,'added_state_bits':2,'added_command_cycles':0,'same_edge_public_output_and_old_state_twins':results,'inventory':inventory,'source_sha256':sha(f),'parent_sha256':selection.digest(old),'runner_sha256':sha(__file__),'helper_sha256':sha(u/selection.TOOL),'candidate_sha256':sha(out/'candidate.sv'),'source_unchanged':f.read_text()==new,'mapped_induction_proven':False,'new_held_payload_bits_require_CDC_and_finite_timing_audit':True,'hardware_tested':False}
(out/'verification.json').write_text(json.dumps(r,indent=2)+'\n')
