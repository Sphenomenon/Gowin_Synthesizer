"""Same-edge W record peer/session fence; exact historical inverse."""
from pathlib import Path
import hashlib,json
SOURCE='rtl/workstation/workstation_task3_w_bus_endpoint.sv'
MANIFEST='rtl/workstation/workstation_record_peer_compare_v1.adaptation.json'
TOOL='tools/workstation_record_peer_compare.py'
POLICY='task3_W_record_peer64_same_edge_byte_compare_v1'
MANIFEST_SHA256='a000d43f65f14e50e86e470aa7ff2cc2f1beadf64febf29ce5b68be3769a44e1'

def normalize(payload):
    if b'record_peer_equal_bytes' not in payload:return payload
    raw=(Path(__file__).resolve().parents[1]/MANIFEST).read_bytes()
    digest=lambda b:hashlib.sha256(b).hexdigest()
    if digest(raw)!=MANIFEST_SHA256:raise ValueError('record peer manifest drift')
    d=json.loads(raw)
    if digest(payload)!=d['native_sha256']:raise ValueError('record peer source drift')
    text=payload.decode()
    for e in reversed(d['edits']):
        if text.count(e['after'])!=1:raise ValueError('record peer inverse anchor drift')
        text=text.replace(e['after'],e['before'],1)
    if digest(text.encode())!=d['parent_sha256']:raise ValueError('record peer parent drift')
    return text.encode()


def audit_mapped(n):
    """Prove every mapped byte includes all eight actual peer/session bits."""
    from tools.workstation_runtime_pcm_cdc import Graph
    from tools.workstation_task3_root_reset_audit import RootDiagram
    g=Graph(n);scope='u_task3_bus_endpoint';rows=[]
    for byte in range(8):
        pairs=[(n.canonical('',f'task3_pair_rx_payload[{130+byte*8+bit}]'),
                n.canonical('',('task3_pair_session'if byte<4 else'task3_pair_peer_boot')+
                            f'[{(byte%4)*8+bit}]'))for bit in range(8)]
        result=n.canonical(scope,f'record_peer_equal_bytes[{byte}]')
        frontier=g.carry_frontier(result)
        if len(frontier)!=1:raise ValueError('record peer byte carry frontier changed')
        carry=next(iter(frontier));actual=g.inequality_chain(carry)
        wanted={frozenset(pair)for pair in pairs};remaining=wanted-actual
        if not actual<=wanted or len(actual)!=7 or len(remaining)!=1:
            raise ValueError('record peer byte operand inventory changed')
        left,right=sorted(next(iter(remaining)));b=RootDiagram([carry,left,right])
        expected=b.both(b.invert(b.inputs[carry]),b.invert(b.different(b.inputs[left],b.inputs[right])))
        if b.net(g,result)!=expected:raise ValueError('record peer final byte equation changed')
        rows.append(dict(byte=byte,output=result,actual_pairs=pairs,
                         seven_bit_carry_exact=True,last_bit_LUT_exact=True))
    return dict(policy=POLICY,compared_peer_session_bits=64,byte_equations=rows,
                added_state_bits=0,scope='Exact mapped byte comparisons; not whole ingress state machine',
                routed_timing_verified=False,hardware_tested=False)
