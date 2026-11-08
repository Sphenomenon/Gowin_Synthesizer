"""Actual W raw-DDR held command capture and local business fanout.

Keep the 10ns payload maximum and normal hold checks. Source data cannot
change while request is outstanding; request has two memory-clock stages;
all business consumers use the registered tuple on the following cycle.
"""
from tools.workstation_runtime_pcm_cdc import Graph,BooleanDiagram,COMB
from tools.workstation_task3_native_held import zero_ff
from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_task3_m_session_boundary import frontier,KeyDiagram

S='u_task3_media/raw_store'

def require(ok,message):
    if not ok:raise ValueError('W raw command capture: '+message)


def audit(n,*,publication=False):
    g=Graph(n);reg=lambda stem:g.register(S,stem);q=lambda p:n.pin(p,'Q')
    req,ack,ack_sync,active,valid=map(reg,['command_req','command_ack','command_ack_sync','memory_command_active','g_command_capture.valid'])
    source=[];equations=[]
    for stem,width in [('command_event_target',9),('command_length',14),('command_offset',32),('command_generation',32),('command_kind',2)]:
        for i in range(width):
            if stem=='command_length'and i==13:
                const=n.pin(g.register(S,'g_command_capture.payload',22),'D');require(const in g.low,'length high constant changed');source.append(None)
            else:
                p=g.register(S,stem,i);source.append(p);zero_ff(n,g,p,'clk_50m')
    capture=g.group(S,'g_command_capture.payload',89)
    reqq,acksq=q(req),q(ack_sync)
    for ce in sorted({n.pin(p,'CE')for p in source if p}):
        leaves=frontier(n,g,[ce],{reqq,acksq});b=KeyDiagram(leaves)
        require(b.both(b.different(b.inputs[reqq],b.inputs[acksq]),b.net(g,ce))==0,
                'source tuple overwritten while request outstanding')
        equations.append(dict(source_enable=ce,busy_prevents_overwrite=True,conservative_cuts=leaves))
    # The source request is published by the same common enable as the tuple.
    zero_ff(n,g,req,'clk_50m');b=BooleanDiagram([reqq])
    require(b.net(g,n.pin(req,'D'))==b.invert(b.inputs[reqq])and
            n.pin(req,'CE')==n.pin(g.register(S,'command_generation',0),'CE'),
            'source request publication event changed')
    chains=[]
    for src,one,two,domain in [(req,reg('command_req_meta'),reg('command_req_sync'),'memory_clk'),
                              (ack,reg('command_ack_meta'),ack_sync,'clk_50m')]:
        for p in [one,two]:zero_ff(n,g,p,domain)
        require(n.pin(one,'D')==q(src)and n.pin(two,'D')==q(one)and
                n.pin(one,'CE')in g.high and n.pin(two,'CE')in g.high and
                n.pin(one,'CLEAR')==n.pin(two,'CLEAR'),'toggle capture stage changed')
        c=complete_closure(n,g,[one]);require(c['ff_endpoints']=={two+'/D':domain}and
                not c['primitive_endpoints']and not c['top_output_endpoints'],'first stage extra consumer')
        chains.append(dict(source=src,first=one,second=two,complete_first_closure=c))
    local_ack=ack
    publication_proof=None
    if publication:
        from tools.workstation_ble_completion_publication import audit_mapped
        publication_proof=audit_mapped(n)
        local_ack=reg('completion_ready')
    sync=reg('command_req_sync');leaves=list(map(q,[sync,local_ack,active,valid]));b=BooleanDiagram(leaves)
    request=b.both(b.different(b.inputs[q(sync)],b.inputs[q(local_ack)]),b.invert(b.inputs[q(active)]))
    cap=b.both(request,b.invert(b.inputs[q(valid)]));start=b.both(request,b.inputs[q(valid)])
    for dst,src in zip(capture,source):
        zero_ff(n,g,dst,'memory_clk')
        require((n.pin(dst,'D')==q(src)if src else n.pin(dst,'D')in g.low)and
                b.net(g,n.pin(dst,'CE'))==cap,'whole tuple data/capture enable changed '+dst)
    zero_ff(n,g,valid,'memory_clk')
    actual=b.choose(b.net(g,n.pin(valid,'CE')),b.net(g,n.pin(valid,'D')),b.inputs[q(valid)])
    require(actual==b.choose(request,b.invert(b.inputs[q(valid)]),b.inputs[q(valid)]),'valid next-Q differs')
    # Named business start must be exact request && registered valid.
    # Gowin eliminates the named start wire. Resolve its complete exact
    # Boolean implementation among the actual valid-output fanout nets.
    start_nets=[]
    for cell,pin,kind in g.fan[q(valid)]:
        if kind!='comb':continue
        for output in COMB[n.cells[cell]['kind']]:
            net=n.pin(cell,output)
            try:
                if b.net(g,net) in (start,b.invert(start)):start_nets.append(net)
            except ValueError:pass
    require(bool(start_nets),'registered business-start gate absent')
    closure=complete_closure(n,g,[p for p in source if p]);remote={p:c for p,c in closure['ff_endpoints'].items()if c!='clk_50m'}
    require(remote=={p+'/D':'memory_clk'for p,s in zip(capture,source)if s}and
            not closure['primitive_endpoints']and not closure['top_output_endpoints'],
            'uncaptured remote tuple consumer added')
    src=' '.join(p+'/Q'for p in source if p);dst=' '.join(p+'/D'for p,s in zip(capture,source)if s)
    path=f'-from [get_pins {{{src}}}] -to [get_pins {{{dst}}}]'
    sdc='\n# W raw command: exact held tuple into one memory-domain register bank\nset_max_delay 10.000 '+path+'\nset_min_delay 1.800 '+path+'\n'
    # W B16 reports -0.040ns hold on this real functional status consumer.
    # Tighten its minimum data flight; keep normal setup and hold analysis.
    # This is deliberately not a status-bus or clock-domain false path.
    status=g.register(S,'status_payload',4);fetch_fault=reg('fetch_fault_o')
    zero_ff(n,g,status,'memory_clk');zero_ff(n,g,fetch_fault,'clk_50m')
    status_closure=complete_closure(n,g,[status])
    require(status_closure['ff_endpoints'].get(fetch_fault+'/D')=='clk_50m',
            'routed status-to-fetch fault hold path absent')
    status_path='-from [get_pins {'+status+'/Q}] -to [get_pins {'+fetch_fault+'/D}]'
    sdc+='\n# B16 actual status fault consumer: strengthen minimum data delay only\nset_min_delay 1.800 '+status_path+'\n'
    return dict(policy='task3_W_raw_held_command_capture89_v1',tuple_bits=89,
        variable_bits=88,constant_bits=1,source=source,capture=capture,
        source_equations=equations,toggle_chains=chains,source_complete_closure=closure,
        captured_valid_next_Q_exact=True,business_start_requires_registered_valid=True,
        request_stages_before_capture=2,hold_check_retained=True,
        completion_publication=publication_proof,
        status_fetch_fault_hold=dict(source=status+'/Q',capture=fetch_fault+'/D',
            min_data_delay_ns=1.8,source_complete_closure=status_closure,
            normal_setup_retained=True,hold_check_retained=True,timing_exception_added=False),
        max_data_delay_ns=10.0,min_data_delay_ns=1.8,routed_timing_verified=False,hardware_tested=False),sdc
