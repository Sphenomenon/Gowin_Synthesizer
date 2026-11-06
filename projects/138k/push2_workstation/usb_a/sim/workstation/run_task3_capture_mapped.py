#!/usr/bin/env python3
"""Prove the full32 unsigned capture comparison in the actual M netlist.

The response bus is a combinational cutpoint. Only last_capture_id operands
are required to be real FF-Qs. This is a local function proof, not proof of
upstream response generation, the complete batch machine, CDC or STA.
"""
from pathlib import Path
import argparse,copy,hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools import workstation_profile as profiles
from tools import workstation_task3_capture_compare as capture
from tools.workstation_task3_phone_batch_mapped_m import MappedDiagram
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_native_protocol_audit import protocol_netlist

class CaptureDiagram(MappedDiagram):
    """Exact GW5A SUB/GE/LE COUT with grounded I3, plus MUX2_LUT5..8.

    prim_sim.v defines S=~(I0^I1), and C=I0 for SUB/GE or
    C=I1 for LE. Therefore COUT=equal?CIN:C. No other mode
    is admitted beyond those already reviewed in MappedDiagram.
    The MUX2_LUT primitives implement O=S0?I1:I0 as in prim_sim.v.
    """
    def net(self,graph,net,memo=None,active=()):
        memo={} if memo is None else memo
        if net in self.inputs or net in graph.high|graph.low or net in memo:
            return super().net(graph,net,memo,active)
        ds=graph.drivers[net]
        if len(ds)==1:
            path,output=ds[0];cell=graph.n.cells[path];mode=cell['parameters'].get('ALU_MODE')
            if cell['kind']=='ALU' and mode in ('1','4','5'):
                if output!='COUT' or graph.n.pin(path,'I3') not in graph.low or net in active:
                    raise ValueError('unreviewed capture comparison arithmetic: '+path+'/'+output)
                x,y,carry=[self.net(graph,graph.n.pin(path,p),memo,(*active,net)) for p in ('I0','I1','CIN')]
                memo[net]=self.choose(self.invert(self.different(x,y)),carry,y if mode=='5' else x)
                return memo[net]
            if re.fullmatch(r'MUX2_LUT[5-8]',cell['kind']):
                if output!='O' or net in active:raise ValueError('capture mux output/cycle changed')
                x,y,select=[self.net(graph,graph.n.pin(path,p),memo,(*active,net)) for p in ('I0','I1','S0')]
                memo[net]=self.choose(select,y,x)
                return memo[net]
        return super().net(graph,net,memo,active)


def prove(n,left,right,target):
    named=[net for pair in zip(left,right) for net in pair];g=Graph(n)
    if len(left)!=32 or len(right)!=32 or len(set(named))!=64:raise ValueError('full independent32-bit operand boundary required')
    for net in right:
        ds=g.drivers[net]
        if len(ds)!=1 or ds[0][0] not in g.regs or ds[0][1]!='Q':raise ValueError('last capture operand is not FF-Q: '+net)
    def expected(bd,*,strict=False,swap=False):
        less=0 if strict else 1
        for a,b in zip(right if swap else left,left if swap else right):
            x,y=bd.inputs[a],bd.inputs[b]
            less=bd.choose(bd.different(x,y),y,less)
        return less
    bd=CaptureDiagram(named);actual=bd.net(g,target);want=expected(bd)
    if actual!=want:raise ValueError('mapped capture comparison is not unsigned32 <=')
    if actual==expected(bd,strict=True) or actual==expected(bd,swap=True):raise ValueError('comparison/operator negative control survived')
    cells=set();memo={};leaves=set(named)
    def depth(net):
        if net in leaves|g.high|g.low:return (0,0)
        if net in memo:return memo[net]
        ds=g.drivers[net]
        if len(ds)!=1:raise ValueError('ambiguous comparison driver')
        p,output=ds[0];kind=n.cells[p]['kind'];cells.add(p)
        pins=('I0','I1','CIN') if kind=='ALU' else ('I0','I1','S0') if re.fullmatch(r'MUX2_LUT[5-8]',kind) else ('I',) if kind=='INV' else tuple('I'+str(i) for i in range(int(kind[3:]))) if re.fullmatch(r'LUT[1-6]',kind) else None
        if pins is None:raise ValueError('unexpected primitive below comparison boundary: '+p)
        children=[depth(n.pin(p,pin)) for pin in pins]
        memo[net]=(1+max(x[0] for x in children),(kind=='ALU')+max(x[1] for x in children))
        return memo[net]
    levels,alu=depth(target);negatives=[]
    for side,vector in (('response',left),('last_capture',right)):
        for bit,net in enumerate(vector):
            loads=[(p,pin) for p,pin,_ in g.fan[net] if p in cells]
            if not loads:raise ValueError('operand missing from mapped cone')
            saved={p:copy.deepcopy(n.cells[p]) for p,pin in loads}
            try:
                for p,pin in loads:n.cells[p]['ports'][pin]="1'b0"
                mutant=CaptureDiagram(named)
                if mutant.net(g,target)==expected(mutant):raise ValueError('missing operand bit survived')
                negatives.append(dict(operand=side,bit=bit))
            finally:n.cells.update(saved)
    boundaries=[0,1,254,255,256,257,65535,65536,0x7fffffff,0x80000000,0xfffffffe,0xffffffff]
    def evaluate(value,x,y):
        values={net:(v>>bit)&1 for vector,v in ((left,x),(right,y)) for bit,net in enumerate(vector)}
        while value>1:
            var,low,high=bd.nodes[value];value=high if values[named[var]] else low
        return value
    for x in boundaries:
        for y in boundaries:
            if evaluate(actual,x,y)!=(x<=y):raise ValueError('unsigned boundary check failed')
    return dict(compared_bits=32,independent_boundary_inputs=64,right_actual_FF_Q_inputs=32,
        left_combinational_cutpoints=32,all_operand_state_assignments_proven=True,state_assignments=str(1<<64),
        BDD_nodes=len(bd.nodes),max_unit_weight_stages=levels,max_serial_ALU_stages=alu,
        missing_operand_bit_controls_rejected=negatives,strict_and_swapped_order_controls_rejected=True,
        boundary_value_pairs=len(boundaries)**2,output_net=target,operand_pairs=list(zip(left,right)),
        cone_primitive_counts={kind:sum(n.cells[p]['kind']==kind for p in cells) for kind in sorted({n.cells[p]['kind'] for p in cells})})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);candidate=a.candidate.resolve();stage=candidate/'workstation/Prj1';vg=stage/'impl/gwsynthesis/custom_138k_integration.vg'
    paths=[Path(__file__),ROOT/capture.TOOL,ROOT/'tools/workstation_task3_phone_batch_mapped_m.py',ROOT/'tools/workstation_runtime_pcm_cdc.py',ROOT/'tools/workstation_native_protocol_audit.py',stage/capture.SOURCE,vg,candidate/'workstation_profile.json',candidate/'integration_inputs.json']
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();before={str(p):sha(p) for p in paths}
    result=dict(schema=1,passed=False,input_sha256=before,hardware_tested=False,timing_closed=False,full_CDC_accepted=False,
        scope='Local combinational function on64 independent boundary values;left32 are response cutpoints,right32 actual FF-Qs. No upstream,whole-machine,CDC or physical delay proof.')
    try:
        artifact=profiles.verify(ROOT,candidate);assert artifact['profile']==capture.PROFILE
        selected=capture.evidence(stage,artifact['configuration'])
        n=protocol_netlist(vg.read_text(),mapping='synthesis');scope='u_task3_m_endpoint/g_phone_batch.batch_m'
        left=[n.canonical(scope,'task3_m_phone_response['+str(i)+']') for i in range(32)]
        right=[n.canonical(scope,'last_capture_id['+str(i)+']') for i in range(32)]
        proof=prove(n,left,right,n.canonical(scope,'capture_not_newer'))
        if proof['max_serial_ALU_stages']>8:raise ValueError('grouped capture comparator not retained')
        result.update(passed=True,candidate_identity=artifact['candidate_identity'],source=selected,proof=proof)
    except Exception as exc:result['error']=repr(exc);raise
    finally:
        result['inputs_unchanged']=before=={str(p):sha(p) for p in paths}
        (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    assert result['inputs_unchanged']
    print(dict(passed=True,serial_ALU_stages=proof['max_serial_ALU_stages'],logic_stages=proof['max_unit_weight_stages'],missing_bits_rejected=len(proof['missing_operand_bit_controls_rejected'])))
if __name__=='__main__':main()
