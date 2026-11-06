#!/usr/bin/env python3
"""Full32 local equality proof on the explicit full-M experiment netlist."""
from pathlib import Path
import argparse,copy,hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools import workstation_task3_capture_identity_experiment as identity
from tools.workstation_task3_phone_batch_mapped_m import MappedDiagram,BATCH
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_native_protocol_audit import protocol_netlist

def prove(n,left,right,target):
    named=[net for pair in zip(left,right) for net in pair];g=Graph(n)
    if len(left)!=32 or len(right)!=32 or len(set(named))!=64:
        raise ValueError('independent full32 response/capture boundary required')
    for net in right:
        drivers=g.drivers[net]
        if len(drivers)!=1 or drivers[0][0] not in g.regs or drivers[0][1]!='Q':
            raise ValueError('capture identity is not actual FF-Q: '+net)
    def expected(bd):
        return bd.all([bd.invert(bd.different(bd.inputs[a],bd.inputs[b])) for a,b in zip(left,right)])
    bd=MappedDiagram(named);actual=bd.net(g,target)
    if actual!=expected(bd):raise ValueError('mapped capture identity differs from exact unsigned32 equality')
    cells=set();memo={};leaves=set(named)
    def depth(net):
        if net in leaves|g.high|g.low:return 0,0
        if net in memo:return memo[net]
        drivers=g.drivers[net]
        if len(drivers)!=1:raise ValueError('ambiguous comparator driver')
        path,output=drivers[0];cell=n.cells[path];kind=cell['kind'];cells.add(path)
        pins=(('I0','I1','CIN') if kind=='ALU' else ('I',) if kind=='INV' else
              tuple('I'+str(i) for i in range(int(kind[3:]))) if re.fullmatch(r'LUT[1-6]',kind) else None)
        if pins is None:raise ValueError('unreviewed comparator primitive: '+path)
        children=[depth(n.pin(path,p)) for p in pins]
        memo[net]=(1+max(v[0] for v in children),int(kind=='ALU')+max(v[1] for v in children))
        return memo[net]
    levels,alu=depth(target);negatives=[]
    for side,vector in [('response',left),('capture',right)]:
        for bit,net in enumerate(vector):
            loads=[(p,pin) for p,pin,_ in g.fan[net] if p in cells]
            if not loads:raise ValueError('operand bit absent from mapped cone')
            saved={p:copy.deepcopy(n.cells[p]) for p,pin in loads}
            try:
                for p,pin in loads:n.cells[p]['ports'][pin]="1'b0"
                mutant=MappedDiagram(named)
                if mutant.net(g,target)==expected(mutant):raise ValueError('missing operand bit survived')
                negatives.append(dict(operand=side,bit=bit))
            finally:n.cells.update(saved)
    return dict(compared_bits=32,independent_boundary_inputs=64,
        right_actual_FF_Q_inputs=32,left_combinational_cutpoints=32,
        all_operand_state_assignments_proven=True,state_assignments=str(1<<64),
        BDD_nodes=len(bd.nodes),max_unit_weight_stages=levels,max_serial_ALU_stages=alu,
        missing_operand_bit_controls_rejected=negatives,
        output_net=target,operand_pairs=list(zip(left,right)),
        cone_primitive_counts={k:sum(n.cells[p]['kind']==k for p in cells)
            for k in sorted({n.cells[p]['kind'] for p in cells})})

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preparation',type=Path,required=True)
    p.add_argument('--netlist',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('fresh evidence output required')
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    preparation=json.loads(a.preparation.read_text());stage=Path(preparation['parent_stage'])
    if preparation['policy']!=identity.POLICY or preparation['production_profile_selected']:
        raise ValueError('explicit offline experiment required')
    paths=[Path(__file__),ROOT/'tools/workstation_task3_capture_identity_experiment.py',
           ROOT/'tools/workstation_task3_phone_batch_mapped_m.py',ROOT/'tools/workstation_runtime_pcm_cdc.py',
           ROOT/'tools/workstation_native_protocol_audit.py',a.preparation,a.netlist]
    before={str(p):sha(p) for p in paths}
    result=dict(schema=1,passed=False,input_sha256=before,hardware_tested=False,timing_closed=False,
        full_CDC_accepted=False,whole_batch_formal_proof=False,
        scope='Local combinational equality on64 independent boundary inputs;response cutpoints and32 real capture FF-Qs. No upstream,complete machine,CDC or physical delay proof.')
    try:
        if any(sha(stage/p)!=h for p,h in preparation['parent_staged_input_sha256'].items()):
            raise ValueError('immutable parent input changed')
        if any(sha(p)!=h for p,h in preparation['input_sha256'].items()):
            raise ValueError('explicit experimental input changed')
        selected=Path(a.netlist).parents[2]/'capture_batch_experiment.sv'
        source=identity.evidence(selected.read_text())
        n=protocol_netlist(a.netlist.read_text(),mapping='synthesis')
        left=[n.canonical(BATCH,'task3_m_phone_response['+str(i)+']') for i in range(32)]
        right=[n.canonical(BATCH,'capture_id['+str(i)+']') for i in range(32)]
        proof=prove(n,left,right,n.canonical(BATCH,'capture_identity_matches'))
        if proof['max_serial_ALU_stages']>8:raise ValueError('grouped equality not retained in actual netlist')
        result.update(passed=True,experiment_identity=preparation['identity'],source=source,proof=proof)
    except Exception as exc:result['error']=repr(exc);raise
    finally:
        result['inputs_unchanged']=before=={str(p):sha(p) for p in paths}
        a.output.write_text(json.dumps(result,indent=2)+'\n')
    if not result['inputs_unchanged']:raise ValueError('proof input changed')
    print(dict(passed=True,serial_ALU_stages=proof['max_serial_ALU_stages'],logic_stages=proof['max_unit_weight_stages'],
        omitted_bits_rejected=len(proof['missing_operand_bit_controls_rejected'])))
if __name__=='__main__':main()
