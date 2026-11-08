from pathlib import Path
import sys,json,importlib.util
import argparse,hashlib
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
from tools import workstation_ble_terminal_tuple as repair
parser=argparse.ArgumentParser(description='Complete raw-store tuple cofactor twin regression')
parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
p=root/'sim/memory/prove_ble_raw_start_factor.py';spec=importlib.util.spec_from_file_location('twin',p);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
current=(root/repair.SOURCE).read_text();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
inputs={str(p):sha(p)for p in [root/repair.SOURCE,root/repair.MANIFEST,root/repair.TOOL,Path(__file__)]}
old=repair.restore(current).replace('parameter bit PIPELINED_COMPLETION_ENABLE=0','parameter bit PIPELINED_COMPLETION_ENABLE=1').replace('parameter bit TERMINAL_COFACTOR_ENABLE=0','parameter bit TERMINAL_COFACTOR_ENABLE=1')
new=current.replace('parameter bit PIPELINED_COMPLETION_ENABLE=0','parameter bit PIPELINED_COMPLETION_ENABLE=1').replace('parameter bit TERMINAL_COFACTOR_ENABLE=0','parameter bit TERMINAL_COFACTOR_ENABLE=1').replace('parameter bit TUPLE_COFACTOR_ENABLE=0','parameter bit TUPLE_COFACTOR_ENABLE=1')
ref=out/'reference.sv';ref.write_text(old.replace('module workstation_ble_raw_ddr_store #(','module workstation_ble_raw_ddr_store_reference #(',1));dut=out/'candidate.sv';dut.write_text(new)
ports,states,nets=h.inventories(old);states=[s for s in states if s not in ('valid','payload')];nets=[s for s in nets if s!='capture']
deps=[root/p for p in ('rtl/memory/workstation_sdp.sv','rtl/music/music_async_fifo.sv','rtl/memory/workstation_recording_ddr_native_bridge.sv')];results={}
tb,inventory=h.twin_bench(old,ports,states,nets);bench=out/'twin.sv';bench.write_text(tb)
for capture in (0,1):
 for half in (5,7,11):
  label=f'capture{capture}-mem{half}';results[label]=h.simulate(out,label,[dut,ref,*deps,bench],'tb_ble_raw_ddr_store',[('CAPTURE_COMMAND',capture),('MEM_HALF',half)],timeout=120);print(label,'complete twin passed',flush=True)
directed,cases=h.directed_bench(ports,states,nets)
directed=directed.replace('reg [255:0] random_bits;','reg [255:0] random_bits;reg random_binary=0;')
directed=directed.replace('endcase\nend end end endfunction','endcase\nif(random_binary)random_value[chunk*32+bit_index]=low_bits[bit_index];\nend end end endfunction')
directed=directed.replace('i<4096','i<8192').replace('set_base;twin_case=100+i;','set_base;twin_case=100+i;random_binary=(i>=4096);')
bench=out/'arbitrary.sv';bench.write_text(directed);results['arbitrary']=h.simulate(out,'arbitrary',[dut,ref,*deps,bench],'directed',timeout=300);print('arbitrary complete twin passed',flush=True)
assert inputs=={str(p):sha(p)for p in map(Path,inputs)},'source changed during regression'
(out/'verification.json').write_text(json.dumps(dict(passed=True,cases=results,inventory=inventory,directed_cases=cases,input_sha256=inputs,scope='Complete sequential twin plus sampled arbitrary two-state/four-state one-step comparison; not whole-design induction',hardware_tested=False),indent=2)+'\n')
