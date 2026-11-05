#!/usr/bin/env python3
"""Actual96-bit RPC comparator: Gowin mapping and complete192-input proof."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.workstation_task3_phone_identity_compare import ENDPOINT,comparator_block,restore_endpoint
from tools.workstation_task3_phone_batch_mapped_m import MappedDiagram
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.workstation_memory import clock_estimates


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PhoneDiagram(MappedDiagram):
    """Local192-input comparison only; retain the generic Boolean limit."""
    def __init__(self,inputs):
        if len(inputs)!=192 or len(set(inputs))!=192:
            raise ValueError('exact192 independent phone identity operands required')
        self.nodes,self.unique,self.cache=[None,None],{},{}
        self.inputs={net:self.node(i,0,1) for i,net in enumerate(inputs)}


def prove(n,left,right,target,*,equality):
    g=Graph(n)
    named=[net for pair in zip(left,right) for net in pair]
    if len(left)!=96 or len(right)!=96 or len(set(named))!=192:
        raise ValueError('complete96-bit operand vectors required')
    for net in named:
        ds=g.drivers[net]
        if len(ds)!=1 or ds[0][0] not in g.regs or ds[0][1]!='Q':
            raise ValueError('operand is not one independent actual FF-Q: '+net)
    def expected(bd):
        different=0
        for x,y in zip(left,right):
            different=bd.either(different,bd.different(bd.inputs[x],bd.inputs[y]))
        return bd.invert(different) if equality else different
    bd=PhoneDiagram(named)
    if bd.net(g,target)!=expected(bd):raise ValueError('complete mapped96-bit identity function differs')
    cells=set();memo={}
    def depth(net):
        if net in set(named)|g.high|g.low:return (0,0)
        if net in memo:return memo[net]
        ds=g.drivers[net]
        if len(ds)!=1:raise ValueError('ambiguous comparison driver')
        path,output=ds[0];kind=n.cells[path]['kind'];cells.add(path)
        if kind=='ALU':pins=('I0','I1','CIN')
        elif kind=='INV':pins=('I',)
        elif re.fullmatch(r'LUT[1-6]',kind):pins=tuple('I'+str(i) for i in range(int(kind[3:])))
        else:raise ValueError('unreviewed comparison primitive: '+path)
        child=[depth(n.pin(path,p)) for p in pins]
        memo[net]=(1+max(c[0] for c in child),(kind=='ALU')+max(c[1] for c in child))
        return memo[net]
    levels,alu_depth=depth(target);negative=[]
    for bit,(x,y) in enumerate(zip(left,right)):
        # Gowin may fold the final compare bit into the reduction LUT.
        # Omit this operand from every actual load inside the proved cone.
        loads=[(p,pin) for p,pin,_ in g.fan[x] if p in cells]
        if not loads:raise ValueError('comparison operand has no actual cone load: '+str(bit))
        saved={p:copy.deepcopy(n.cells[p]) for p,_ in loads}
        for path,pin in loads:n.cells[path]['ports'][pin]=y
        try:
            mutant=PhoneDiagram(named)
            if mutant.net(g,target)==expected(mutant):raise ValueError('omitted identity bit survived')
            negative.append(bit)
        finally:n.cells.update(saved)
    return dict(compared_identity_bits=96,independent_FF_Q_inputs=192,
        all_operand_state_assignments_proven=True,state_assignments=str(1<<192),
        BDD_nodes=len(bd.nodes),max_unit_weight_stages=levels,max_serial_ALU_stages=alu_depth,
        cone_primitive_counts={k:sum(n.cells[p]['kind']==k for p in cells)
                              for k in sorted({n.cells[p]['kind'] for p in cells})},
        missing_bit_mutants_rejected=negative,output_net=target,output_is_equality=equality,
        operand_pairs=list(zip(left,right)),
        scope='Exact combinational identity function on192 independent actual FF-Q values; no proof cuts,physical delay or whole endpoint/CDC acceptance.')


def prove_candidate(candidate,*,legacy):
    candidate=Path(candidate);stage=candidate/'workstation/Prj1'
    vg=stage/'impl/gwsynthesis/custom_138k_integration.vg'
    n=protocol_netlist(vg.read_text(),mapping='synthesis');g=Graph(n);scope='u_task3_m_endpoint'
    left=[n.canonical(scope,'task3_pair_rx_payload['+str(i)+']') for i in range(82,178)]
    right=[]
    for name in ('generation','session','local_boot'):
        formal='task3_pair_'+name
        if n.frames[scope]['ports'].get(formal)!=formal+'[31:0]':
            raise ValueError('actual pair identity binding changed')
        right.extend(n.canonical(scope,formal+'['+str(i)+']') for i in range(32))
    if legacy:
        # Locate all96 cells by the actual operand pairing and carry wiring,
        # never by a historical generated n-number.
        target=None
        for x,y in zip(left,right):
            found=[p for p,pin,_ in g.fan[x] if n.cells[p]['kind']=='ALU'
                   and n.cells[p]['parameters'].get('ALU_MODE')=='3'
                   and {n.pin(p,'I0'),n.pin(p,'I1')}=={x,y}
                   and (n.pin(p,'CIN') in g.low if target is None else n.pin(p,'CIN')==target)]
            if len(set(found))!=1:raise ValueError('legacy96-bit serial comparison binding changed')
            target=n.pin(found[0],'COUT')
    else:target=n.canonical(scope,'phone_matches')
    result=prove(n,left,right,target,equality=not legacy)
    result.update(candidate_identity=json.loads((candidate/'workstation_profile.json').read_text())['candidate_identity'],
                  netlist_path=str(vg),netlist_sha256=sha(vg),
                  profile_sha256=sha(candidate/'workstation_profile.json'),
                  integration_sha256=sha(candidate/'integration_inputs.json'))
    return result


def run(args):
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    paths=[ROOT/ENDPOINT,Path(__file__),ROOT/'tools/workstation_task3_phone_identity_compare.py',
           ROOT/'tools/workstation_task3_phone_batch_mapped_m.py',ROOT/'tools/workstation_runtime_pcm_cdc.py',
           ROOT/'tools/workstation_native_protocol_audit.py',ROOT/'tools/workstation_synthesis_netlist.py']
    for candidate in (args.candidate,args.reference_candidate):
        if candidate:paths.extend(candidate/p for p in ('workstation_profile.json','integration_inputs.json',
                           'workstation/Prj1/impl/gwsynthesis/custom_138k_integration.vg'))
    before={str(p):sha(p) for p in paths}
    result=dict(schema=1,passed=False,input_sha256=before,cases=[],hardware_tested=False,
                physical_CDC_accepted=False,timing_closed=False)
    try:
        source=(ROOT/ENDPOINT).read_text();restore_endpoint(source);block=comparator_block(source)
        if not args.mapped_only:
            env=dict(os.environ)
            for key in ('DYLD_LIBRARY_PATH','DYLD_FALLBACK_LIBRARY_PATH','DYLD_FRAMEWORK_PATH','DYLD_FALLBACK_FRAMEWORK_PATH'):
                env[key]=str(args.gowin_lib)
            for width in (96,8):
                folder=out/f'group{width}';folder.mkdir()
                wrapper='''module phone_identity_probe(input wire clk_i,input wire[95:0] left_i,right_i,output reg match_o);
reg[95:0] rx_payload_r,current_r;
wire[255:0] rx_payload_i={78'd0,rx_payload_r,82'd0};wire[95:0]common=current_r;
localparam integer PHONE_IDENTITY_COMPARE_GROUP_BITS='''+str(width)+''';
always @(posedge clk_i)begin rx_payload_r<=left_i;current_r<=right_i;match_o<=phone_matches;end
'''+block+'\nendmodule\n'
                (folder/'probe.sv').write_text(wrapper)
                (folder/'clocks.sdc').write_text('create_clock -name clk_i -period 10.000 [get_ports {clk_i}]\n')
                (folder/'run.tcl').write_text('''set root [file normalize [file dirname [info script]]]
cd $root
set_device GW5AST-LV138PG484AC2/I1 -device_version C
set_option -synthesis_tool gowinsynthesis
set_option -top_module phone_identity_probe
set_option -output_base_name phone_identity_probe
set_option -verilog_std sysv2017
set_option -timing_driven 1
add_file -type verilog [file join $root probe.sv]
add_file -type sdc [file join $root clocks.sdc]
run syn
''')
                start=time.monotonic()
                with (folder/'synthesis.log').open('w') as log:
                    p=subprocess.run([str(args.gowin),str(folder/'run.tcl')],cwd=folder,env=env,
                                     stdout=log,stderr=subprocess.STDOUT,timeout=180)
                if p.returncode:raise ValueError('phone comparator synthesis failed')
                stage=folder/'impl/gwsynthesis';vg=stage/'phone_identity_probe.vg'
                n=SynthesisNetlist(vg.read_text(),'phone_identity_probe');g=Graph(n)
                def reg(stem):
                    found=[p for p in g.regs if re.fullmatch(re.escape(stem)+r'_s\d+',p)]
                    if len(found)!=1:raise ValueError('probe register absent/ambiguous: '+stem)
                    return found[0]
                proof=prove(n,[n.pin(reg('rx_payload_r_'+str(i)),'Q') for i in range(96)],
                            [n.pin(reg('current_r_'+str(i)),'Q') for i in range(96)],
                            n.pin(reg('match_o'),'D'),equality=True)
                xml=ET.parse(stage/'phone_identity_probe_syn_rsc.xml').getroot()
                result['cases'].append(dict(group_bits=width,elapsed_seconds=time.monotonic()-start,
                    netlist_path=str(vg),netlist_sha256=sha(vg),proof=proof,
                    resources={k.removeprefix('T_'):int(v.split('(')[0]) for k,v in xml.attrib.items() if k.startswith('T_')},
                    clocks=clock_estimates(stage/'phone_identity_probe_syn.rpt.html')))
        if args.candidate:
            result['full_M']=prove_candidate(args.candidate,legacy=False)
            result['reference_full_M']=prove_candidate(args.reference_candidate,legacy=True)
        result['passed']=True
    except Exception as exc:
        result['error']=repr(exc)
        raise
    finally:
        result['inputs_unchanged']=before=={str(p):sha(p) for p in paths}
        (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    if not result['inputs_unchanged']:raise ValueError('proof input drift')
    print(json.dumps(dict(passed=True,evidence=str(out/'verification.json'))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gowin',type=Path,default='/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/bin/gw_sh')
    parser.add_argument('--gowin-lib',type=Path,default='/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/lib')
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--reference-candidate',type=Path)
    parser.add_argument('--mapped-only',action='store_true')
    args=parser.parse_args()
    if bool(args.candidate)!=bool(args.reference_candidate) or args.mapped_only and not args.candidate:
        parser.error('mapped proof needs both explicit current and reference candidates')
    run(args)
