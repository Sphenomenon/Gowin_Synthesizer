"""Explicit M preboard TF functional reset selection and exact source inverse.

Only compute functional CLEARs change. Root assertion, startup chains, source
invalidation counting, sample clocks and session lifetimes remain unchanged.
The maintained RTL owns the implementation; this adapter selects one default.
"""
from pathlib import Path
import hashlib
import json

KEY='tf_compute_reset_policy'
POLICY='task3_M_TF_compute_functional_local_release_v1'
SERVICE='rtl/tf_audio/workstation_tf_direct_runtime_service.sv'
BRIDGE='rtl/tf_audio/workstation_tf_frame_bridge_v2.sv'
MANIFEST='rtl/tf_audio/workstation_tf_compute_local_release_v1.adaptation.json'
MANIFEST_SHA256='a9fee8e99e62407ce9ee2ec45be12f5c7be4fc0f548562915baafda1f76b75ee'
TOOL='tools/workstation_tf_compute_local_release.py'
DEFAULT='parameter bit LOCAL_COMPUTE_RESET_ENABLE=0'
SELECTED='parameter bit LOCAL_COMPUTE_RESET_ENABLE=1'


def digest(data):return hashlib.sha256(data.encode()if isinstance(data,str)else data).hexdigest()


def require(ok,message):
    if not ok:raise ValueError('TF compute local release: '+message)


def records():
    raw=(Path(__file__).resolve().parents[1]/MANIFEST).read_bytes()
    require(digest(raw)==MANIFEST_SHA256,'adaptation manifest changed')
    data=json.loads(raw)
    require(data['schema']==1 and data['policy']==POLICY,'adaptation policy changed')
    return data['inputs']


def unselect(text):
    if SELECTED in text:
        require(text.count(SELECTED)==1 and DEFAULT not in text,'duplicate parameter selection')
        text=text.replace(SELECTED,DEFAULT,1)
    from tools.workstation_tf_native_head import unselect as unselect_head
    return unselect_head(text)


def restore(relative,data):
    text=data.decode()if isinstance(data,bytes)else data
    if DEFAULT not in text and SELECTED not in text:return data
    text=unselect(text)
    if relative==SERVICE:
        from tools.workstation_tf_native_head import restore as restore_head
        text=restore_head(text)
    row=records()[relative]
    require(digest(text)==row['native_sha256'],'native source drift: '+relative)
    for edit in reversed(row['edits']):
        require(text.count(edit['after'])==1,'inverse anchor drift: '+relative)
        text=text.replace(edit['after'],edit['before'],1)
    require(digest(text)==row['parent_sha256'],'historical inverse drift: '+relative)
    return text.encode()if isinstance(data,bytes)else text


def configured(configuration):
    value=configuration.get(KEY)
    require(value in (None,POLICY),'unknown compute reset policy')
    if value is not None:
        require(configuration.get('demo_role')=='M' and
                configuration.get('tf_policy')=='task3_m_native_direct_tf_v1',
                'requires complete paired M direct TF')
    return value is not None


def select(stage,configuration):
    if not configured(configuration):return None
    path=Path(stage)/SERVICE;text=path.read_text()
    restore(SERVICE,text)
    require(text.count(DEFAULT)==1 and SELECTED not in text,'default source option missing')
    from tools.workstation_tf_native_head import select as select_head
    path.write_text(select_head(text.replace(DEFAULT,SELECTED,1),configuration))
    return evidence(stage,configuration)


def evidence(stage,configuration):
    if not configured(configuration):return None
    stage=Path(stage);hashes={}
    for relative in (SERVICE,BRIDGE):
        text=(stage/relative).read_text();restore(relative,text)
        require(text.count(SELECTED if relative==SERVICE else DEFAULT)==1,
                'compute reset source option differs: '+relative)
        hashes[relative]=digest(text)
    from tools.workstation_tf_native_head import evidence as head_evidence
    result=dict(policy=POLICY,source_sha256=hashes,manifest_sha256=MANIFEST_SHA256,
        release='existing local compute_release[2]',new_reset_registers=0,
        root_async_assertion_preserved=True,source_invalidation_semantics_unchanged=True,
        session_fence_resets_mailboxes=False,legacy_source_inverse_verified=True,
        mapped_reset_verified=False,routed_timing_verified=False,hardware_tested=False)
    head=head_evidence(stage,configuration)
    if head:result['native_PCM_head']=head
    return result


def audit_mapped(n,*,stage,root=None):
    """Bind the selected source to every actual compute-domain reset consumer.

    The eight startup/release FFs remain asynchronously asserted by the root.
    Only those synchronizer CLEAR pins may receive physical reset exceptions;
    the 438 functional CLEAR pins retain recovery/removal timing.
    """
    from tools.workstation_runtime_pcm_cdc import Graph,BooleanDiagram
    from tools.workstation_task3_root_reset_audit import audit_root_startup
    from tools.workstation_task3_tf_startup_audit import audit_tf_startup_releases
    from tools.workstation_task3_native_held import zero_ff
    from tools.workstation_recording_phase1_cdc import complete_closure
    stage=Path(stage)
    profile=json.loads((stage.parents[1]/'workstation_profile.json').read_text())
    if not configured(profile['configuration']):return None
    require(profile['profile']=='custom138k-workstation-task3-m-preboard-v1',
            'mapped proof requires explicit M preboard profile')
    selected=evidence(stage,profile['configuration'])
    root=root if root is not None else audit_root_startup(n,stage=stage)
    startup=audit_tf_startup_releases(n,root=root)
    g=Graph(n);service='u_tf_audio';frame=service+'/frames';fifo=frame+'/frames_0'
    sq=n.pin(g.register(service,'compute_release',2),'Q')
    fq=n.pin(g.register(frame,'compute_release',2),'Q')
    regs={}
    def add(scope,stem,width,release):
        paths=[g.register(scope,stem)]if width is None else g.group(scope,stem,width)
        for p in paths:
            require(p not in regs,'functional reset inventory aliases '+p)
            regs[p]=release
    for name,width in [('receipt_payload',34),('queued_receipt_session',32),
        ('receipt_ack_sync',2),('status_request_sync',2),('status_ack',None),
        ('status_capture',None),('receipt_request',None),('abort_queued',None),('eos_queued',None)]:
        add(service,name,width,sq)
    for bit in range(1,68):regs[g.register(service,'compute_status',bit)]=sq
    for name,width in [('generation_meta',32),('generation_sync',32),('source_alive_sync',2),
        ('quiesce_sync',2),('expected_generation_o',32),('expected_generation_valid_o',None),
        ('ack_binary',32),('ack_gray',31),('held_valid',None),('quiet_published',None),('quiet_settle',3)]:
        add(frame,name,width,fq)
    for bit in [*range(34),36,*range(40,48),49,*range(54,118)]:
        regs[g.register(frame,'held_packet',bit)]=fq
    for name,width in [('read_binary',5),('read_gray',4),('write_gray_meta',5),('write_gray_sync',5)]:
        add(fifo,name,width,fq)
    frame_release=g.group(frame,'compute_release',3)
    chains=g.group(service,'startup_compute',2)+g.group(service,'compute_release',3)+frame_release
    require(len(regs)==438 and len(set(chains))==8,'reviewed compute inventory changed')
    require({p for p in g.regs if p.startswith(service+'/')and n.pin(p,'CLK')=='audio_clk'}
            ==set(regs)|set(chains),'complete compute inventory has extra/missing register')
    for p,r in regs.items():
        zero_ff(n,g,p,'audio_clk');clear=n.pin(p,'CLEAR');b=BooleanDiagram([r])
        require(g.support(clear)=={r}and b.net(g,clear)==b.invert(b.inputs[r]),
                'functional CLEAR bypasses exact local release '+p)
    closures=[]
    for i,p in enumerate(frame_release):
        zero_ff(n,g,p,'audio_clk');clear=n.pin(p,'CLEAR');b=BooleanDiagram([root['root_q']])
        require(g.support(clear)=={root['root_q']}and
            b.net(g,clear)==b.invert(b.inputs[root['root_q']]),'frame release root assertion changed')
        require(n.pin(p,'CE')in g.high and
            (n.pin(p,'D')in g.high if i==0 else n.pin(p,'D')==n.pin(frame_release[i-1],'Q')),
            'frame release exact shift/enable changed')
        if i<2:
            c=complete_closure(n,g,[p])
            require(c['ff_endpoints']=={frame_release[i+1]+'/D':'audio_clk'}and
                not c['primitive_endpoints']and not c['top_output_endpoints'],
                'frame early release has extra consumer')
            closures.append(c)
    return dict(policy=POLICY,source_selection=selected,actual_startup=startup,
        service_compute_release=sq,frame_compute_release=fq,
        functional_compute_register_count=len(regs),functional_register_release=regs,
        root_asserted_synchronizer_registers=chains,frame_early_release_closures=closures,
        exact_complete_compute_inventory=True,root_async_assertion_preserved=True,
        functional_false_paths_added=False,routed_timing_verified=False,hardware_tested=False)
