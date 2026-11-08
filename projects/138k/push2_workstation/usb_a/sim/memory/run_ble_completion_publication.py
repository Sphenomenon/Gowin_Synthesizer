#!/usr/bin/env python3
"""Full raw-store twin: original behavior, or explicit one-edge ACK retiming.

Only the private count is excluded before publication. Public count, all
outputs, original state, FIFO/native bridge and actual cache remain compared.
No SAT or complete board proof is claimed by this simulation.
"""
from pathlib import Path
import argparse,ast,hashlib,json,re,subprocess,sys,types
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools import workstation_ble_completion_publication as publication

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    helperfile=ROOT/'sim/memory/prove_ble_raw_start_factor.py'
    tbfile=ROOT/'sim/memory/tb_ble_raw_ddr_store.sv'
    deps=[ROOT/p for p in ('rtl/memory/workstation_sdp.sv','rtl/music/music_async_fifo.sv',
                          'rtl/memory/workstation_recording_ddr_native_bridge.sv')]
    source=ROOT/publication.SOURCE
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    inputs={str(p):sha(p)for p in (source,helperfile,tbfile,Path(__file__),
             ROOT/publication.TOOL,ROOT/publication.MANIFEST,*deps)}
    current=source.read_text();old=publication.restore(current)
    # Reuse only the maintained simulation helpers. The parent entrypoint also
    # contains optional SAT routines; those are neither imported nor executed.
    selected={'split_top','stripped','require','inventories','checks_text','reference_instance','memory_checks','twin_bench'}
    tree=ast.parse(helperfile.read_text());nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name in selected]
    assert {n.name for n in nodes}==selected
    helper=types.SimpleNamespace();namespace=dict(re=re,TB=tbfile)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(helperfile),'exec'),namespace)
    helper.__dict__.update(namespace)
    ports,states,nets=helper.inventories(old)
    # The old flat helper sees these generate-local names. Compare the actual
    # generated command tuple explicitly below when that branch is present.
    states=[s for s in states if s not in ('valid','payload')]
    nets=[s for s in nets if s!='capture']
    results=[]
    for pipeline in (0,1):
        ref=old
        if pipeline:
            ref=re.sub(r'\bcommand_ack\b','completion_ready',ref)
            ref=ref.replace('reg command_req,completion_ready;',
                            'reg command_req,completion_ready;\n    reg command_ack;')
            ref=ref.replace('command_ack_meta<=completion_ready;','command_ack_meta<=command_ack;')
            ref=ref.replace('\nendmodule','''
    always @(posedge memory_clk_i or negedge memory_reset_n)
        if(!memory_reset_n)command_ack<=0;
        else command_ack<=completion_ready;
endmodule''',1)
        ref=ref.replace('module workstation_ble_raw_ddr_store #(',
                        'module workstation_ble_raw_ddr_store_reference #(',1)
        reference=out/f'reference{pipeline}.sv';reference.write_text(ref)
        compare_states=[s for s in states if not(pipeline and s=='completion_committed')]
        tb,inventory=helper.twin_bench(old,ports,compare_states,nets)
        checks='''generate if(CAPTURE_COMMAND)begin:publication_capture_check
always @(posedge memory_clk or negedge memory_clk)begin #0.01;
if({dut.g_command_capture.valid,dut.g_command_capture.payload}!==
   {reference.g_command_capture.valid,reference.g_command_capture.payload})$fatal(1,"captured command changed");
end end endgenerate
'''
        if pipeline:
            checks+='''always @(posedge memory_clk or negedge memory_clk)begin #0.01;
if(dut.completion_ready!==reference.completion_ready)$fatal(1,"local retirement moved");
if(dut.completion_ready==dut.command_ack && dut.completion_committed!==reference.completion_committed)$fatal(1,"published completion count changed");
end
'''
        tb=tb.replace('integer twin_edges=0',checks+'integer twin_edges=0')
        bench=out/f'twin{pipeline}.sv';bench.write_text(tb)
        candidate=out/f'candidate{pipeline}.sv'
        candidate.write_text(current if not pipeline else current.replace(publication.DEFAULT,publication.SELECTED,1))
        for capture in (0,1):
            for half in (5,7,11):
                case=out/f'pipeline{pipeline}-capture{capture}-mem{half}';case.mkdir()
                cmd=['iverilog','-g2012','-s','tb_ble_raw_ddr_store',
                     f'-Ptb_ble_raw_ddr_store.CAPTURE_COMMAND={capture}',
                     f'-Ptb_ble_raw_ddr_store.MEM_HALF={half}','-o',str(case/'test.vvp'),
                     str(candidate),str(reference),*map(str,deps),str(bench)]
                r=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
                (case/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
                r=subprocess.run(['vvp',str(case/'test.vvp')],capture_output=True,text=True,timeout=120)
                (case/'run.log').write_text(r.stdout+r.stderr)
                results.append(dict(pipeline=pipeline,capture=capture,memory_half=half,
                                    passed=r.returncode==0,inventory=inventory,log=r.stdout+r.stderr))
                print(case.name,'passed',r.returncode==0,flush=True)
                assert r.returncode==0,r.stdout+r.stderr
    result=dict(passed=all(r['passed']for r in results),inputs_sha256=inputs,
                inputs_unchanged=all(sha(p)==h for p,h in inputs.items()),cases=results,
                default_full_cycle_equivalence=True,
                selected_reference_normalization='one memory edge public ACK delay, original local retirement and count capture',
                generated_command_capture_compared=True,private_count_checked_after_publication=True,
                hardware_tested=False,routed_timing_verified=False)
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    assert result['inputs_unchanged']

if __name__=='__main__':main()
