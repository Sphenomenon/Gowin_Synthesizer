"""Verify command capture precomputation against the retained parallel-range source."""
from pathlib import Path
import sys,json,hashlib,subprocess,importlib.util,re
import argparse
u=Path(__file__).resolve().parents[2];sys.path.insert(0,str(u))
from tools import workstation_fetch_range as repair
ap=argparse.ArgumentParser(description='Captured full end-address invariant and real raw-store sequential twins')
ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
source=repair.SOURCE;old=repair.adapt(repair.parent_source(u));new=old
new=repair.adapt(repair.parent_source(u),repair.CAPTURE_POLICY)
assert repair.restore(new)==repair.restore(old)
spec=importlib.util.spec_from_file_location('twin',u/'sim/memory/prove_ble_raw_start_factor.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
(out/'candidate.sv').write_text(new);(out/'reference.sv').write_text(old.replace('module workstation_ble_raw_ddr_store #(','module workstation_ble_raw_ddr_store_reference #(',1))
ports,states,nets=h.inventories(old);ports={k:v for k,v in ports.items()if k not in ('native_fault_probe_i','response_fault_probe_i')};states=[s for s in states if s not in ('valid','payload')];nets=[s for s in nets if s!='capture']
nba=set(re.findall(r'\b(\w+)(?:\[[^]\n]+\])?\s*<=',old))
for lhs in re.findall(r'\{([^}]+)\}\s*<=',old):nba.update(re.findall(r'\b\w+\b',lhs))
comb=[s for s in states if s not in nba];states=[s for s in states if s in nba];nets=list(dict.fromkeys(nets+comb))
private=[n for n in nets if n=='memory_fetch_end' or n=='memory_fetch_range_bad' or n.startswith('fetch_range_')];nets=[n for n in nets if n not in private]
def inject(tb):
 for label in ('dut','reference'):
  name='workstation_ble_raw_ddr_store'+('_reference' if label=='reference' else '')
  match=re.search(name+r' #\((.*?)\) '+label+r'\((.*?)\);',tb,re.S);assert match
  d=dict(re.findall(r'\.(\w+)\(([^()]*)\)',match[2]));t=d['transport_fault_i'];a=d['native_accept_i'];z=d['read_response_i'];extra=f",.native_fault_probe_i(({t}===1'b0)?{a}:~{a}),.response_fault_probe_i(({t}===1'b0)?{z}:~{z})"
  tb=tb[:match.end()-2]+extra+tb[match.end()-2:]
 return tb
deps=[u/p for p in ('rtl/memory/workstation_sdp.sv','rtl/music/music_async_fifo.sv','rtl/memory/workstation_recording_ddr_native_bridge.sv')];results={};tb,inventory=h.twin_bench(old,ports,states,nets)
# Check exact captured arithmetic whenever its existing valid bit owns it.
extra="""generate if(CAPTURE_COMMAND)begin:check_captured_end
always @(posedge memory_clk or negedge memory_clk) begin #0.02;
if(dut.g_command_capture.valid===1'b1 && dut.memory_fetch_end !== ({1'b0,reference.memory_command_offset}+{19'd0,reference.memory_command_length}))$fatal(1,"captured end invariant");
if({dut.g_command_capture.valid,dut.g_command_capture.payload} !== {reference.g_command_capture.valid,reference.g_command_capture.payload})$fatal(1,"capture payload unchanged");
end end endgenerate
"""
tb=tb.replace('endmodule',extra+'endmodule');bench=out/'twin.sv';bench.write_text(inject(tb))
for cap in (0,1):
 for half in (5,7,11):
  label=f'capture{cap}-mem{half}';results[label]=h.simulate(out,label,[out/'candidate.sv',out/'reference.sv',*deps,bench],'tb_ble_raw_ddr_store',[('CAPTURE_COMMAND',cap),('MEM_HALF',half)],timeout=120);print(label,'PASS',flush=True)
# Randomize all shared old registers independently. The one new state has
# its exact capture invariant; private end arithmetic is ignored only without
# a valid descriptor. All registered old state and public outputs stay compared.
directed,cases=h.directed_bench(ports,states,nets)
directed=directed.replace(".BASE_APP(29'h0040000),.FIFO_ADDRESS_BITS(3)",".CAPTURE_COMMAND(1),.BASE_APP(29'h0040000),.FIFO_ADDRESS_BITS(3)")
start=directed.index('initial begin\n');comment=directed.index('// Every old register',start);directed=directed[:start]+'initial begin\n'+directed[comment:]
directed=directed.replace('reg [255:0] random_bits;','reg [255:0] random_bits;reg random_binary=0;').replace('endcase\nend end end endfunction','endcase\nif(random_binary)random_value[chunk*32+bit_index]=low_bits[bit_index];\nend end end endfunction').replace('i<4096','i<8192').replace('set_base;twin_case=100+i;','set_base;twin_case=100+i;random_binary=(i>=4096);')
anchor='#0.1;compare_all;step;'
assert directed.count(anchor)==1
directed=directed.replace(anchor,"""random_bits=random_value();dut.g_command_capture.payload=random_bits[$bits(dut.g_command_capture.payload)-1:0];reference.g_command_capture.payload=dut.g_command_capture.payload;
random_bits=random_value();dut.g_command_capture.valid=random_bits[0];reference.g_command_capture.valid=random_bits[0];
#0.1;dut.g_command_capture.fetch_end={1'b0,reference.memory_command_offset}+{19'd0,reference.memory_command_length};
"""+anchor)
bench=out/'arbitrary.sv';bench.write_text(inject(directed));results['arbitrary-captured']=h.simulate(out,'arbitrary-captured',[out/'candidate.sv',out/'reference.sv',*deps,bench],'directed',timeout=300)
# Corrupt the captured sum; real capture+fetch must reject this mutant.
mutant=new.replace("fetch_end<={1'b0,command_offset}+{19'd0,command_length};","fetch_end<={1'b0,command_offset}+{19'd0,command_length}+33'd1;",1);assert mutant!=new;(out/'mutant.sv').write_text(mutant)
results['negative_sum_mutant']=h.simulate(out,'sum-plus-one-mutant',[out/'mutant.sv',out/'reference.sv',*deps,out/'twin.sv'],'tb_ble_raw_ddr_store',[('CAPTURE_COMMAND',1),('MEM_HALF',7)],expected='captured end invariant',timeout=120)
rejected=True
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();proof=dict(passed=True,source_parent_sha256=hashlib.sha256(old.encode()).hexdigest(),source_selected_sha256=hashlib.sha256(new.encode()).hexdigest(),added_state_bits=33,added_command_cycles=0,private_combinational_differences=private,inventory=inventory,cases=results,negative_sum_mutant_rejected=rejected,arbitrary_correspondence_edges=8192,scope='Sequential real raw-store twins; all common logical registers/public outputs plus valid capture arithmetic. No mapped/physical proof.',new_timing_verified=False,board_accessed=False,input_sha256={str(p):sha(p)for p in [u/source,u/repair.TOOL,u/repair.MANIFEST,u/repair.CAPTURE_MANIFEST,u/'sim/memory/prove_ble_raw_start_factor.py',u/'sim/memory/tb_ble_raw_ddr_store.sv',Path(__file__),*deps]});(out/'verification.json').write_text(json.dumps(proof,indent=2)+'\n')
