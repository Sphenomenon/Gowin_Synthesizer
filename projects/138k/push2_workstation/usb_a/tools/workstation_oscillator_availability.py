"""Exact same-edge availability reduction over unchanged voice allocation."""
from pathlib import Path
import hashlib,json
SOURCE='rtl/audio/workstation_runtime_oscillator_engine.sv'
MANIFEST='rtl/audio/workstation_runtime_oscillator_engine.availability_groups.json'
TOOL='tools/workstation_oscillator_availability.py'
POLICY='native_oscillator_available_groups_v1'
MANIFEST_SHA256='9ecf45b73b70d6a1fd691e219c4c2ca41ac50cf316a365b7d7f45343e7eb3e97'

def digest(raw):return hashlib.sha256(raw).hexdigest()

def require(ok,message):
    if not ok:raise ValueError('oscillator availability: '+message)

def restore(relative,source):
    if str(relative)!=SOURCE or b'allocation_available_groups'not in source:return source
    raw=(Path(__file__).resolve().parents[1]/MANIFEST).read_bytes()
    require(digest(raw)==MANIFEST_SHA256,'manifest drift');d=json.loads(raw)
    require(d['policy']==POLICY and d['source']==SOURCE and digest(source)==d['native_sha256'],
            'native source identity drift')
    text=source.decode()
    for row in reversed(d['edits']):
        require(text.count(row['after'])==1,'inverse anchor drift')
        text=text.replace(row['after'],row['before'],1)
    parent=text.encode();require(digest(parent)==d['parent_sha256'],'parent identity drift')
    return parent

def audit_mapped(n):
    from tools.workstation_runtime_pcm_cdc import Graph,BooleanDiagram
    scope='u_managed/runtime/service/workstation/runtime_engines.engines/oscillator'
    g=Graph(n);rows=[]
    for group in range(8):
        net=n.canonical(scope,f'allocation_available_groups[{group}]')
        qs=[n.pin(g.register(scope,'allocated_mask_o',group*4+i),'Q')for i in range(4)]
        b=BooleanDiagram(qs)
        require(b.net(g,net)==b.invert(b.all(b.inputs[x]for x in qs)),
                'actual four-voice availability differs '+str(group))
        require(bool(g.fan[net]),'preserved availability group is unused')
        rows.append(dict(group=group,net=net,allocated_state=qs,exact_any_free=True))
    return dict(policy=POLICY,ordinary_voices=32,preserved_groups=rows,
                exact_same_edge_candidates=True,priority_encoder_source_unchanged=True,
                extra_state=0,extra_cycles=0,routed_timing_verified=False,hardware_tested=False)
