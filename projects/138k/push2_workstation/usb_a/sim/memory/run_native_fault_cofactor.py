"""Full raw-store twins, preserving the conditional diagnostic contract.

Use together with prove_native_fault_cofactor.py, which proves the enclosing
memory boundary and actual W diagnostic wiring. This is no timing proof.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,sys
u=Path(__file__).resolve().parents[2];sys.path.insert(0,str(u))
from tools import workstation_native_fault_cofactor as repair
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
spec=importlib.util.spec_from_file_location('twin',u/'sim/memory/prove_ble_raw_start_factor.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
old=repair.restore(repair.SOURCE,(u/repair.SOURCE).read_text());new=(u/repair.SOURCE).read_text()
for stem in ('PIPELINED_COMPLETION_ENABLE','TERMINAL_COFACTOR_ENABLE','TUPLE_COFACTOR_ENABLE','PACK_COFACTOR_ENABLE'):
 old=old.replace('parameter bit '+stem+'=0','parameter bit '+stem+'=1');new=new.replace('parameter bit '+stem+'=0','parameter bit '+stem+'=1')
new=new.replace('parameter bit NATIVE_FAULT_COFACTOR_ENABLE=0','parameter bit NATIVE_FAULT_COFACTOR_ENABLE=1')
(out/'candidate.sv').write_text(new);(out/'reference.sv').write_text(old.replace('module workstation_ble_raw_ddr_store #(','module workstation_ble_raw_ddr_store_reference #(',1))
ports,states,nets=h.inventories(old);states=[s for s in states if s not in ('valid','payload')];nets=[s for s in nets if s!='capture']
# Only clocked NBA targets are independent state. Combinational reg outputs
# remain compared but must not be assigned arbitrary values by the harness.
nba=set(re.findall(r'\b(\w+)(?:\[[^]\n]+\])?\s*<=',old))
for lhs in re.findall(r'\{([^}]+)\}\s*<=',old):nba.update(re.findall(r'\b\w+\b',lhs))
comb=[s for s in states if s not in nba];states=[s for s in states if s in nba];nets=list(dict.fromkeys(nets+comb))
(out/'arbitrary-state-inventory.json').write_text(json.dumps(dict(clock_state=states,compared_unforced_combinational=comb),indent=2)+'\n')
def inject(tb):
 match=re.search(r'workstation_ble_raw_ddr_store #\((.*?)\) dut\((.*?)\);',tb,re.S);assert match
 d=dict(re.findall(r'\.(\w+)\(([^()]*)\)',match[2]));t=d['transport_fault_i'];a=d['native_accept_i'];z=d['read_response_i'];extra=f",.native_fault_probe_i(({t}===1'b0)?{a}:~{a}),.response_fault_probe_i(({t}===1'b0)?{z}:~{z})"
 return tb[:match.end()-2]+extra+tb[match.end()-2:]
deps=[u/p for p in ('rtl/memory/workstation_sdp.sv','rtl/music/music_async_fifo.sv','rtl/memory/workstation_recording_ddr_native_bridge.sv')];results={}
tb,inventory=h.twin_bench(old,ports,states,nets);bench=out/'twin.sv';bench.write_text(inject(tb))
for cap in (0,1):
 for half in (5,7,11):
  label=f'capture{cap}-mem{half}'
  results[label]=h.simulate(out,label,[out/'candidate.sv',out/'reference.sv',*deps,bench],'tb_ble_raw_ddr_store',[('CAPTURE_COMMAND',cap),('MEM_HALF',half)],timeout=120)
  print(label,'complete sequential twin passed',flush=True)
directed,cases=h.directed_bench(ports,states,nets);directed=directed.replace('reg [255:0] random_bits;','reg [255:0] random_bits;reg random_binary=0;').replace('endcase\nend end end endfunction','endcase\nif(random_binary)random_value[chunk*32+bit_index]=low_bits[bit_index];\nend end end endfunction').replace('i<4096','i<8192').replace('set_base;twin_case=100+i;','set_base;twin_case=100+i;random_binary=(i>=4096);');bench=out/'arbitrary.sv';bench.write_text(inject(directed));results['arbitrary']=h.simulate(out,'arbitrary',[out/'candidate.sv',out/'reference.sv',*deps,bench],'directed',timeout=300)
(out/'verification.json').write_text(json.dumps(dict(passed=True,cases=results,inventory=inventory,assumption='Probe equals the real input whenever immediate transport fault is zero; otherwise independent. Enclosing-boundary proof still required.',scope='Six full raw-store dual-clock twins and8192 sampled arbitrary binary/X/Z next edges; not whole-design induction',manifest_sha256=sha(u/repair.MANIFEST),board_accessed=False),indent=2)+'\n')
