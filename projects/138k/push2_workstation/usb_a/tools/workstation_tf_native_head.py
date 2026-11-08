"""Exact inverse and explicit selection of M's bounded native PCM head.

The RTL owns the slot. This helper checks provenance and selects a parameter;
it does not generate an implementation or relax cancellation/CDC timing.
"""
from pathlib import Path
import hashlib
import json

KEY='tf_native_head_policy'
POLICY='task3_M_TF_bounded_native_PCM_head_v1'
SOURCE='rtl/tf_audio/workstation_tf_direct_runtime_service.sv'
MANIFEST='rtl/tf_audio/workstation_tf_native_head_v1.adaptation.json'
MANIFEST_SHA256='12495fc802ccced598de96824c321b9165b2b49c2c894e079c34454c1a215ae2'
DEFAULT='parameter bit LOCAL_NATIVE_HEAD_ENABLE=0'
SELECTED='parameter bit LOCAL_NATIVE_HEAD_ENABLE=1'

def digest(raw):
    return hashlib.sha256(raw.encode()if isinstance(raw,str)else raw).hexdigest()

def require(ok,message):
    if not ok:raise ValueError('TF native head: '+message)

def unselect(text):
    if SELECTED in text:
        require(text.count(SELECTED)==1 and DEFAULT not in text,'duplicate selection')
        text=text.replace(SELECTED,DEFAULT,1)
    return text

def restore(text):
    from tools.workstation_tf_status_compare import restore as restore_status
    text=restore_status(text)
    if 'LOCAL_NATIVE_HEAD_ENABLE' not in text:return text
    raw=(Path(__file__).resolve().parents[1]/MANIFEST).read_bytes()
    require(digest(raw)==MANIFEST_SHA256,'manifest drift')
    row=json.loads(raw)
    require(row['policy']==POLICY and row['source']==SOURCE and row['default']==0,
            'manifest contract changed')
    text=unselect(text)
    require(digest(text)==row['native_sha256'],'native source drift')
    for edit in reversed(row['edits']):
        require(text.count(edit['after'])==1,'inverse anchor drift')
        text=text.replace(edit['after'],edit['before'],1)
    require(digest(text)==row['parent_sha256'],'parent identity drift')
    return text

def configured(configuration):
    value=configuration.get(KEY)
    require(value in (None,POLICY),'unknown policy')
    if value:
        require(configuration.get('demo_role')=='M' and
                configuration.get('tf_compute_reset_policy')=='task3_M_TF_compute_functional_local_release_v1',
                'requires explicit M preboard compute-release selection')
    return bool(value)

def select(text,configuration):
    if not configured(configuration):return text
    require(text.count(DEFAULT)==1 and SELECTED not in text,'default selection missing')
    return text.replace(DEFAULT,SELECTED,1)

def evidence(stage,configuration):
    if not configured(configuration):return None
    text=(Path(stage)/SOURCE).read_text()
    require(text.count(SELECTED)==1 and DEFAULT not in text,'selected head absent')
    # The compute-release verifier checks the complete inverse chain.
    return dict(policy=POLICY,source_sha256=digest(text),manifest_sha256=MANIFEST_SHA256,
                capacity_frames=1,maximum_acceptance_interval_source_clocks=2,
                same_edge_publication_cancel_retained=True,overflow='native ready backpressure',
                cancellation='discard local head; no old session publication',
                routed_timing_verified=False,hardware_tested=False)

def audit_mapped(n,*,stage):
    """Check the actual isolation that addresses M A11's RAM CEB setup path.

    A head must be a real source-clock register, and every native RAM enable
    must exclude the session/receipt and paired endpoint combinational cones.
    This is not a timing waiver or a substitute for cancellation simulation.
    """
    from tools.workstation_runtime_pcm_cdc import Graph
    stage=Path(stage)
    profile=json.loads((stage.parents[1]/'workstation_profile.json').read_text())
    if not configured(profile['configuration']):return None
    selected=evidence(stage,profile['configuration'])
    g=Graph(n);head=g.register('u_tf_audio','head_valid')
    release=g.register('u_tf_audio','source_release',2)
    cell=n.cells[head]
    require(cell['kind']=='DFFCE' and n.pin(head,'CLK')=='clk_50m' and
            n.pin(head,'CE') in g.high and
            cell['parameters'].get('INIT')=="1'b0",'head clock/reset/enable/init changed')
    reset_proof=g.equivalent('head async CLEAR inverse final source release',
        [n.pin(head,'CLEAR'),n.pin(release,'Q')],lambda v:v[0]==1-v[1],
        cuts=(n.pin(release,'Q'),))
    expected={f'u_tf_audio/native/ingress/pcm_mem_pcm_mem_0_{i}_s' for i in range(9)}
    actual={p for p,c in n.cells.items()
            if p.startswith('u_tf_audio/native/ingress/pcm_mem_') and
            c['kind'].startswith(('SDP','DP'))}
    require(actual==expected,'native PCM RAM inventory changed')
    rows=[]
    for p in sorted(actual):
        require(n.cells[p]['kind'].startswith(('SDP','DP')),'native PCM RAM primitive changed')
        require({'CEA','CEB','OCE'}<=set(n.cells[p]['ports']),'native PCM RAM enables changed')
        for pin in ('CEA','CEB','OCE'):
            leaves=g.support(n.pin(p,pin))
            for net in leaves:
                for path,_ in g.drivers[net]:
                    require(not path.startswith(('u_task3_m_endpoint/','u_tf_audio/session_',
                                                 'u_tf_audio/receipt_')),
                            'session/receipt/endpoint reaches native RAM enable '+p+'/'+pin)
            if pin=='CEB':require(n.pin(head,'Q') in leaves,'native RAM read bypasses head')
            rows.append(dict(endpoint=p+'/'+pin,support=sorted(leaves)))
    return dict(policy=POLICY,selected_source=selected,head_register=head,
                source_release_CLEAR=reset_proof,
                native_PCM_RAM_enables=rows,enable_pin_count=len(rows),
                read_enable_count=9,source_session_receipt_endpoint_isolated=True,
                routed_timing_verified=False,hardware_tested=False)
