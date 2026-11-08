#!/usr/bin/env python3
"""Compare complete raw-store behavior for the W B13 terminal fault repair."""
from pathlib import Path
import argparse,ast,hashlib,json,re,subprocess,sys,types
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools import workstation_ble_terminal_cofactor as repair
from tools import workstation_ble_completion_publication as publication

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    helperfile=ROOT/'sim/memory/prove_ble_raw_start_factor.py'
    tbfile=ROOT/'sim/memory/tb_ble_raw_ddr_store.sv'
    deps=[ROOT/p for p in ('rtl/memory/workstation_sdp.sv','rtl/music/music_async_fifo.sv',
                          'rtl/memory/workstation_recording_ddr_native_bridge.sv')]
    source=ROOT/repair.SOURCE
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    paths=(source,ROOT/repair.TOOL,ROOT/repair.MANIFEST,ROOT/publication.TOOL,
           ROOT/publication.MANIFEST,helperfile,tbfile,Path(__file__),*deps)
    inputs={str(p.relative_to(ROOT)):sha(p)for p in paths}
    current=source.read_text();old=repair.restore(current)
    selected=current.replace(repair.DEFAULT,repair.SELECTED,1)
    assert repair.digest(old)==json.loads((ROOT/repair.MANIFEST).read_text())['parent_sha256']
    assert repair.restore(selected)==old
    # Reuse maintained bench construction without importing its optional Z3.
    names={'split_top','stripped','require','inventories','checks_text','reference_instance',
           'memory_checks','twin_bench','directed_bench','simulate'}
    nodes=[n for n in ast.parse(helperfile.read_text()).body if isinstance(n,ast.FunctionDef)and n.name in names]
    assert {n.name for n in nodes}==names
    namespace=dict(re=re,TB=tbfile,subprocess=subprocess,sha=sha)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(helperfile),'exec'),namespace)
    h=types.SimpleNamespace(**namespace)
    ports,states,nets=h.inventories(old)
    states=[s for s in states if s not in ('valid','payload')]
    nets=[s for s in nets if s!='capture']
    results={}
    for pipeline in (0,1):
        select_pub=lambda s:s.replace(publication.DEFAULT,publication.SELECTED,1)if pipeline else s
        ref=out/f'reference{pipeline}.sv'
        ref.write_text(select_pub(old).replace('module workstation_ble_raw_ddr_store #(',
                                                'module workstation_ble_raw_ddr_store_reference #(',1))
        dut=out/f'candidate{pipeline}.sv';dut.write_text(select_pub(selected))
        tb,inventory=h.twin_bench(old,ports,states,nets)
        checks='''generate if(CAPTURE_COMMAND)begin:terminal_capture_check
always @(posedge memory_clk or negedge memory_clk)begin #0.01;
if({dut.g_command_capture.valid,dut.g_command_capture.payload}!==
   {reference.g_command_capture.valid,reference.g_command_capture.payload})$fatal(1,"captured command changed");
end end endgenerate
'''
        bench=out/f'twin{pipeline}.sv';bench.write_text(tb.replace('endmodule',checks+'\nendmodule'))
        for capture in (0,1):
            for half in (5,7,11):
                name=f'pub{pipeline}-capture{capture}-mem{half}'
                results[name]=h.simulate(out,name,[dut,ref,*deps,bench],'tb_ble_raw_ddr_store',
                    [('CAPTURE_COMMAND',capture),('MEM_HALF',half)],timeout=120)
        directed,cases=h.directed_bench(ports,states,nets)
        # Add binary arbitrary edges: dense X/Z states alone frequently mask
        # descriptor comparisons. Keep all original four-state checks too.
        directed=directed.replace('reg [255:0] random_bits;','reg [255:0] random_bits;reg random_binary=0;')
        directed=directed.replace('endcase\nend end end endfunction',
            'endcase\nif(random_binary)random_value[chunk*32+bit_index]=low_bits[bit_index];\nend end end endfunction')
        directed=directed.replace('i<4096','i<8192').replace('set_base;twin_case=100+i;',
            'if(i%1024==0)begin $display("arbitrary progress %0d/8192",i);$fflush();end '
            'set_base;twin_case=100+i;random_binary=(i>=4096);')
        directed=directed.replace('random_four_state_edges=4096 total_edges=',
            'random_four_state_edges=4096 random_binary_edges=4096 total_edges=')
        bench=out/f'directed{pipeline}.sv';bench.write_text(directed)
        results[f'arbitrary-pub{pipeline}']=h.simulate(out,f'arbitrary-pub{pipeline}',
            [dut,ref,*deps,bench],'directed',timeout=300)
        if not pipeline:
            default=out/'default.sv';default.write_text(current)
            results['default-arbitrary']=h.simulate(out,'default-arbitrary',
                [default,ref,*deps,bench],'directed',timeout=300)
            mutations=[
                ('fault-code','completion_code_with_fault=memory_failure==0 ? F_TRANSPORT:memory_failure;',
                              'completion_code_with_fault=0;'),
                ('unknown-fallback','default:legacy_terminal_writes=1;','default:legacy_terminal_writes=0;'),
                ('index-fault-veto',"1'b1:completion_code<=completion_code_with_fault;",
                    "1'b1:begin completion_code<=completion_code_with_fault;memory_next_index<=0;end")]
            for label,a,b in mutations:
                assert selected.count(a)==1
                mutant=out/(label+'.sv');mutant.write_text(selected.replace(a,b,1))
                results[label]=h.simulate(out,label,[mutant,ref,*deps,bench],'directed',
                    expected='complete raw twin',timeout=120)
    unchanged=inputs=={str(p.relative_to(ROOT)):sha(p)for p in paths}
    result=dict(passed=unchanged,inputs_sha256=inputs,inputs_unchanged=unchanged,
                cases=results,whole_twin_inventory=inventory,directed_cases=cases,
                sampled_arbitrary_edges_per_publication_mode=8192,
                scope='complete raw-store sequential twin and sampled arbitrary conditional one-step comparison; no formal exhaustion',
                source_implementation=True,synthesis=False,pnr=False,hardware_tested=False)
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    assert unchanged,'source changed during verification'

if __name__=='__main__':main()
