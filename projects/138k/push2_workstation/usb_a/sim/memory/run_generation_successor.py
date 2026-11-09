#!/usr/bin/env python3
"""Selected W generation successor: complete raw-store twins and induction.

Uses the actual prepared dependencies; no synthesis, P&R or board access.
"""
from pathlib import Path
import sys,json,hashlib,re,importlib.util
import z3
U=Path(__file__).resolve().parents[2];sys.path.insert(0,str(U))
from tools import workstation_w_generation_successor as selection
import argparse
parser=argparse.ArgumentParser(description='Whole selected raw-store twin and32-bit successor induction')
parser.add_argument('--stage',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();stage=args.stage.resolve();out=args.output.resolve();out.mkdir(exist_ok=False,parents=True)
f=stage/selection.SOURCE;new=f.read_text();old=selection.restore(new)
assert selection.digest(new)==selection.SELECTED_SHA256
count=7
(out/'candidate.sv').write_text(new);(out/'reference.sv').write_text(old.replace('module workstation_ble_raw_ddr_store #(','module workstation_ble_raw_ddr_store_reference #(',1))
g,s,c=z3.BitVecs('generation successor command',32);write,reset=z3.Bools('write reset');gn=z3.If(reset,z3.BitVecVal(0,32),z3.If(write,c,g));sn=z3.If(reset,z3.BitVecVal(1,32),z3.If(write,c+1,s));solver=z3.Solver();solver.add(s==g+1,sn!=gn+1);assert solver.check()==z3.unsat
negative=[]
for label,wrong in [('bad_reset',z3.If(reset,z3.BitVecVal(0,32),z3.If(write,c+1,s))),('missed_write',z3.If(reset,z3.BitVecVal(1,32),s))]:
 so=z3.Solver();so.add(s==g+1,wrong!=gn+1);assert so.check()==z3.sat;negative.append(dict(case=label,witness=str(so.model())))
spec=importlib.util.spec_from_file_location('raw_twins',U/'sim/memory/prove_ble_raw_start_factor.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
ports,states,nets=h.inventories(old);ports={k:v for k,v in ports.items()if k not in('native_fault_probe_i','response_fault_probe_i')};states=[x for x in states if x not in('valid','payload')];nets=[x for x in nets if x!='capture'];nba=set(re.findall(r'\b(\w+)(?:\[[^]\n]+\])?\s*<=',old))
for lhs in re.findall(r'\{([^}]+)\}\s*<=',old):nba.update(re.findall(r'\b\w+\b',lhs))
comb=[x for x in states if x not in nba];states=[x for x in states if x in nba];nets=list(dict.fromkeys(nets+comb));tb,inventory=h.twin_bench(old,ports,states,nets)
for name,value in set(re.findall(r'\bforce\s+dut\.(memory_generation)\s*=([^;]+);',tb)):
 token='force dut.'+name+'='+value+';';tb=tb.replace(token,token+"force dut.memory_generation_successor=("+value+")+32'd1;")
tb=tb.replace('release dut.memory_generation;','release dut.memory_generation;release dut.memory_generation_successor;')
for instance in('dut','reference'):
 match=re.search(r'workstation_ble_raw_ddr_store(?:_reference)? #\((.*?)\) '+instance+r'\((.*?)\);',tb,re.S);assert match;d=dict(re.findall(r'\.(\w+)\(([^()]*)\)',match[2]));t=d['transport_fault_i'];a=d['native_accept_i'];z=d['read_response_i'];extra=f",.native_fault_probe_i(({t}===1'b0)?{a}:~{a}),.response_fault_probe_i(({t}===1'b0)?{z}:~{z})";tb=tb[:match.end()-2]+extra+tb[match.end()-2:]
(out/'twin.sv').write_text(tb);deps=[stage/p for p in('rtl/memory/workstation_sdp.sv','rtl/music/music_async_fifo.sv','rtl/memory/workstation_recording_ddr_native_bridge.sv')];results={}
for cap in(0,1):
 for half in(5,7,11):
  name=f'capture{cap}-mem{half}';results[name]=h.simulate(out,name,[out/'candidate.sv',out/'reference.sv',*deps,out/'twin.sv'],'tb_ble_raw_ddr_store',[('CAPTURE_COMMAND',cap),('MEM_HALF',half)],timeout=120);print(name,'PASS',flush=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();r=dict(passed=True,diagnostic_only=False,parent_sha256=selection.digest(old),actual_stage_source_sha256=sha(f),selected_sha256=sha(out/'candidate.sv'),comparison_replacements=count,reset_writes=1,generation_writes=2,new_state_bits=32,new_cycles=0,invariant='successor == generation + 1 modulo 2^32 after reset',inductive_all32_binary_bits='unsat',negative_controls=negative,complete_twins=results,inventory=inventory,input_sha256={str(p):sha(p)for p in[f,*deps,U/'sim/memory/prove_ble_raw_start_factor.py',U/'sim/memory/tb_ble_raw_ddr_store.sv',U/selection.TOOL,Path(__file__)]},physical_timing_tested=False,production_selection=True,hardware_tested=False);(out/'verification.json').write_text(json.dumps(r,indent=2)+'\n')
