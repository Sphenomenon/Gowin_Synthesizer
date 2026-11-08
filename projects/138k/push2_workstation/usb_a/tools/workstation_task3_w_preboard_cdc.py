"""Exact W startup and CNN drain boundaries omitted by historical SDC.

Only proven asynchronous reset-release stages and Gray first-capture hold are
excepted. Payload, later stage setup/hold and functional reset timing remain.
"""
from pathlib import Path
import hashlib
import json
import fnmatch
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_task3_root_reset_audit import RootDiagram
from tools.workstation_task3_native_held import zero_ff
from tools.workstation_recording_phase1_cdc import complete_closure

KEY='preboard_cdc_policy'
POLICY='task3_W_proven_release_and_CNN_drain_CDC_v1'
TOOL='tools/workstation_task3_w_preboard_cdc.py'
CNN='u_task3_media/cnn_stream/task_service/cnn'
STREAM='u_task3_media/cnn_stream'
TASK=STREAM+'/task_service'
MARKER='\n# TASK3 W preboard: proven local release and CNN drain boundaries\n'
# First and second startup CLEAR have identical asynchronous assertion.
STARTUP=(('u_managed','startup_compute','audio_clk'),
         ('u_managed/runtime','startup_compute','audio_clk'),
         ('u_managed/runtime','startup_memory','memory_clk'),
         ('u_managed/runtime','startup_serial','dac_mclk_d'))
RELEASES=((STREAM,'control_release','clk_50m'),
          (TASK,'g_domain_reset.control_release','clk_50m'),
          (TASK,'g_domain_reset.native_release','memory_clk'),
          ('u_managed/control_cdc','a_release','audio_clk'))


def require(ok,message):
    if not ok:raise ValueError('W preboard CDC: '+message)


def configured(configuration):
    value=configuration.get(KEY)
    require(value in (None,POLICY),'unknown policy')
    if value is not None:
        from tools.workstation_local_stream_release import configured as local
        require(configuration.get('demo_role')=='W' and local(configuration),
                'requires selected local-release paired W')
    return value is not None


def constraints():
    clear=[]
    for scope in ['u_managed/pc_bytes','u_managed/health_snapshot']:
        clear += [f'{scope}/g_preserved_release.{side}_pipe_{i}_s*/CLEAR'
                  for side in ['source','destination']for i in range(3)]
    clear += [f'{scope}/{stem}_{i}_s*/CLEAR'for scope,stem,_ in RELEASES for i in range(3)]
    # The existing SDC already selects each first CLEAR; add only its peer.
    clear += [f'{scope}/{stem}_1_s*/CLEAR'for scope,stem,_ in STARTUP]
    lines=['set_false_path -to [get_pins {'+' '.join(clear)+'}]']
    # MSB Gray is the actual binary MSB register. Every other bit is distinct.
    source=' '.join(f'{CNN}/g_drain_restart.writes_committed'+('_'if i==15 else '_gray_')+f'{i}_s*/Q' for i in range(16))
    first=' '.join(f'{CNN}/g_drain_restart.writes_gray_meta_{i}_s*/D'for i in range(16))
    first_q=' '.join(f'{CNN}/g_drain_restart.writes_gray_meta_{i}_s*/Q'for i in range(16))
    second=' '.join(f'{CNN}/g_drain_restart.writes_gray_sync_{i}_s*/D'for i in range(16))
    path=f'-from [get_pins {{{source}}}] -to [get_pins {{{first}}}]'
    lines += ['set_max_delay 10.000 '+path,'set_false_path -hold '+path,
              f'set_max_delay 2.000 -from [get_pins {{{first_q}}}] -to [get_pins {{{second}}}]']
    return MARKER+'\n'.join(lines)+'\n'


def select(sdc,configuration):
    if not configured(configuration):return sdc,None
    require(MARKER not in sdc,'already selected')
    selected=sdc+constraints();sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
    return selected,dict(policy=POLICY,parent_sha256=sha(sdc),selected_sha256=sha(selected),
                         source_period_ns=10.0,second_stage_budget_ns=2.0,
                         mapped_proof_required=True,physical_CDC_accepted=False)


def restore(sdc,receipt):
    require(sdc.endswith(constraints()) and sdc.count(MARKER)==1,'selected constraints drift')
    parent=sdc[:-len(constraints())];selected,expected=select(parent,{KEY:POLICY,
        'demo_role':'W','stream_release_policy':'task3_W_preserved_local_stream_release3_v1'})
    require(selected==sdc and receipt==expected,'constraint inverse receipt drift')
    return parent


def audit_gray(n,g):
    r=lambda stem,i:g.register(CNN,'g_drain_restart.'+stem,i)
    binary=[r('writes_committed',i)for i in range(16)]
    gray=[r('writes_committed_gray',i)for i in range(15)]+[binary[15]]
    first=[r('writes_gray_meta',i)for i in range(16)]
    second=[r('writes_gray_sync',i)for i in range(16)]
    q=[n.pin(p,'Q')for p in binary];clear=n.pin(binary[0],'CLEAR');enable=n.pin(binary[15],'CE')
    cuts=[n.pin(g.register(CNN,'g_drain_restart.memory_failed'),'Q'),
          n.canonical(CNN,'cnn_ddr_write'),n.canonical(CNN,'ddr_cmd_ready')]
    leaves=list(dict.fromkeys([*q,*sorted(g.support(enable,cuts=cuts)),clear]))
    b=RootDiagram(leaves);en=b.net(g,enable);reset=b.net(g,clear)
    require(en==b.both(b.invert(b.inputs[cuts[0]]),b.both(b.inputs[cuts[1]],b.inputs[cuts[2]])),
            'native write commit enable changed')
    carry=en
    for bit,p in enumerate(binary):
        zero_ff(n,g,p,'memory_clk')
        require(n.pin(p,'CLEAR')==clear,'binary ledger assertion differs')
        v=b.inputs[q[bit]];expected=b.both(b.invert(reset),b.different(v,carry));carry=b.both(carry,v)
        actual=b.both(b.invert(reset),b.choose(b.net(g,n.pin(p,'CE')),b.net(g,n.pin(p,'D')),v))
        require(actual==expected,'native commit increment changed bit '+str(bit))
    for bit,p in enumerate(gray[:15]):
        zero_ff(n,g,p,'memory_clk');bd=RootDiagram(list(dict.fromkeys([*leaves,n.pin(p,'Q')])))
        en2=bd.net(g,enable);carry=en2;steps=[]
        for i in range(bit+2):
            v=bd.inputs[q[i]];steps.append(bd.different(v,carry));carry=bd.both(carry,v)
        expect=bd.both(bd.invert(bd.net(g,clear)),bd.choose(en2,
            bd.different(steps[bit],steps[bit+1]),bd.inputs[n.pin(p,'Q')]))
        require(n.pin(p,'CLEAR')==clear,'Gray ledger assertion differs')
        actual=bd.both(bd.invert(bd.net(g,clear)),bd.choose(bd.net(g,n.pin(p,'CE')),
            bd.net(g,n.pin(p,'D')),bd.inputs[n.pin(p,'Q')]))
        require(actual==expect,'registered Gray next-Q changed bit '+str(bit))
    for source,one,two in zip(gray,first,second):
        zero_ff(n,g,one,'clk_50m');zero_ff(n,g,two,'clk_50m')
        require(n.pin(one,'D')==n.pin(source,'Q') and n.pin(two,'D')==n.pin(one,'Q') and
            n.pin(one,'CE')in g.high and n.pin(two,'CE')in g.high and
            n.pin(one,'CLEAR')==n.pin(two,'CLEAR'),'Gray capture mapping/enable/reset changed')
        closure=complete_closure(n,g,[one])
        require(closure['ff_endpoints']=={two+'/D':'clk_50m'}and
            not closure['primitive_endpoints']and not closure['top_output_endpoints'],
            'Gray first-stage extra consumer')
    closure=complete_closure(n,g,gray)
    remote={p:c for p,c in closure['ff_endpoints'].items()if c!='memory_clk'}
    require(remote=={p+'/D':'clk_50m'for p in first}and not closure['primitive_endpoints']and
            not closure['top_output_endpoints'],'Gray source remote/opaque consumer inventory changed')
    return dict(binary_next_Q_equations=16,Gray_next_Q_equations=15,MSB_exact_binary_alias=True,
                source=gray,first=first,second=second,source_complete_closure=closure,
                source_period_ns=10.0,second_stage_budget_ns=2.0)


def audit(n,stage,sdc,metadata):
    configuration=json.loads((Path(stage).parent.parent/'workstation_profile.json').read_text())['configuration']
    require(configured(configuration),'unselected proof')
    restore(sdc,metadata.get('task3_w_preboard_cdc'))
    from tools.workstation_local_stream_release import verify
    verify(stage,configuration,metadata.get('local_stream_release'),metadata['enabled_inputs'])
    from tools.workstation_task3_cnn_reset import source_evidence
    source=source_evidence(stage)
    from tools.workstation_task3_w_paired_cdc_audit import audit_retirements,_closure
    retirements=audit_retirements(n);g=Graph(n);releases=[]
    # These reset synchronizers, unlike functional payload reset pins, may
    # deassert asynchronously. Only their final stage releases each owner.
    for scope,stem,domain in RELEASES:
        regs=g.group(scope,stem,3)
        for p in regs:zero_ff(n,g,p,domain)
        require(all(n.pin(p,'CE')in g.high for p in regs)and n.pin(regs[0],'D')in g.high and
                all(n.pin(regs[i],'D')==n.pin(regs[i-1],'Q')for i in [1,2])and
                len({n.pin(p,'CLEAR')for p in regs})==1,'reset release shift chain changed: '+scope+'/'+stem)
        closures=[_closure(n,g,[regs[i]],{regs[i+1]+'/D':domain},'preboard release')for i in [0,1]]
        releases.append(dict(stages=regs,domain=domain,early_complete_closures=closures))
    # Existing held proof establishes local mailbox reset equations and
    # complete first/second-stage closures independently of these exceptions.
    from tools.workstation_task3_w_paired_cdc_audit import _held_resets,_mailboxes
    from tools.workstation_task3_root_reset_audit import audit_root_startup
    root=audit_root_startup(n,stage=stage)
    from tools.workstation_native_protocol_audit import audit_timing_boundaries
    held=_held_resets(n,g,dict(mailboxes=_mailboxes(n,g),
        timing_boundaries=audit_timing_boundaries(n,g,profile='w-demo-d'),
        local_stream_release=metadata['local_stream_release']),root)
    pins={p+'/'+pin for p,c in n.cells.items()if c['kind'].startswith('DFF')for pin in c['ports']}
    import re
    resolutions={}
    for query in re.findall(r'\[get_pins \{([^{}]+)\}\]',constraints()):
        for pattern in query.split():
            matches=sorted(p for p in pins if fnmatch.fnmatchcase(p,pattern))
            require(len(matches)==1,'exact selected pin absent/ambiguous: '+pattern)
            resolutions[pattern]=matches[0]
    return dict(policy=POLICY,source=source,release_chains=releases,retirements=retirements,
                retained_held_release_proof=held,gray=audit_gray(n,g),exact_pin_resolutions=resolutions,
                functional_payload_or_later_stage_exceptions_added=False,
                routed_timing_verified=False,physical_CDC_accepted=False,hardware_tested=False)
