"""Prove the unchanged complete raw-store path and its byte comparison cone."""
from pathlib import Path
import sys,json,hashlib,subprocess,importlib.util,re
import z3
import argparse
u=Path(__file__).resolve().parents[2];sys.path.insert(0,str(u))
from tools import workstation_fetch_range as repair
ap=argparse.ArgumentParser(description='Full raw-store twins and parallel fetch-range comparison proof')
ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
source=repair.SOURCE;old=repair.parent_source(u);expr="{2'd0,memory_fetch_end}>{1'b0,memory_committed,2'b0}";assert old.count(expr)==4
block='''    // Parallel byte comparisons replace the serial full-width magnitude chain.
    // The original relational expression remains the four-state fallback.
    wire [34:0] fetch_range_left={2'd0,memory_fetch_end};
    wire [34:0] fetch_range_right={1'b0,memory_committed,2'b0};
    wire [4:0] fetch_range_greater,fetch_range_equal;
'''
for i,(hi,lo)in enumerate([(7,0),(15,8),(23,16),(31,24),(34,32)]):
 block+=f'    assign fetch_range_greater[{i}]=fetch_range_left[{hi}:{lo}]>fetch_range_right[{hi}:{lo}];\n'
 block+=f'    assign fetch_range_equal[{i}]=fetch_range_left[{hi}:{lo}]==fetch_range_right[{hi}:{lo}];\n'
f='fetch_range_greater[0]'
for i in range(1,5):f=f'(fetch_range_greater[{i}] || (fetch_range_equal[{i}] && {f}))'
block+='    reg memory_fetch_range_bad;\n    always @* begin\n        memory_fetch_range_bad='+expr+''';
        case (^{fetch_range_left,fetch_range_right})
            1'b0,1'b1: memory_fetch_range_bad='''+f+''';
            default: begin end
        endcase
    end
'''
anchor="    wire [32:0] memory_fetch_end={1'b0,memory_command_offset}+{19'd0,memory_command_length};";assert old.count(anchor)==1
new=repair.adapt(old);assert repair.restore(new)==old;assert new==old.replace(expr,'memory_fetch_range_bad').replace(anchor,anchor+'\n'+block);(out/'candidate.sv').write_text(new);(out/'reference.sv').write_text(old.replace('module workstation_ble_raw_ddr_store #(','module workstation_ble_raw_ddr_store_reference #(',1))
# Independent all-value unsigned comparison theorem, including each high bit.
a,b=z3.BitVecs('a b',35);greater=[];equal=[]
for hi,lo in [(7,0),(15,8),(23,16),(31,24),(34,32)]:greater.append(z3.UGT(z3.Extract(hi,lo,a),z3.Extract(hi,lo,b)));equal.append(z3.Extract(hi,lo,a)==z3.Extract(hi,lo,b))
def combine(g):
 v=g[0]
 for i in range(1,5):v=z3.Or(g[i],z3.And(equal[i],v))
 return v
s=z3.Solver();s.add(z3.UGT(a,b)!=combine(greater));assert s.check()==z3.unsat
negatives=[]
for i in range(5):
 g=list(greater);g[i]=z3.BoolVal(False);s=z3.Solver();s.add(z3.UGT(a,b)!=combine(g));assert s.check()==z3.sat;negatives.append(dict(removed_byte=i,rejected=True,witness=str(s.model())))
# Actual-source four-state relational cone with all bit positions and boundaries.
logic=block.replace("{2'd0,memory_fetch_end}",'a').replace("{1'b0,memory_committed,2'b0}",'b')
tb='module tb;reg[34:0]a,b;'+logic+'''
integer i,k;initial begin
for(i=0;i<10000;i=i+1)begin a={$random,$random};b={$random,$random};k=i%70;
if(i%3==0)begin if(k<35)a[k]=i[0]?1'bx:1'bz;else b[k-35]=i[0]?1'bx:1'bz;end
#1;if(memory_fetch_range_bad !== (a>b))$fatal(1,"range comparator mismatch");end
$display("PASS four-state fetch compare 10000");$finish;end endmodule''';(out/'fourstate.sv').write_text(tb)
for name,argv in [('compile',['iverilog','-g2012','-s','tb','-o',str(out/'fourstate.vvp'),str(out/'fourstate.sv')]),('run',['vvp',str(out/'fourstate.vvp')])]:
 with(out/(name+'.log')).open('w')as log:subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
# Reuse the existing real raw-store sequential/arbitrary-state oracle.
r=(u/'sim/memory/run_native_fault_cofactor.py').read_text();start=r.index("spec=importlib.util.spec_from_file_location");end=r.index("ports,states,nets=h.inventories(old)");setup=r[start:end];setup=setup[:setup.index('old=repair.restore')]
exec(setup)
ports,states,nets=h.inventories(old);ports={k:v for k,v in ports.items()if k not in ('native_fault_probe_i','response_fault_probe_i')};states=[s for s in states if s not in ('valid','payload')];nets=[s for s in nets if s!='capture']
nba=set(re.findall(r'\b(\w+)(?:\[[^]\n]+\])?\s*<=',old))
for lhs in re.findall(r'\{([^}]+)\}\s*<=',old):nba.update(re.findall(r'\b\w+\b',lhs))
comb=[s for s in states if s not in nba];states=[s for s in states if s in nba];nets=list(dict.fromkeys(nets+comb))
def inject(tb):
 match=re.search(r'workstation_ble_raw_ddr_store #\((.*?)\) dut\((.*?)\);',tb,re.S);assert match
 d=dict(re.findall(r'\.(\w+)\(([^()]*)\)',match[2]));t=d['transport_fault_i'];a=d['native_accept_i'];z=d['read_response_i'];extra=f",.native_fault_probe_i(({t}===1'b0)?{a}:~{a}),.response_fault_probe_i(({t}===1'b0)?{z}:~{z})"
 tb=tb[:match.end()-2]+extra+tb[match.end()-2:]
 match=re.search(r'workstation_ble_raw_ddr_store_reference #\((.*?)\) reference\((.*?)\);',tb,re.S);assert match
 return tb[:match.end()-2]+extra+tb[match.end()-2:]
deps=[u/p for p in ('rtl/memory/workstation_sdp.sv','rtl/music/music_async_fifo.sv','rtl/memory/workstation_recording_ddr_native_bridge.sv')];results={};tb,inventory=h.twin_bench(old,ports,states,nets);bench=out/'twin.sv';bench.write_text(inject(tb))
for cap in (0,1):
 for half in (5,7,11):
  label=f'capture{cap}-mem{half}';results[label]=h.simulate(out,label,[out/'candidate.sv',out/'reference.sv',*deps,bench],'tb_ble_raw_ddr_store',[('CAPTURE_COMMAND',cap),('MEM_HALF',half)],timeout=120);print(label,'PASS',flush=True)
directed,cases=h.directed_bench(ports,states,nets);directed=directed.replace('reg [255:0] random_bits;','reg [255:0] random_bits;reg random_binary=0;').replace('endcase\nend end end endfunction','endcase\nif(random_binary)random_value[chunk*32+bit_index]=low_bits[bit_index];\nend end end endfunction').replace('i<4096','i<8192').replace('set_base;twin_case=100+i;','set_base;twin_case=100+i;random_binary=(i>=4096);');bench=out/'arbitrary.sv';bench.write_text(inject(directed));results['arbitrary']=h.simulate(out,'arbitrary',[out/'candidate.sv',out/'reference.sv',*deps,bench],'directed',timeout=300)
sha=lambda s:hashlib.sha256(s.encode()).hexdigest();proof=dict(passed=True,parent_sha256=sha(old),selected_sha256=sha(new),edits=[dict(before=expr,after='memory_fetch_range_bad',count=4),dict(before=anchor,after=anchor+'\n'+block,count=1)],unsigned_all_70_binary_input_bits='unsat',negative_controls=negatives,four_state_cases=10000,cases=results,inventory=inventory,scope='Same-edge full raw-store twins and8192 sampled arbitrary next edges; local comparator theorem, not whole-design induction.',board_accessed=False,new_timing_verified=False,input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in [u/source,u/repair.TOOL,u/repair.MANIFEST,u/'sim/memory/prove_ble_raw_start_factor.py',u/'sim/memory/tb_ble_raw_ddr_store.sv',Path(__file__),*deps]});(out/'verification.json').write_text(json.dumps(proof,indent=2)+'\n');print('PASS all W fetch-range probes',flush=True)
