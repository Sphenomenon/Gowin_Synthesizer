#!/usr/bin/env python3
"""Actual source cone, Gowin mapping and exact256-input identity proof."""
from pathlib import Path
import argparse,copy,hashlib,json,os,re,subprocess,sys,time,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.workstation_task3_identity_compare import ENDPOINT,comparator_block,restore_endpoint
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_task3_phone_batch_mapped_m import MappedDiagram
from tools.workstation_memory import clock_estimates

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def artifact(p):return dict(path=str(p),sha256=sha(p))

class IdentityDiagram(MappedDiagram):
    """Only this comparison admits256 interleaved operand bits; global120 stays."""
    def __init__(self,inputs):
        if len(inputs)!=256 or len(set(inputs))!=256:raise ValueError('exact256 identity state bits required')
        self.nodes,self.unique,self.cache=[None,None],{},{}
        self.inputs={net:self.node(i,0,1) for i,net in enumerate(inputs)}

def prove(vg):
    n=SynthesisNetlist(vg.read_text(),'identity_probe');g=Graph(n)
    def register(stem):
        found=[p for p in g.regs if n.scopes[p]=='' and re.fullmatch(re.escape(stem)+r'_s\d+',p)]
        if len(found)!=1:raise ValueError('exact root register missing/duplicate: '+stem)
        return found[0]
    left=[register('configured_identity_'+str(i)) for i in range(128)]
    right=[register('current_identity_r_'+str(i)) for i in range(128)]
    named=[n.pin(p,'Q') for pair in zip(left,right) for p in pair]
    output=register('changed_o');target=n.pin(output,'D');bd=IdentityDiagram(named)
    expected=0
    for a,b in zip(left,right):expected=bd.either(expected,bd.different(bd.inputs[n.pin(a,'Q')],bd.inputs[n.pin(b,'Q')]))
    if bd.net(g,target)!=expected:raise ValueError('mapped complete128-bit comparison differs')
    negatives=[]
    for bit,(a,b) in enumerate(zip(left,right)):
        q=n.pin(a,'Q');other=n.pin(b,'Q')
        loads=[(p,pin) for p,pin,_ in g.fan[q] if n.cells[p]['kind']=='ALU' and pin in ('I0','I1')]
        if len(loads)!=1:raise ValueError('exact identity comparator leaf inventory changed')
        cell,pin=loads[0];saved=copy.deepcopy(n.cells[cell]);n.cells[cell]['ports'][pin]=other
        try:
            # Bound each fault proof independently; do not accumulate128
            # distinct mutant functions into the nominal diagram's node pool.
            mutant=IdentityDiagram(named)
            want=0
            for x,y in zip(left,right):want=mutant.either(want,mutant.different(
                mutant.inputs[n.pin(x,'Q')],mutant.inputs[n.pin(y,'Q')]))
            if mutant.net(g,target)==want:raise ValueError('missing identity bit mutant survived')
            negatives.append(bit)
        finally:n.cells[cell]=saved
    return dict(all_256_input_assignments_proven=True,state_assignments=str(1<<256),
        compared_identity_bits=128,BDD_nodes=len(bd.nodes),missing_bit_mutants_rejected=negatives,
        named_leaf_registers=[*left,*right],output_register=output,
        proof_scope='Exact mapped FF-to-FF combinational function,all256 operand-state inputs; no physical timing or whole endpoint CDC claim.')

def run(args):
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    source=(ROOT/ENDPOINT).read_text();restore_endpoint(source);block=comparator_block(source)
    inputs={str(p):sha(p) for p in (ROOT/ENDPOINT,Path(__file__),ROOT/'tools/workstation_task3_identity_compare.py',ROOT/'tools/workstation_task3_phone_batch_mapped_m.py',ROOT/'tools/workstation_runtime_pcm_cdc.py')}
    result=dict(schema=1,passed=False,input_sha256=inputs,cases=[],hardware_tested=False,timing_closed=False)
    env=os.environ.copy();env.update(DYLD_LIBRARY_PATH=str(args.gowin_lib),DYLD_FRAMEWORK_PATH=str(args.gowin_lib))
    try:
        for width in (128,8):
            folder=out/f'group{width}';folder.mkdir()
            wrapper='''module identity_probe(input wire clk_i,input wire[127:0] left_i,right_i,output reg changed_o);
reg[127:0] configured_identity,current_identity_r;
wire[31:0] local_boot_i=current_identity_r[127:96],peer_boot_i=current_identity_r[95:64],session_i=current_identity_r[63:32],generation_i=current_identity_r[31:0];
localparam integer IDENTITY_COMPARE_GROUP_BITS='''+str(width)+''';
always @(posedge clk_i)begin configured_identity<=left_i;current_identity_r<=right_i;changed_o<=new_identity;end
'''+block+'\nendmodule\n'
            (folder/'probe.sv').write_text(wrapper);(folder/'clocks.sdc').write_text('create_clock -name clk_i -period 10.000 [get_ports {clk_i}]\n')
            script='''set root [file normalize [file dirname [info script]]]
cd $root
set_device GW5AST-LV138PG484AC2/I1 -device_version C
set_option -synthesis_tool gowinsynthesis
set_option -top_module identity_probe
set_option -output_base_name identity_probe
set_option -verilog_std sysv2017
set_option -timing_driven 1
add_file -type verilog [file join $root probe.sv]
add_file -type sdc [file join $root clocks.sdc]
run syn
'''
            (folder/'run.tcl').write_text(script);start=time.monotonic()
            with (folder/'synthesis.log').open('w') as log:p=subprocess.run([str(args.gowin),str(folder/'run.tcl')],cwd=folder,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
            if p.returncode:raise RuntimeError('actual identity cone synthesis failed')
            stage=folder/'impl/gwsynthesis';vg=stage/'identity_probe.vg';xml=ET.parse(stage/'identity_probe_syn_rsc.xml').getroot()
            result['cases'].append(dict(group_bits=width,elapsed_seconds=time.monotonic()-start,
                source=artifact(folder/'probe.sv'),netlist=artifact(vg),log=artifact(folder/'synthesis.log'),
                resources={k.removeprefix('T_'):int(v.split('(')[0]) for k,v in xml.attrib.items() if k.startswith('T_')},
                clocks=clock_estimates(stage/'identity_probe_syn.rpt.html'),proof=prove(vg)))
        result.update(passed=True,inputs_unchanged=inputs=={p:sha(Path(p)) for p in inputs},
            exact_other_endpoint_bytes_preserved=True,tool=artifact(args.gowin.resolve()),
            scope='Actual selected-source comparator cone; complete source inverse and both mapped functions proved. Probe is not complete workstation P&R or deployment acceptance.')
        if not result['inputs_unchanged']:raise RuntimeError('identity proof input drift')
    finally:(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=[dict(group_bits=r['group_bits'],resources=r['resources'],clocks=r['clocks'],BDD_nodes=r['proof']['BDD_nodes'],negative_bits=len(r['proof']['missing_bit_mutants_rejected'])) for r in result['cases']]),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--gowin',type=Path,required=True);p.add_argument('--gowin-lib',type=Path,required=True)
    run(p.parse_args())
