"""Explicit W published-epoch source; legacy selection remains default off."""
POLICY='registered_controller_epoch_v1'
CDC_POLICY='classic_pcm_registered_controller_epoch_cdc_v2'
HCI_POLICY='native_shared_hci_audio_only_registered_epoch_v2'
PROVIDER='rtl/bluetooth/hci_owner/workstation_hci_audio_registered_epoch_provider.sv'
TOOL='tools/workstation_hci_epoch.py'
SOURCE='rtl/bluetooth/hci_owner/workstation_hci_native_transport.sv'
RAW_SOURCE='u_bluetooth/u_core/initializer/boot_id*'
REGISTERED_SOURCE='u_bluetooth/u_core/owner/published_epoch*'

def selected(value):
    if type(value)is not bool:raise ValueError('registered HCI epoch requires explicit boolean')
    return value

def cdc_selection(bundle,enabled=False):
    """Rebind the existing held source; never add or relax an exception."""
    if not selected(enabled):return bundle
    if bundle['policy']!='classic_pcm_scoped_candidate_cdc_v1':raise ValueError('registered HCI epoch original CDC policy drift')
    source=RAW_SOURCE+' u_bluetooth/u_core/owner/flow/generations* u_bluetooth/u_core/owner/flow/active* u_bluetooth/u_core/owner/flow/is_le*'
    destination='u_managed/runtime/cpu_pcm/session/epoch_o* u_managed/runtime/cpu_pcm/session/generation_o*'
    pair=['set_max_delay 10.000 -from [get_regs {'+source+'}] -to [get_regs {'+destination+'}]',
          'set_false_path -hold -from [get_regs {'+source+'}] -to [get_regs {'+destination+'}]']
    text=bundle['sdc'];lines=[line for line in text.splitlines()if RAW_SOURCE in line]
    if bundle.get('held_payload_max_delay_ns')!=10 or lines!=pair:
        raise ValueError('registered HCI epoch exact original held source pair missing')
    if REGISTERED_SOURCE in text:raise ValueError('registered HCI epoch selector already installed')
    result=dict(bundle,policy=CDC_POLICY,sdc=text.replace(RAW_SOURCE,REGISTERED_SOURCE))
    result['controller_epoch_source']=POLICY
    return result

def audit_registered_epoch(n,*,source_clock,destination_clock):
    """Resolve real Q sources, normalization, async-close and fourth-edge capture."""
    import functools
    from tools.workstation_runtime_pcm_cdc import Graph,BooleanDiagram
    g=Graph(n);H='u_bluetooth/u_core/owner';I='u_bluetooth/u_core/initializer';S='u_managed/runtime/cpu_pcm.session'
    def need(ok,message):
        if not ok:raise ValueError('registered HCI epoch audit: '+message)
    published=g.group(H,'published_epoch',32);boot=g.group(I,'boot_id',64);epoch=g.group(S,'epoch_o',32)
    release=g.group(S,'release_pipe',3);live=g.register(S,'live_o');ready=g.register(H,'classic_ready_o')
    need(source_clock!=destination_clock,'source and compute clock must remain distinct')
    for p in published+[ready]:
        c=n.cells[p]
        need(c['kind']=='DFFRE'and set(c['ports'])=={'D','Q','CLK','CE','RESET'}and c['parameters']=={'INIT':"1'b0"},'published source FF shape: '+p)
        need(n.pin(p,'CLK')==source_clock and n.pin(p,'CE')in g.high,'published source clock/enable: '+p)
    source_reset=n.pin(ready,'RESET')
    need(source_reset not in g.high|g.low and g.support(source_reset),'published source reset must remain driven and nonconstant')
    need(all(n.pin(p,'RESET')==source_reset for p in published),'published32 and registered ready require one source reset')
    need(all(n.pin(p,'CLK')==source_clock for p in boot),'initializer source clock')
    q=[n.pin(p,'Q')for p in boot];bd=BooleanDiagram(q)
    low=functools.reduce(bd.either,(bd.inputs[v]for v in q[:32]),0)
    rows=[]
    for bit,(p,e)in enumerate(zip(published,epoch)):
        d=n.pin(p,'D');need(g.support(d)==set(q[:32]+[q[bit+32]]),'normalization inputs: '+str(bit))
        need(bd.net(g,d)==bd.choose(low,bd.inputs[q[bit]],bd.inputs[q[bit+32]]),'normalization equation: '+str(bit))
        need(n.pin(e,'D')==n.pin(p,'Q')and g.drivers[n.pin(e,'D')]==[(p,'Q')],'session must capture sole published Q: '+str(bit))
        rows.append(dict(bit=bit,source_register=p,capture_register=e,source_output='Q',normalized_boot_mux_exact=True))
    for p in epoch+release+[live]:
        c=n.cells[p];need(c['kind']=='DFFCE'and set(c['ports'])=={'D','Q','CLK','CE','CLEAR'}and c['parameters']=={'INIT':"1'b0"}and n.pin(p,'CLK')==destination_clock,'session FF shape/clock: '+p)
    clear=n.pin(live,'CLEAR')
    for i,p in enumerate(release):
        need(n.pin(p,'CE')in g.high and n.pin(p,'CLEAR')==clear,'release enable/reset: '+str(i))
        need(n.pin(p,'D')in g.high if i==0 else n.pin(p,'D')==n.pin(release[i-1],'Q'),'release stage link: '+str(i))
    need(n.pin(live,'D')in g.high and n.pin(live,'CE')==n.pin(release[2],'Q'),'fourth-edge live publication')
    capture=n.pin(epoch[0],'CE');need(all(n.pin(p,'CE')==capture and n.pin(p,'CLEAR')==n.pin(epoch[0],'CLEAR')for p in epoch),'one immutable epoch capture enable/reset')
    rq=n.pin(release[2],'Q');lq=n.pin(live,'Q');bd=BooleanDiagram([rq,lq])
    need(bd.net(g,capture)==bd.both(bd.inputs[rq],bd.invert(bd.inputs[lq])),'epoch capture release2 and not live')
    support=g.support(clear);ready_q=n.pin(ready,'Q');need(ready_q in support,'registered ready async-close missing')
    bd=BooleanDiagram(sorted(support));need(bd.both(bd.invert(bd.inputs[ready_q]),bd.invert(bd.net(g,clear)))==0,'ready low must asynchronously close release/live')
    epoch_clear=n.pin(epoch[0],'CLEAR');epoch_support=g.support(epoch_clear)
    need(epoch_clear not in g.high|g.low and epoch_support and ready_q not in epoch_support,'epoch capture reset must stay separate from ready revocation')
    bd=BooleanDiagram(sorted(support|epoch_support))
    need(bd.both(bd.net(g,epoch_clear),bd.invert(bd.net(g,clear)))==0,'epoch reset must also close release/live')
    return dict(policy=POLICY,source_clock=source_clock,destination_clock=destination_clock,source_registers=32,capture_registers=32,rows=rows,normalization_64bit_input_exact=True,source_is_existing_HCI_published_epoch=True,parallel_owner_added=False,source_reset=source_reset,published_and_ready_reset_identical=True,ready_source=ready,release_pipe=release,minimum_capture_edges=4,payload_maximum_delay_ns=10,physical_timing_verified=False,hardware_tested=False)
