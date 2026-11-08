"""Explicit W completion publication selection and exact historical inverse.

The raw store owns all implementation. This helper only selects its default;
it never adds a timing exception or another recording object.
"""
from pathlib import Path
import hashlib,json

KEY='raw_completion_policy'
POLICY='task3_W_raw_completion_publication_one_memory_edge_v1'
SOURCE='rtl/memory/workstation_ble_raw_ddr_store.sv'
MANIFEST='rtl/memory/workstation_ble_completion_publication_v1.adaptation.json'
TOOL='tools/workstation_ble_completion_publication.py'
MANIFEST_SHA256='9469ef3002d11921eab73b83ed247f213a276aa1a2fd0f17cb068151ba5c4385'
DEFAULT='parameter bit PIPELINED_COMPLETION_ENABLE=0'
SELECTED='parameter bit PIPELINED_COMPLETION_ENABLE=1'

def digest(raw):return hashlib.sha256(raw.encode()if isinstance(raw,str)else raw).hexdigest()

def require(ok,message):
    if not ok:raise ValueError('raw completion publication: '+message)

def unselect(text):
    if SELECTED in text:
        require(text.count(SELECTED)==1 and DEFAULT not in text,'duplicate selection')
        text=text.replace(SELECTED,DEFAULT,1)
    return text

def restore(text):
    text=unselect(text)
    if DEFAULT not in text:return text
    raw=(Path(__file__).resolve().parents[1]/MANIFEST).read_bytes()
    require(digest(raw)==MANIFEST_SHA256,'manifest drift')
    data=json.loads(raw)
    require(data['policy']==POLICY and data['source']==SOURCE,'manifest policy/source changed')
    require(digest(text)==data['native_sha256'],'native source drift')
    for edit in reversed(data['edits']):
        require(text.count(edit['after'])==1,'inverse anchor drift')
        text=text.replace(edit['after'],edit['before'],1)
    require(digest(text)==data['parent_sha256'],'parent identity drift')
    return text

def configured(configuration):
    value=configuration.get(KEY)
    require(value in (None,POLICY),'unknown policy')
    if value:
        require(configuration.get('demo_role')=='W' and
                configuration.get('preboard_cdc_policy')=='task3_W_proven_release_and_CNN_drain_CDC_v1',
                'requires explicit paired preboard W')
    return bool(value)

def select(stage,configuration):
    if not configured(configuration):return None
    path=Path(stage)/SOURCE;text=path.read_text();restore(text)
    require(text.count(DEFAULT)==1 and SELECTED not in text,'default missing')
    path.write_text(text.replace(DEFAULT,SELECTED,1))
    return evidence(stage,configuration)

def evidence(stage,configuration):
    if not configured(configuration):return None
    text=(Path(stage)/SOURCE).read_text();restore(text)
    require(text.count(SELECTED)==1 and DEFAULT not in text,'selected publication absent')
    return dict(policy=POLICY,source_sha256=digest(text),manifest_sha256=MANIFEST_SHA256,
                public_ACK_added_memory_clocks=1,local_retirement_edge_unchanged=True,
                error_count_preserved=True,same_edge_fault_and_cancel_retained=True,
                timing_exception_added=False,routed_timing_verified=False,hardware_tested=False)

def audit_mapped(n):
    """Exact memory-domain publication equations on the selected actual VG.

    Only named registered inputs are BDD leaves. Fault feedback cannot be
    hidden by an arbitrary combinational cut at the count or its enable.
    """
    from tools.workstation_runtime_pcm_cdc import Graph,BooleanDiagram
    from tools.workstation_task3_native_held import zero_ff
    from tools.workstation_recording_phase1_cdc import complete_closure
    scope='u_task3_media/raw_store';g=Graph(n)
    reg=lambda stem:g.register(scope,stem)
    q=lambda p:n.pin(p,'Q')
    ready,ack,zero=map(reg,('completion_ready','command_ack','completion_zero'))
    snapshot=g.group(scope,'completion_count_snapshot',32)
    count=g.group(scope,'completion_committed',32)
    committed=g.group(scope,'memory_committed',32)
    release=g.register(scope,'memory_release',1)
    rows=[]
    for p in [ready,ack,zero,*snapshot,*count]:
        zero_ff(n,g,p,'memory_clk')
        g.equivalent('completion CLEAR inverse final memory release',
            [n.pin(p,'CLEAR'),q(release)],lambda x:x[0]==1-x[1],cuts=(q(release),))
    def next_q(b,p):return b.choose(b.net(g,n.pin(p,'CE')),b.net(g,n.pin(p,'D')),b.inputs[q(p)])
    b=BooleanDiagram([q(ready),q(ack)])
    require(next_q(b,ack)==b.inputs[q(ready)],'public ACK no longer follows local ready by one edge')
    for i,(snap,dst,src) in enumerate(zip(snapshot,count,committed)):
        leaves=list(dict.fromkeys(map(q,[ready,ack,zero,snap,dst,src])))
        b=BooleanDiagram(leaves);pending=b.different(b.inputs[q(ready)],b.inputs[q(ack)])
        selected=b.choose(b.inputs[q(zero)],0,b.inputs[q(snap)])
        require(next_q(b,dst)==b.choose(pending,selected,b.inputs[q(dst)]),
                'published count data/enable changed bit '+str(i))
        require(next_q(b,snap)==b.choose(pending,b.inputs[q(snap)],b.inputs[q(src)]),
                'private snapshot preload/freeze changed bit '+str(i))
        rows.append(dict(bit=i,registered_snapshot=snap,published_count=dst,
                         exact_next_Q=True,BDD_nodes=len(b.nodes)))
    closure=complete_closure(n,g,[ready])
    require(set(closure['ff_endpoints'].values())=={'memory_clk'} and
            not closure['primitive_endpoints']and not closure['top_output_endpoints'],
            'private ready escapes local memory FFs')
    return dict(policy=POLICY,public_ACK_added_memory_clocks=1,
                count_bits=32,private_preload_and_freeze_equations=rows,
                local_ready_complete_closure=closure,
                same_edge_fault_to_published_count_combinational_path=False,
                original_payload_and_local_retirement_require_source_twin=True,
                routed_timing_verified=False,hardware_tested=False)
