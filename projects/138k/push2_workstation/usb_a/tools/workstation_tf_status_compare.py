"""Explicit M status comparison selection and exact, layered source inverse."""
from pathlib import Path
import hashlib,json

KEY='tf_status_compare_policy'
POLICY='task3_M_TF_status_generation_byte_compare_v1'
SOURCE='rtl/tf_audio/workstation_tf_direct_runtime_service.sv'
MANIFEST='rtl/tf_audio/workstation_tf_status_compare_v1.adaptation.json'
TOOL='tools/workstation_tf_status_compare.py'
MANIFEST_SHA256='6866bc52cf27a914c2b53716e7f4ced7b73553c93e23e2a298fda8316c701029'
DEFAULT='parameter bit PARALLEL_STATUS_COMPARE_ENABLE=0'
SELECTED='parameter bit PARALLEL_STATUS_COMPARE_ENABLE=1'

def digest(raw):return hashlib.sha256(raw.encode()if isinstance(raw,str)else raw).hexdigest()

def require(ok,message):
    if not ok:raise ValueError('TF status compare: '+message)

def unselect(text):
    if SELECTED in text:
        require(text.count(SELECTED)==1 and DEFAULT not in text,'duplicate selection')
        text=text.replace(SELECTED,DEFAULT,1)
    return text

def restore(text):
    if 'PARALLEL_STATUS_COMPARE_ENABLE'not in text:return text
    text=unselect(text)
    raw=(Path(__file__).resolve().parents[1]/MANIFEST).read_bytes()
    require(digest(raw)==MANIFEST_SHA256,'manifest drift');data=json.loads(raw)
    require(data['policy']==POLICY and data['source']==SOURCE,'manifest contract drift')
    require(digest(text)==data['native_sha256'],'native source drift')
    for row in reversed(data['edits']):
        require(text.count(row['after'])==1,'inverse anchor drift')
        text=text.replace(row['after'],row['before'],1)
    require(digest(text)==data['parent_sha256'],'parent identity drift')
    return text

def configured(configuration):
    value=configuration.get(KEY)
    require(value in(None,POLICY),'unknown policy')
    if value:
        require(configuration.get('demo_role')=='M'and
                configuration.get('tf_native_head_policy')=='task3_M_TF_bounded_native_PCM_head_v1',
                'requires explicit paired M native head')
    return bool(value)

def select(text,configuration):
    if not configured(configuration):return text
    require(text.count(DEFAULT)==1 and SELECTED not in text,'default missing')
    return text.replace(DEFAULT,SELECTED,1)

def evidence(stage,configuration):
    if not configured(configuration):return None
    text=(Path(stage)/SOURCE).read_text()
    require(text.count(SELECTED)==1 and DEFAULT not in text,'selected comparison absent')
    return dict(policy=POLICY,source_sha256=digest(text),manifest_sha256=MANIFEST_SHA256,
                compared_bits=32,byte_groups=4,extra_state=0,extra_cycles=0,
                same_edge_stale_status_fence_preserved=True,
                routed_timing_verified=False,hardware_tested=False)

def audit_mapped(n,*,stage):
    from tools.workstation_runtime_pcm_cdc import Graph,BooleanDiagram
    stage=Path(stage)
    configuration=json.loads((stage.parents[1]/'workstation_profile.json').read_text())['configuration']
    if not configured(configuration):return None
    selected=evidence(stage,configuration);g=Graph(n);scope='u_tf_audio'
    q=lambda stem,bit=None:n.pin(g.register(scope,stem,bit),'Q')
    fq=lambda stem,bit=None:n.pin(g.register(scope+'/frames',stem,bit),'Q')
    rows=[];bytes_=[]
    for byte in range(4):
        net=n.canonical(scope,'\\g_parallel_status.generation_equal_bytes ['+str(byte)+']')
        pairs=[(q('compute_status',36+byte*8+i),fq('expected_generation_o',byte*8+i))for i in range(8)]
        front=g.carry_frontier(net)
        require(len(front)==1,'byte carry frontier differs '+str(byte))
        carry=next(iter(front));actual=g.inequality_chain(carry)
        wanted={frozenset(pair)for pair in pairs};remaining=wanted-actual
        require(actual<=wanted and len(actual)==7 and len(remaining)==1,
                'byte comparison operands differ '+str(byte))
        left,right=sorted(next(iter(remaining)));b=BooleanDiagram([carry,left,right])
        expected=b.both(b.invert(b.inputs[carry]),b.invert(b.different(b.inputs[left],b.inputs[right])))
        require(b.net(g,net)==expected,'byte final equality differs '+str(byte))
        bytes_.append(net);rows.append(dict(byte=byte,net=net,exact_full8_equality=True,
                                           operands=pairs,carry_comparisons=7))
    valid=fq('expected_generation_valid_o');release=q('compute_release',2)
    # Gowin distributes these outputs into their consumers. In v35 the
    # complete active equation remains one real gate; busy/pause are factored
    # into larger permission expressions and have no standalone output net.
    # Their unchanged source equations are covered by the exact source inverse
    # and real runtime regression, rather than inventing mapped port aliases.
    s=q('compute_status',3);leaves=[*bytes_,valid,release,s];b=BooleanDiagram(leaves);v=b.inputs
    current=b.all(v[x]for x in [valid,*bytes_])
    active=n.canonical('u_managed/runtime','direct_silence_8')
    require(b.net(g,active)==b.all([v[release],current,v[s]]) and bool(g.fan[active]),
            'actual active consumer lost full generation guard')
    require(all(g.fan[net]for net in bytes_),'comparison output disconnected from actual consumers')
    return dict(policy=POLICY,source_selection=selected,byte_equations=rows,
                compared_bits=32,public_status_outputs_proven=1,
                actual_active_consumer=active,busy_pause_factored_in_consumers=True,
                no_extra_state_or_cycles=True,routed_timing_verified=False,hardware_tested=False)
